import asyncio
import logging
import re
from io import BytesIO
import uuid
import httpx
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from html import escape
from math import ceil
from pathlib import Path

from openai import RateLimitError
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction
from telegram.error import NetworkError, TelegramError
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from .config import Settings, load_settings
from .database import Database
from .openai_limits import ModelLimit, OpenAILimitsUnavailable, get_openai_limits
from . import ui, model_catalog, image_generation
from .downloads import classify_link, download_media, is_instagram_media_url, resolve_spotify_track
from .content import edit_subtitle_line, generate_content
from .pipeline import (
    JobCancelled,
    OpenAICost,
    cleanup,
    cleanup_expired_downloads,
    get_video_details,
    process_video,
    publish_download,
    publish_subtitle_player,
    validate_youtube_url,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)


@dataclass
class Job:
    id: str
    user_id: int
    chat_id: int
    url: str
    message_id: int
    directory: Path
    selected_height: int | None
    mode: str
    api_provider: str
    draft_id: int
    can_use_draft: bool
    draft_was_used: bool = False
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    billable_minutes: int = 0
    billed_amount_toman: int = 0
    models: model_catalog.ModelSelection | None = None
    team_glossary: str = ""
    package_minutes: int = 0
    dub_mode: str = "simple"
    progress_stage: str = "در صف پردازش"
    progress_percent: int = 0
    progress_last_edit: float = 0.0
    progress_last_text: str = ""
    delivery_started: bool = False


@dataclass
class DownloadJob:
    id: str
    user_id: int
    chat_id: int
    url: str
    message_id: int
    directory: Path
    kind: str
    source: str
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)


@dataclass
class ContentJob:
    id: str
    user_id: int
    chat_id: int
    message_id: int
    subtitle: str
    kind: str
    models: model_catalog.ModelSelection
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)


@dataclass
class ImageJob:
    id: str
    user_id: int
    chat_id: int
    message_id: int
    prompt: str
    aspect: str
    model: image_generation.ImageModel
    optimizer: model_catalog.StageSelection
    reference: bytes | None = None
    reference_type: str | None = None
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    delivery_started: bool = False


@dataclass
class PendingQuality:
    user_id: int
    chat_id: int
    url: str
    message_id: int
    is_private_chat: bool
    api_provider: str
    mode: str | None = None
    duration_seconds: int = 0
    selected_height: int | None = None
    quoted_rate: int = 0
    confirming: bool = False
    download_source: str = ""
    dub_mode: str = "simple"
    probing: bool = False
    available_heights: list[int] = field(default_factory=list)


class BotState:
    def __init__(self, settings: Settings, database: Database) -> None:
        self.settings = settings
        self.database = database
        self.queue: asyncio.Queue[Job | DownloadJob | ContentJob | ImageJob | None] = asyncio.Queue()
        self.active: dict[int, Job | DownloadJob | ContentJob | ImageJob] = {}
        self.pending_quality: dict[str, PendingQuality] = {}
        self.pending_by_user: dict[int, str] = {}
        self.admin_editing: dict[int, str] = {}
        self.awaiting_topup: set[int] = set()
        self.awaiting_support: set[int] = set()
        self.subtitle_editing: dict[int, str] = {}
        self.content_quotes: dict[str, tuple[int, str, str, int]] = {}
        self.package_quotes: dict[str, tuple[int, str, int, int, int]] = {}
        self.awaiting_image_prompt: set[int] = set()
        self.image_quotes: dict[str, dict] = {}
        self.image_references: dict[int, tuple[bytes, str]] = {}
        self.api_provider = settings.default_api_provider


def _state(context: ContextTypes.DEFAULT_TYPE) -> BotState:
    return context.application.bot_data["state"]


async def _edit_query_screen(query, text: str, **kwargs) -> None:
    """Edit text screens and update captions when a screen is attached to media."""
    message = getattr(query, "message", None)
    media_fields = ("photo", "video", "animation", "audio", "document", "voice", "video_note")
    has_media = message and any(getattr(message, field, None) for field in media_fields)
    if message and (getattr(message, "caption", None) is not None or has_media):
        kwargs.pop("disable_web_page_preview", None)
        if len(text) > 1024:
            text = text[:1021] + "..."
        await query.edit_message_caption(caption=text, **kwargs)
        return
    await query.edit_message_text(text, **kwargs)


async def _show_screen(update: Update, text: str, **kwargs) -> None:
    """Edit the active inline screen, or send a screen for a command/message flow."""
    query = update.callback_query
    if query:
        await _edit_query_screen(query, text, **kwargs)
        return
    message = update.effective_message
    if message:
        await message.reply_text(text, **kwargs)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, message = update.effective_user, update.effective_message
    if not user or not message:
        return
    state = _state(context)
    if message.chat.type != "private":
        await message.reply_text("برای حفظ حریم خصوصی، ربات را در گفت‌وگوی خصوصی باز کن.")
        return
    await state.database.upsert_user(user, True)
    state.awaiting_topup.discard(user.id)
    state.awaiting_support.discard(user.id)
    state.subtitle_editing.pop(user.id, None)
    state.admin_editing.pop(user.id, None)
    state.awaiting_image_prompt.discard(user.id)
    state.image_references.pop(user.id, None)
    if not state.image_quotes.get(str(user.id), {}).get("confirming"):
        state.image_quotes.pop(str(user.id), None)
    balance = await state.database.get_wallet_balance(user.id)
    await message.reply_text(ui.home_text(balance), parse_mode="HTML", reply_markup=ui.home_keyboard())


async def receive_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, message = update.effective_user, update.effective_message
    state = _state(context)
    if not user or not message or not message.text:
        return
    await state.database.upsert_user(user, True)
    if user.id in state.subtitle_editing:
        await _receive_subtitle_edit(update, context)
        return
    if user.id in state.admin_editing:
        await _save_admin_value(update, state, context.application)
        return
    if message.chat.type != "private":
        await message.reply_text("برای حفظ حریم خصوصی، لطفاً در گفت‌وگوی خصوصی ربات پیام بده.")
        return
    if user.id in state.awaiting_image_prompt:
        await _receive_image_prompt(update, context)
        return
    url = message.text.strip()
    source_type = classify_link(url)
    if user.id in state.awaiting_support:
        await _send_support_request(update, context, url)
        return
    if user.id in state.awaiting_topup and not source_type:
        await _create_charge_request(update, context, url)
        return
    if source_type:
        state.awaiting_topup.discard(user.id)
    pending_deposit = await state.database.get_user_pending_deposit(user.id)
    if pending_deposit and pending_deposit["status"] == "awaiting_proof" and not source_type:
        submitted = await state.database.submit_deposit_proof(
            pending_deposit["id"], user.id, "text", proof_text=url
        )
        if submitted:
            await message.reply_text("✅ رسید/شماره پیگیری ثبت شد و برای بررسی به مدیر ارسال شد. پس از تأیید، کیف پولت شارژ می‌شود.")
            await _notify_admin_deposit(context.application, submitted, user.username)
        else:
            await message.reply_text("درخواست شارژ پیدا نشد یا منقضی شده است.")
        return
    if source_type == "spotify_unsupported":
        await message.reply_text("در Spotify فعلاً فقط لینک تک‌آهنگ پشتیبانی می‌شود؛ آلبوم، پلی‌لیست و پادکست پشتیبانی نمی‌شوند.", reply_markup=ui.back_keyboard())
        return
    if not source_type:
        await message.reply_text("لینک یوتیوب، اینستاگرام، تیک‌تاک، X، فیسبوک، ویمئو، آپارات، ساندکلاد یا تک‌آهنگ Spotify بفرست.", reply_markup=ui.back_keyboard())
        return
    if user.id in state.active or user.id in state.pending_by_user:
        await message.reply_text("یک سفارش باز داری. وضعیت آن را ببین یا لغو کن.",
            reply_markup=InlineKeyboardMarkup([
                [ui.button("📦 وضعیت سفارش", "menu:status", style="primary")],
                [ui.button("‹ بازگشت", "menu:home")],
            ]))
        return
    if state.image_quotes.get(str(user.id), {}).get("confirming"):
        await message.reply_text("سفارش تصویر در حال ثبت است؛ چند لحظه صبر کن.")
        return

    if not await state.database.has_accepted_terms(user.id):
        await message.reply_text("برای شروع، شرایط استفاده را بخوان و بپذیر؛ سپس لینک را دوباره بفرست.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📜 شرایط استفاده", callback_data="terms:show")],
                [ui.button("‹ بازگشت", "menu:home")],
            ]))
        return

    progress = await message.reply_text("✨ نوع پردازش را انتخاب کن:")
    token = uuid.uuid4().hex[:12]
    selection = PendingQuality(
        user.id, message.chat_id, url, progress.message_id, True, state.api_provider,
    )
    state.pending_quality[token] = selection
    state.pending_by_user[user.id] = token
    if source_type != "youtube":
        selection.download_source = source_type
        if source_type == "spotify":
            text = "🎵 دانلود آهنگ\nفایل از Spotify دریافت نمی‌شود؛ نسخهٔ مشابه از YouTube پیدا می‌شود. ممکن است نتیجه متفاوت باشد."
            keyboard = InlineKeyboardMarkup([
                [ui.button("🔎 دریافت نسخهٔ مشابه MP3", f"dl:{token}:audio", style="primary")],
                [ui.button("‹ بازگشت (لغو)", f"order_cancel:{token}", style="danger")],
            ])
        else:
            text = "📥 دانلود فایل\n\nنوع خروجی را انتخاب کن. این مسیر فقط دانلود است و هزینهٔ پردازش ندارد."
            buttons = []
            if is_instagram_media_url(url):
                text = "📥 دانلود اینستاگرام\n\nنوع مدیا را خودکار تشخیص می‌دهم و با قالب مناسب می‌فرستم: عکس، ویدیو، ریلز، استوری یا کاروسل. چند مدیا در یک فایل ZIP قرار می‌گیرد."
                buttons.append([ui.button("⬇️ دانلود هوشمند", f"dl:{token}:media", style="primary")])
            else:
                buttons.append([
                    ui.button("🎬 ویدیو", f"dl:{token}:video", style="primary"),
                    ui.button("🎵 فایل صوتی MP3", f"dl:{token}:audio"),
                ])
            buttons.append([ui.button("‹ بازگشت (لغو)", f"order_cancel:{token}", style="danger")])
            keyboard = InlineKeyboardMarkup(buttons)
        await context.application.bot.edit_message_text(text, chat_id=selection.chat_id,
            message_id=selection.message_id, reply_markup=keyboard)
        return
    await context.application.bot.edit_message_text(
        "🎬 سفارش جدید  ·  ۱ از ۳\n\nکدام خروجی را می‌خواهی؟\n"
        "📝 زیرنویس: متن فارسی همراه ویدیو\n🎙 دوبله: جایگزینی صدای اصلی با صدای فارسی هوش مصنوعی",
        chat_id=selection.chat_id, message_id=selection.message_id,
        reply_markup=ui.mode_keyboard(token),
    )


async def choose_download(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query, user = update.callback_query, update.effective_user
    if not query or not user:
        return
    state = _state(context)
    try:
        _, token, kind = (query.data or "").split(":", 2)
    except ValueError:
        await query.answer("انتخاب نامعتبر است.", show_alert=True)
        return
    selection = state.pending_quality.get(token)
    if (not selection or selection.user_id != user.id or selection.confirming
            or selection.download_source not in {"social", "spotify"}
            or kind not in {"video", "audio", "media"}
            or (kind == "media" and (selection.download_source != "social" or not is_instagram_media_url(selection.url)))
            or (is_instagram_media_url(selection.url) and kind != "media")
            or (selection.download_source == "spotify" and kind != "audio")):
        await query.answer("این انتخاب دیگر معتبر نیست.", show_alert=True)
        return
    selection.confirming = True
    try:
        await query.answer()
    except Exception:
        selection.confirming = False
        raise
    job_id = uuid.uuid4().hex
    try:
        await state.database.create_download_task(job_id, user.id, selection.chat_id, selection.url, kind)
    except Exception:
        state.pending_quality.pop(token, None)
        state.pending_by_user.pop(user.id, None)
        logger.exception("Could not persist download order %s", job_id)
        await _edit_query_screen(query, "ثبت درخواست دانلود ممکن نشد؛ دوباره تلاش کن.", reply_markup=ui.back_keyboard())
        return
    job = DownloadJob(job_id, user.id, selection.chat_id, selection.url, selection.message_id,
                      Path(state.settings.work_dir) / job_id, kind, selection.download_source)
    state.pending_quality.pop(token, None)
    state.pending_by_user.pop(user.id, None)
    state.active[user.id] = job
    await state.queue.put(job)
    await _edit_query_screen(query, "📥 درخواست دانلود در صف ثبت شد.", reply_markup=ui.job_keyboard(job.id))


async def choose_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    if not query or not user:
        return
    state: BotState = context.application.bot_data["state"]
    try:
        _, token, mode = (query.data or "").split(":", 2)
    except ValueError:
        await query.answer("این انتخاب معتبر نیست.", show_alert=True)
        return
    if mode not in {"subtitle", "dub"}:
        await query.answer("این انتخاب معتبر نیست.", show_alert=True)
        return
    selection = state.pending_quality.get(token)
    if not selection or selection.user_id != user.id or selection.confirming or selection.probing:
        await query.answer("این انتخاب منقضی شده؛ لینک را دوباره بفرست.", show_alert=True)
        return

    await query.answer()
    selection.mode = mode
    if mode == "dub":
        await _edit_query_screen(query,
            "🎙 روش دوبله را انتخاب کن:\n"
            "ساده: سریع‌تر.\n"
            "هوشمند: تلاش می‌کند صدای پس‌زمینه را بهتر حفظ کند.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🎧 دوبلهٔ ساده", callback_data=f"dubmode:{token}:simple")],
                [InlineKeyboardButton("✨ دوبلهٔ هوشمند", callback_data=f"dubmode:{token}:smart")],
                [InlineKeyboardButton("↩️ بازگشت", callback_data=f"order_back:{token}")],
            ]),
        )
        return
    await _probe_order(query, context, selection, token)


async def choose_dub_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query, user = update.callback_query, update.effective_user
    if not query or not user:
        return
    parts = (query.data or "").split(":")
    selection = _state(context).pending_quality.get(parts[1]) if len(parts) == 3 else None
    if not selection or selection.user_id != user.id or selection.mode != "dub" or selection.confirming or selection.probing or parts[2] not in {"simple", "smart"}:
        await query.answer("این انتخاب دیگر معتبر نیست.", show_alert=True)
        return
    if parts[2] == "smart" and not await _separator_available(_state(context).settings):
        await query.answer("دوبلهٔ هوشمند فعلاً در دسترس نیست؛ دوبلهٔ ساده را انتخاب کن یا با پشتیبانی تماس بگیر.", show_alert=True)
        return
    selection.dub_mode = parts[2]
    await query.answer()
    await _probe_order(query, context, selection, parts[1])


async def _separator_available(settings: Settings) -> bool:
    if not settings.dub_separator_url:
        return False
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            response = await client.get(settings.dub_separator_url + "/health")
            return response.status_code == 200
    except httpx.HTTPError:
        return False


async def _probe_order(query, context, selection: PendingQuality, token: str) -> None:
    state = _state(context)
    selection.probing = True
    try:
        await _edit_query_screen(query, _progress_text("بررسی کیفیت‌های موجود", 0))
        heights, duration = await asyncio.to_thread(get_video_details, selection.url, state.settings)
        if duration <= 0:
            raise RuntimeError("مدت ویدیو از یوتیوب دریافت نشد.")
        if duration > state.settings.video_max_minutes * 60:
            if state.pending_quality.get(token) is not selection:
                return
            state.pending_quality.pop(token, None)
            if state.pending_by_user.get(selection.user_id) == token:
                state.pending_by_user.pop(selection.user_id, None)
            await _edit_query_screen(query,
                f"مدت ویدیو بیشتر از سقف {state.settings.video_max_minutes} دقیقه است. لینک کوتاه‌تری بفرست.",
                reply_markup=ui.back_keyboard())
            return
        selection.duration_seconds = int(ceil(duration))
    except Exception:
        logger.exception("Could not probe YouTube formats for Telegram user %s", selection.user_id)
        if state.pending_quality.get(token) is not selection:
            return
        state.pending_quality.pop(token, None)
        if state.pending_by_user.get(selection.user_id) == token:
            state.pending_by_user.pop(selection.user_id, None)
        await _edit_query_screen(query, "کیفیت‌های ویدیو دریافت نشد. کمی بعد دوباره تلاش کن.",
                                 reply_markup=ui.back_keyboard())
        return

    if state.pending_quality.get(token) is not selection:
        return
    selection.probing = False
    selection.available_heights = heights

    mode_label = "زیرنویس فارسی" if selection.mode == "subtitle" else ("دوبلهٔ هوشمند" if selection.dub_mode == "smart" else "دوبلهٔ ساده")
    await context.application.bot.edit_message_text(
        f"🎬 سفارش جدید  ·  ۲ از ۳\n\nخروجی: {mode_label}\nکیفیت ویدیو را انتخاب کن:",
        chat_id=selection.chat_id, message_id=selection.message_id,
        reply_markup=ui.quality_keyboard(token, heights),
    )


async def choose_quality(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query, user = update.callback_query, update.effective_user
    if not query or not user:
        return
    state: BotState = context.application.bot_data["state"]
    try:
        _, token, raw_height = (query.data or "").split(":", 2)
        selected_height = int(raw_height) or None
    except (ValueError, TypeError):
        await query.answer("این انتخاب معتبر نیست.", show_alert=True)
        return
    selection = state.pending_quality.get(token)
    if not selection or selection.user_id != user.id or not selection.mode or selection.probing or selection.confirming:
        await query.answer("این انتخاب منقضی شده؛ لینک را دوباره بفرست.", show_alert=True)
        return
    if not await state.database.has_accepted_terms(user.id):
        state.pending_quality.pop(token, None)
        state.pending_by_user.pop(user.id, None)
        await query.answer("برای ادامه، شرایط استفاده را بخوان و تأیید کن.", show_alert=True)
        await _edit_query_screen(query,
            "قبل از ادامه، شرایط استفاده را بخوان و تأیید کن.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📜 شرایط استفاده", callback_data="terms:show")],
                [ui.button("‹ بازگشت", "menu:home")],
            ]),
        )
        return
    if user.id in state.active:
        await query.answer("یک کار در حال اجرا داری.", show_alert=True)
        return

    mode = selection.mode
    rate_key = "price_subtitle_toman_per_minute" if mode == "subtitle" else "price_dub_toman_per_minute"
    default_rate = (state.settings.default_subtitle_price_toman_per_minute
                    if mode == "subtitle" else state.settings.default_dub_price_toman_per_minute)
    rate = max(1, int(await state.database.get_setting(rate_key, str(default_rate))))
    minutes = max(1, ceil(selection.duration_seconds / 60))
    amount = minutes * rate
    selection.selected_height = selected_height
    selection.quoted_rate = rate
    quality = "خودکار" if selected_height is None else f"{selected_height}p"
    mode_label = "زیرنویس فارسی" if mode == "subtitle" else ("دوبلهٔ هوشمند" if selection.dub_mode == "smart" else "دوبلهٔ ساده")
    balance = await state.database.get_wallet_balance(user.id)
    packages = await state.database.available_minutes(user.id)
    package = next((p for p in packages if p["mode"] == mode and p["minutes"] >= minutes), None)
    package_note = f"\nبستهٔ قابل استفاده: {package['minutes']} دقیقه" if package else ""
    await query.answer()
    await _edit_query_screen(query,
        f"🧾 سفارش جدید  ·  ۳ از ۳\n\nخروجی: {mode_label} · کیفیت: {quality}\n"
        f"مدت قابل محاسبه: {minutes} دقیقه\nتعرفه: {rate:,} تومان در دقیقه\n"
        f"هزینه: {amount:,} تومان · موجودی: {balance:,} تومان{package_note}\n\n"
        "روش پرداخت را انتخاب کن؛ پس از تأیید سفارش وارد صف می‌شود.",
        reply_markup=ui.confirmation_keyboard(token, package["id"] if package else None),
    )


async def confirm_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query, user = update.callback_query, update.effective_user
    if not query or not user:
        return
    state = _state(context)
    parts = (query.data or "").split(":")
    if len(parts) not in {2, 3}:
        await query.answer("سفارش نامعتبر است.", show_alert=True)
        return
    token = parts[1]
    package_id = parts[2] if len(parts) == 3 else None
    selection = state.pending_quality.get(token)
    if not selection or selection.user_id != user.id or not selection.mode or not selection.quoted_rate or selection.confirming:
        await query.answer("این سفارش دیگر قابل تأیید نیست.", show_alert=True)
        return
    selection.confirming = True
    mode = selection.mode
    if mode == "dub" and selection.dub_mode == "smart" and not await _separator_available(state.settings):
        selection.confirming = False
        await query.answer("دوبلهٔ هوشمند فعلاً در دسترس نیست؛ هزینه‌ای کسر نشد.", show_alert=True)
        return
    selected_height = selection.selected_height
    rate = selection.quoted_rate
    minutes = max(1, ceil(selection.duration_seconds / 60))
    amount = minutes * rate
    job_id = uuid.uuid4().hex
    try:
        models = await model_catalog.load_selection(state.database, state.settings, selection.api_provider)
        team = await state.database.team_info(user.id)
        team_glossary = team["glossary"] if team else ""
        required = [models.stt, models.translation] + ([models.tts] if mode == "dub" else [])
        missing = {item.provider for item in required if not (
            state.settings.openai_api_key if item.provider == "openai" else state.settings.openrouter_api_key
        )}
        if missing:
            selection.confirming = False
            await query.answer("پردازشگر سفارش تنظیم نشده است؛ لطفاً با پشتیبانی تماس بگیر.", show_alert=True)
            return
        await query.answer()
        if package_id:
            balance = await state.database.create_package_job(
                job_id=job_id, user_id=user.id, chat_id=selection.chat_id, url=selection.url,
                selected_height=selected_height, mode=mode, api_provider=selection.api_provider,
                billable_minutes=minutes, package_id=package_id)
        else:
            balance = await state.database.create_wallet_job(
                job_id=job_id, user_id=user.id, chat_id=selection.chat_id,
                url=selection.url, selected_height=selected_height, mode=mode,
                api_provider=selection.api_provider, billable_minutes=minutes, amount_toman=amount)

    except Exception:
        selection.confirming = False
        raise
    state.pending_quality.pop(token, None)
    state.pending_by_user.pop(user.id, None)
    if balance is None:
        if package_id:
            await _edit_query_screen(query, "بسته معتبر نیست. سفارش را دوباره شروع کن.", reply_markup=ui.back_keyboard())
            return
        current = await state.database.get_wallet_balance(user.id)
        shortage = max(0, amount - current)
        await _edit_query_screen(query,
            f"موجودی کافی نیست.\nمدت ویدیو: {minutes} دقیقه\nهزینه: {amount:,} تومان\n"
            f"موجودی: {current:,} تومان · کسری: {shortage:,} تومان\n\n"
            "برای ادامه، کیف پول را شارژ کن و لینک را دوباره بفرست.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💳 شارژ کیف پول", callback_data="wallet:topup")],
                [ui.button("‹ بازگشت", "menu:home")],
            ]),
        )
        return

    quality_label = "خودکار" if selected_height is None else f"{selected_height}p"
    mode_label = "زیرنویس فارسی" if mode == "subtitle" else "دوبلهٔ فارسی"
    directory = Path(state.settings.work_dir) / job_id
    job = Job(
        id=job_id, user_id=user.id, chat_id=selection.chat_id,
        url=selection.url, message_id=selection.message_id, directory=directory,
        selected_height=selected_height, mode=mode,
        api_provider=selection.api_provider, draft_id=int(job_id[:7], 16) or 1,
        can_use_draft=True, billable_minutes=minutes,
        billed_amount_toman=0 if package_id else amount, models=models, team_glossary=team_glossary,
        package_minutes=minutes if package_id else 0,
        dub_mode=selection.dub_mode,
    )
    state.active[user.id] = job
    await state.queue.put(job)
    try:
        await _edit_query_screen(query,
            _progress_text("سفارش در صف پردازش قرار گرفت", 0)
            + f"\nخروجی: {mode_label} | کیفیت: {quality_label}"
            + (f"\nمصرف از بسته: {minutes} دقیقه · باقی‌مانده: {balance} دقیقه" if package_id else
               f"\nمبلغ: {minutes} × {rate:,} = {amount:,} تومان\nموجودی باقی‌مانده: {balance:,} تومان"),
            reply_markup=ui.job_keyboard(job.id),
        )
    except TelegramError:
        logger.exception("Could not edit wallet-job status message %s", job_id)


async def back_to_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query, user = update.callback_query, update.effective_user
    if not query or not user:
        return
    token = (query.data or "").partition(":")[2]
    selection = _state(context).pending_quality.get(token)
    if not selection or selection.user_id != user.id or selection.confirming or selection.probing:
        await query.answer("این سفارش دیگر فعال نیست.", show_alert=True)
        return
    selection.mode = None
    selection.quoted_rate = 0
    await query.answer()
    await _edit_query_screen(query,
        "🎬 سفارش جدید  ·  ۱ از ۳\n\nنوع خروجی را انتخاب کن:",
        reply_markup=ui.mode_keyboard(token),
    )


async def back_to_quality(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query, user = update.callback_query, update.effective_user
    if not query or not user:
        return
    token = (query.data or "").partition(":")[2]
    selection = _state(context).pending_quality.get(token)
    if not selection or selection.user_id != user.id or not selection.mode or selection.probing or selection.confirming:
        await query.answer("این سفارش دیگر فعال نیست.", show_alert=True)
        return
    selection.quoted_rate = 0
    await query.answer()
    await _edit_query_screen(query, "🎬 کیفیت ویدیو را انتخاب کن:", reply_markup=ui.quality_keyboard(token, selection.available_heights))


async def cancel_order_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query, user = update.callback_query, update.effective_user
    if not query or not user:
        return
    state = _state(context)
    token = (query.data or "").partition(":")[2]
    selection = state.pending_quality.get(token)
    if not selection or selection.user_id != user.id or selection.confirming:
        await query.answer("این سفارش دیگر قابل لغو نیست.", show_alert=True)
        return
    state.pending_quality.pop(token, None)
    state.pending_by_user.pop(user.id, None)
    await query.answer()
    await _edit_query_screen(query, "سفارش لغو شد.", reply_markup=ui.back_keyboard())


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, message = update.effective_user, update.effective_message
    state = _state(context)
    if not user or not message:
        return
    await state.database.upsert_user(user, True)
    if state.subtitle_editing.pop(user.id, None):
        await message.reply_text("ویرایش زیرنویس لغو شد.", reply_markup=ui.back_keyboard())
        return
    if user.id in state.awaiting_support:
        state.awaiting_support.discard(user.id)
        await message.reply_text("نوشتن پیام پشتیبانی لغو شد.", reply_markup=ui.back_keyboard())
        return
    if user.id in state.awaiting_topup:
        state.awaiting_topup.discard(user.id)
        await message.reply_text("درخواست وارد کردن مبلغ لغو شد.", reply_markup=ui.back_keyboard())
        return
    if user.id in state.awaiting_image_prompt:
        state.awaiting_image_prompt.discard(user.id)
        state.image_references.pop(user.id, None)
        state.image_quotes.pop(str(user.id), None)
        await message.reply_text("ساخت تصویر لغو شد.", reply_markup=ui.back_keyboard())
        return
    image_quote = state.image_quotes.get(str(user.id))
    if image_quote:
        if image_quote.get("confirming"):
            await message.reply_text("در حال ثبت سفارش تصویر هستیم؛ چند لحظه صبر کن.")
            return
        state.image_quotes.pop(str(user.id), None)
        await message.reply_text("انتخاب تصویر لغو شد.", reply_markup=ui.back_keyboard())
        return
    if state.admin_editing.pop(user.id, None):
        await message.reply_text("تغییر تنظیمات لغو شد.")
        return
    pending_token = state.pending_by_user.get(user.id)
    if pending_token:
        selection = state.pending_quality.get(pending_token)
        if selection and selection.confirming:
            await message.reply_text("در حال ثبت سفارش هستیم؛ چند لحظه صبر کن و سپس وضعیت سفارش را ببین.", reply_markup=ui.back_keyboard())
            return
        state.pending_by_user.pop(user.id, None)
        selection = state.pending_quality.pop(pending_token, None)
        if selection:
            await _safe_edit(context.application, selection, "درخواست لغو شد.")
        await message.reply_text("درخواست پردازش لغو شد.")
        return
    job = state.active.get(user.id)
    if job:
        if isinstance(job, (Job, ImageJob)) and job.delivery_started:
            await message.reply_text("خروجی در حال تحویل است و دیگر نمی‌توان این سفارش را لغو کرد.", reply_markup=ui.back_keyboard())
            return
        job.cancel_event.set()
        await message.reply_text(_cancel_requested_text(job), reply_markup=ui.back_keyboard())
        return
    pending_deposit = await state.database.get_user_pending_deposit(user.id)
    if pending_deposit and pending_deposit["status"] == "awaiting_proof":
        await state.database.cancel_deposit_request(pending_deposit["id"], user.id)
        await message.reply_text("درخواست شارژ لغو شد؛ اگر انتقال کارت‌به‌کارت انجام داده‌ای با /paysupport پیگیری کن.")
        return
    await message.reply_text("درخواستی برای لغو وجود ندارد.")


def _cancel_requested_text(job: Job | DownloadJob | ContentJob | ImageJob) -> str:
    if isinstance(job, DownloadJob):
        return "درخواست لغو ثبت شد؛ پس از پایان مرحلهٔ فعلی دانلود متوقف می‌شود."
    if isinstance(job, Job) and job.package_minutes:
        return "درخواست لغو ثبت شد؛ پس از توقف، دقیقهٔ مصرف‌شده به بسته برمی‌گردد."
    return "درخواست لغو ثبت شد؛ پس از توقف، هزینه طبق نتیجهٔ بازپرداخت به کیف پول برمی‌گردد."


async def cancel_job_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query, user = update.callback_query, update.effective_user
    if not query or not user:
        return
    job_id = (query.data or "").partition(":")[2]
    job = _state(context).active.get(user.id)
    if not job or job.id != job_id:
        await query.answer("این سفارش دیگر فعال نیست.", show_alert=True)
        return
    if isinstance(job, (Job, ImageJob)) and job.delivery_started:
        await query.answer("خروجی در حال تحویل است و لغو دیگر ممکن نیست.", show_alert=True)
        return
    if job.cancel_event.is_set():
        await query.answer("درخواست لغو قبلاً ثبت شده است.")
        return
    job.cancel_event.set()
    await query.answer("درخواست لغو ثبت شد.")
    await _edit_query_screen(query, _cancel_requested_text(job), reply_markup=ui.back_keyboard("menu:status"))


async def limits(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    message = update.effective_message
    if not user or not message:
        return
    state = _state(context)
    if user.id != state.settings.provider_control_user_id:
        return
    try:
        model_limits = await asyncio.to_thread(get_openai_limits, state.settings)
    except OpenAILimitsUnavailable:
        await message.reply_text(
            "برای نمایش زندهٔ سقف و مصرف، این دو مقدار را در .env سرور تنظیم کن:\n"
            "OPENAI_ADMIN_KEY=کلید Admin سازمان\n"
            "OPENAI_PROJECT_ID=شناسهٔ پروژه با پیشوند proj_\n\n"
            "کلید Admin را در چت نفرست. پس از تنظیم، bot را با docker compose up -d --build bot بازسازی کن.\n"
            "تنظیم سقف‌ها: https://platform.openai.com/account/rate-limits\n"
            "Billing: https://platform.openai.com/account/billing"
        )
        return

    lines = ["سقف پروژه و مصرف گزارش‌شده در ۲۴ ساعت اخیر:"]
    lines.extend(_format_model_limit(item) for item in model_limits)
    lines.extend([
        "",
        "مصرف اخیر از Admin API می‌آید و ممکن است با کمی تأخیر به‌روز شود؛ درخواست‌های خارج از این پروژه ممکن است روی سقف سازمان اثر بگذارند.",
        "برای افزایش سقف، در Rate Limits بخش Organization > Limits را باز کن؛ ارتقای Usage Tier و Billing هم می‌تواند سقف‌ها را بالا ببرد.",
        "https://platform.openai.com/account/rate-limits",
    ])
    await message.reply_text("\n".join(lines), disable_web_page_preview=True)


async def pricing(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, message = update.effective_user, update.effective_message
    if not user or not message:
        return
    state = _state(context)
    subtitle = int(await state.database.get_setting(
        "price_subtitle_toman_per_minute", str(state.settings.default_subtitle_price_toman_per_minute)
    ))
    dub = int(await state.database.get_setting(
        "price_dub_toman_per_minute", str(state.settings.default_dub_price_toman_per_minute)
    ))
    await _show_screen(update,
        "💎 تعرفه‌ها\n\n"
        f"📝 زیرنویس فارسی  ·  {subtitle:,} تومان / دقیقه\n"
        f"🎙 دوبلهٔ فارسی  ·  {dub:,} تومان / دقیقه\n\n"
        "هزینهٔ نهایی پیش از تأیید نمایش داده می‌شود.",
        reply_markup=ui.back_keyboard("menu:services" if update.callback_query else "menu:home"),
    )


async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, message = update.effective_user, update.effective_message
    if not user or not message:
        return
    if message.chat.type != "private":
        await message.reply_text("موجودی فقط در گفت‌وگوی خصوصی نمایش داده می‌شود.")
        return
    await _state(context).database.upsert_user(user, True)
    amount = await _state(context).database.get_wallet_balance(user.id)
    await _show_screen(update,
        f"👛 موجودی کیف پول\n\n<b>{amount:,} تومان</b>", parse_mode="HTML",
        reply_markup=ui.wallet_keyboard(),
    )


async def charge_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, message = update.effective_user, update.effective_message
    if not user or not message:
        return
    if message.chat.type != "private":
        await message.reply_text("برای امنیت اطلاعات کارت، درخواست شارژ را در گفت‌وگوی خصوصی ربات ثبت کن.")
        return
    state = _state(context)
    if not state.settings.card_to_card_number or not state.settings.card_to_card_holder:
        await message.reply_text("اطلاعات کارت مقصد هنوز تنظیم نشده است؛ مدیر را از طریق /paysupport مطلع کن.")
        return
    if not await state.database.has_accepted_terms(user.id):
        await message.reply_text(
            "قبل از درخواست شارژ، شرایط استفاده را بخوان و تأیید کن.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📜 شرایط استفاده", callback_data="terms:show")],
                [ui.button("‹ بازگشت", "menu:home")],
            ]),
        )
        return
    if not context.args:
        await _prompt_topup(update, context)
        return
    await _create_charge_request(update, context, context.args[0])


async def _prompt_topup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, message = update.effective_user, update.effective_message
    if not user or not message or message.chat.type != "private":
        return
    state = _state(context)
    back_action = "wallet:balance" if update.callback_query else "menu:home"
    state.awaiting_support.discard(user.id)
    if not state.settings.card_to_card_number or not state.settings.card_to_card_holder:
        await _show_screen(update, "شارژ در حال حاضر در دسترس نیست؛ با پشتیبانی تماس بگیر.",
                           reply_markup=ui.back_keyboard(back_action))
        return
    if not await state.database.has_accepted_terms(user.id):
        await _show_screen(update, "برای شارژ، شرایط استفاده را بخوان و بپذیر.",
            reply_markup=InlineKeyboardMarkup([
                [ui.button("📜 شرایط استفاده", "terms:show", style="primary")],
                [ui.button("‹ بازگشت", back_action)],
            ]))
        return
    pending = await state.database.get_user_pending_deposit(user.id)
    if pending:
        if pending["status"] == "awaiting_proof":
            await _show_screen(update,
                f"💳 درخواست شارژ باز · {pending['amount_toman']:,} تومان\n"
                f"شماره کارت: {state.settings.card_to_card_number}\n"
                f"به نام: {state.settings.card_to_card_holder}\n"
                "رسید یا شمارهٔ پیگیری را بفرست.",
                reply_markup=ui.back_keyboard(back_action))
        else:
            await _show_screen(update, "⏳ رسیدت در حال بررسی است.",
                               reply_markup=ui.back_keyboard(back_action))
        return
    state.awaiting_support.discard(user.id)
    state.awaiting_topup.add(user.id)
    await _show_screen(update,
        f"💳 شارژ کیف پول\nمبلغ را به تومان بفرست.\n"
        f"حداقل: {state.settings.minimum_wallet_topup_toman:,} تومان",
        reply_markup=ui.back_keyboard(back_action))


async def _create_charge_request(update: Update, context: ContextTypes.DEFAULT_TYPE, raw_amount: str) -> None:
    user, message = update.effective_user, update.effective_message
    if not user or not message or message.chat.type != "private":
        return
    state = _state(context)
    if not state.settings.card_to_card_number or not state.settings.card_to_card_holder:
        state.awaiting_topup.discard(user.id)
        await message.reply_text("شارژ در حال حاضر در دسترس نیست.", reply_markup=ui.back_keyboard())
        return
    if not await state.database.has_accepted_terms(user.id):
        state.awaiting_topup.discard(user.id)
        await message.reply_text("برای شارژ، ابتدا شرایط استفاده را بپذیر.",
            reply_markup=InlineKeyboardMarkup([
                [ui.button("📜 شرایط استفاده", "terms:show", style="primary")],
                [ui.button("‹ بازگشت", "wallet:balance")],
            ]))
        return
    try:
        amount = int(raw_amount.strip().replace(",", "").replace("٬", ""))
        if not state.settings.minimum_wallet_topup_toman <= amount <= 1_000_000_000:
            raise ValueError
    except ValueError:
        await message.reply_text(
            f"مبلغ را به عدد و بین {state.settings.minimum_wallet_topup_toman:,} تا 1,000,000,000 تومان بفرست.")
        return
    state.awaiting_topup.discard(user.id)
    state.awaiting_support.discard(user.id)
    await state.database.upsert_user(user, True)
    request_id = uuid.uuid4().hex
    created = await state.database.create_deposit_request(request_id, user.id, message.chat_id, amount)
    if not created:
        pending = await state.database.get_user_pending_deposit(user.id)
        if pending and pending["status"] == "awaiting_proof":
            await message.reply_text(
                f"یک درخواست باز برای {pending['amount_toman']:,} تومان داری.\n"
                f"شماره کارت: {state.settings.card_to_card_number}\n"
                f"به نام: {state.settings.card_to_card_holder}\n\n"
                "رسید/شماره پیگیری را بفرست یا /cancel کن."
            )
        else:
            await message.reply_text("یک رسید در حال بررسی داری؛ برای ایجاد درخواست تازه صبر کن تا مدیر نتیجه را اعلام کند.")
        return
    await message.reply_text(
        "🏦 درخواست شارژ ثبت شد.\n"
        f"مبلغ: <b>{amount:,} تومان</b>\n"
        f"شماره کارت: <code>{state.settings.card_to_card_number}</code>\n"
        f"به نام: <b>{escape(state.settings.card_to_card_holder)}</b>\n\n"
        "پس از واریز، رسید را بفرست. پس از تأیید مدیر، کیف پول شارژ می‌شود.",
        parse_mode="HTML", reply_markup=ui.back_keyboard("wallet:balance"),
    )


async def history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, message = update.effective_user, update.effective_message
    if not user or not message:
        return
    if message.chat.type != "private":
        await message.reply_text("گردش حساب فقط در گفت‌وگوی خصوصی نمایش داده می‌شود.")
        return
    rows = await _state(context).database.wallet_history(user.id)
    if not rows:
        await _show_screen(update, "📒 هنوز تراکنشی ثبت نشده است.", reply_markup=ui.wallet_keyboard())
        return
    labels = {
        "card_transfer_deposit": "شارژ کارت‌به‌کارت",
        "admin_credit": "شارژ توسط مدیر",
        "admin_debit": "برداشت توسط مدیر",
        "job_charge": "هزینهٔ پردازش",
        "job_refund": "بازگشت هزینهٔ پردازش",
    }
    lines = ["📒 گردش کیف پول · زمان‌ها UTC", ""]
    for row in rows:
        sign = "+" if row["amount_toman"] > 0 else ""
        description = labels.get(row['entry_type'], row['entry_type'])
        if row['memo'].startswith("خرید بسته"):
            description = "خرید بستهٔ دقیقه"
        elif "محتوای تکمیلی" in row['memo']:
            description = "محتوای تکمیلی" if row['amount_toman'] < 0 else "بازگشت هزینهٔ محتوای تکمیلی"
        lines.append(f"{row['created_at']:%Y-%m-%d %H:%M} · {description} · {sign}{row['amount_toman']:,} تومان")
    await _show_screen(update, "\n".join(lines), reply_markup=ui.wallet_keyboard())


async def terms(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, message = update.effective_user, update.effective_message
    if not user or not message:
        return
    await _show_screen(update,
        "📜 شرایط استفاده و حریم خصوصی\n\n"
        "• هزینه پیش از تأیید نمایش داده می‌شود.\n"
        "• در صورت خطای پردازش، هزینه به کیف پول برمی‌گردد.\n"
        "• شارژ کارت‌به‌کارت پس از بررسی رسید توسط مدیر انجام می‌شود.\n"
        "• بسته‌ها برای نوع مشخص‌اند و مدت اعتبار دارند.\n"
        "• لینک ویدیو برای پردازش به سرویس‌های فنی فرستاده می‌شود. متن زیرنویس و خروجی‌ها ذخیره می‌شوند.\n"
        "• خروجی هوش مصنوعی را پیش از استفاده بررسی کن.\n"
        "• فقط محتوایی را بفرست که اجازهٔ استفاده از آن را داری.\n\n"
        "با انتخاب «می‌پذیرم»، شرایط را تأیید می‌کنی.",
        reply_markup=InlineKeyboardMarkup([
            [ui.button("✓ می‌پذیرم", "terms:accept", style="success")],
            [ui.button("‹ بازگشت", "menu:home")],
        ]),
    )


async def payment_support(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message, user = update.effective_message, update.effective_user
    if not message or not user:
        return
    if message.chat.type != "private":
        await message.reply_text("برای تماس با پشتیبانی، گفت‌وگوی خصوصی ربات را باز کن.")
        return
    detail = " ".join(context.args).strip() if not update.callback_query else ""
    if detail:
        await _send_support_request(update, context, detail)
        return
    state = _state(context)
    state.awaiting_topup.discard(user.id)
    state.awaiting_support.add(user.id)
    contact = f"@{state.settings.support_username}" if state.settings.support_username else "مدیر ربات"
    await _show_screen(update,
        f"💬 پشتیبانی\nپیامت را همین‌جا بنویس.\nراه ارتباطی: {contact}",
        reply_markup=ui.back_keyboard("menu:support" if update.callback_query else "menu:home"))


async def _send_support_request(update: Update, context: ContextTypes.DEFAULT_TYPE, detail: str) -> None:
    message, user = update.effective_message, update.effective_user
    if not message or not user:
        return
    state = _state(context)
    detail = detail.strip()
    if not detail or len(detail) > 3000:
        await message.reply_text("پیامت را در ۱ تا ۳۰۰۰ نویسه بفرست.")
        return
    ticket_id = uuid.uuid4().hex[:8].upper()
    try:
        await context.application.bot.send_message(
            chat_id=state.settings.provider_control_user_id,
            text=f"💬 تیکت {ticket_id}\nاز کاربر {user.id} (@{user.username or 'بدون نام کاربری'})\n{detail}",
        )
        state.awaiting_support.discard(user.id)
        await message.reply_text(f"✅ پیامت برای پشتیبانی ارسال شد.\nشناسهٔ پیگیری: {ticket_id}", reply_markup=ui.back_keyboard())
    except TelegramError:
        logger.exception("Could not forward support ticket %s", ticket_id)
        await message.reply_text("ارسال پیام ممکن نشد. کمی بعد دوباره تلاش کن.")



async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, message = update.effective_user, update.effective_message
    if not user or not message:
        return
    if message.chat.type != "private":
        await message.reply_text("پنل مدیریت را در گفت‌وگوی خصوصی ربات باز کن.")
        return
    state = _state(context)
    if user.id != state.settings.provider_control_user_id:
        await message.reply_text("این پنل فقط برای مدیر ربات است.")
        return
    await _show_admin_panel(message.reply_text, state, user.id)


def _bounded_percent(value: str, default: int = 10) -> int:
    try:
        return max(0, min(100, int(value)))
    except (TypeError, ValueError):
        return default


async def _show_admin_panel(send, state: BotState, user_id: int) -> None:
    stats = await state.database.get_business_stats()
    subtitle = int(await state.database.get_setting("price_subtitle_toman_per_minute", str(state.settings.default_subtitle_price_toman_per_minute)))
    dub = int(await state.database.get_setting("price_dub_toman_per_minute", str(state.settings.default_dub_price_toman_per_minute)))
    original_audio_percent = _bounded_percent(
        await state.database.get_setting("dub_original_audio_percent", "10")
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ نرخ زیرنویس", callback_data="admin:edit:subtitle"),
         InlineKeyboardButton("✏️ نرخ دوبله", callback_data="admin:edit:dub")],
        [InlineKeyboardButton(f"🔊 صدای اصلی دوبله: {original_audio_percent}%", callback_data="admin:dub-audio-level")],
        [InlineKeyboardButton("➕ شارژ کاربر", callback_data="admin:wallet:credit"),
         InlineKeyboardButton("➖ کسر از کیف پول", callback_data="admin:wallet:debit")],
        [InlineKeyboardButton("👤 بررسی کاربر", callback_data="admin:wallet:lookup")],
        [InlineKeyboardButton(f"🧾 رسیدهای منتظر بررسی ({stats['pending_deposits']})", callback_data="admin:deposits")],
        [InlineKeyboardButton("🎟 تنظیم بسته‌های دقیقه", callback_data="admin:packages")],
        [InlineKeyboardButton("📝 قیمت محتوای تکمیلی", callback_data="admin:contentprices")],
        [InlineKeyboardButton("🎨 تنظیم ساخت تصویر", callback_data="admin:images", style="primary")],
        [InlineKeyboardButton("🤖 مدل‌ها و صدای دوبله", callback_data="admin:models", style="primary")],
        [InlineKeyboardButton("🔌 پردازشگر پیش‌فرض", callback_data="admin:providers")],
        [InlineKeyboardButton("🔄 به‌روزرسانی پنل", callback_data="admin:refresh")],
    ])
    await send(
        "🛠 پنل مدیریت\n\n"
        f"زیرنویس: {subtitle:,} تومان/دقیقه · دوبله: {dub:,} تومان/دقیقه\n"
        f"پردازشگر: {_provider_label(state.api_provider)}\n\n"
        f"کاربران: {stats['users']} · کل کارها: {stats['jobs']} · موفق: {stats['completed']}\n"
        f"درآمد پردازش خالص: {stats['net_sales_toman']:,} تومان · ماندهٔ کیف پول‌ها: {stats['wallet_total_toman']:,} تومان\n"
        f"هزینهٔ تخمینی API سفارش‌های اصلی: ${stats['api_cost_usd']:.4f}\n"
        f"هزینهٔ ثبت‌شدهٔ محتوای تکمیلی: ${stats['content_cost_usd']:.4f} · موارد نامشخص: {stats['content_cost_unknown']}\n"
        f"هزینهٔ ثبت‌شدهٔ تصاویر: ${stats.get('image_cost_usd', 0):.4f} · بهینه‌سازی: ${stats.get('image_optimizer_cost_usd', 0):.4f} · تصویر با هزینهٔ نامشخص: {stats.get('image_cost_unknown', 0)}\n"
        f"رسیدهای منتظر بررسی: {stats['pending_deposits']}\n\n"
        "برای شارژ/کسر دستی، دکمه را بزن و شناسهٔ تلگرام و مبلغ تومان را با فاصله بفرست.",
        reply_markup=keyboard,
    )


async def _show_model_settings(query, state: BotState) -> None:
    selection = await model_catalog.load_selection(state.database, state.settings, state.api_provider)
    lines = ["🤖 مدل‌های پردازش · برآورد هر دقیقه", ""]
    costs = {}
    for stage, label in model_catalog.STAGE_LABELS.items():
        item = getattr(selection, stage)
        costs[stage] = model_catalog.estimate_cents(stage, item)
        lines.append(f"{label}: {item.model} · {_provider_label(item.provider)}\n"
                     f"   {model_catalog.format_dollars(costs[stage])}")
    subtitle = model_catalog.sum_estimates(costs['stt'], costs['translation'])
    dubbing = model_catalog.sum_estimates(subtitle, costs['tts'])
    lines.extend([
        f"صدای دوبله: {selection.voice}", "",
        f"جمع زیرنویس: {model_catalog.format_dollars(subtitle)}",
        f"جمع دوبله: {model_catalog.format_dollars(dubbing)}", "",
        "فرض برای هر دقیقه ویدیو: رونویسی ۶۰ ثانیه، ترجمه ۳۰۰ توکن ورودی و ۱۵۰ توکن خروجی؛ برای دوبله نیز ۶۰ ثانیه صدای تولیدشده و ۳۰۰ توکن متن ورودی.",
        "این فقط سناریوی نمونه است؛ بازنویسی، تلاش مجدد، سکوت و تغییر نرخ می‌توانند هزینه را تغییر دهند. مدل ناشناخته یا OpenAI Realtime بدون نرخ قابل‌اتکای دقیقه‌ای، نامشخص نمایش داده می‌شود.",
        "انتخاب‌ها برای سفارش‌های بعدی اعمال می‌شوند.",
    ])
    await _edit_query_screen(query, "\n".join(lines), reply_markup=InlineKeyboardMarkup([
        [ui.button("🎧 مدل رونویسی", "admin:model:stt"), ui.button("🌐 مدل ترجمه", "admin:model:translation")],
        [ui.button("🎙 مدل تولید صدا", "admin:model:tts"), ui.button("🗣 صدای گوینده", "admin:voices")],
        [ui.button("‹ پنل مدیریت", "admin:refresh")],
    ]))


async def _show_model_options(query, state: BotState, stage: str) -> None:
    selection = await model_catalog.load_selection(state.database, state.settings, state.api_provider)
    current = getattr(selection, stage)
    options = [o for o in model_catalog.OPTIONS if o.stage == stage]
    lines = [f"🤖 {model_catalog.STAGE_LABELS[stage]}", ""]
    buttons = []
    for index, option in enumerate(options, 1):
        selected = option.model == current.model and option.provider == current.provider
        estimate = model_catalog.estimate_cents(stage, model_catalog.StageSelection(option.provider, option.model))
        lines.append(f"{index}. {'✓ ' if selected else ''}{option.model} · {_provider_label(option.provider)}\n"
                     f"   {model_catalog.format_dollars(estimate)}\n   نرخ مبنا: {option.price}")
        buttons.append([ui.button(f"{'✓ ' if selected else ''}{index}. {option.model}", f"admin:setmodel:{option.code}", style="success" if selected else None)])
    lines.extend(["", "قیمت‌ها تقریبی و مربوط به ۱۲ نوامبر ۲۰۲۶ هستند؛ نرخ نهایی را در داشبورد سرویس بررسی کن."])
    if stage == "translation":
        lines.append("برآورد نمونه در هر دقیقه: ۳۰۰ توکن ورودی و ۱۵۰ توکن خروجی، بدون تکرار. هزینهٔ واقعی به متن، دستورها و تعداد درخواست‌ها بستگی دارد.")
    elif stage == "tts":
        lines.append("برآورد نمونهٔ Gemini: ۶۰ ثانیه صدای تولیدشده (۲۵ توکن در ثانیه) و ۳۰۰ توکن متن ورودی. مدت صدا با ویدیو یکسان نیست و تکرار تولید هزینه را بیشتر می‌کند.")
        lines.append("برای OpenAI تبدیل قابل‌اتکای دقیقه‌ای در دسترس نیست؛ هزینه با توکن محاسبه می‌شود.")
    buttons.append([ui.button("‹ مدل‌ها", "admin:models")])
    await _edit_query_screen(query, "\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons))


async def _show_voice_options(query, state: BotState) -> None:
    selection = await model_catalog.load_selection(state.database, state.settings, state.api_provider)
    provider = selection.tts.provider
    voices = model_catalog.VOICES[provider]
    buttons = [ui.button(f"{'✓ ' if name == selection.voice else ''}{name}",
                         f"admin:voice:{provider}:{name}", style="success" if name == selection.voice else None)
               for name in voices]
    await _edit_query_screen(query,
        f"🗣 صدای دوبله · {_provider_label(provider)}\nمدل: {selection.tts.model}\n"
        "صدا بر اساس مدل انتخاب‌شده نمایش داده می‌شود؛ کیفیت فارسی را با ویدیوی نمونه بررسی کن.",
        reply_markup=InlineKeyboardMarkup([buttons[i:i + 2] for i in range(0, len(buttons), 2)] + [[ui.button("‹ مدل‌ها", "admin:models")]]),
    )


async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query, user = update.callback_query, update.effective_user
    if not query or not user:
        return
    state = _state(context)
    if user.id != state.settings.provider_control_user_id:
        await query.answer("فقط مدیر دسترسی دارد.", show_alert=True)
        return
    action = (query.data or "").split(":")
    if action == ["admin", "images"]:
        await query.answer()
        model = await image_generation.selected_model(state.database)
        price = int(await state.database.get_setting("image_price", "0"))
        edit_price = int(await state.database.get_setting("image_edit_price", "0"))
        buttons = [[ui.button(f"{'✓ ' if option == model else ''}{option.model}", f"admin:imagemodel:{option.code}")]
                   for option in image_generation.MODELS]
        buttons += [[ui.button("✏️ قیمت ساخت", "admin:imageprice"), ui.button("✏️ قیمت ویرایش", "admin:imageeditprice")], [ui.button("‹ پنل مدیریت", "admin:refresh")]]
        rates = "\n".join(f"{item.model} · {_provider_label(item.provider)}: {item.price_hint}" for item in image_generation.MODELS)
        await _edit_query_screen(query, f"🎨 تنظیم تولید تصویر\n\nمدل: {model.model}\nساخت: {price:,} تومان · ویرایش: {edit_price:,} تومان (صفر = غیرفعال)\n\n{rates}\n\nهزینهٔ بهینه‌سازی و عکس ورودی جداگانه به هزینهٔ API افزوده می‌شود. نرخ‌ها تقریبی‌اند؛ قیمت و دسترسی را بررسی کن.", reply_markup=InlineKeyboardMarkup(buttons))
        return
    if action == ["admin", "dub-audio-level"]:
        current = _bounded_percent(
            await state.database.get_setting("dub_original_audio_percent", "10")
        )
        state.admin_editing[user.id] = "dub_original_audio_percent"
        await query.answer()
        await _edit_query_screen(
            query,
            f"🔊 صدای اصلی در دوبله اکنون {current}% است.\n"
            "درصد دلخواه را از ۰ تا ۱۰۰ بفرست؛ مقدار پیش‌فرض ۱۰٪ است.\nلغو: /cancel",
        )
        return
    if len(action) == 3 and action[1] == "imagemodel":
        option = image_generation.BY_CODE.get(action[2])
        if not option or not (state.settings.openai_api_key if option.provider == "openai" else state.settings.openrouter_api_key):
            await query.answer("مدل یا کلید سرویس در دسترس نیست.", show_alert=True)
            return
        await state.database.set_setting("image_model", option.code)
        await query.answer("مدل تصویر ذخیره شد.")
        await _edit_query_screen(query, f"✅ مدل تصویر برای سفارش‌های بعدی: {option.model}", reply_markup=InlineKeyboardMarkup([[ui.button("‹ تنظیم تصویر", "admin:images")]]))
        return
    if action == ["admin", "imageprice"]:
        state.admin_editing[user.id] = "image_price"
        await query.answer()
        await _edit_query_screen(query, "قیمت فروش هر تصویر را به تومان بفرست؛ صفر سرویس را غیرفعال می‌کند. لغو: /cancel")
        return
    if action == ["admin", "imageeditprice"]:
        state.admin_editing[user.id] = "image_edit_price"
        await query.answer()
        await _edit_query_screen(query, "قیمت ویرایش هر تصویر را به تومان بفرست؛ صفر ویرایش را غیرفعال می‌کند. لغو: /cancel")
        return
    if action == ["admin", "packages"]:
        await query.answer()
        await _edit_query_screen(query, "🎟 تنظیم بسته‌ها\n\nبرای هر نوع، دقیقه، قیمت تومان و روز اعتبار را وارد کن؛ صفر برای غیرفعال‌سازی.",
            reply_markup=InlineKeyboardMarkup([
                [ui.button("📝 بستهٔ زیرنویس", "admin:package:subtitle"), ui.button("🎙 بستهٔ دوبله", "admin:package:dub")],
                [ui.button("‹ پنل مدیریت", "admin:refresh")],
            ]))
        return
    if len(action) == 3 and action[1] == "package" and action[2] in {"subtitle", "dub"}:
        state.admin_editing[user.id] = f"package_{action[2]}"
        await query.answer()
        await _edit_query_screen(query, "سه عدد دقیقه، قیمت تومان و روز اعتبار را با فاصله بفرست؛ نمونه: 100 400000 30\nبرای غیرفعال‌سازی عدد 0 و برای لغو /cancel را بزن.")
        return
    if action == ["admin", "contentprices"]:
        summary = await state.database.get_setting("content_price_summary", "0")
        social = await state.database.get_setting("content_price_social", "0")
        await query.answer()
        await _edit_query_screen(query,
            f"📝 قیمت محتوای تکمیلی\n\nخلاصه و جزوه: {int(summary):,} تومان\n"
            f"بستهٔ تولید محتوا: {int(social):,} تومان\n\nعدد صفر یعنی سرویس غیرفعال است.",
            reply_markup=InlineKeyboardMarkup([
                [ui.button("✏️ قیمت خلاصه", "admin:contentprice:summary"), ui.button("✏️ قیمت بسته", "admin:contentprice:social")],
                [ui.button("‹ پنل مدیریت", "admin:refresh")],
            ]))
        return
    if len(action) == 3 and action[1] == "contentprice" and action[2] in {"summary", "social"}:
        state.admin_editing[user.id] = f"content_{action[2]}"
        await query.answer()
        await _edit_query_screen(query, "قیمت ثابت هر سفارش را به تومان بفرست؛ عدد ۰ سرویس را غیرفعال می‌کند. لغو: /cancel")
        return
    if action == ["admin", "models"]:
        await query.answer()
        await _show_model_settings(query, state)
        return
    if len(action) == 3 and action[1] == "model" and action[2] in model_catalog.STAGE_LABELS:
        await query.answer()
        await _show_model_options(query, state, action[2])
        return
    if len(action) == 3 and action[1] == "setmodel":
        option = model_catalog.BY_CODE.get(action[2])
        if not option:
            await query.answer("مدل نامعتبر است.", show_alert=True)
            return
        key = state.settings.openai_api_key if option.provider == "openai" else state.settings.openrouter_api_key
        if not key:
            await query.answer("کلید این سرویس در سرور تنظیم نشده است.", show_alert=True)
            return
        await state.database.set_setting(f"model_choice_{option.stage}", option.code)
        await query.answer("مدل ذخیره شد.")
        await _show_model_options(query, state, option.stage)
        return
    if action == ["admin", "voices"]:
        await query.answer()
        await _show_voice_options(query, state)
        return
    if len(action) == 4 and action[1] == "voice":
        provider, voice = action[2], action[3]
        current = await model_catalog.load_selection(state.database, state.settings, state.api_provider)
        if provider != current.tts.provider or voice not in model_catalog.VOICES.get(provider, ()):
            await query.answer("این صدا برای پردازشگر فعلی معتبر نیست.", show_alert=True)
            return
        await state.database.set_setting(f"model_voice_{provider}", voice)
        await query.answer("صدا ذخیره شد.")
        await _show_voice_options(query, state)
        return
    if len(action) == 3 and action[1] == "edit" and action[2] in {"subtitle", "dub"}:
        state.admin_editing[user.id] = action[2]
        await query.answer()
        await _edit_query_screen(query, "نرخ جدید را به تومان برای هر دقیقه بفرست. لغو: /cancel")
        return
    if action == ["admin", "wallet", "credit"] or action == ["admin", "wallet", "debit"]:
        state.admin_editing[user.id] = action[2]
        await query.answer()
        await _edit_query_screen(query, "شناسهٔ عددی تلگرام و مبلغ تومان را بفرست؛ نمونه: 123456789 500000\nلغو: /cancel")
        return
    if action == ["admin", "wallet", "lookup"]:
        state.admin_editing[user.id] = "lookup"
        await query.answer()
        await _edit_query_screen(query, "شناسهٔ عددی تلگرام کاربر را بفرست؛ لغو: /cancel")
        return
    if action == ["admin", "providers"]:
        await query.answer()
        await _edit_query_screen(query,
            f"پردازشگر فعلی: {_provider_label(state.api_provider)}",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("OpenAI", callback_data="provider:openai"),
                InlineKeyboardButton("OpenRouter", callback_data="provider:openrouter"),
            ]]),
        )
        return
    if action == ["admin", "deposits"]:
        rows = await state.database.list_pending_deposits()
        await query.answer(f"{len(rows)} رسید در انتظار بررسی")
        if not rows:
            await query.message.reply_text("رسید تأییدنشده‌ای وجود ندارد.")
            return
        for row in rows:
            await _notify_admin_deposit(context.application, row, row.get("username"))
        await query.message.reply_text("رسیدهای باز دوباره برای بررسی ارسال شدند.")
        return
    if action == ["admin", "refresh"]:
        await query.answer()
        await _edit_query_screen(query, "در حال به‌روزرسانی…")
        await _show_admin_panel(query.message.reply_text, state, user.id)
        return
    await query.answer("دکمه منقضی شده است.", show_alert=True)


async def _save_admin_value(update: Update, state: BotState, application: Application) -> None:
    user, message = update.effective_user, update.effective_message
    if not user or not message:
        return
    key = state.admin_editing.get(user.id)
    if not key:
        return
    if key in {"package_subtitle", "package_dub"}:
        raw = message.text.strip().replace(",", "").replace("٬", "")
        try:
            if raw == "0":
                value = "0"
            else:
                minutes, price, days = map(int, raw.split())
                if not (1 <= minutes <= 10000 and 1 <= price <= 1_000_000_000 and 1 <= days <= 365):
                    raise ValueError
                value = f"{minutes}:{price}:{days}"
        except ValueError:
            await message.reply_text("سه عدد معتبر دقیقه، قیمت تومان و روز اعتبار یا عدد 0 بفرست.")
            return
        await state.database.set_setting(f"plan_{key.removeprefix('package_')}", value)
        state.admin_editing.pop(user.id, None)
        await message.reply_text("✅ تنظیم بسته ذخیره شد؛ بسته‌های خریداری‌شدهٔ قبلی تغییر نمی‌کنند.")
        return
    if key == "lookup":
        try:
            target_id = int(message.text.strip())
            if target_id <= 0:
                raise ValueError
        except ValueError:
            await message.reply_text("شناسهٔ عددی تلگرام را بفرست.")
            return
        summary = await state.database.user_admin_summary(target_id)
        if not summary:
            await message.reply_text("کاربری با این شناسه در دیتابیس نیست.")
            return
        state.admin_editing.pop(user.id, None)
        lines = [
            f"👤 کاربر {summary['telegram_id']} (@{summary['username'] or 'بدون نام کاربری'})",
            f"موجودی: {summary['wallet_balance_toman']:,} تومان · شارژهای ثبت‌شده: {summary['total_deposited_toman']:,} تومان",
            f"کارها: {summary['jobs']} · موفق: {summary['completed']} · آخرین فعالیت: {summary['last_seen_at']:%Y-%m-%d %H:%M UTC}",
            "کارهای اخیر:",
        ]
        mode_names = {"subtitle": "زیرنویس", "dub": "دوبله"}
        for item in summary["recent_jobs"]:
            amount = f"{item['amount_toman']:,} تومان" if item["amount_toman"] else "—"
            minutes = f" · {item['minutes']} دقیقه" if item["minutes"] else ""
            lines.append(
                f"• {item['created_at']:%m-%d %H:%M} · {mode_names.get(item['mode'], item['mode'])} · "
                f"{item['status']}{minutes} · {amount}"
            )
        await message.reply_text("\n".join(lines))
        return
    if key == "dub_original_audio_percent":
        digits = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
        raw = message.text.strip().translate(digits)
        try:
            percent = int(raw)
            if not 0 <= percent <= 100:
                raise ValueError
        except ValueError:
            await message.reply_text("یک عدد صحیح بین ۰ تا ۱۰۰ بفرست؛ نمونه: 10")
            return
        await state.database.set_setting(key, str(percent))
        state.admin_editing.pop(user.id, None)
        await message.reply_text(f"✅ صدای اصلی برای دوبله‌های بعدی روی {percent}% تنظیم شد.")
        return
    if key in {"credit", "debit"}:
        try:
            raw_user_id, raw_amount = message.text.replace(",", "").replace("٬", "").split()
            target_id, amount = int(raw_user_id), int(raw_amount)
            if target_id <= 0 or not 1 <= amount <= 1_000_000_000:
                raise ValueError
        except ValueError:
            await message.reply_text("فرمت درست: شناسهٔ تلگرام و مبلغ تومان، مثل 123456789 500000")
            return
        new_balance = await state.database.direct_wallet_adjustment(
            target_id, amount, user.id, credit=key == "credit",
            memo="شارژ دستی توسط مدیر" if key == "credit" else "کسر دستی توسط مدیر",
        )
        if new_balance is None:
            await message.reply_text("موجودی برای این کسر کافی نیست یا اطلاعات کاربر معتبر نیست.")
            return
        state.admin_editing.pop(user.id, None)
        action_label = "شارژ شد" if key == "credit" else "کسر شد"
        await message.reply_text(f"✅ کیف پول {target_id} به مبلغ {amount:,} تومان {action_label}.\nموجودی جدید: {new_balance:,} تومان")
        if key == "credit":
            try:
                await application.bot.send_message(target_id, f"💰 کیف پول شما توسط پشتیبانی {amount:,} تومان شارژ شد.\nموجودی: {new_balance:,} تومان")
            except TelegramError:
                logger.info("Could not notify wallet top-up recipient %s; they may not have started the bot", target_id)
        return
    try:
        price = int(message.text.strip().replace(",", "").replace("٬", ""))
        if not (0 if key.startswith("content_") or key in {"image_price", "image_edit_price"} else 1) <= price <= 1_000_000_000:
            raise ValueError
    except ValueError:
        await message.reply_text("یک عدد صحیح تومان بین ۱ تا ۱٬۰۰۰٬۰۰۰٬۰۰۰ بفرست.")
        return
    state.admin_editing.pop(user.id, None)
    if key in {"image_price", "image_edit_price"}:
        await state.database.set_setting(key, str(price))
        await message.reply_text(f"✅ قیمت {'ویرایش' if key == 'image_edit_price' else 'ساخت'} هر تصویر: {price:,} تومان؛ صفر سرویس را غیرفعال می‌کند.")
        return
    if key in {"content_summary", "content_social"}:
        await state.database.set_setting(f"content_price_{key.removeprefix('content_')}", str(price))
        await message.reply_text(f"✅ قیمت سرویس روی {price:,} تومان تنظیم شد؛ صفر به معنی غیرفعال است.")
        return
    db_key = "price_subtitle_toman_per_minute" if key == "subtitle" else "price_dub_toman_per_minute"
    await state.database.set_setting(db_key, str(price))
    await message.reply_text(f"✅ نرخ {('زیرنویس' if key == 'subtitle' else 'دوبله')} روی {price:,} تومان/دقیقه تنظیم شد.")


async def terms_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query, user = update.callback_query, update.effective_user
    if not query or not user:
        return
    state = _state(context)
    action = (query.data or "")
    if action == "terms:show":
        await query.answer()
        await terms(update, context)
    elif action == "terms:accept":
        await state.database.accept_terms(user.id)
        await query.answer("شرایط پذیرفته شد.")
        await _edit_query_screen(query, "✅ شرایط ثبت شد. حالا لینک ویدیو را بفرست.", reply_markup=ui.back_keyboard())


async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query, user = update.callback_query, update.effective_user
    if not query or not user:
        return
    action = (query.data or "").partition(":")[2]
    await query.answer()
    state = _state(context)
    state.awaiting_image_prompt.discard(user.id)
    state.image_references.pop(user.id, None)
    state.subtitle_editing.pop(user.id, None)
    if not state.image_quotes.get(str(user.id), {}).get("confirming"):
        state.image_quotes.pop(str(user.id), None)
    if action != "contact":
        state.awaiting_support.discard(user.id)
    state.awaiting_topup.discard(user.id)
    if action == "home":
        state.subtitle_editing.pop(user.id, None)
        await state.database.upsert_user(user, True)
        balance = await state.database.get_wallet_balance(user.id)
        await _edit_query_screen(query, ui.home_text(balance), parse_mode="HTML", reply_markup=ui.home_keyboard())
    elif action == "new":
        if user.id in state.active or user.id in state.pending_by_user:
            await _edit_query_screen(query, "یک سفارش باز داری. وضعیت آن را ببین یا لغو کن.",
                reply_markup=InlineKeyboardMarkup([
                    [ui.button("📦 وضعیت سفارش", "menu:status", style="primary")],
                    [ui.button("‹ بازگشت", "menu:home")],
                ]))
            return
        await _edit_query_screen(query, "🎬 سفارش جدید\nلینک ویدیو یا آهنگ را همین‌جا بفرست.",
                                      reply_markup=ui.back_keyboard())
    elif action == "services":
        await _edit_query_screen(query, "✨ خدمات\nیکی از گزینه‌ها را انتخاب کن:", reply_markup=ui.services_keyboard())
    elif action == "pricing":
        await pricing(update, context)
    elif action == "status":
        if user.id in state.active:
            job = state.active[user.id]
            label = ("دانلود" if isinstance(job, DownloadJob) else "ساخت تصویر" if isinstance(job, ImageJob) else "محتوای تکمیلی" if isinstance(job, ContentJob) else
                     "زیرنویس" if job.mode == "subtitle" else "دوبله")
            await _edit_query_screen(query,
                f"📦 سفارش فعال\n\nنوع: {label}\nشمارهٔ سفارش: {job.id[:8]}\n"
                + ((_progress_text(job.progress_stage, job.progress_percent) + "\nدرصد تقریبی مراحل پردازش است.")
                   if isinstance(job, Job) else "وضعیت در پیام سفارش نمایش داده می‌شود.")
                + ("\n⏳ درخواست لغو در حال انجام است." if job.cancel_event.is_set() else ""),
                reply_markup=ui.job_keyboard(job.id, cancellable=not isinstance(job, (Job, ImageJob)) or not job.delivery_started))
        elif user.id in state.pending_by_user:
            token = state.pending_by_user[user.id]
            await _edit_query_screen(query, "📦 سفارش هنوز در مرحلهٔ انتخاب است. آن را ادامه بده یا لغو کن.",
                reply_markup=InlineKeyboardMarkup([
                    [ui.button("✕ لغو انتخاب", f"order_cancel:{token}", style="danger")],
                    [ui.button("‹ بازگشت", "menu:home")],
                ]))
        else:
            await _edit_query_screen(query, "📦 سفارش فعالی نداری.", reply_markup=InlineKeyboardMarkup([
                [ui.button("🎬 سفارش جدید", "menu:new", style="primary")],
                [ui.button("‹ بازگشت", "menu:home")],
            ]))
    elif action == "canceljob":
        await _edit_query_screen(query, "برای لغو، وضعیت سفارش را باز کن.",
            reply_markup=InlineKeyboardMarkup([
                [ui.button("📦 وضعیت سفارش", "menu:status", style="primary")],
                [ui.button("‹ بازگشت", "menu:home")],
            ]))
    elif action == "team":
        await team_command(update, context)
    elif action == "history":
        await history(update, context)
    elif action == "terms":
        await terms(update, context)
    elif action == "support":
        await _edit_query_screen(query, "💬 پشتیبانی\nچطور می‌توانیم کمکت کنیم؟", reply_markup=ui.support_keyboard())
    elif action == "contact":
        await payment_support(update, context)
    elif action == "help":
        await _edit_query_screen(query,
            "📖 راهنما\nلینک را بفرست، خروجی را انتخاب کن و هزینه را پیش از تأیید ببین.\n"
            "در صورت خطای پردازش، هزینه برمی‌گردد.",
            reply_markup=InlineKeyboardMarkup([
                [ui.button("✉️ ارسال پیام", "menu:contact", style="primary")],
                [ui.button("📜 شرایط استفاده", "menu:terms")],
                [ui.button("‹ بازگشت", "menu:support")],
            ]))
    else:
        await _edit_query_screen(query, "این بخش در دسترس نیست.", reply_markup=ui.back_keyboard())



async def receive_deposit_proof(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, message = update.effective_user, update.effective_message
    if not user or not message:
        return
    if message.chat.type != "private":
        await message.reply_text("رسید را فقط در گفت‌وگوی خصوصی ربات بفرست.")
        return
    if user.id in _state(context).awaiting_image_prompt:
        await _receive_image_reference(update, context)
        return
    pending = await _state(context).database.get_user_pending_deposit(user.id)
    if not pending or pending["status"] != "awaiting_proof":
        await message.reply_text("برای ارسال رسید، ابتدا از بخش کیف پول درخواست شارژ بساز.", reply_markup=ui.wallet_keyboard())
        return
    proof_type, file_id, proof_text = "text", None, None
    if message.photo:
        proof_type, file_id = "photo", message.photo[-1].file_id
    elif message.document:
        proof_type, file_id = "document", message.document.file_id
    else:
        return
    proof_text = (message.caption or "").strip() or None
    saved = await _state(context).database.submit_deposit_proof(
        pending["id"], user.id, proof_type, proof_text=proof_text, proof_file_id=file_id
    )
    if not saved:
        await message.reply_text("درخواست شارژ پیدا نشد یا قبلاً رسیدی ثبت شده است.")
        return
    await message.reply_text("✅ رسید دریافت شد و برای بررسی مدیر ارسال شد. پس از تأیید، موجودی کیف پول به‌روزرسانی می‌شود.")
    await _notify_admin_deposit(context.application, saved, user.username)


async def _notify_admin_deposit(application: Application, request: dict, username: str | None) -> None:
    admin_id = application.bot_data["settings"].provider_control_user_id
    label = (
        f"💳 درخواست کارت‌به‌کارت {request['id'][:8]}\n"
        f"کاربر: {request['user_id']} (@{username or 'بدون نام کاربری'})\n"
        f"مبلغ: {request['amount_toman']:,} تومان\n"
        f"شماره پیگیری/یادداشت: {request.get('proof_text') or 'در تصویر پیوست'}\n"
        "پس از بررسی گردش حساب بانکی، تأیید یا رد کن."
    )
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ تأیید و شارژ", callback_data=f"deposit:approve:{request['id']}", style="success"),
        InlineKeyboardButton("❌ رد", callback_data=f"deposit:reject:{request['id']}", style="danger"),
    ]])
    try:
        if request.get("proof_type") == "photo" and request.get("proof_file_id"):
            await application.bot.send_photo(admin_id, request["proof_file_id"], caption=label[:1000], reply_markup=keyboard)
        elif request.get("proof_type") == "document" and request.get("proof_file_id"):
            await application.bot.send_document(admin_id, request["proof_file_id"], caption=label[:1000], reply_markup=keyboard)
        else:
            await application.bot.send_message(admin_id, label, reply_markup=keyboard)
    except TelegramError:
        logger.exception("Could not send card transfer request %s to admin", request["id"])


async def deposit_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query, user = update.callback_query, update.effective_user
    if not query or not user:
        return
    state = _state(context)
    if user.id != state.settings.provider_control_user_id:
        await query.answer("فقط مدیر می‌تواند رسید را بررسی کند.", show_alert=True)
        return
    try:
        _, action, request_id = (query.data or "").split(":", 2)
    except ValueError:
        await query.answer("درخواست نامعتبر است.", show_alert=True)
        return
    if action == "approve":
        result = await state.database.approve_deposit(request_id, user.id)
        if not result:
            await query.answer("این رسید قبلاً بررسی شده یا معتبر نیست.", show_alert=True)
            return
        await query.answer("کیف پول شارژ شد.")
        if query.message and (query.message.photo or query.message.document):
            await query.edit_message_caption(caption=f"✅ تأیید شد · {result['amount_toman']:,} تومان برای {result['user_id']} شارژ شد.")
        else:
            await _edit_query_screen(query, f"✅ تأیید شد · {result['amount_toman']:,} تومان برای {result['user_id']} شارژ شد.")
        try:
            await context.application.bot.send_message(
                result["chat_id"],
                f"✅ شارژ کارت‌به‌کارت تأیید شد. {result['amount_toman']:,} تومان به کیف پول اضافه شد.\nموجودی: {result['balance_toman']:,} تومان",
            )
        except TelegramError:
            logger.exception("Could not notify user about approved deposit %s", request_id)
    elif action == "reject":
        result = await state.database.reject_deposit(request_id, user.id)
        if not result:
            await query.answer("این رسید قبلاً بررسی شده یا معتبر نیست.", show_alert=True)
            return
        await query.answer("درخواست رد شد.")
        if query.message and (query.message.photo or query.message.document):
            await query.edit_message_caption(caption="❌ درخواست شارژ رد شد؛ در صورت اشتباه با /paysupport پیگیری کن.")
        else:
            await _edit_query_screen(query, "❌ درخواست شارژ رد شد؛ در صورت اشتباه با /paysupport پیگیری کن.")
        try:
            await context.application.bot.send_message(result["chat_id"], "درخواست شارژ تأیید نشد. اگر انتقال را انجام داده‌ای، با /paysupport شمارهٔ پیگیری را بفرست.")
        except TelegramError:
            logger.exception("Could not notify user about rejected deposit %s", request_id)
    else:
        await query.answer("عملیات نامعتبر است.", show_alert=True)


async def wallet_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query, user = update.callback_query, update.effective_user
    if not query or not user:
        return
    await query.answer()
    action = (query.data or "").partition(":")[2]
    if action == "balance":
        _state(context).awaiting_support.discard(user.id)
        _state(context).awaiting_topup.discard(user.id)
        await balance(update, context)
    elif action == "topup":
        await _prompt_topup(update, context)



async def legacy_stars_refund(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Refund any old Stars invoice paid after switching this bot to wallet billing."""
    message, user = update.effective_message, update.effective_user
    payment = message.successful_payment if message else None
    if not user or not payment or payment.currency != "XTR":
        return
    try:
        await context.application.bot.refund_star_payment(
            user_id=user.id, telegram_payment_charge_id=payment.telegram_payment_charge_id
        )
        await message.reply_text("پرداخت Stars دیگر برای این ربات فعال نیست؛ مبلغ به‌صورت خودکار برگشت داده شد. برای ادامه از کیف پول تومانی استفاده کن.")
    except TelegramError:
        logger.exception("Could not refund legacy Stars payment for user %s", user.id)
        await message.reply_text("پرداخت قدیمی Stars دریافت شد اما برگشت خودکار انجام نشد؛ /paysupport را بزن.")


async def choose_provider_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    message = update.effective_message
    if not user or not message:
        return
    state = _state(context)
    if user.id != state.settings.provider_control_user_id:
        await message.reply_text("فقط مدیر تعیین‌شده می‌تواند سرویس پردازش را تغییر دهد.")
        return
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("OpenAI", callback_data="provider:openai"),
        InlineKeyboardButton("OpenRouter", callback_data="provider:openrouter"),
    ]])
    await message.reply_text(
        f"سرویس فعلی: {_provider_label(state.api_provider)}\nبرای jobهای بعدی انتخاب کن:",
        reply_markup=keyboard,
    )


async def choose_provider_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    if not query or not user:
        return
    state = _state(context)
    if user.id != state.settings.provider_control_user_id:
        await query.answer("فقط مدیر تعیین‌شده می‌تواند سرویس را تغییر دهد.", show_alert=True)
        return
    provider = (query.data or "").partition(":")[2]
    if provider not in {"openai", "openrouter"}:
        await query.answer("انتخاب نامعتبر است.", show_alert=True)
        return
    if provider == "openrouter" and not state.settings.openrouter_api_key:
        await query.answer("OPENROUTER_API_KEY در .env تنظیم نشده است.", show_alert=True)
        return
    if provider == "openai" and not state.settings.openai_api_key:
        await query.answer("OPENAI_API_KEY در .env تنظیم نشده است.", show_alert=True)
        return
    await state.database.set_setting("api_provider", provider)
    state.api_provider = provider
    await query.answer("سرویس تغییر کرد.")
    await _edit_query_screen(query,
        f"سرویس برای jobهای بعدی روی {_provider_label(provider)} تنظیم شد."
    )


def _provider_label(provider: str) -> str:
    return "OpenRouter" if provider == "openrouter" else "OpenAI"


def _format_model_limit(item: ModelLimit) -> str:
    parts = [item.model]
    if item.requests_last_24h is not None and item.max_requests_per_day is not None:
        remaining = item.remaining_today or 0
        parts.append(
            f"درخواست روزانه: حدود {item.requests_last_24h}/{item.max_requests_per_day} مصرف شده؛ "
            f"حدود {remaining} باقی‌مانده"
        )
    elif item.max_requests_per_day is not None:
        parts.append(f"سقف روزانه: {item.max_requests_per_day} درخواست؛ مصرف در دسترس نیست")
    else:
        parts.append("سقف روزانه/مصرف درخواست از API در دسترس نیست")
    if item.max_requests_per_minute is not None:
        parts.append(f"RPM: {item.max_requests_per_minute}")
    if item.max_tokens_per_minute is not None:
        parts.append(f"TPM: {item.max_tokens_per_minute:,}")
    return " • ".join(parts)


ORDER_PAGE_SIZE = 5
ORDER_CATEGORIES = {"processing": "دوبله و زیرنویس", "download": "دانلود فایل", "content": "محتوای تکمیلی"}
ORDER_STATUS = {"queued": "در صف", "running": "در حال پردازش", "completed": "تکمیل‌شده",
                "failed": "ناموفق", "cancelled": "لغوشده", "interrupted": "متوقف‌شده با راه‌اندازی مجدد",
                "refunded": "ناموفق؛ بازپرداخت‌شده"}


def _order_kind(category: str, kind: str) -> str:
    if category == "processing":
        return "زیرنویس فارسی" if kind == "subtitle" else "دوبلهٔ فارسی"
    if category == "download":
        return {"audio": "فایل صوتی", "media": "مدیای اینستاگرام"}.get(kind, "ویدیو")
    return "خلاصه و جزوه" if kind == "summary" else "بستهٔ تولید محتوا"


def _order_active_link(order: dict, category: str, settings, now: datetime) -> tuple[str, datetime, str] | None:
    """Only expose a published token that belongs to this order and is still live."""
    if order['status'] != "completed" or not settings.download_base_url:
        return None
    directory = Path(settings.download_dir)
    if category == "processing":
        candidates = order.get('links', [])
    elif category == "download":
        candidates = [{"token": order.get('token'), "filename": order.get('extension'),
                       "expires_at": order.get('expires_at')}]
    else:
        return None
    for item in candidates:
        token, filename, expiry = item.get('token'), item.get('filename'), item.get('expires_at')
        if not isinstance(token, str) or not re.fullmatch(r"[a-f0-9]{32}", token):
            continue
        if not isinstance(expiry, datetime) or expiry.tzinfo is None or expiry <= now:
            continue
        if category == "processing" and filename == "video.mp4":
            if (directory / f"{token}.mp4").is_file():
                if (directory / f"{token}.html").is_file():
                    return f"{settings.download_base_url}/{token}", expiry, "player"
                return f"{settings.download_base_url}/{token}.mp4", expiry, "video"
        elif category == "processing" and filename == "video-fa.mp4":
            if (directory / f"{token}.mp4").is_file():
                return f"{settings.download_base_url}/{token}.mp4", expiry, "video"
        elif category == "download" and filename in {"mp3", "mp4", "zip", "jpg", "jpeg", "png", "webp", "avif"}:
            if (directory / f"{token}.{filename}").is_file():
                return f"{settings.download_base_url}/{token}.{filename}", expiry, "download"
    return None


async def orders_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query, user = update.callback_query, update.effective_user
    if not query or not user or not query.message or query.message.chat.type != "private":
        return
    state = _state(context)
    parts = (query.data or "").split(":")
    action = parts[1] if len(parts) > 1 else ""
    if action == "home":
        await query.answer()
        await _edit_query_screen(query, "📦 سفارش‌های من\nنوع سفارش را انتخاب کن:", reply_markup=ui.orders_keyboard())
        return
    if action == "list" and len(parts) == 4 and parts[2] in ORDER_CATEGORIES:
        category = parts[2]
        try:
            page = int(parts[3])
            if not 0 <= page <= 10000:
                raise ValueError
        except ValueError:
            await query.answer("شمارهٔ صفحه معتبر نیست.", show_alert=True)
            return
        rows = await state.database.list_orders(user.id, category, page * ORDER_PAGE_SIZE, ORDER_PAGE_SIZE + 1)
        await query.answer()
        buttons = []
        for row in rows[:ORDER_PAGE_SIZE]:
            label = f"{_order_kind(category, row['kind'])} · {ORDER_STATUS.get(row['status'], 'نامشخص')} · {row['id'][:8]}"
            buttons.append([ui.button(label, f"orders:detail:{category}:{row['id']}:{page}")])
        navigation = []
        if page:
            navigation.append(ui.button("‹ قبلی", f"orders:list:{category}:{page - 1}"))
        if len(rows) > ORDER_PAGE_SIZE:
            navigation.append(ui.button("بعدی ›", f"orders:list:{category}:{page + 1}"))
        if navigation:
            buttons.append(navigation)
        buttons.append([ui.button("‹ بازگشت", "orders:home")])
        text = f"📦 {ORDER_CATEGORIES[category]} · صفحهٔ {page + 1}\n\n" + ("سفارشی پیدا نشد." if not rows else "برای مشاهدهٔ جزئیات، یک سفارش را انتخاب کن.")
        await _edit_query_screen(query, text, reply_markup=InlineKeyboardMarkup(buttons))
        return
    if action == "detail" and len(parts) == 5 and parts[2] in ORDER_CATEGORIES:
        category, order_id = parts[2], parts[3]
        try:
            page = int(parts[4])
            if not 0 <= page <= 10000 or not re.fullmatch(r"[a-f0-9]{32}", order_id):
                raise ValueError
        except ValueError:
            await query.answer("سفارش معتبر نیست.", show_alert=True)
            return
        order = await state.database.get_owned_order(user.id, category, order_id)
        if not order:
            await query.answer("سفارش پیدا نشد.", show_alert=True)
            return
        text = (f"📦 {_order_kind(category, order['kind'])}\n"
                f"شماره: {order_id[:8]}\nوضعیت: {ORDER_STATUS.get(order['status'], 'نامشخص')}\n"
                f"تاریخ ثبت: {order['created_at']:%Y-%m-%d %H:%M} UTC")
        if category == "processing" and order.get('minutes'):
            text += f"\nمدت قابل محاسبه: {order['minutes']} دقیقه"
            if order.get('package_minutes'):
                text += f"\nپرداخت: {order['package_minutes']} دقیقه از بسته"
            elif order.get('amount') is not None:
                text += f"\nهزینه: {order['amount']:,} تومان"
        if category in {"processing", "download"} and order.get('source_url'):
            text += f"\nمنبع: {order['source_url'][:500]}"
        if category == "download" and order.get('title'):
            text += f"\nعنوان: {order['title']}"
        buttons = []
        link = _order_active_link(order, category, state.settings, datetime.now(UTC))
        if link:
            url, expires, kind = link
            text += f"\n\n⏳ لینک تا {expires:%Y-%m-%d %H:%M} UTC معتبر است."
            buttons.append([InlineKeyboardButton("▶️ پخش و دانلود" if kind == "player" else "⬇️ دریافت فایل", url=url, style="primary")])
            if kind == "player":
                token = url.rsplit('/', 1)[-1]
                if (Path(state.settings.download_dir) / f"{token}.srt").is_file():
                    buttons.append([InlineKeyboardButton("📝 دریافت SRT", url=f"{state.settings.download_base_url}/{token}.srt")])
        elif order['status'] == "completed" and category != "content":
            if order.get('links') or order.get('token'):
                text += "\n\nلینک این سفارش منقضی شده یا فایل آن دیگر در دسترس نیست."
            else:
                text += "\n\nبرای این سفارش لینک ذخیره نشده؛ فایل ممکن است مستقیماً در چت ارسال شده باشد."
        if category == "content" and order['status'] == "completed":
            buttons.append([ui.button("⬇️ دریافت خروجی", f"content:result:{order_id}", style="primary")])
        if category == "processing" and order['status'] == "completed":
            buttons.append([ui.button("📝 خروجی‌های تکمیلی و ویرایش", f"content:job:{order_id}")])
        buttons.append([ui.button("‹ بازگشت", f"orders:list:{category}:{page}")])
        await query.answer()
        await _edit_query_screen(query, text, reply_markup=InlineKeyboardMarkup(buttons), disable_web_page_preview=True)
        return
    await query.answer("گزینهٔ نامعتبر است.", show_alert=True)


def _parse_package_plan(value: str) -> tuple[int, int, int] | None:
    try:
        minutes, price, days = map(int, value.split(":"))
        return (minutes, price, days) if 1 <= minutes <= 10000 and 1 <= price <= 1_000_000_000 and 1 <= days <= 365 else None
    except (ValueError, TypeError):
        return None


async def packages_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query, user = update.callback_query, update.effective_user
    if not query or not user or not query.message or query.message.chat.type != "private":
        return
    state = _state(context)
    parts = (query.data or "").split(":")
    action = parts[1] if len(parts) > 1 else ""
    if action == "list":
        await query.answer()
        active = await state.database.available_minutes(user.id)
        lines = ["🎟 بسته‌های دقیقه", ""]
        for p in active:
            lines.append(f"{'زیرنویس' if p['mode'] == 'subtitle' else 'دوبله'}: {p['minutes']} دقیقه · انقضا {p['expires_at']:%Y-%m-%d %H:%M} UTC")
        if not active:
            lines.append("بستهٔ فعالی نداری.")
        buttons = []
        for mode, label in (("subtitle", "زیرنویس"), ("dub", "دوبله")):
            plan = _parse_package_plan(await state.database.get_setting(f"plan_{mode}", "0"))
            if plan:
                minutes, price, days = plan
                lines.append(f"\n{label}: {minutes} دقیقه · {price:,} تومان · اعتبار {days} روز")
                buttons.append([ui.button(f"خرید بستهٔ {label}", f"packs:quote:{mode}")])
        lines.append("\nهزینه از کیف پول کم می‌شود.")
        buttons.append([ui.button("‹ بازگشت", "menu:services")])
        await _edit_query_screen(query, "\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons))
        return
    if action == "quote" and len(parts) == 3 and parts[2] in {"subtitle", "dub"}:
        mode = parts[2]
        plan = _parse_package_plan(await state.database.get_setting(f"plan_{mode}", "0"))
        if not plan:
            await query.answer("این بسته فعال نیست.", show_alert=True)
            return
        minutes, price, days = plan
        token = uuid.uuid4().hex[:12]
        state.package_quotes[token] = (user.id, mode, minutes, price, days)
        await query.answer()
        await _edit_query_screen(query, f"🧾 بستهٔ {'زیرنویس' if mode == 'subtitle' else 'دوبله'}\n"
            f"{minutes} دقیقه · {price:,} تومان · اعتبار {days} روز از زمان خرید\n\n"
            "با تأیید، مبلغ از کیف پول کم می‌شود. در سفارش بعدی می‌توانی پرداخت از بسته را انتخاب کنی.",
            reply_markup=InlineKeyboardMarkup([[ui.button("✓ تأیید خرید", f"packs:buy:{token}", style="success")], [ui.button("‹ بازگشت", "packs:list")]]))
        return
    if action == "buy" and len(parts) == 3:
        quote = state.package_quotes.get(parts[2])
        if not quote or quote[0] != user.id:
            await query.answer("این پیشنهاد دیگر معتبر نیست.", show_alert=True)
            return
        state.package_quotes.pop(parts[2], None)
        _, mode, minutes, price, days = quote
        current = _parse_package_plan(await state.database.get_setting(f"plan_{mode}", "0"))
        if current != (minutes, price, days):
            await query.answer("مشخصات بسته تغییر کرده؛ دوباره فهرست بسته‌ها را باز کن.", show_alert=True)
            return
        result = await state.database.purchase_minutes(user.id, mode, minutes, price, days)
        if result != "purchased":
            await query.answer("موجودی کافی نیست یا بسته معتبر نیست.", show_alert=True)
            return
        await query.answer()
        await _edit_query_screen(query, f"✅ بستهٔ {minutes} دقیقه‌ای فعال شد؛ اعتبار {days} روز.",
                                      reply_markup=ui.back_keyboard("menu:services"))
        return
    await query.answer("گزینهٔ نامعتبر است.", show_alert=True)


async def team_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, message = update.effective_user, update.effective_message
    if not user or not message or message.chat.type != "private":
        return
    state = _state(context)
    await state.database.upsert_user(user, True)
    team = await state.database.team_info(user.id)
    if team:
        header = f"👥 تیم: {team['name']} · اعضا: {team['members']}/20\n"
        role = "مدیر" if team['owner_id'] == user.id else "عضو"
        header += f"نقش شما: {role}\n\n"
    else:
        header = "👥 هنوز عضو تیمی نیستی.\n\n"
    await _show_screen(update, header +
        "ساخت تیم: /team_create نام\n"
        "دعوت: /team_invite · پیوستن: /team_join کد\n"
        "خروج: /team_leave\n\n"
        "هر عضو کیف پول خودش را دارد.",
        reply_markup=ui.back_keyboard("menu:support" if update.callback_query else "menu:home"))


async def team_create(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, message = update.effective_user, update.effective_message
    if not user or not message or message.chat.type != "private":
        return
    state = _state(context)
    await state.database.upsert_user(user, True)
    name = " ".join(context.args).strip()
    if not name or len(name) > 120:
        await message.reply_text("نام تیم را بعد از دستور بنویس؛ حداکثر ۱۲۰ نویسه.")
        return
    team_id = await state.database.create_team(user.id, name)
    await message.reply_text("✅ تیم ساخته شد. برای دعوت /team_invite را بزن." if team_id else "شما هم‌اکنون عضو یک تیم هستی.")


async def team_invite(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, message = update.effective_user, update.effective_message
    if not user or not message or message.chat.type != "private":
        return
    token = await _state(context).database.create_team_invite(user.id)
    if not token:
        await message.reply_text("فقط مدیر تیم می‌تواند دعوت بسازد.")
        return
    await message.reply_text(f"🔗 کد دعوت یک‌بارمصرف تا ۴۸ ساعت معتبر است. آن را فقط به عضو موردنظر بده:\n\n/team_join {token}\n\nعضو با پیوستن می‌پذیرد آمار سفارش‌های بعدی‌اش برای مدیر تیم قابل مشاهده باشد.")


async def team_join(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, message = update.effective_user, update.effective_message
    if not user or not message or message.chat.type != "private":
        return
    state = _state(context)
    await state.database.upsert_user(user, True)
    token = context.args[0].strip() if context.args else ""
    if len(token) != 32 or any(c not in "0123456789abcdef" for c in token):
        await message.reply_text("کد دعوت معتبر را بعد از /team_join بفرست.")
        return
    invite = await state.database.preview_team_invite(token)
    if not invite:
        await message.reply_text("دعوت معتبر نیست یا منقضی شده است.")
        return
    await message.reply_text(
        f"👥 دعوت به تیم {invite['name']}\nمدیر: {invite['owner_id']}\n\n"
        "مدیر تعداد و مدت سفارش‌های آینده را می‌بیند. کیف پول و محتوای سفارش‌ها مستقل می‌مانند.",
        reply_markup=InlineKeyboardMarkup([
            [ui.button("✓ پذیرش دعوت", f"team:join:{token}", style="success")],
            [ui.button("‹ بازگشت", "menu:home")],
        ]))


async def team_join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query, user = update.callback_query, update.effective_user
    if not query or not user or not query.message or query.message.chat.type != "private":
        return
    token = (query.data or "").split(":")[-1]
    result = await _state(context).database.join_team(user.id, token)
    texts = {"joined": "✅ به تیم پیوستی. آمار سفارش‌های بعدی برای مدیر تیم قابل مشاهده است؛ کیف پول مستقل می‌ماند.",
             "member": "ابتدا از تیم فعلی خارج شو.", "full": "ظرفیت تیم کامل است.", "invalid": "دعوت معتبر نیست یا منقضی شده است."}
    await query.answer()
    await _edit_query_screen(query, texts[result], reply_markup=ui.back_keyboard())


async def team_remove(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, message = update.effective_user, update.effective_message
    if not user or not message or message.chat.type != "private":
        return
    try:
        target = int(context.args[0])
        if target <= 0:
            raise ValueError
    except (IndexError, ValueError):
        await message.reply_text("شناسهٔ عددی عضو را بفرست؛ نمونه: /team_remove 123456789")
        return
    removed = await _state(context).database.remove_team_member(user.id, target)
    await message.reply_text("عضو از تیم حذف شد." if removed else "عضو پیدا نشد یا شما مدیر تیم نیستی.")



async def team_leave(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, message = update.effective_user, update.effective_message
    if not user or not message or message.chat.type != "private":
        return
    result = await _state(context).database.leave_team(user.id)
    await message.reply_text({"left": "از تیم خارج شدی.", "missing": "عضو تیمی نیستی.", "owner": "مدیر تیم نمی‌تواند از تیم خودش خارج شود؛ برای مدیریت با پشتیبانی تماس بگیر."}[result])


async def team_glossary(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, message = update.effective_user, update.effective_message
    if not user or not message or message.chat.type != "private":
        return
    glossary = " ".join(context.args).strip()
    if not glossary or len(glossary) > 2000:
        await message.reply_text("واژه‌نامه را بعد از دستور بفرست؛ حداکثر ۲۰۰۰ نویسه. نمونه: /team_glossary cloud = رایانش ابری ؛ برای پاک‌کردن: /team_glossary -")
        return
    saved = await _state(context).database.set_team_glossary(user.id, "" if glossary == "-" else glossary)
    await message.reply_text("✅ واژه‌نامه برای سفارش‌های بعدی اعضا ذخیره شد." if saved else "فقط مدیر تیم می‌تواند واژه‌نامه را تغییر دهد.")


async def team_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, message = update.effective_user, update.effective_message
    if not user or not message or message.chat.type != "private":
        return
    rows = await _state(context).database.team_report(user.id)
    if rows is None:
        await message.reply_text("فقط مدیر تیم به گزارش دسترسی دارد.")
        return
    lines = ["📊 گزارش تیم · سفارش‌های موفق از زمان عضویت", ""]
    lines.extend(f"{row['user_id']}: {row['jobs']} سفارش · {row['minutes']} دقیقه" for row in rows)
    await message.reply_text("\n".join(lines))


async def _receive_image_reference(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, message = update.effective_user, update.effective_message
    state = _state(context)
    item = message.photo[-1] if message.photo else message.document
    if not item or not item.file_size or item.file_size > 10_000_000:
        await message.reply_text("یک تصویر PNG، JPEG یا WebP با حجم حداکثر ۱۰ مگابایت بفرست.")
        return
    try:
        file = await context.application.bot.get_file(item.file_id)
        data = bytes(await file.download_as_bytearray())
    except TelegramError:
        await message.reply_text("دریافت تصویر ممکن نشد؛ دوباره امتحان کن.")
        return
    media_type = image_generation.image_type(data)
    if not media_type or len(data) > 10_000_000:
        await message.reply_text("فایل باید یک تصویر PNG، JPEG یا WebP تا ۱۰ مگابایت باشد.")
        return
    state.image_references[user.id] = (data, media_type)
    if message.caption and message.caption.strip():
        await _receive_image_prompt(update, context, message.caption)
    else:
        await message.reply_text("✅ تصویر مرجع دریافت شد. حالا تغییر دلخواهت را توضیح بده؛ می‌توانی تصویر دیگری بفرستی تا جایگزین شود.")


async def _receive_image_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE, prompt_text: str | None = None) -> None:
    user, message = update.effective_user, update.effective_message
    state = _state(context)
    prompt = (prompt_text if prompt_text is not None else message.text or "").strip()
    if not 1 <= len(prompt) <= 3000:
        await message.reply_text("توضیح تصویر باید بین ۱ تا ۳۰۰۰ نویسه باشد.")
        return
    price_key = "image_edit_price" if user.id in state.image_references else "image_price"
    price = int(await state.database.get_setting(price_key, "0"))
    if price <= 0:
        state.awaiting_image_prompt.discard(user.id)
        state.image_references.pop(user.id, None)
        await message.reply_text("این نوع سرویس تصویر فعلاً فعال نیست.", reply_markup=ui.back_keyboard())
        return
    model = await image_generation.selected_model(state.database)
    optimizer = (await model_catalog.load_selection(state.database, state.settings, state.api_provider)).translation
    token = uuid.uuid4().hex[:12]
    reference = state.image_references.pop(user.id, None)
    state.image_quotes[str(user.id)] = {"token": token, "prompt": prompt, "price": price,
                                        "model": model, "optimizer": optimizer, "aspect": "1:1", "reference": reference}
    state.awaiting_image_prompt.discard(user.id)
    await message.reply_text(_image_quote_text(state.image_quotes[str(user.id)]), reply_markup=_image_quote_keyboard(token, "1:1"))


def _image_quote_text(quote: dict) -> str:
    labels = {"1:1": "مربع", "2:3": "عمودی", "3:2": "افقی"}
    return (f"🎨 {'ویرایش تصویر' if quote.get('reference') else 'ساخت تصویر'}\n"
            f"درخواست: {quote['prompt']}\n"
            f"ابعاد: {labels[quote['aspect']]} · هزینه: {quote['price']:,} تومان\n"
            "با تأیید، هزینه کم می‌شود و در صورت خطا برمی‌گردد.")


def _image_quote_keyboard(token: str, aspect: str) -> InlineKeyboardMarkup:
    choices = [("مربع", "1:1"), ("عمودی", "2:3"), ("افقی", "3:2")]
    return InlineKeyboardMarkup([
        [ui.button(("✓ " if value == aspect else "") + label, f"image:aspect:{token}:{value}") for label, value in choices],
        [ui.button("✓ تأیید و ساخت تصویر", f"image:buy:{token}", style="success")],
        [ui.button("✏️ تغییر توضیح", f"image:revise:{token}")],
        [ui.button("✕ لغو", f"image:cancel:{token}", style="danger")],
            [ui.button("‹ بازگشت به خدمات", "menu:services")],
    ])


async def image_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query, user = update.callback_query, update.effective_user
    if not query or not user or not query.message or query.message.chat.type != "private":
        return
    state = _state(context)
    parts = (query.data or "").split(":")
    action = parts[1] if len(parts) > 1 else ""
    if action == "start":
        if state.image_quotes.get(str(user.id), {}).get("confirming"):
            await query.answer("سفارش تصویر در حال ثبت است؛ چند لحظه صبر کن.", show_alert=True)
            return
        if user.id in state.active or user.id in state.pending_by_user:
            await query.answer("ابتدا سفارش فعال خود را تمام یا لغو کن.", show_alert=True)
            return
        if not await state.database.has_accepted_terms(user.id):
            await query.answer("ابتدا شرایط استفاده را بپذیر.", show_alert=True)
            await _edit_query_screen(query, "برای استفاده، شرایط را بخوان و بپذیر.", reply_markup=InlineKeyboardMarkup([
                [ui.button("📜 شرایط استفاده", "terms:show", style="primary")],
                [ui.button("‹ بازگشت", "menu:services")],
            ]))
            return
        if (int(await state.database.get_setting("image_price", "0")) <= 0
                and int(await state.database.get_setting("image_edit_price", "0")) <= 0):
            await query.answer("این سرویس هنوز فعال نشده است.", show_alert=True)
            return
        state.awaiting_support.discard(user.id)
        state.awaiting_topup.discard(user.id)
        state.subtitle_editing.pop(user.id, None)
        state.image_quotes.pop(str(user.id), None)
        state.image_references.pop(user.id, None)
        state.awaiting_image_prompt.add(user.id)
        await query.answer()
        await _edit_query_screen(query, "🎨 ساخت تصویر\nمتن تصویر را بفرست. برای ویرایش، عکس را بفرست و بعد تغییر موردنظر را بنویس.\nقیمت را پیش از تأیید می‌بینی.",
                                      reply_markup=ui.back_keyboard("menu:services"))
        return
    if action == "history":
        state.awaiting_image_prompt.discard(user.id)
        state.image_references.pop(user.id, None)
        try:
            page = max(0, min(10000, int(parts[2]))) if len(parts) == 3 else 0
        except ValueError:
            await query.answer("صفحه نامعتبر است.", show_alert=True)
            return
        rows = await state.database.list_image_orders(user.id, page * 5, 6)
        buttons = [[ui.button(f"🖼 {row['id'][:8]} · {row['created_at']:%Y-%m-%d} · {row['status']}", f"image:get:{row['id']}")] for row in rows[:5] if row["status"] == "completed"]
        navigation = []
        if page:
            navigation.append(ui.button("‹ قبلی", f"image:history:{page - 1}"))
        if len(rows) > 5:
            navigation.append(ui.button("بعدی ›", f"image:history:{page + 1}"))
        if navigation:
            buttons.append(navigation)
        buttons.append([ui.button("‹ بازگشت", "orders:home")])
        await query.answer()
        labels = {"queued": "در صف", "completed": "آماده", "refunded": "ناموفق، بازپرداخت‌شده"}
        listing = "\n".join(f"• {row['id'][:8]} · {labels.get(row['status'], row['status'])} · {row['amount']:,} تومان" for row in rows[:5])
        await _edit_query_screen(query, ("🖼 سفارش‌های تصویر\n\n" + listing + "\n\nبرای دریافت تصویر آماده دکمهٔ آن را بزن.") if rows else "🖼 در این صفحه سفارشی وجود ندارد.", reply_markup=InlineKeyboardMarkup(buttons))
        return
    if action == "remix" and len(parts) == 3:
        if user.id in state.active or user.id in state.pending_by_user or state.image_quotes.get(str(user.id), {}).get("confirming"):
            await query.answer("ابتدا سفارش فعال را تمام یا لغو کن.", show_alert=True)
            return
        if int(await state.database.get_setting("image_edit_price", "0")) <= 0:
            await query.answer("ویرایش تصویر فعلاً فعال نیست.", show_alert=True)
            return
        saved = await state.database.owned_image(user.id, parts[2])
        if not saved or len(saved["image"]) > 10_000_000:
            await query.answer("تصویر پیدا نشد یا برای ویرایش بیش از ۱۰ مگابایت است.", show_alert=True)
            return
        state.awaiting_support.discard(user.id)
        state.awaiting_topup.discard(user.id)
        state.subtitle_editing.pop(user.id, None)
        state.image_quotes.pop(str(user.id), None)
        state.image_references[user.id] = (saved["image"], saved["media_type"])
        state.awaiting_image_prompt.add(user.id)
        await query.answer()
        await _edit_query_screen(query, "🖌 تغییر موردنظرت را بنویس. قیمت را پیش از تأیید می‌بینی.",
                                      reply_markup=ui.back_keyboard("orders:home"))
        return
    if action == "get" and len(parts) == 3:
        saved = await state.database.owned_image(user.id, parts[2])
        if not saved:
            await query.answer("تصویر در دسترس نیست.", show_alert=True)
            return
        await query.answer()
        await _send_generated_image(context.application, user.id, saved["image"], saved["media_type"], parts[2])
        await _edit_query_screen(query, "✅ تصویر ارسال شد.", reply_markup=ui.back_keyboard("image:history:0"))
        return
    quote = state.image_quotes.get(str(user.id))
    if len(parts) < 3 or not quote or quote["token"] != parts[2] or quote.get("confirming"):
        await query.answer("این سفارش دیگر معتبر نیست.", show_alert=True)
        return
    if action == "cancel":
        state.image_quotes.pop(str(user.id), None)
        await query.answer()
        await _edit_query_screen(query, "سفارش تصویر لغو شد.", reply_markup=ui.back_keyboard("menu:services"))
        return
    if action == "revise":
        reference = quote.get("reference")
        state.image_quotes.pop(str(user.id), None)
        if reference:
            state.image_references[user.id] = reference
        state.awaiting_image_prompt.add(user.id)
        await query.answer()
        await _edit_query_screen(query, "✏️ توضیح جدید را بفرست.", reply_markup=ui.back_keyboard("menu:services"))
        return
    if action == "aspect" and len(parts) == 5 and ":".join(parts[3:]) in {"1:1", "2:3", "3:2"}:
        quote["aspect"] = ":".join(parts[3:])
        await query.answer()
        await _edit_query_screen(query, _image_quote_text(quote), reply_markup=_image_quote_keyboard(parts[2], quote["aspect"]))
        return
    if action != "buy" or len(parts) != 3:
        await query.answer("انتخاب معتبر نیست.", show_alert=True)
        return
    if user.id in state.active or user.id in state.pending_by_user:
        await query.answer("ابتدا سفارش فعال خود را تمام یا لغو کن.", show_alert=True)
        return
    quote["confirming"] = True
    try:
        price_key = "image_edit_price" if quote["reference"] else "image_price"
        if (int(await state.database.get_setting(price_key, "0")) != quote["price"]
                or await image_generation.selected_model(state.database) != quote["model"]):
            state.image_quotes.pop(str(user.id), None)
            await query.answer("تنظیم سرویس تغییر کرده؛ دوباره سفارش بده.", show_alert=True)
            return
        model, optimizer = quote["model"], quote["optimizer"]
        for provider in {model.provider, optimizer.provider}:
            if not (state.settings.openai_api_key if provider == "openai" else state.settings.openrouter_api_key):
                await query.answer("سرویس تصویر یا بهینه‌سازی فعلاً در دسترس نیست.", show_alert=True)
                return
        order_id = uuid.uuid4().hex
        reference, reference_type = quote["reference"] or (None, None)
        result = await state.database.create_image_order(order_id, user.id, query.message.chat_id,
            quote["prompt"], quote["aspect"], model.provider, model.model, optimizer.provider, optimizer.model, quote["price"], reference, reference_type)
        if result != "created":
            await query.answer("موجودی کافی نیست؛ ابتدا کیف پول را شارژ کن.", show_alert=True)
            return
        state.image_quotes.pop(str(user.id), None)
        job = ImageJob(order_id, user.id, query.message.chat_id, query.message.message_id,
                       quote["prompt"], quote["aspect"], model, optimizer, reference, reference_type)
        state.active[user.id] = job
        await state.queue.put(job)
        await query.answer("سفارش ثبت شد.")
        await _edit_query_screen(query, "🎨 سفارش تصویر در صف قرار گرفت.", reply_markup=ui.job_keyboard(job.id))
    finally:
        quote["confirming"] = False


async def _send_generated_image(application, chat_id: int, data: bytes, media_type: str, order_id: str) -> None:
    ext = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}.get(media_type, "png")
    document = BytesIO(data)
    document.name = f"image-{order_id[:8]}.{ext}"
    await application.bot.send_document(chat_id, document, caption=f"🎨 تصویر سفارش {order_id[:8]} · فایل با کیفیت اصلی",
        reply_markup=InlineKeyboardMarkup([[ui.button("🖌 ویرایش این تصویر", f"image:remix:{order_id}", style="primary")],
                                           [ui.button("🖼 تصاویر من", "image:history:0")],
                                           [ui.button("‹ بازگشت", "orders:home")]]))


async def _run_image_job(application: Application, state: BotState, job: ImageJob) -> None:
    completed = False
    try:
        if job.cancel_event.is_set():
            raise JobCancelled()
        await _safe_progress(application, job, "✨ در حال بهینه‌سازی توضیح تصویر…", interactive=True)
        optimized, prompt_cost = await asyncio.to_thread(image_generation.optimize_prompt, job.prompt, state.settings, job.optimizer, job.reference, job.reference_type)
        if not await state.database.set_image_prompt(job.id, optimized, prompt_cost):
            raise RuntimeError("Image order is no longer pending")
        if job.cancel_event.is_set():
            raise JobCancelled()
        await _safe_progress(application, job, "🎨 در حال ساخت تصویر… ممکن است چند دقیقه طول بکشد.", interactive=True)
        data, media_type, image_cost = await asyncio.to_thread(image_generation.generate_image, optimized, job.prompt, job.aspect, state.settings, job.model, job.reference, job.reference_type)
        if job.cancel_event.is_set():
            raise JobCancelled()
        job.delivery_started = True
        if not await state.database.finish_image_order(job.id, data, media_type, image_cost):
            raise RuntimeError("Image order could not be completed")
        completed = True
        await _send_generated_image(application, job.chat_id, data, media_type, job.id)
        await _safe_progress(application, job, "✅ تصویر آماده شد؛ از بخش تصاویر من هم می‌توانی دوباره دریافتش کنی.")
    except Exception:
        logger.exception("Image order %s failed", job.id)
        if completed:
            await _safe_progress(application, job, "تصویر ساخته و ذخیره شد، اما ارسال ناموفق بود. از بخش تصاویر من دوباره دریافتش کن.")
        else:
            try:
                refunded = await state.database.refund_image_order(job.id)
            except Exception:
                logger.exception("Could not refund image order %s", job.id)
                refunded = False
            await _safe_progress(application, job, "ساخت تصویر کامل نشد. " + ("هزینه به کیف پول برگشت." if refunded else "برای پیگیری با پشتیبانی تماس بگیر."))
    finally:
        state.active.pop(job.user_id, None)
        state.queue.task_done()


async def content_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query, user = update.callback_query, update.effective_user
    if not query or not user or not query.message or query.message.chat.type != "private":
        return
    state = _state(context)
    parts = (query.data or "").split(":")
    action = parts[1] if len(parts) > 1 else ""
    if action == "list":
        rows = await state.database.recent_completed_jobs(user.id)
        await query.answer()
        if not rows:
            await _edit_query_screen(query, "هنوز سفارش تکمیل‌شده‌ای نداری.", reply_markup=ui.back_keyboard("menu:services"))
            return
        buttons = [[ui.button(f"{'دوبله' if row['mode'] == 'dub' else 'زیرنویس'} · {row['id'][:8]} · {row['created_at']:%Y-%m-%d}",
                               f"content:job:{row['id']}")] for row in rows]
        buttons.append([ui.button("‹ بازگشت", "menu:services")])
        await _edit_query_screen(query, "📝 سفارش را انتخاب کن:", reply_markup=InlineKeyboardMarkup(buttons))
        return
    if action == "job" and len(parts) == 3:
        state.subtitle_editing.pop(user.id, None)
        job_id = parts[2]
        if not await state.database.owned_subtitle(job_id, user.id):
            await query.answer("سفارش پیدا نشد.", show_alert=True)
            return
        results = await state.database.content_results(user.id, job_id)
        buttons = [
            [ui.button("📚 خلاصه و جزوه", f"content:quote:summary:{job_id}"),
             ui.button("📣 بستهٔ تولید محتوا", f"content:quote:social:{job_id}")],
            [ui.button("✏️ ویرایش زیرنویس", f"content:edit:{job_id}")],
        ]
        for result in results:
            label = "جزوه" if result['kind'] == "summary" else "بستهٔ محتوا"
            buttons.append([ui.button(f"⬇️ دریافت دوبارهٔ {label} · {result['created_at']:%Y-%m-%d}", f"content:result:{result['id']}")])
        buttons.append([ui.button("‹ سفارش‌ها", "content:list")])
        await query.answer()
        await _edit_query_screen(query, f"📝 خروجی‌های سفارش {job_id[:8]}\n\nیکی از گزینه‌ها را انتخاب کن.",
                                      reply_markup=InlineKeyboardMarkup(buttons))
        return
    if action == "result" and len(parts) == 3:
        saved = await state.database.owned_content_result(user.id, parts[2])
        if not saved:
            await query.answer("فایل پیدا نشد.", show_alert=True)
            return
        data = BytesIO(saved["text"].encode("utf-8"))
        data.name = "summary-fa.txt" if saved["kind"] == "summary" else "content-pack-fa.txt"
        await query.answer()
        await query.message.reply_document(data, caption="خروجی ذخیره‌شدهٔ سفارش شما",
            reply_markup=InlineKeyboardMarkup([[ui.button("‹ بازگشت", "content:list")]]))
        await _edit_query_screen(query, "✅ فایل خروجی ارسال شد.", reply_markup=ui.back_keyboard("content:list"))
        return
    if action == "edit" and len(parts) == 3:
        job_id = parts[2]
        subtitle = await state.database.owned_subtitle(job_id, user.id)
        if not subtitle:
            await query.answer("سفارش پیدا نشد.", show_alert=True)
            return
        state.subtitle_editing[user.id] = job_id
        data = BytesIO(subtitle.encode("utf-8")); data.name = "fa.srt"
        await query.answer()
        await query.message.reply_document(data,
            caption="فایل فعلی را ببین و اصلاح را با شمارهٔ بخش و متن جدید بفرست. نمونه: 12 متن اصلاح‌شده",
            reply_markup=InlineKeyboardMarkup([[ui.button("‹ بازگشت", f"content:job:{job_id}")]]))
        await _edit_query_screen(query, "📎 فایل زیرنویس ارسال شد. شمارهٔ بخش و متن جدید را بفرست.",
                                 reply_markup=ui.back_keyboard(f"content:job:{job_id}"))
        return
    if action == "quote" and len(parts) == 4 and parts[2] in {"summary", "social"}:
        kind, job_id = parts[2], parts[3]
        if not await state.database.owned_subtitle(job_id, user.id):
            await query.answer("سفارش پیدا نشد.", show_alert=True)
            return
        price = max(0, int(await state.database.get_setting(f"content_price_{kind}", "0")))
        if not price:
            await query.answer("این سرویس هنوز فعال نشده است.", show_alert=True)
            return
        token = uuid.uuid4().hex[:12]
        state.content_quotes[token] = (user.id, job_id, kind, price)
        label = "خلاصه و جزوه" if kind == "summary" else "بستهٔ تولید محتوا"
        await query.answer()
        await _edit_query_screen(query, f"🧾 {label}\nهزینه: {price:,} تومان\n\nبا تأیید، هزینه از کیف پول کم می‌شود؛ در صورت خطا بازگردانده می‌شود.",
            reply_markup=InlineKeyboardMarkup([[ui.button("✓ تأیید و شروع", f"content:buy:{token}", style="success")], [ui.button("‹ بازگشت", f"content:job:{job_id}")]]))
        return
    if action == "buy" and len(parts) == 3:
        quote = state.content_quotes.get(parts[2])
        if not quote or quote[0] != user.id:
            await query.answer("این سفارش منقضی شده است.", show_alert=True)
            return
        if user.id in state.active or user.id in state.pending_by_user:
            await query.answer("ابتدا سفارش فعال خود را تمام یا لغو کن.", show_alert=True)
            return
        state.content_quotes.pop(parts[2], None)
        _, job_id, kind, price = quote
        if int(await state.database.get_setting(f"content_price_{kind}", "0")) != price:
            await query.answer("قیمت سرویس تغییر کرده؛ دوباره سفارش را باز کن.", show_alert=True)
            return
        subtitle = await state.database.owned_subtitle(job_id, user.id)
        if not subtitle:
            await query.answer("سفارش پیدا نشد.", show_alert=True)
            return
        models = await model_catalog.load_selection(state.database, state.settings, state.api_provider)
        key = state.settings.openai_api_key if models.translation.provider == "openai" else state.settings.openrouter_api_key
        if not key:
            await query.answer("مدل ترجمه در دسترس نیست.", show_alert=True)
            return
        order_id = uuid.uuid4().hex
        status = await state.database.create_content_order(order_id, user.id, job_id, query.message.chat_id, kind, price)
        if status != "created":
            await query.answer("موجودی کافی نیست یا سفارش در دسترس نیست.", show_alert=True)
            return
        job = ContentJob(order_id, user.id, query.message.chat_id, query.message.message_id, subtitle, kind, models)
        state.active[user.id] = job
        await state.queue.put(job)
        try:
            await query.answer()
            await _edit_query_screen(query, "📝 درخواست ثبت شد و در صف پردازش است.",
                                     reply_markup=ui.job_keyboard(job.id))
        except TelegramError:
            logger.exception("Could not acknowledge content order %s", order_id)
        return
    await query.answer("این گزینه دیگر در دسترس نیست.", show_alert=True)


async def _receive_subtitle_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, message = update.effective_user, update.effective_message
    if not user or not message or message.chat.type != "private":
        return
    state = _state(context)
    job_id = state.subtitle_editing.get(user.id)
    old = await state.database.owned_subtitle(job_id, user.id)
    if not old:
        state.subtitle_editing.pop(user.id, None)
        await message.reply_text("سفارش پیدا نشد.")
        return
    try:
        raw_number, replacement = message.text.strip().split(maxsplit=1)
        changed = edit_subtitle_line(old, int(raw_number), replacement)
    except ValueError as exc:
        await message.reply_text(f"ورودی معتبر نیست: {exc}\nنمونه: 12 متن اصلاح‌شده")
        return
    if not await state.database.replace_subtitle(job_id, user.id, old, changed):
        await message.reply_text("زیرنویس هم‌زمان تغییر کرد؛ دوباره تلاش کن.")
        return
    state.subtitle_editing.pop(user.id, None)
    data = BytesIO(changed.encode("utf-8")); data.name = "fa-edited.srt"
    await message.reply_document(data, caption="✅ فایل SRT اصلاح شد. ویدیوی قبلی و زیرنویس پلیر قبلی خودکار تغییر نمی‌کنند.")


async def _run_content_job(application: Application, state: BotState, job: ContentJob) -> None:
    try:
        if job.cancel_event.is_set():
            raise JobCancelled()
        await _safe_progress(application, job, "📝 در حال تولید محتوای تکمیلی…")
        result, api_cost_usd = await asyncio.to_thread(generate_content, job.subtitle, job.kind, state.settings, job.models, job.cancel_event)
        if job.cancel_event.is_set():
            raise JobCancelled()
        document = BytesIO(result.encode("utf-8")); document.name = "summary-fa.txt" if job.kind == "summary" else "content-pack-fa.txt"
        await application.bot.send_document(job.chat_id, document, caption="✅ محتوای تولیدشده آماده است؛ پیش از انتشار بررسی‌اش کن.")
        if not await state.database.finish_content_order(job.id, result, api_cost_usd):
            raise RuntimeError("Content order status changed before completion")
        await _safe_progress(application, job, "✅ محتوای تکمیلی ارسال شد.")
    except Exception:
        logger.exception("Content order %s did not complete", job.id)
        try:
            refunded = await state.database.refund_content_order(job.id)
        except Exception:
            refunded = False
            logger.exception("Could not refund content order %s", job.id)
        await _safe_progress(application, job, "پردازش کامل نشد. " + ("هزینه به کیف پول برگشت." if refunded else "برای پیگیری با پشتیبانی تماس بگیر."))
    finally:
        state.active.pop(job.user_id, None)
        state.queue.task_done()


async def _run_download_job(application: Application, state: BotState, job: DownloadJob) -> None:
    try:
        if job.cancel_event.is_set():
            raise JobCancelled()
        await state.database.update_download_task(job.id, "running")
        url = job.url
        if job.source == "spotify":
            await _safe_progress(application, job, "🔎 جست‌وجوی نسخهٔ مشابه در YouTube…")
            url, title = await asyncio.to_thread(resolve_spotify_track, url, state.settings)
            await _safe_progress(application, job, f"🎵 نسخهٔ پیدا شده: {title}\nدر حال دریافت از YouTube…")
        elif is_instagram_media_url(url):
            await _safe_progress(application, job, "🔎 در حال تشخیص خودکار نوع مدیای اینستاگرام و دریافت آن…")
        else:
            await _safe_progress(application, job, "📥 در حال دریافت فایل…")
        if job.cancel_event.is_set():
            raise JobCancelled()
        output, title = await asyncio.to_thread(download_media, url, job.kind, job.directory, state.settings, job.cancel_event)
        if job.cancel_event.is_set():
            raise JobCancelled()
        token, suffix, expires_at = None, None, None
        output_extension = output.suffix.lower().removeprefix(".")
        media_label = {
            "mp4": "🎬 ویدیوی اینستاگرام",
            "zip": "📦 مجموعهٔ مدیاهای اینستاگرام",
            "jpg": "🖼 عکس اینستاگرام",
            "jpeg": "🖼 عکس اینستاگرام",
            "png": "🖼 عکس اینستاگرام",
            "webp": "🖼 عکس اینستاگرام",
            "avif": "🖼 عکس اینستاگرام",
        }.get(output_extension, "📥 مدیای اینستاگرام") if job.kind == "media" else ""
        caption_prefix = f"{media_label}\n" if media_label else ""
        caption = f"{caption_prefix}✅ {title}" + ("\nنسخهٔ یافت‌شده در YouTube؛ ممکن است با نسخهٔ Spotify متفاوت باشد." if job.source == "spotify" else "")
        if output.stat().st_size <= 48_000_000:
            with output.open('rb') as media:
                if output_extension == "mp3":
                    await application.bot.send_audio(job.chat_id, media, caption=caption, read_timeout=120, write_timeout=120)
                elif output_extension == "mp4":
                    await application.bot.send_video(job.chat_id, media, caption=caption, supports_streaming=True, read_timeout=120, write_timeout=120)
                else:
                    await application.bot.send_document(job.chat_id, media, filename=output.name, caption=caption, read_timeout=120, write_timeout=120)
        elif state.settings.download_base_url:
            suffix = output_extension
            token = await asyncio.to_thread(publish_download, output, Path(state.settings.download_dir), state.settings.download_ttl_hours, suffix=suffix)
            link = f"{state.settings.download_base_url}/{token}.{suffix}"
            expires_at = datetime.now(UTC) + timedelta(hours=state.settings.download_ttl_hours)
            await application.bot.send_message(job.chat_id,
                f"{caption}\nلینک تا {state.settings.download_ttl_hours} ساعت فعال است.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬇️ دریافت فایل", url=link, style="primary")]]))
        else:
            await state.database.update_download_task(job.id, "failed")
            await _safe_progress(application, job, "فایل از سقف ارسال تلگرام بزرگ‌تر است و لینک دانلود روی سرور تنظیم نشده. با پشتیبانی تماس بگیر.")
            return
        await state.database.update_download_task(job.id, "completed", title=title, token=token,
                                                  extension=suffix, expires_at=expires_at)
        await _safe_progress(application, job, "✅ فایل آماده و ارسال شد.")
    except JobCancelled:
        try:
            await state.database.update_download_task(job.id, "cancelled")
        except Exception:
            logger.exception("Could not persist cancelled download %s", job.id)
        await _safe_progress(application, job, "دانلود لغو شد.")
    except Exception:
        logger.exception("Download failed for job %s", job.id)
        try:
            await state.database.update_download_task(job.id, "failed")
        except Exception:
            logger.exception("Could not persist failed download %s", job.id)
        await _safe_progress(application, job, "دانلود انجام نشد. لینک ممکن است خصوصی، منقضی یا به‌دلیل تغییرات اینستاگرام موقتاً غیرقابل‌دسترسی باشد؛ دوباره تلاش کن.")
    finally:
        cleanup(job.directory)
        state.active.pop(job.user_id, None)
        state.queue.task_done()


async def worker(application: Application) -> None:
    state: BotState = application.bot_data["state"]
    while True:
        try:
            job = await asyncio.wait_for(state.queue.get(), timeout=3600)
        except TimeoutError:
            await asyncio.to_thread(
                cleanup_expired_downloads,
                Path(state.settings.download_dir),
                state.settings.download_ttl_hours,
            )
            continue
        if job is None:
            state.queue.task_done()
            return
        if isinstance(job, DownloadJob):
            await _run_download_job(application, state, job)
            continue
        if isinstance(job, ContentJob):
            await _run_content_job(application, state, job)
            continue
        if isinstance(job, ImageJob):
            await _run_image_job(application, state, job)
            continue
        progress_queue: asyncio.Queue[tuple[str, int] | None] | None = None
        progress_task: asyncio.Task | None = None
        progress_stopped = False

        async def stop_progress_updates() -> None:
            nonlocal progress_stopped
            if progress_queue is None or progress_task is None or progress_stopped:
                return
            await asyncio.sleep(0)
            progress_queue.put_nowait(None)
            await progress_task
            progress_stopped = True

        try:
            if job.cancel_event.is_set():
                raise JobCancelled()
            logger.info(
                "Starting job %s for Telegram user %s with provider %s",
                job.id,
                job.user_id,
                job.api_provider,
            )
            await state.database.update_job(job.id, "running")
            progress_queue = asyncio.Queue()
            loop = asyncio.get_running_loop()

            def report_progress(stage: str, percent: int) -> None:
                loop.call_soon_threadsafe(progress_queue.put_nowait, (stage, percent))

            progress_task = asyncio.create_task(_progress_updater(application, job, progress_queue))
            await _publish_progress(application, job, "دانلود ویدیو", 0)
            original_audio_percent = 10
            if job.mode == "dub":
                original_audio_percent = _bounded_percent(
                    await state.database.get_setting("dub_original_audio_percent", "10")
                )
            output, srt, vtt, costs = await asyncio.to_thread(
                process_video,
                job.url,
                job.directory,
                state.settings,
                job.cancel_event,
                job.selected_height,
                report_progress,
                job.mode,
                job.api_provider,
                job.models,
                job.team_glossary,
                job.dub_mode,
                original_audio_percent,
            )
            subtitle_text = srt.read_text(encoding="utf-8")
            if job.cancel_event.is_set():
                raise JobCancelled()
            await stop_progress_updates()
            if job.cancel_event.is_set():
                raise JobCancelled()
            job.delivery_started = True
            await _publish_progress(application, job, "ارسال ویدیو", 95)
            receipt = _receipt_text(job)
            completion_note = "پردازش کامل شد؛ ویدیوی آماده ارسال شد."
            if (
                job.mode == "subtitle"
                and not state.settings.watermark_text
                and state.settings.download_base_url
            ):
                await stop_progress_updates()
                player_url = await _publish_subtitle_player_link(
                    application, job, output, srt, vtt, state.settings, state.database
                )
                await state.database.update_job(
                    job.id, "completed", size=output.stat().st_size,
                    subtitle=subtitle_text, cost_usd=costs.total_usd,
                )
                await _send_srt(application, job, srt)
                await _notify_admin_cost(application, state, job, costs)
                await _finish_progress(
                    application,
                    job,
                    f"ویدیو و زیرنویس آماده شد؛ ویدیو بدون رندر دوباره منتشر شده است.\n"
                    f"▶️ پخش با زیرنویس روشن/خاموش: {player_url}\n\n{receipt}",
                    complete=True,
                )
                continue
            if output.stat().st_size > 48_000_000:
                if state.settings.download_base_url:
                    await stop_progress_updates()
                    await _send_download_link(
                        application, job, output, srt, state.settings, state.database,
                        include_srt=job.mode == "subtitle",
                    )
                    await application.bot.delete_message(job.chat_id, job.message_id)
                    await application.bot.send_message(job.chat_id, receipt)
                else:
                    if job.mode == "subtitle":
                        await _send_srt(application, job, srt)
                    await stop_progress_updates()
                    refunded = await _refund_job(application, state, job)
                    await state.database.update_job(job.id, "failed", error="Output exceeds Telegram limit and no download host is configured.")
                    refund_note = _job_refund_note(job, refunded)
                    await _finish_progress(
                        application, job,
                        f"فایل برای ارسال مستقیم بزرگ است و لینک دانلود تنظیم نشده. {refund_note}",
                    )
                    continue
                await state.database.update_job(
                    job.id, "completed", size=output.stat().st_size,
                    subtitle=subtitle_text, cost_usd=costs.total_usd,
                )
                await _notify_admin_cost(application, state, job, costs)
                if not state.settings.download_base_url:
                    await _finish_progress(
                        application, job, completion_note + "\n\n" + receipt, complete=True
                    )
                continue
            try:
                with output.open("rb") as video_file:
                    await application.bot.send_chat_action(job.chat_id, ChatAction.UPLOAD_VIDEO)
                    await application.bot.send_video(
                        chat_id=job.chat_id,
                        video=video_file,
                        supports_streaming=True,
                        caption=(
                            "ویدیو با دوبلهٔ فارسی؛ صدای اصلی در پس‌زمینه حفظ شده و ممکن است دیالوگ اصلی هم شنیده شود."
                            if job.mode == "dub"
                            else "ویدیو با زیرنویس فارسی"
                        ),
                        read_timeout=120,
                        write_timeout=120,
                        connect_timeout=30,
                    )
            except NetworkError as exc:
                if "request entity too large" not in str(exc).lower():
                    raise
                if state.settings.download_base_url:
                    await stop_progress_updates()
                    await _send_download_link(
                        application, job, output, srt, state.settings, state.database,
                        include_srt=job.mode == "subtitle",
                    )
                    await application.bot.delete_message(job.chat_id, job.message_id)
                    await application.bot.send_message(job.chat_id, receipt)
                else:
                    if job.mode == "subtitle":
                        await _send_srt(application, job, srt)
                    await stop_progress_updates()
                    refunded = await _refund_job(application, state, job)
                    await state.database.update_job(job.id, "failed", error="Telegram rejected output size and no download host is configured.")
                    refund_note = _job_refund_note(job, refunded)
                    await _finish_progress(
                        application, job,
                        f"تلگرام ارسال ویدیو را نپذیرفت و لینک دانلود تنظیم نشده. {refund_note}",
                    )
                    continue
                await state.database.update_job(
                    job.id, "completed", size=output.stat().st_size,
                    subtitle=subtitle_text, cost_usd=costs.total_usd,
                )
                await _notify_admin_cost(application, state, job, costs)
                if not state.settings.download_base_url:
                    await _finish_progress(
                        application, job, completion_note + "\n\n" + receipt, complete=True
                    )
                continue
            if job.mode == "subtitle":
                await _send_srt(application, job, srt)
            await stop_progress_updates()
            await state.database.update_job(
                job.id, "completed", size=output.stat().st_size,
                subtitle=subtitle_text, cost_usd=costs.total_usd,
            )
            await _notify_admin_cost(application, state, job, costs)
            await _finish_progress(
                application,
                job,
                completion_note
                + "\n\n" + receipt,
                complete=True,
            )
        except JobCancelled:
            await stop_progress_updates()
            refunded = await _refund_job(application, state, job)
            await state.database.update_job(job.id, "cancelled")
            refund_note = _job_refund_note(job, refunded)
            await _finish_progress(application, job, f"پردازش لغو شد.\n{refund_note}")
        except RateLimitError as exc:
            provider = "سرویس پردازش"
            detail = str(exc).replace("\n", " ")[:600]
            logger.warning(
                "%s returned HTTP 429 for job %s, Telegram user %s: %s",
                provider,
                job.id,
                job.user_id,
                detail,
            )
            await stop_progress_updates()
            refunded = await _refund_job(application, state, job)
            try:
                await state.database.update_job(
                    job.id,
                    "failed",
                    error=f"{provider} returned HTTP 429: {detail}",
                )
            except Exception:
                logger.exception("Could not persist rate-limit failure for job %s", job.id)
            error_text = "یکی از سرویس‌های پردازش به محدودیت درخواست رسیده است؛ لطفاً کمی بعد دوباره تلاش کن."
            await _finish_progress(
                application,
                job,
                error_text + "\n" + _job_refund_note(job, refunded),
            )
        except Exception:
            logger.exception("Job failed for Telegram user %s", job.user_id)
            await stop_progress_updates()
            refunded = await _refund_job(application, state, job)
            try:
                await state.database.update_job(job.id, "failed", error="Job failed; see bot logs for details.")
            except Exception:
                logger.exception("Could not persist failure status for job %s", job.id)
            refund_note = _job_refund_note(job, refunded)
            await _finish_progress(application, job, f"پردازش انجام نشد.\n{refund_note} لطفاً کمی بعد دوباره تلاش کن.")
        finally:
            await stop_progress_updates()
            cleanup(job.directory)
            state.active.pop(job.user_id, None)
            state.queue.task_done()


async def _safe_progress(application: Application, job: Job, text: str, *, interactive: bool = False) -> bool:
    try:
        await application.bot.edit_message_text(text, job.chat_id, job.message_id,
                                                reply_markup=ui.job_keyboard(job.id, cancellable=not job.delivery_started) if interactive else None)
        return True
    except Exception:
        logger.debug("Could not update job progress", exc_info=True)
        return False


def _progress_text(stage: str, percent: int) -> str:
    percent = max(0, min(100, percent))
    filled = percent // 10
    bar = "▰" * filled + "▱" * (10 - filled)
    return f"{'✅' if percent == 100 else '⏳'} {stage}\n{bar} {percent}%"


async def _publish_progress(application: Application, job: Job, stage: str, percent: int) -> None:
    job.progress_percent = max(job.progress_percent, min(99, max(0, percent)))
    job.progress_stage = stage
    text = _progress_text(stage, job.progress_percent) + "\nدرصد تقریبی است."
    now = asyncio.get_running_loop().time()
    if text != job.progress_last_text and (job.delivery_started or now - job.progress_last_edit >= 5 or not job.progress_last_text):
        if await _safe_progress(application, job, text, interactive=True):
            job.progress_last_edit = now
            job.progress_last_text = text
    if job.can_use_draft:
        draft_sender = getattr(application.bot, "send_message_draft", None)
        if callable(draft_sender):
            try:
                await draft_sender(
                    chat_id=job.chat_id,
                    draft_id=job.draft_id,
                    text=text,
                )
                job.draft_was_used = True
                return
            except TelegramError as exc:
                # Fall back to the durable status message if Telegram rejects a draft.
                logger.debug("Telegram live draft unavailable (%s)", type(exc).__name__)
        job.can_use_draft = False
    if text != job.progress_last_text:
        if await _safe_progress(application, job, text, interactive=True):
            job.progress_last_edit = now
            job.progress_last_text = text


async def _progress_updater(
    application: Application,
    job: Job,
    updates: asyncio.Queue[tuple[str, int] | None],
) -> None:
    latest = ("دانلود ویدیو", 0)
    last_sent = 0.0
    while True:
        try:
            update = await asyncio.wait_for(updates.get(), timeout=10)
        except TimeoutError:
            await _publish_progress(application, job, *latest)
            last_sent = asyncio.get_running_loop().time()
            continue
        if update is None:
            return
        latest = update
        stopped = False
        while not updates.empty():
            update = updates.get_nowait()
            if update is None:
                stopped = True
                break
            latest = update
        delay = 1.2 - (asyncio.get_running_loop().time() - last_sent)
        if delay > 0:
            await asyncio.sleep(delay)
        await _publish_progress(application, job, *latest)
        last_sent = asyncio.get_running_loop().time()
        if stopped:
            return


async def _finish_progress(
    application: Application, job: Job, message: str, *, complete: bool = False
) -> None:
    text = _progress_text(message, 100) if complete else message
    if job.draft_was_used:
        try:
            # sendMessage turns Telegram's temporary live draft into a regular
            # chat message, as required by the Bot API.
            await application.bot.send_message(chat_id=job.chat_id, text=text)
            job.draft_was_used = False
            try:
                await application.bot.delete_message(job.chat_id, job.message_id)
            except TelegramError:
                logger.debug("Could not remove old progress message", exc_info=True)
            return
        except TelegramError as exc:
            logger.debug("Could not finalize Telegram live draft (%s)", type(exc).__name__)
    await _safe_progress(application, job, text)


async def _safe_edit(application: Application, selection: PendingQuality, text: str) -> None:
    try:
        await application.bot.edit_message_text(text, selection.chat_id, selection.message_id)
    except Exception:
        logger.debug("Could not update quality selection", exc_info=True)


def _job_refund_note(job: Job, refunded: bool) -> str:
    if refunded:
        return "دقیقهٔ مصرف‌شده به بسته بازگشت." if job.package_minutes else "مبلغ پرداختی به کیف پول بازگشت."
    return "برای پیگیری بازگشت اعتبار، /paysupport را بزن."


async def _refund_job(application: Application, state: BotState, job: Job) -> bool:
    result = await state.database.refund_job_wallet(job.id)
    if result and result["refunded"]:
        logger.info("Returned payment for failed job %s", job.id)
        return True
    return False


async def _notify_admin_cost(
    application: Application, state: BotState, job: Job, costs: OpenAICost
) -> None:
    estimate = "نامشخص" if costs.total_usd is None else f"${costs.total_usd:.6f}"
    mode = "زیرنویس" if job.mode == "subtitle" else "دوبله"
    model_info = ""
    if job.models:
        model_info = (f"\nرونویسی: {job.models.stt.model} · ترجمه: {job.models.translation.model}"
                      + (f"\nدوبله: {job.models.tts.model} · صدا: {job.models.voice}" if job.mode == "dub" else ""))
    try:
        await application.bot.send_message(
            chat_id=state.settings.provider_control_user_id,
            text=(
                f"📊 job {job.id[:8]} کامل شد\nکاربر: {job.user_id} · نوع: {mode}\n"
                + (f"پرداخت: بستهٔ دقیقه ({job.package_minutes} دقیقه)\n" if job.package_minutes else
                 f"فروش: {job.billed_amount_toman:,} تومان برای {job.billable_minutes} دقیقه\n")
                + f"هزینهٔ تخمینی API: {estimate}{model_info}"
            ),
        )
    except TelegramError:
        logger.exception("Could not send job cost report to admin for %s", job.id)


async def _send_srt(application: Application, job: Job, srt: Path) -> None:
    with srt.open("rb") as subtitle_file:
        await application.bot.send_document(
            chat_id=job.chat_id,
            document=subtitle_file,
            filename="fa.srt",
            caption="فایل زیرنویس جداگانه",
        )


def _receipt_text(job: Job) -> str:
    mode = "زیرنویس فارسی" if job.mode == "subtitle" else "دوبلهٔ فارسی"
    if job.package_minutes:
        return f"✅ {mode} آماده شد\nمصرف از بسته: {job.package_minutes} دقیقه"
    rate = job.billed_amount_toman // max(1, job.billable_minutes)
    return f"✅ {mode} آماده شد\nهزینه: {job.billable_minutes} دقیقه × {rate:,} = {job.billed_amount_toman:,} تومان"


async def _send_download_link(
    application: Application,
    job: Job,
    video: Path,
    srt: Path,
    settings: Settings,
    database: Database,
    *,
    include_srt: bool = True,
) -> None:
    download_dir = Path(settings.download_dir)
    token = await asyncio.to_thread(
        publish_download, video, download_dir, settings.download_ttl_hours
    )
    await database.add_download(
        job_id=job.id,
        token=token,
        filename="video-fa.mp4",
        size=video.stat().st_size,
        expires_at=datetime.now(UTC) + timedelta(hours=settings.download_ttl_hours),
    )
    await application.bot.send_message(
        chat_id=job.chat_id,
        text=(
            f"حجم ویدیو از سقف ارسال تلگرام بیشتر است. لینک دانلود مستقیم:\n"
            f"{settings.download_base_url}/{token}.mp4\n"
            f"این لینک تا {settings.download_ttl_hours} ساعت فعال می‌ماند."
        ),
        disable_web_page_preview=True,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(
            "⬇️ دانلود ویدیو", url=f"{settings.download_base_url}/{token}.mp4", style="primary"
        )]]),
    )
    job.draft_was_used = False
    if include_srt:
        await _send_srt(application, job, srt)


async def _publish_subtitle_player_link(
    application: Application,
    job: Job,
    video: Path,
    srt: Path,
    vtt: Path,
    settings: Settings,
    database: Database,
) -> str:
    token = await asyncio.to_thread(
        publish_subtitle_player,
        video,
        srt,
        vtt,
        Path(settings.download_dir),
        settings.download_ttl_hours,
    )
    await database.add_download(
        job_id=job.id,
        token=token,
        filename="video.mp4",
        size=video.stat().st_size,
        expires_at=datetime.now(UTC) + timedelta(hours=settings.download_ttl_hours),
    )
    return f"{settings.download_base_url}/{token}"


async def post_init(application: Application) -> None:
    settings: Settings = application.bot_data["settings"]
    database = Database(settings.database_url)
    await database.initialize()
    Path(settings.work_dir).mkdir(parents=True, exist_ok=True)
    download_dir = Path(settings.download_dir)
    download_dir.mkdir(parents=True, exist_ok=True)
    await asyncio.to_thread(cleanup_expired_downloads, download_dir, settings.download_ttl_hours)
    state = BotState(settings, database)
    for order in await database.unfinished_content_orders():
        try:
            if await database.refund_content_order(order["id"]):
                await application.bot.send_message(order["chat_id"], "پردازش محتوای تکمیلی به دلیل راه‌اندازی مجدد متوقف شد و هزینه به کیف پول برگشت.")
        except Exception:
            logger.exception("Could not refund interrupted content order %s", order["id"])
    for order in await database.unfinished_image_orders():
        try:
            if await database.refund_image_order(order["id"]):
                await application.bot.send_message(order["chat_id"], "سفارش تصویر با راه‌اندازی مجدد متوقف شد و هزینه به کیف پول برگشت.")
        except Exception:
            logger.exception("Could not refund interrupted image order %s", order["id"])
    for interrupted in await database.interrupted_wallet_jobs():
        try:
            refund = await database.refund_job_wallet(interrupted["job_id"])
            if refund and refund["refunded"]:
                await application.bot.send_message(
                    chat_id=interrupted["chat_id"],
                    text=(f"پردازش قبلی {interrupted['job_id'][:8]} به‌دلیل راه‌اندازی مجدد کامل نشد؛ " +
                          (f"{refund['package_minutes']} دقیقه به بسته برگشت." if 'package_minutes' in refund else
                           f"هزینه به کیف پول برگشت. موجودی: {refund['balance_toman']:,} تومان.")),
                )
        except Exception:
            logger.exception("Could not return wallet balance for interrupted job")
    # Refund old Stars charges from jobs that failed before wallet billing was introduced.
    # This is migration cleanup only; new work is billed through the Toman wallet.
    for legacy in await database.legacy_failed_stars_jobs():
        try:
            await application.bot.refund_star_payment(
                user_id=legacy["user_id"],
                telegram_payment_charge_id=legacy["charge_id"],
            )
            await database.mark_legacy_stars_refunded(legacy["payload"])
            try:
                await application.bot.send_message(
                    chat_id=legacy["chat_id"],
                    text="هزینهٔ پرداخت قدیمی Stars برای پردازش ناموفق به‌صورت خودکار برگشت داده شد.",
                )
            except TelegramError:
                logger.info("Could not notify legacy Stars refund user %s", legacy["user_id"])
        except TelegramError:
            logger.exception("Could not refund legacy Stars payment for user %s", legacy["user_id"])
    stored_provider = await database.get_setting("api_provider", settings.default_api_provider)
    if stored_provider in {"openai", "openrouter"}:
        state.api_provider = stored_provider
    if state.api_provider == "openrouter" and not settings.openrouter_api_key and settings.openai_api_key:
        state.api_provider = "openai"
    if state.api_provider == "openai" and not settings.openai_api_key and settings.openrouter_api_key:
        state.api_provider = "openrouter"
    application.bot_data["state"] = state
    from telegram import BotCommand
    await application.bot.set_my_commands([
        BotCommand("start", "شروع و راهنمای ربات"),
        BotCommand("team", "حساب تیمی و راهنمای آن"),
        BotCommand("pricing", "تعرفه‌ها به‌ازای هر دقیقه"),
        BotCommand("history", "گردش کیف پول"),
        BotCommand("balance", "موجودی کیف پول"),
        BotCommand("charge", "درخواست شارژ کارت‌به‌کارت"),
        BotCommand("terms", "شرایط استفاده"),
        BotCommand("paysupport", "پشتیبانی پرداخت"),
        BotCommand("cancel", "لغو درخواست یا شارژ"),
    ])
    application.bot_data["worker_task"] = asyncio.create_task(worker(application), name="video-worker")


async def post_shutdown(application: Application) -> None:
    state = application.bot_data.get("state")
    if not state:
        return
    for job in state.active.values():
        job.cancel_event.set()
    worker_task = application.bot_data.get("worker_task")
    if worker_task:
        await state.queue.put(None)
        await worker_task
    await state.database.close()


def main() -> None:
    settings = load_settings()
    application = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )
    application.bot_data["settings"] = settings
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("team", team_command))
    application.add_handler(CommandHandler("team_create", team_create))
    application.add_handler(CommandHandler("team_invite", team_invite))
    application.add_handler(CommandHandler("team_join", team_join))
    application.add_handler(CommandHandler("team_leave", team_leave))
    application.add_handler(CommandHandler("team_remove", team_remove))
    application.add_handler(CommandHandler("team_glossary", team_glossary))
    application.add_handler(CommandHandler("team_report", team_report))
    application.add_handler(CommandHandler("pricing", pricing))
    application.add_handler(CommandHandler("history", history))
    application.add_handler(CommandHandler("balance", balance))
    application.add_handler(CommandHandler("charge", charge_wallet))
    application.add_handler(CommandHandler("terms", terms))
    application.add_handler(CommandHandler("paysupport", payment_support))
    application.add_handler(CommandHandler("admin", admin_panel))
    application.add_handler(CommandHandler("cancel", cancel))
    application.add_handler(CommandHandler("limits", limits))
    application.add_handler(CommandHandler("provider", choose_provider_command))
    application.add_handler(CallbackQueryHandler(choose_provider_callback, pattern=r"^provider:"))
    application.add_handler(CallbackQueryHandler(admin_callback, pattern=r"^admin:"))
    application.add_handler(CallbackQueryHandler(terms_callback, pattern=r"^terms:"))
    application.add_handler(CallbackQueryHandler(menu_callback, pattern=r"^menu:"))
    application.add_handler(CallbackQueryHandler(orders_callback, pattern=r"^orders:"))
    application.add_handler(CallbackQueryHandler(content_callback, pattern=r"^content:"))
    application.add_handler(CallbackQueryHandler(image_callback, pattern=r"^image:"))
    application.add_handler(CallbackQueryHandler(packages_callback, pattern=r"^packs:"))
    application.add_handler(CallbackQueryHandler(team_join_callback, pattern=r"^team:join:"))
    application.add_handler(CallbackQueryHandler(choose_mode, pattern=r"^mode:"))
    application.add_handler(CallbackQueryHandler(cancel_job_callback, pattern=r"^job_cancel:"))
    application.add_handler(CallbackQueryHandler(choose_dub_mode, pattern=r"^dubmode:"))
    application.add_handler(CallbackQueryHandler(choose_download, pattern=r"^dl:"))
    application.add_handler(CallbackQueryHandler(choose_quality, pattern=r"^quality:"))
    application.add_handler(CallbackQueryHandler(confirm_order, pattern=r"^confirm:"))
    application.add_handler(CallbackQueryHandler(cancel_order_callback, pattern=r"^order_cancel:"))
    application.add_handler(CallbackQueryHandler(back_to_mode, pattern=r"^order_back:"))
    application.add_handler(CallbackQueryHandler(back_to_quality, pattern=r"^order_quality_back:"))
    application.add_handler(CallbackQueryHandler(deposit_action, pattern=r"^deposit:"))
    application.add_handler(CallbackQueryHandler(wallet_callback, pattern=r"^wallet:"))
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, legacy_stars_refund))
    application.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, receive_deposit_proof))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, receive_link))
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
