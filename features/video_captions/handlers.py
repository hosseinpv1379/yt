"""Telegram workflow for offline caption and color jobs."""
import asyncio
import logging
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from math import ceil
from pathlib import Path

from telegram import InlineKeyboardMarkup
from telegram.ext import ApplicationHandlerStop, CallbackQueryHandler, MessageHandler, filters

from app import ui
from app.pipeline import publish_download
from .ass_builder import FONT_FILES, FONT_LABELS, FONT_SIZE_LABELS
from .grading import GradeSettings
from .pipeline import probe, render

logger = logging.getLogger(__name__)
MAX_INPUT = 20_000_000


@dataclass
class VideoCaptionJob:
    id: str
    user_id: int
    chat_id: int
    message_id: int
    file_id: str
    edit_mode: str
    color: str
    billable_minutes: int
    package_minutes: int = 0
    language: str | None = None
    font: str = "vazirmatn"
    font_size: str = "medium"
    mode: str = "subtitle"
    delivery_started: bool = False
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)


def _pending(application):
    return application.bot_data.setdefault("video_captions_pending", {})


async def callback(update, context):
    query, user = update.callback_query, update.effective_user
    if not query or not user or not query.message or query.message.chat.type != "private":
        return
    state = context.application.bot_data["state"]
    parts = (query.data or "").split(":")
    action = parts[1] if len(parts) > 1 else ""
    pending = _pending(context.application)
    if action == "start":
        if user.id in state.active or user.id in state.pending_by_user:
            await query.answer("یک سفارش باز داری.", show_alert=True)
            return
        if not await state.database.has_accepted_terms(user.id):
            await query.answer("ابتدا شرایط استفاده را بپذیر.", show_alert=True)
            return
        token = uuid.uuid4().hex[:12]
        pending[user.id] = {"stage": "video", "token": token}
        state.track_stage(user.id, "video_upload", token, "menu:services")
        await query.answer()
        await query.edit_message_text(
            ui.screen("زیرنویس ویدیوی ارسالی",
                "ویدیویی تا ۹۰ ثانیه و ۲۰ مگابایت را همین‌جا بفرست.", icon="🎬"),
            parse_mode="HTML",
            reply_markup=ui.cancel_keyboard(f"vclip:cancel:{token}", "menu:services"),
        )
        return
    item = pending.get(user.id)
    if not item or len(parts) < 3 or parts[2] != item.get("token") or item.get("confirming"):
        await query.answer("این انتخاب منقضی شده است.", show_alert=True)
        return
    if action == "confirm" and item.get("amount") and item.get("mode") in {"caption", "both"}:
        # Older pending confirmations did not collect these options. Honor the
        # price the user already saw and use the established, Persian-safe defaults.
        if item.get("font") not in FONT_FILES:
            item["font"] = "vazirmatn"
        if item.get("font_size") not in FONT_SIZE_LABELS:
            item["font_size"] = "medium"
    if action == "mode" and len(parts) == 4 and parts[3] == "caption" and item.get("stage") == "options":
        item["mode"] = parts[3]
        item["stage"] = "language"
        state.track_stage(user.id, "video_language", item["token"], "menu:services")
        for key in ("language", "color", "font", "font_size", "amount", "package_id"):
            item.pop(key, None)
        await query.answer()
        if item["mode"] == "color":
            item["language"] = "auto"
            item["color"] = "yellow"
            await _quote(query, state, user.id, item)
        else:
            await query.edit_message_text(ui.screen("زبان گفتار", "زبان ویدیو را انتخاب کن:", icon="🌐"),
                parse_mode="HTML", reply_markup=InlineKeyboardMarkup([
                [ui.button("🇮🇷 فارسی", f"vclip:lang:{item['token']}:fa", style="primary"),
                 ui.button("🇬🇧 انگلیسی", f"vclip:lang:{item['token']}:en")],
                [ui.button("🌐 تشخیص خودکار", f"vclip:lang:{item['token']}:auto")],
                [ui.button("✕ لغو", f"vclip:cancel:{item['token']}")],
            ]))
    elif action == "lang" and len(parts) == 4 and parts[3] in {"fa", "en", "auto"} and item.get("stage") == "language" and item.get("mode") in {"caption", "both"}:
        item["language"] = parts[3]
        item["stage"] = "color"
        state.track_stage(user.id, "video_color", item["token"], "menu:services")
        for key in ("amount", "package_id", "color", "font", "font_size"):
            item.pop(key, None)
        await query.answer()
        await query.edit_message_text(ui.screen("رنگ زیرنویس", "رنگ کلمهٔ فعال را انتخاب کن:", icon="🎨"),
            parse_mode="HTML", reply_markup=InlineKeyboardMarkup([
            [ui.button("🟡 زرد", f"vclip:color:{item['token']}:yellow"), ui.button("🟢 سبز", f"vclip:color:{item['token']}:green")],
            [ui.button("🔵 آبی", f"vclip:color:{item['token']}:blue"), ui.button("⚪ سفید", f"vclip:color:{item['token']}:white")],
            [ui.button("✕ لغو", f"vclip:cancel:{item['token']}")],
        ]))
    elif action == "color" and len(parts) == 4 and parts[3] in {"yellow", "green", "blue", "white"} and item.get("stage") == "color" and item.get("mode") in {"caption", "both"} and item.get("language") in {"fa", "en", "auto"}:
        item["color"] = parts[3]
        item["stage"] = "font"
        state.track_stage(user.id, "video_font", item["token"], "menu:services")
        await query.answer()
        await query.edit_message_text(ui.screen("فونت زیرنویس", "فونت دلخواهت را انتخاب کن:", icon="🔤"),
            parse_mode="HTML", reply_markup=InlineKeyboardMarkup([
            [ui.button(FONT_LABELS["vazirmatn"], f"vclip:font:{item['token']}:vazirmatn"),
             ui.button(FONT_LABELS["noto_sans_arabic"], f"vclip:font:{item['token']}:noto_sans_arabic")],
            [ui.button(FONT_LABELS["noto_naskh_arabic"], f"vclip:font:{item['token']}:noto_naskh_arabic"),
             ui.button(FONT_LABELS["noto_sans"], f"vclip:font:{item['token']}:noto_sans")],
            [ui.button(FONT_LABELS["noto_serif"], f"vclip:font:{item['token']}:noto_serif"),
             ui.button(FONT_LABELS["montserrat"], f"vclip:font:{item['token']}:montserrat")],
            [ui.button("✕ لغو", f"vclip:cancel:{item['token']}")],
        ]))
    elif action == "font" and len(parts) == 4 and parts[3] in FONT_FILES and item.get("stage") == "font" and item.get("mode") in {"caption", "both"} and item.get("color") in {"yellow", "green", "blue", "white"} and item.get("language") in {"fa", "en", "auto"}:
        item["font"] = parts[3]
        item["stage"] = "font_size"
        state.track_stage(user.id, "video_font_size", item["token"], "menu:services")
        item.pop("font_size", None)
        item.pop("amount", None)
        item.pop("package_id", None)
        await query.answer()
        await query.edit_message_text(ui.screen("اندازهٔ زیرنویس", "اندازهٔ مناسب نمایش را انتخاب کن:", icon="🔠"),
            parse_mode="HTML", reply_markup=InlineKeyboardMarkup([
            [ui.button("کوچک", f"vclip:size:{item['token']}:small"),
             ui.button("متوسط", f"vclip:size:{item['token']}:medium", style="primary")],
            [ui.button("بزرگ", f"vclip:size:{item['token']}:large")],
            [ui.button("✕ لغو", f"vclip:cancel:{item['token']}")],
        ]))
    elif action == "size" and len(parts) == 4 and parts[3] in FONT_SIZE_LABELS and item.get("stage") == "font_size" and item.get("mode") in {"caption", "both"} and item.get("font") in FONT_FILES and item.get("color") in {"yellow", "green", "blue", "white"} and item.get("language") in {"fa", "en", "auto"}:
        item["font_size"] = parts[3]
        await query.answer()
        await _quote(query, state, user.id, item)
    elif action == "cancel":
        pending.pop(user.id, None)
        state.clear_stage(user.id, item["token"])
        await query.answer()
        await query.edit_message_text(ui.screen("درخواست لغو شد", "هر زمان خواستی می‌توانی دوباره شروع کنی.", icon="✖️"),
                                      parse_mode="HTML", reply_markup=ui.back_keyboard("menu:services"))
    elif action == "confirm" and item.get("stage") == "payment" and item.get("amount") and item.get("mode") == "caption" and item.get("color") and item.get("language") in {"fa", "en", "auto"} and item.get("font") in FONT_FILES and item.get("font_size") in FONT_SIZE_LABELS:
        package_id = parts[3] if len(parts) == 4 else None
        if len(parts) not in {3, 4} or (package_id and package_id != item.get("package_id")):
            await query.answer("روش پرداخت معتبر نیست.", show_alert=True)
            return
        if user.id in state.active or user.id in state.pending_by_user:
            await query.answer("یک سفارش باز داری.", show_alert=True)
            return
        if item["mode"] in {"caption", "both"} and not (Path(state.settings.caption_model_path) / "model.bin").is_file():
            await query.answer("مدل رونویسی محلی نصب نشده است؛ هزینه‌ای کسر نشد.", show_alert=True)
            return
        if item["mode"] in {"caption", "both"} and not (Path(state.settings.caption_fonts_dir) / FONT_FILES[item["font"]]).is_file():
            await query.answer("فونت انتخاب‌شده روی سرور نصب نشده است؛ هزینه‌ای کسر نشد.", show_alert=True)
            return
        item["confirming"] = True
        item["stage"] = "confirming"
        state.track_stage(user.id, "video_confirming", item["token"], "menu:services")
        await query.answer()
        job_id = uuid.uuid4().hex
        try:
            if package_id:
                balance = await state.database.create_package_job(
                    job_id=job_id, user_id=user.id, chat_id=query.message.chat_id, url="telegram-upload",
                    selected_height=None, mode="subtitle", api_provider=state.api_provider,
                    billable_minutes=item["minutes"], package_id=package_id,
                )
            else:
                balance = await state.database.create_wallet_job(
                    job_id=job_id, user_id=user.id, chat_id=query.message.chat_id, url="telegram-upload",
                    selected_height=None, mode="subtitle", api_provider=state.api_provider,
                    billable_minutes=item["minutes"], amount_toman=item["amount"],
                )
        except Exception:
            item["confirming"] = False
            item["stage"] = "payment"
            state.track_stage(user.id, "video_payment", item["token"], "menu:services")
            logger.exception("Could not create caption job")
            await query.edit_message_text(ui.screen("ثبت سفارش انجام نشد", "لطفاً دوباره تلاش کن.", icon="⚠️"), parse_mode="HTML")
            return
        if balance is None:
            item["confirming"] = False
            item["stage"] = "payment"
            state.track_stage(user.id, "video_payment", item["token"], "menu:services")
            await query.edit_message_text(ui.screen("پرداخت انجام نشد", "بسته معتبر نیست یا موجودی کیف پول کافی نیست. دوباره تلاش کن.", icon="⚠️"),
                                          parse_mode="HTML", reply_markup=ui.wallet_keyboard())
            return
        job = VideoCaptionJob(job_id, user.id, query.message.chat_id, query.message.message_id,
                              item["file_id"], item["mode"], item["color"], item["minutes"],
                              item["minutes"] if package_id else 0,
                              language=None if item["language"] == "auto" else item["language"],
                              font=item.get("font", "vazirmatn"), font_size=item.get("font_size", "medium"))
        pending.pop(user.id, None)
        state.clear_stage(user.id, item["token"])
        state.active[user.id] = job
        running = int(len(state.active) > state.queue.qsize() + 1)
        position = state.queue.qsize() + running + 1
        state.queue.put_nowait(job)
        balance_text = f"باقی‌ماندهٔ بسته: {balance} دقیقه" if package_id else f"موجودی: {balance:,} تومان"
        await query.edit_message_text(ui.screen("سفارش ثبت شد",
            f"جایگاه در صف: {position}\n{balance_text}\n\nپس از آماده‌شدن، خروجی همین‌جا ارسال می‌شود.", icon="✅"),
            parse_mode="HTML", reply_markup=ui.job_keyboard(job.id))
    else:
        await query.answer("این انتخاب دیگر معتبر نیست.", show_alert=True)


async def _quote(query, state, user_id, item):
    item["stage"] = "payment"
    state.track_stage(user_id, "video_payment", item["token"], "menu:services")
    rate = max(1, int(await state.database.get_setting("price_subtitle_toman_per_minute", str(state.settings.default_subtitle_price_toman_per_minute))))
    item["minutes"] = max(1, ceil(item["duration"] / 60))
    item["amount"] = item["minutes"] * rate
    balance = await state.database.get_wallet_balance(user_id)
    packages = await state.database.available_minutes(user_id)
    package = next((p for p in packages if p["mode"] == "subtitle" and p["minutes"] >= item["minutes"]), None)
    item["package_id"] = package["id"] if package else None
    payment = [ui.button("✓ پرداخت از کیف پول", f"vclip:confirm:{item['token']}", style="success")]
    if package:
        payment.append(ui.button("🎟 استفاده از بسته", f"vclip:confirm:{item['token']}:{package['id']}", style="primary"))
    language_note = "" if item["mode"] == "color" else f"\nزبان گفتار: { {'fa': 'فارسی', 'en': 'انگلیسی', 'auto': 'تشخیص خودکار'}[item['language']] }"
    style_note = "" if item["mode"] == "color" else (
        f"\nفونت: {FONT_LABELS[item['font']]} · اندازه: {FONT_SIZE_LABELS[item['font_size']]}"
        if item.get("font") in FONT_LABELS and item.get("font_size") in FONT_SIZE_LABELS else ""
    )
    await query.edit_message_text(ui.screen("بررسی زیرنویس و پرداخت",
        f"مدت قابل محاسبه: {item['minutes']} دقیقه\nتعرفه: {rate:,} تومان در دقیقه\n"
        f"هزینه: {item['amount']:,} تومان · موجودی: {balance:,} تومان{language_note}{style_note}\n\n"
        "پردازش گفتار روی سرور انجام می‌شود.", icon="🧾"),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([payment,
                                           [ui.button("✕ لغو", f"vclip:cancel:{item['token']}")]]),
    )


async def receive_video(update, context):
    user, message = update.effective_user, update.effective_message
    if not user or not message or message.chat.type != "private":
        return
    item = _pending(context.application).get(user.id)
    if not item or item.get("stage") != "video":
        return
    video = message.video or message.document
    if not video:
        return
    if not video.file_size or video.file_size > MAX_INPUT:
        await ui.reply(message, ui.screen("محدودیت ویدیو", "حداکثر مدت ۹۰ ثانیه و حداکثر حجم ۲۰ مگابایت است.", icon="⚠️"), parse_mode="HTML")
        raise ApplicationHandlerStop
    duration = getattr(video, "duration", None)
    if duration is None:
        await ui.reply(message, ui.screen("در حال بررسی ویدیو", "لطفاً چند لحظه صبر کن…", icon="⏳"), parse_mode="HTML")
        try:
            with tempfile.TemporaryDirectory(prefix="caption-probe-", dir=context.application.bot_data["state"].settings.work_dir) as temp:
                source = Path(temp).resolve() / "input"
                file = await context.application.bot.get_file(video.file_id)
                if file.file_size and file.file_size > MAX_INPUT:
                    raise ValueError("حجم ویدیو بیشتر از ۲۰ مگابایت است.")
                await file.download_to_drive(custom_path=source, read_timeout=120, write_timeout=120)
                if source.stat().st_size > MAX_INPUT:
                    raise ValueError("حجم ویدیو بیشتر از ۲۰ مگابایت است.")
                duration = (await asyncio.to_thread(probe, source))["duration"]
        except Exception as exc:
            logger.exception("Could not inspect uploaded video")
            detail = str(exc) if isinstance(exc, ValueError) else "بررسی فایل ویدیو ممکن نشد؛ دوباره تلاش کن."
            await ui.reply(message, ui.screen("بررسی ویدیو ناموفق بود", detail, icon="⚠️"), parse_mode="HTML")
            raise ApplicationHandlerStop
    if duration <= 0 or duration > 90:
        await ui.reply(message, ui.screen("محدودیت ویدیو", "حداکثر مدت ۹۰ ثانیه و حداکثر حجم ۲۰ مگابایت است.", icon="⚠️"), parse_mode="HTML")
        raise ApplicationHandlerStop
    token = uuid.uuid4().hex[:12]
    item.update(stage="options", token=token, file_id=video.file_id, duration=duration)
    context.application.bot_data["state"].track_stage(
        user.id, "video_options", token, "menu:services"
    )
    await ui.reply(message, ui.screen("نوع پردازش", "برای ویدیو زیرنویس فارسی بساز.", icon="📝"),
        parse_mode="HTML", reply_markup=InlineKeyboardMarkup([
        [ui.button("📝 فقط زیرنویس", f"vclip:mode:{token}:caption")],
        [ui.button("✕ لغو", f"vclip:cancel:{token}")],
    ]))
    raise ApplicationHandlerStop


async def run_job(application, state, job):
    progress_queue = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def progress(text):
        loop.call_soon_threadsafe(progress_queue.put_nowait, text)

    async def update_progress():
        while (text := await progress_queue.get()) is not None:
            try:
                await application.bot.edit_message_text(ui.plain_screen(text), parse_mode="HTML",
                                                       chat_id=job.chat_id, message_id=job.message_id)
            except Exception:
                logger.exception("Could not update caption job progress")

    updater = asyncio.create_task(update_progress())
    progress_stopped = False
    delivered = False
    try:
        await state.database.update_job(job.id, "running")
        if job.cancel_event.is_set():
            raise InterruptedError("لغو شد")
        with tempfile.TemporaryDirectory(prefix="caption-", dir=state.settings.work_dir) as temp:
            directory = Path(temp).resolve()
            source, output = directory / "input.mp4", directory / "output.mp4"
            progress("📥 در حال دریافت ویدیو…")
            file = await application.bot.get_file(job.file_id)
            if file.file_size and file.file_size > MAX_INPUT:
                raise ValueError("حجم ویدیو بیشتر از ۲۰ مگابایت است.")
            await file.download_to_drive(custom_path=source, read_timeout=120, write_timeout=120)
            if source.stat().st_size > MAX_INPUT:
                raise ValueError("حجم ویدیو بیشتر از ۲۰ مگابایت است.")
            checked = await asyncio.to_thread(probe, source)
            if ceil(checked["duration"] / 60) > job.billable_minutes:
                raise ValueError("مدت واقعی ویدیو با مدت اعلام‌شده متفاوت است؛ ویدیو را دوباره ارسال کن.")
            try:
                meta, language, has_words = await asyncio.to_thread(
                    render, source, output, job.edit_mode, job.color, state.settings.caption_model_path,
                    Path(state.settings.caption_fonts_dir), job.cancel_event, progress,
                    GradeSettings(background_brightness=state.settings.caption_background_brightness,
                                  background_saturation=state.settings.caption_background_saturation,
                                  subject_saturation=state.settings.caption_subject_saturation,
                                  contrast=state.settings.caption_contrast,
                                  mask_smoothing=state.settings.caption_mask_smoothing),
                    language=job.language, font=job.font, font_size=job.font_size,
                )
            except Exception as exc:
                log = directory / "ffmpeg.log"
                if log.exists():
                    logger.error("ffmpeg job %s: %s", job.id, log.read_text(errors="replace")[-8000:])
                if getattr(exc, "stderr", None):
                    logger.error("ffmpeg job %s: %r", job.id, exc.stderr[-8000:])
                raise
            if job.cancel_event.is_set():
                raise InterruptedError("لغو شد")
            progress_queue.put_nowait(None)
            await updater
            progress_stopped = True
            job.delivery_started = True
            if output.stat().st_size <= 48_000_000:
                with output.open("rb") as media:
                    await application.bot.send_video(job.chat_id, media, width=meta["width"], height=meta["height"],
                                                     duration=ceil(meta["duration"]), supports_streaming=True,
                                                     read_timeout=120, write_timeout=120)
            elif state.settings.download_base_url:
                token = await asyncio.to_thread(publish_download, output, Path(state.settings.download_dir), state.settings.download_ttl_hours)
                await state.database.add_download(job.id, token, "video-fa.mp4", output.stat().st_size,
                                                  datetime.now(UTC) + timedelta(hours=state.settings.download_ttl_hours))
                await application.bot.send_message(
                    job.chat_id,
                    ui.screen("ویدیو آماده است", f"لینک دریافت: {state.settings.download_base_url}/{token}.mp4", icon="⬇️"),
                    parse_mode="HTML", disable_web_page_preview=True,
                )
            else:
                raise ValueError("ویدیو برای ارسال تلگرام بزرگ است و لینک دانلود تنظیم نشده است.")
            delivered = True
            await state.database.update_job(job.id, "completed", size=output.stat().st_size, cost_usd=0)
        language_name = {"fa": "فارسی", "en": "انگلیسی"}.get(language, language)
        grading_skipped = meta.get("color_correction_skipped_timing", False)
        if job.edit_mode != "color" and not has_words:
            result_note = "گفتاری پیدا نشد." if grading_skipped else "گفتاری پیدا نشد؛ اصلاح رنگ انجام شد."
        else:
            result_note = f"زبان {'انتخاب‌شده' if job.language else 'تشخیص‌داده‌شده'}: {language_name}" if language else ""
        if grading_skipped:
            if result_note:
                result_note += "\n"
            result_note += "اصلاح رنگ به‌دلیل نرخ فریم متغیر یا نامشخص انجام نشد تا هم‌زمانی صدای اصلی و تصویر حفظ شود."
            if has_words:
                result_note += " زیرنویس با زمان‌بندی اصلی درج شد."
        await application.bot.edit_message_text(ui.screen("ویدیوی پردازش‌شده آماده است", result_note, icon="✅"),
            parse_mode="HTML", chat_id=job.chat_id, message_id=job.message_id)
    except Exception as exc:
        logger.exception("Caption job %s failed", job.id)
        try:
            if delivered:
                await state.database.update_job(job.id, "completed")
            else:
                await state.database.update_job(job.id, "cancelled" if isinstance(exc, InterruptedError) else "failed", error=str(exc))
                refund = await state.database.refund_job_wallet(job.id)
                note = ((f"{refund['package_minutes']} دقیقه به بسته برگشت." if refund.get("package_minutes") else "هزینه به کیف پول برگشت.")
                        if refund and refund.get("refunded") else "برای پیگیری با پشتیبانی تماس بگیر.")
                detail = str(exc) if isinstance(exc, ValueError) else "پردازش به پایان نرسید."
                await application.bot.send_message(job.chat_id,
                    ui.screen("پردازش ناموفق بود", f"{detail}\n{note}", icon="⚠️"), parse_mode="HTML")
        except Exception:
            logger.exception("Could not refund caption job %s", job.id)
    finally:
        if not progress_stopped:
            progress_queue.put_nowait(None)
            await updater
        state.active.pop(job.user_id, None)
        state.queue.task_done()


def register(application):
    application.add_handler(CallbackQueryHandler(callback, pattern=r"^vclip:"))
    application.add_handler(MessageHandler(filters.VIDEO | filters.Document.VIDEO, receive_video), group=-1)
