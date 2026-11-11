import asyncio
import logging
import uuid
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
from . import ui, model_catalog
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


class BotState:
    def __init__(self, settings: Settings, database: Database) -> None:
        self.settings = settings
        self.database = database
        self.queue: asyncio.Queue[Job | None] = asyncio.Queue()
        self.active: dict[int, Job] = {}
        self.pending_quality: dict[str, PendingQuality] = {}
        self.pending_by_user: dict[int, str] = {}
        self.admin_editing: dict[int, str] = {}
        self.awaiting_topup: set[int] = set()
        self.awaiting_support: set[int] = set()
        self.api_provider = settings.default_api_provider


def _state(context: ContextTypes.DEFAULT_TYPE) -> BotState:
    return context.application.bot_data["state"]


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
    balance = await state.database.get_wallet_balance(user.id)
    await message.reply_text(ui.home_text(balance), parse_mode="HTML", reply_markup=ui.home_keyboard())


async def receive_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, message = update.effective_user, update.effective_message
    state = _state(context)
    if not user or not message or not message.text:
        return
    await state.database.upsert_user(user, True)
    if user.id in state.admin_editing:
        await _save_admin_value(update, state, context.application)
        return
    if message.chat.type != "private":
        await message.reply_text("برای حفظ حریم خصوصی، لطفاً در گفت‌وگوی خصوصی ربات پیام بده.")
        return
    url = message.text.strip()
    if user.id in state.awaiting_support:
        await _send_support_request(update, context, url)
        return
    if user.id in state.awaiting_topup and not validate_youtube_url(url):
        await _create_charge_request(update, context, url)
        return
    if validate_youtube_url(url):
        state.awaiting_topup.discard(user.id)
    pending_deposit = await state.database.get_user_pending_deposit(user.id)
    if pending_deposit and pending_deposit["status"] == "awaiting_proof" and not validate_youtube_url(url):
        submitted = await state.database.submit_deposit_proof(
            pending_deposit["id"], user.id, "text", proof_text=url
        )
        if submitted:
            await message.reply_text("✅ رسید/شماره پیگیری ثبت شد و برای بررسی به مدیر ارسال شد. پس از تأیید، کیف پولت شارژ می‌شود.")
            await _notify_admin_deposit(context.application, submitted, user.username)
        else:
            await message.reply_text("درخواست شارژ پیدا نشد یا منقضی شده است.")
        return
    if not validate_youtube_url(url):
        await message.reply_text("لینک معتبر youtube.com یا youtu.be بفرست. برای فرستادن رسید شارژ، ابتدا /charge را بزن.")
        return
    if user.id in state.active or user.id in state.pending_by_user:
        await message.reply_text("یک درخواست پردازش باز داری؛ اول آن را کامل کن یا /cancel بزن.")
        return

    if not await state.database.has_accepted_terms(user.id):
        await message.reply_text("برای شروع، شرایط استفاده را بخوان و بپذیر؛ سپس لینک را دوباره بفرست.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📜 شرایط استفاده", callback_data="terms:show")]]))
        return

    progress = await message.reply_text("✨ نوع پردازش را انتخاب کن:")
    token = uuid.uuid4().hex[:12]
    selection = PendingQuality(
        user.id, message.chat_id, url, progress.message_id, True, state.api_provider,
    )
    state.pending_quality[token] = selection
    state.pending_by_user[user.id] = token
    await context.application.bot.edit_message_text(
        "🎬 سفارش جدید  ·  ۱ از ۳\n\nکدام خروجی را می‌خواهی؟\n"
        "📝 زیرنویس: متن فارسی همراه ویدیو\n🎙 دوبله: جایگزینی صدای اصلی با صدای فارسی هوش مصنوعی",
        chat_id=selection.chat_id, message_id=selection.message_id,
        reply_markup=ui.mode_keyboard(token),
    )


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
    if not selection or selection.user_id != user.id:
        await query.answer("این انتخاب منقضی شده؛ لینک را دوباره بفرست.", show_alert=True)
        return

    await query.answer()
    selection.mode = mode
    await query.edit_message_text(_progress_text("بررسی کیفیت‌های موجود", 0))
    try:
        heights, duration = await asyncio.to_thread(get_video_details, selection.url, state.settings)
        if duration <= 0:
            raise RuntimeError("مدت ویدیو از یوتیوب دریافت نشد.")
        if duration > state.settings.video_max_minutes * 60:
            raise RuntimeError(f"حداکثر مدت مجاز {state.settings.video_max_minutes} دقیقه است.")
        selection.duration_seconds = int(ceil(duration))
    except Exception:
        logger.exception("Could not probe YouTube formats for Telegram user %s", user.id)
        state.pending_quality.pop(token, None)
        state.pending_by_user.pop(user.id, None)
        await _safe_edit(application=context.application, selection=selection,
                         text="کیفیت‌های ویدیو دریافت نشد. لطفاً کمی بعد دوباره تلاش کن.")
        return

    mode_label = "زیرنویس فارسی" if mode == "subtitle" else "دوبلهٔ فارسی"
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
    if not selection or selection.user_id != user.id or not selection.mode:
        await query.answer("این انتخاب منقضی شده؛ لینک را دوباره بفرست.", show_alert=True)
        return
    if not await state.database.has_accepted_terms(user.id):
        state.pending_quality.pop(token, None)
        state.pending_by_user.pop(user.id, None)
        await query.answer("برای ادامه، شرایط استفاده را بخوان و تأیید کن.", show_alert=True)
        await query.edit_message_text(
            "قبل از ادامه، شرایط استفاده را بخوان و تأیید کن.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📜 مطالعه و پذیرش شرایط", callback_data="terms:show")]]),
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
    mode_label = "زیرنویس فارسی" if mode == "subtitle" else "دوبلهٔ فارسی"
    balance = await state.database.get_wallet_balance(user.id)
    await query.answer()
    await query.edit_message_text(
        f"🧾 سفارش جدید  ·  ۳ از ۳\n\nخروجی: {mode_label} · کیفیت: {quality}\n"
        f"مدت قابل محاسبه: {minutes} دقیقه\nتعرفه: {rate:,} تومان در دقیقه\n"
        f"هزینه: {amount:,} تومان · موجودی: {balance:,} تومان\n\n"
        "با تأیید، هزینه از کیف پول کم و سفارش وارد صف می‌شود.",
        reply_markup=ui.confirmation_keyboard(token),
    )


async def confirm_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query, user = update.callback_query, update.effective_user
    if not query or not user:
        return
    state = _state(context)
    token = (query.data or "").partition(":")[2]
    selection = state.pending_quality.get(token)
    if not selection or selection.user_id != user.id or not selection.mode or not selection.quoted_rate or selection.confirming:
        await query.answer("این سفارش دیگر قابل تأیید نیست.", show_alert=True)
        return
    selection.confirming = True
    mode = selection.mode
    selected_height = selection.selected_height
    rate = selection.quoted_rate
    minutes = max(1, ceil(selection.duration_seconds / 60))
    amount = minutes * rate
    job_id = uuid.uuid4().hex
    try:
        models = await model_catalog.load_selection(state.database, state.settings, selection.api_provider)
        required = [models.stt, models.translation] + ([models.tts] if mode == "dub" else [])
        missing = {item.provider for item in required if not (
            state.settings.openai_api_key if item.provider == "openai" else state.settings.openrouter_api_key
        )}
        if missing:
            selection.confirming = False
            await query.answer("پردازشگر سفارش تنظیم نشده است؛ لطفاً با پشتیبانی تماس بگیر.", show_alert=True)
            return
        await query.answer()
        balance = await state.database.create_wallet_job(
            job_id=job_id, user_id=user.id, chat_id=selection.chat_id,
            url=selection.url, selected_height=selected_height, mode=mode,
            api_provider=selection.api_provider, billable_minutes=minutes,
            amount_toman=amount,
        )
    except Exception:
        selection.confirming = False
        raise
    state.pending_quality.pop(token, None)
    state.pending_by_user.pop(user.id, None)
    if balance is None:
        current = await state.database.get_wallet_balance(user.id)
        shortage = max(0, amount - current)
        await query.edit_message_text(
            f"موجودی کافی نیست.\nمدت ویدیو: {minutes} دقیقه\nهزینه: {amount:,} تومان\n"
            f"موجودی: {current:,} تومان · کسری: {shortage:,} تومان\n\n"
            "برای شارژ، /charge مبلغ را بفرست؛ بعد لینک ویدیو را دوباره ارسال کن.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💳 راهنمای شارژ کیف پول", callback_data="wallet:topup")]]),
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
        billed_amount_toman=amount, models=models,
    )
    state.active[user.id] = job
    await state.queue.put(job)
    try:
        await query.edit_message_text(
            _progress_text("هزینه از کیف پول کم شد؛ در صف پردازش", 0)
            + f"\nخروجی: {mode_label} | کیفیت: {quality_label}"
            + f"\nمبلغ: {minutes} × {rate:,} = {amount:,} تومان"
            + f"\nموجودی باقی‌مانده: {balance:,} تومان"
        )
    except TelegramError:
        logger.exception("Could not edit wallet-job status message %s", job_id)


async def back_to_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query, user = update.callback_query, update.effective_user
    if not query or not user:
        return
    token = (query.data or "").partition(":")[2]
    selection = _state(context).pending_quality.get(token)
    if not selection or selection.user_id != user.id or selection.confirming:
        await query.answer("این سفارش دیگر فعال نیست.", show_alert=True)
        return
    selection.mode = None
    selection.quoted_rate = 0
    await query.answer()
    await query.edit_message_text(
        "🎬 سفارش جدید  ·  ۱ از ۳\n\nنوع خروجی را انتخاب کن:",
        reply_markup=ui.mode_keyboard(token),
    )


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
    await query.edit_message_text("سفارش لغو شد. هر زمان خواستی لینک جدید بفرست.")


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, message = update.effective_user, update.effective_message
    state = _state(context)
    if not user or not message:
        return
    await state.database.upsert_user(user, True)
    if user.id in state.awaiting_support:
        state.awaiting_support.discard(user.id)
        await message.reply_text("نوشتن پیام پشتیبانی لغو شد.", reply_markup=ui.back_keyboard())
        return
    if user.id in state.awaiting_topup:
        state.awaiting_topup.discard(user.id)
        await message.reply_text("درخواست وارد کردن مبلغ لغو شد.", reply_markup=ui.back_keyboard())
        return
    if state.admin_editing.pop(user.id, None):
        await message.reply_text("تغییر تنظیمات لغو شد.")
        return
    pending_token = state.pending_by_user.pop(user.id, None)
    if pending_token:
        selection = state.pending_quality.pop(pending_token, None)
        if selection:
            await _safe_edit(context.application, selection, "درخواست لغو شد.")
        await message.reply_text("درخواست پردازش لغو شد.")
        return
    job = state.active.get(user.id)
    if job:
        job.cancel_event.set()
        await message.reply_text("درخواست لغو ثبت شد؛ پس از پایان گام فعلی هزینه به کیف پول برمی‌گردد.")
        return
    pending_deposit = await state.database.get_user_pending_deposit(user.id)
    if pending_deposit and pending_deposit["status"] == "awaiting_proof":
        await state.database.cancel_deposit_request(pending_deposit["id"], user.id)
        await message.reply_text("درخواست شارژ لغو شد؛ اگر انتقال کارت‌به‌کارت انجام داده‌ای با /paysupport پیگیری کن.")
        return
    await message.reply_text("درخواستی برای لغو وجود ندارد.")


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
    await message.reply_text(
        "💎 تعرفه‌ها\n\n"
        f"📝 زیرنویس فارسی  ·  {subtitle:,} تومان / دقیقه\n"
        f"🎙 دوبلهٔ فارسی  ·  {dub:,} تومان / دقیقه\n\n"
        "مدت ویدیو به دقیقهٔ کامل بعدی گرد می‌شود. هزینه را پیش از تأیید می‌بینی.",
        reply_markup=ui.back_keyboard(),
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
    await message.reply_text(
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
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📜 مطالعهٔ شرایط", callback_data="terms:show")]]),
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
    state.awaiting_support.discard(user.id)
    if not state.settings.card_to_card_number or not state.settings.card_to_card_holder:
        await message.reply_text("شارژ در حال حاضر در دسترس نیست؛ لطفاً با پشتیبانی تماس بگیر.", reply_markup=ui.back_keyboard())
        return
    if not await state.database.has_accepted_terms(user.id):
        await message.reply_text("برای شارژ، ابتدا شرایط استفاده را بخوان و بپذیر.",
            reply_markup=InlineKeyboardMarkup([[ui.button("📜 مشاهدهٔ شرایط", "terms:show", style="primary")]]))
        return
    pending = await state.database.get_user_pending_deposit(user.id)
    if pending:
        if pending["status"] == "awaiting_proof":
            await message.reply_text(
                f"💳 درخواست شارژ باز · {pending['amount_toman']:,} تومان\n\n"
                f"شماره کارت: {state.settings.card_to_card_number}\n"
                f"به نام: {state.settings.card_to_card_holder}\n\n"
                "عکس رسید یا شمارهٔ پیگیری را بفرست. برای لغو /cancel را بزن.",
                reply_markup=ui.back_keyboard())
        else:
            await message.reply_text("⏳ رسیدت در حال بررسی است. پس از بررسی نتیجه را اطلاع می‌دهیم.", reply_markup=ui.back_keyboard())
        return
    state.awaiting_support.discard(user.id)
    state.awaiting_topup.add(user.id)
    await message.reply_text(
        f"💳 شارژ کیف پول\n\nمبلغ دلخواه را به تومان بفرست.\n"
        f"حداقل شارژ: {state.settings.minimum_wallet_topup_toman:,} تومان\n\n"
        "مثال: 200000\nبرای انصراف /cancel را بزن.", reply_markup=ui.back_keyboard())


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
            reply_markup=InlineKeyboardMarkup([[ui.button("📜 مشاهدهٔ شرایط", "terms:show", style="primary")]]))
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
        "🏦 درخواست کارت‌به‌کارت\n\n"
        f"مبلغ: <b>{amount:,} تومان</b>\n"
        f"شماره کارت: <code>{state.settings.card_to_card_number}</code>\n"
        f"به نام: <b>{escape(state.settings.card_to_card_holder)}</b>\n\n"
        "پس از واریز، عکس رسید یا شماره پیگیری را در همین چت بفرست. مدیر انتقال را دستی بررسی می‌کند و سپس کیف پول شارژ می‌شود.\n"
        "این مرحله تأیید خودکار بانکی نیست؛ تا تأیید مدیر موجودی اضافه نخواهد شد.",
        parse_mode="HTML", reply_markup=ui.back_keyboard(),
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
        await message.reply_text("📒 هنوز تراکنشی ثبت نشده است.", reply_markup=ui.wallet_keyboard())
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
        lines.append(
            f"{row['created_at']:%Y-%m-%d %H:%M} · {labels.get(row['entry_type'], row['entry_type'])} · "
            f"{sign}{row['amount_toman']:,} تومان"
        )
    await message.reply_text("\n".join(lines), reply_markup=ui.wallet_keyboard())


async def terms(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, message = update.effective_user, update.effective_message
    if not user or not message:
        return
    await message.reply_text(
        "📜 شرایط استفاده و حریم خصوصی\n\n"
        "• هزینهٔ پردازش بر اساس مدت منبع و تعرفهٔ نمایش‌داده‌شده از کیف پول تومانی کم می‌شود.\n"
        "• شارژ کارت‌به‌کارت پس از بررسی دستی رسید توسط مدیر به کیف پول اضافه می‌شود؛ ارسال رسید به‌تنهایی به معنی تأیید نیست.\n"
        "• اگر پردازش یا تحویل خروجی به‌دلیل خطای سرویس ناموفق شود، مبلغ همان job به کیف پول برمی‌گردد.\n"
        "• لینک و محتوای ویدیو برای دریافت، رونویسی و ترجمه نزد ارائه‌دهندگان فنی پردازش می‌شود. فایل‌های موقت پس از پردازش پاک و لینک‌های خروجی پس از مهلت اعلام‌شده حذف می‌شوند.\n"
        "• فقط محتوایی را ارسال کن که حق استفاده و پردازش آن را داری و قوانین محل استفاده‌ات را رعایت کن.\n"
        "• پشتیبانی: /paysupport · گردش کیف پول: /history\n\n"
        "با انتخاب «می‌پذیرم»، شرایط بالا را تأیید می‌کنی.",
        reply_markup=InlineKeyboardMarkup([[ui.button("✓ می‌پذیرم", "terms:accept", style="success")], [ui.button("⌂ منوی اصلی", "menu:home")]]),
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
    await message.reply_text(
        f"💬 پشتیبانی\n\nپیامت را همین‌جا بنویس تا برای پشتیبانی ارسال شود.\n"
        f"راه ارتباطی: {contact}\nبرای انصراف /cancel را بزن.",
        reply_markup=ui.back_keyboard())


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


async def _show_admin_panel(send, state: BotState, user_id: int) -> None:
    stats = await state.database.get_business_stats()
    subtitle = int(await state.database.get_setting("price_subtitle_toman_per_minute", str(state.settings.default_subtitle_price_toman_per_minute)))
    dub = int(await state.database.get_setting("price_dub_toman_per_minute", str(state.settings.default_dub_price_toman_per_minute)))
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ نرخ زیرنویس", callback_data="admin:edit:subtitle"),
         InlineKeyboardButton("✏️ نرخ دوبله", callback_data="admin:edit:dub")],
        [InlineKeyboardButton("➕ شارژ کاربر", callback_data="admin:wallet:credit"),
         InlineKeyboardButton("➖ کسر از کیف پول", callback_data="admin:wallet:debit")],
        [InlineKeyboardButton("👤 بررسی کاربر", callback_data="admin:wallet:lookup")],
        [InlineKeyboardButton(f"🧾 رسیدهای منتظر بررسی ({stats['pending_deposits']})", callback_data="admin:deposits")],
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
        f"هزینهٔ تخمینی API: ${stats['api_cost_usd']:.4f} · رسیدهای منتظر بررسی: {stats['pending_deposits']}\n\n"
        "برای شارژ/کسر دستی، دکمه را بزن و شناسهٔ تلگرام و مبلغ تومان را با فاصله بفرست.",
        reply_markup=keyboard,
    )


async def _show_model_settings(query, state: BotState) -> None:
    selection = await model_catalog.load_selection(state.database, state.settings, state.api_provider)
    lines = ["🤖 مدل‌های پردازش", ""]
    for stage, label in model_catalog.STAGE_LABELS.items():
        item = getattr(selection, stage)
        lines.append(f"{label}: {item.model} · {_provider_label(item.provider)}")
    lines.extend([f"صدای دوبله: {selection.voice}", "", "انتخاب‌ها برای سفارش‌های بعدی اعمال می‌شوند."])
    await query.edit_message_text("\n".join(lines), reply_markup=InlineKeyboardMarkup([
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
        lines.append(f"{index}. {'✓ ' if selected else ''}{option.model} · {_provider_label(option.provider)}\n   {option.price}")
        buttons.append([ui.button(f"{'✓ ' if selected else ''}{index}. {option.model}", f"admin:setmodel:{option.code}", style="success" if selected else None)])
    lines.extend(["", "قیمت‌ها تقریبی و مربوط به ۱۲ نوامبر ۲۰۲۶ هستند؛ نرخ نهایی را در داشبورد سرویس بررسی کن."])
    if stage != "stt":
        lines.append("نرخ‌های توکنی به ازای هر ۱ میلیون توکن هستند؛ هزینهٔ هر ویدیو به مصرف بستگی دارد.")
    buttons.append([ui.button("‹ مدل‌ها", "admin:models")])
    await query.edit_message_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons))


async def _show_voice_options(query, state: BotState) -> None:
    selection = await model_catalog.load_selection(state.database, state.settings, state.api_provider)
    provider = selection.tts.provider
    voices = model_catalog.VOICES[provider]
    buttons = [ui.button(f"{'✓ ' if name == selection.voice else ''}{name}",
                         f"admin:voice:{provider}:{name}", style="success" if name == selection.voice else None)
               for name in voices]
    await query.edit_message_text(
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
        await query.edit_message_text("نرخ جدید را به تومان برای هر دقیقه بفرست. لغو: /cancel")
        return
    if action == ["admin", "wallet", "credit"] or action == ["admin", "wallet", "debit"]:
        state.admin_editing[user.id] = action[2]
        await query.answer()
        await query.edit_message_text("شناسهٔ عددی تلگرام و مبلغ تومان را بفرست؛ نمونه: 123456789 500000\nلغو: /cancel")
        return
    if action == ["admin", "wallet", "lookup"]:
        state.admin_editing[user.id] = "lookup"
        await query.answer()
        await query.edit_message_text("شناسهٔ عددی تلگرام کاربر را بفرست؛ لغو: /cancel")
        return
    if action == ["admin", "providers"]:
        await query.answer()
        await query.edit_message_text(
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
        await query.edit_message_text("در حال به‌روزرسانی…")
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
        if not 1 <= price <= 1_000_000_000:
            raise ValueError
    except ValueError:
        await message.reply_text("یک عدد صحیح تومان بین ۱ تا ۱٬۰۰۰٬۰۰۰٬۰۰۰ بفرست.")
        return
    state.admin_editing.pop(user.id, None)
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
        await query.edit_message_text("✅ شرایط استفاده ثبت شد. حالا لینک ویدیو را بفرست.")


async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query, user = update.callback_query, update.effective_user
    if not query or not user:
        return
    action = (query.data or "").partition(":")[2]
    await query.answer()
    if action != "support":
        _state(context).awaiting_support.discard(user.id)
        _state(context).awaiting_topup.discard(user.id)
    if action == "home":
        await start(update, context)
    elif action == "new":
        _state(context).awaiting_topup.discard(user.id)
        _state(context).awaiting_support.discard(user.id)
        await query.message.reply_text(
            "🎬 سفارش جدید\n\nلینک ویدیوی YouTube را همین‌جا بفرست.\n"
            f"حداکثر مدت ویدیو: {_state(context).settings.video_max_minutes} دقیقه.",
            reply_markup=ui.back_keyboard())
    elif action == "pricing":
        await pricing(update, context)
    elif action == "status":
        state = _state(context)
        if user.id in state.active:
            job = state.active[user.id]
            label = "زیرنویس" if job.mode == "subtitle" else "دوبله"
            await query.message.reply_text(
                f"📦 سفارش فعال\n\nنوع: {label}\nشمارهٔ سفارش: {job.id[:8]}\n"
                "وضعیت دقیق در پیام پیشرفت سفارش نمایش داده می‌شود.",
                reply_markup=InlineKeyboardMarkup([
                    [ui.button("✕ درخواست لغو", "menu:canceljob", style="danger")],
                    [ui.button("⌂ منوی اصلی", "menu:home")],
                ]))
        elif user.id in state.pending_by_user:
            await query.message.reply_text("📦 سفارش هنوز در مرحلهٔ انتخاب است. به پیام انتخاب برگرد یا /cancel را بزن.", reply_markup=ui.back_keyboard())
        else:
            await query.message.reply_text("📦 سفارش فعالی نداری. برای شروع لینک یوتیوب را بفرست.", reply_markup=ui.home_keyboard())
    elif action == "canceljob":
        job = _state(context).active.get(user.id)
        if job:
            job.cancel_event.set()
            await query.message.reply_text("درخواست لغو ثبت شد؛ پس از پایان گام فعلی هزینه به کیف پول برمی‌گردد.", reply_markup=ui.back_keyboard())
        else:
            await query.message.reply_text("سفارش فعالی برای لغو وجود ندارد.", reply_markup=ui.back_keyboard())
    elif action == "history":
        await history(update, context)
    elif action == "terms":
        await terms(update, context)
    elif action == "support":
        await payment_support(update, context)
    elif action == "help":
        await query.message.reply_text(
            "📖 راهنما\n\nلینک یوتیوب را بفرست و خروجی و کیفیت را انتخاب کن. "
            "پیش از پرداخت، مبلغ نمایش داده می‌شود. در صورت خطای پردازش، هزینه به کیف پول برمی‌گردد.\n\n"
            "برای توقف سفارش از /cancel استفاده کن.",
            reply_markup=InlineKeyboardMarkup([
                [ui.button("🎬 سفارش جدید", "menu:new", style="primary")],
                [ui.button("📜 شرایط استفاده", "menu:terms"), ui.button("⌂ منوی اصلی", "menu:home")],
            ]))



async def receive_deposit_proof(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, message = update.effective_user, update.effective_message
    if not user or not message:
        return
    if message.chat.type != "private":
        await message.reply_text("رسید را فقط در گفت‌وگوی خصوصی ربات بفرست.")
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
            await query.edit_message_text(f"✅ تأیید شد · {result['amount_toman']:,} تومان برای {result['user_id']} شارژ شد.")
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
            await query.edit_message_text("❌ درخواست شارژ رد شد؛ در صورت اشتباه با /paysupport پیگیری کن.")
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
    await query.edit_message_text(
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
                job.models,
            )
            await state.database.update_job(job.id, "running")
            progress_queue = asyncio.Queue()
            loop = asyncio.get_running_loop()

            def report_progress(stage: str, percent: int) -> None:
                loop.call_soon_threadsafe(progress_queue.put_nowait, (stage, percent))

            progress_task = asyncio.create_task(_progress_updater(application, job, progress_queue))
            await _publish_progress(application, job, "دانلود ویدیو", 0)
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
            )
            subtitle_text = srt.read_text(encoding="utf-8")
            if job.cancel_event.is_set():
                raise JobCancelled()
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
                    refund_note = "مبلغ پرداختی برگشت داده شد." if refunded else "برای پیگیری برگشت مبلغ /paysupport را بزن."
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
                            "ویدیو با دوبلهٔ فارسی؛ صدای دوبله با هوش مصنوعی تولید شده."
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
                    refund_note = "مبلغ پرداختی برگشت داده شد." if refunded else "برای پیگیری برگشت مبلغ /paysupport را بزن."
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
            refund_note = "مبلغ پرداختی به‌صورت خودکار برگشت داده شد." if refunded else "برای پیگیری برگشت مبلغ، /paysupport را بزن."
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
                error_text + ("\nمبلغ پرداختی برگشت داده شد." if refunded else "\nاگر مبلغ کسر شده، برای پیگیری /paysupport را بزن."),
            )
        except Exception:
            logger.exception("Job failed for Telegram user %s", job.user_id)
            await stop_progress_updates()
            refunded = await _refund_job(application, state, job)
            try:
                await state.database.update_job(job.id, "failed", error="Job failed; see bot logs for details.")
            except Exception:
                logger.exception("Could not persist failure status for job %s", job.id)
            refund_note = "مبلغ پرداختی برگشت داده شد." if refunded else "برای پیگیری مبلغ، /paysupport را بزن."
            await _finish_progress(application, job, f"پردازش انجام نشد.\n{refund_note} لطفاً کمی بعد دوباره تلاش کن.")
        finally:
            await stop_progress_updates()
            cleanup(job.directory)
            state.active.pop(job.user_id, None)
            state.queue.task_done()


async def _safe_progress(application: Application, job: Job, text: str) -> None:
    try:
        await application.bot.edit_message_text(text, job.chat_id, job.message_id)
    except Exception:
        logger.debug("Could not update job progress", exc_info=True)


def _progress_text(stage: str, percent: int) -> str:
    percent = max(0, min(100, percent))
    filled = round(percent / 10)
    bar = "▰" * filled + "▱" * (10 - filled)
    return f"{stage}\n{bar} {percent}%"


async def _publish_progress(application: Application, job: Job, stage: str, percent: int) -> None:
    text = _progress_text(stage, percent)
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
    await _safe_progress(application, job, text)


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
            await application.bot.delete_message(job.chat_id, job.message_id)
            return
        except TelegramError as exc:
            logger.debug("Could not finalize Telegram live draft (%s)", type(exc).__name__)
    await _safe_progress(application, job, text)


async def _safe_edit(application: Application, selection: PendingQuality, text: str) -> None:
    try:
        await application.bot.edit_message_text(text, selection.chat_id, selection.message_id)
    except Exception:
        logger.debug("Could not update quality selection", exc_info=True)


async def _refund_job(application: Application, state: BotState, job: Job) -> bool:
    result = await state.database.refund_job_wallet(job.id)
    if result and result["refunded"]:
        logger.info("Returned %s toman to wallet for failed job %s", job.billed_amount_toman, job.id)
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
                f"فروش: {job.billed_amount_toman:,} تومان برای {job.billable_minutes} دقیقه\n"
                f"هزینهٔ تخمینی API: {estimate}{model_info}"
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
    for interrupted in await database.interrupted_wallet_jobs():
        try:
            refund = await database.refund_job_wallet(interrupted["job_id"])
            if refund and refund["refunded"]:
                await application.bot.send_message(
                    chat_id=interrupted["chat_id"],
                    text=f"پردازش قبلی {interrupted['job_id'][:8]} به‌دلیل راه‌اندازی مجدد کامل نشد؛ هزینه به کیف پول برگشت. موجودی: {refund['balance_toman']:,} تومان.",
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
    application.add_handler(CallbackQueryHandler(choose_mode, pattern=r"^mode:"))
    application.add_handler(CallbackQueryHandler(choose_quality, pattern=r"^quality:"))
    application.add_handler(CallbackQueryHandler(confirm_order, pattern=r"^confirm:"))
    application.add_handler(CallbackQueryHandler(cancel_order_callback, pattern=r"^order_cancel:"))
    application.add_handler(CallbackQueryHandler(back_to_mode, pattern=r"^order_back:"))
    application.add_handler(CallbackQueryHandler(deposit_action, pattern=r"^deposit:"))
    application.add_handler(CallbackQueryHandler(wallet_callback, pattern=r"^wallet:"))
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, legacy_stars_refund))
    application.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, receive_deposit_proof))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, receive_link))
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
