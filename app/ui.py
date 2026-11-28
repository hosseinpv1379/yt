"""Reusable Telegram screens, safe HTML formatting, and button styles."""
from html import escape, unescape
import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def video_filename(title: str, suffix: str = ".mp4") -> str:
    """Preserve the video title while producing a portable filename."""
    title = re.sub(r'[<>:"/\\|?*\x00-\x1f\x7f]', " ", title)
    title = " ".join(title.split()).strip(" .")
    if title.lower().endswith(suffix.lower()):
        title = title[:-len(suffix)].rstrip(" .")
    title = title.encode("utf-8")[:180].decode("utf-8", errors="ignore").rstrip(" .")
    if re.fullmatch(r"(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?", title):
        title = f"ویدیو {title}"
    return f"{title or 'ویدیو'}{suffix}"


def html_escape(value: object) -> str:
    """Escape dynamic values before placing them in a Telegram HTML message."""
    return escape(str(value), quote=False)


def screen(title: str, body: str = "", *, icon: str = "") -> str:
    """Build a consistent, safe HTML screen from plain text."""
    heading = f"{icon} <b>{html_escape(title)}</b>" if icon else f"<b>{html_escape(title)}</b>"
    return f"{heading}\n\n{html_escape(body)}" if body else heading


def plain_screen(text: str) -> str:
    """Format an ordinary screen and escape every part before HTML parsing."""
    title, separator, body = text.strip().partition("\n")
    if not title:
        return html_escape(text)
    return screen(title.strip(), body.strip() if separator else "")


async def reply(message, text: str, **kwargs):
    """Send a safely formatted screen for plain replies and forms."""
    if kwargs.get("parse_mode") is None:
        text = plain_screen(text)
        kwargs["parse_mode"] = "HTML"
    return await message.reply_text(text, **kwargs)


def truncate_text(text: str, max_units: int, suffix: str = "…") -> str:
    """Truncate text by Telegram's UTF-16 limit without splitting a character."""
    if len(text.encode("utf-16-le")) // 2 <= max_units:
        return text
    budget = max(0, max_units - len(suffix.encode("utf-16-le")) // 2)
    output = []
    units = 0
    for char in text:
        char_units = len(char.encode("utf-16-le")) // 2
        if units + char_units > budget:
            break
        output.append(char)
        units += char_units
    return "".join(output).rstrip() + suffix


def plain_from_html(text: str) -> str:
    """Turn our small HTML subset back into readable text for length fallbacks."""
    return unescape(re.sub(r"</?(?:b|i|u|s|code|pre|blockquote)>", "", text))


def button(text: str, action: str, *, style: str | None = None) -> InlineKeyboardButton:
    if not action or len(action.encode("utf-8")) > 64:
        raise ValueError("Telegram callback data must contain 1 to 64 bytes")
    return InlineKeyboardButton(truncate_text(text, 64), callback_data=action, style=style)


def home_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [button('🎬 سفارش جدید', 'menu:new', style='primary')],
        [button('📦 سفارش‌های من', 'orders:home', style='primary')],
        [button('👛 کیف پول', 'wallet:balance')],
        [button('✨ خدمات', 'menu:services')],
        [button('💬 پشتیبانی', 'menu:support')],
    ])


def services_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [button('📝 زیرنویس ویدیوی ارسالی', 'vclip:start', style='primary')],
        [button('🎟 بسته‌های دقیقه', 'packs:list')],
        [button('💎 تعرفه‌ها', 'menu:pricing')],
        [button('‹ بازگشت', 'menu:home')],
    ])


def support_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [button('✉️ ارسال پیام', 'menu:contact', style='primary')],
        [button('📖 راهنما', 'menu:help')],
        [button('📜 شرایط استفاده', 'menu:terms')],
        [button('‹ بازگشت', 'menu:home')],
    ])


def orders_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [button('🎬 زیرنویس و دوبله', 'orders:list:processing:0', style='primary')],
        [button('⏳ سفارش فعال', 'menu:status')],
        [button('‹ بازگشت', 'menu:home')],
    ])


def home_text(balance: int) -> str:
    return (
        '🎬 <b>ویدیو فارسی</b>\n'
        'زیرنویس و دوبلهٔ ویدیو\n\n'
        'برای شروع، لینک ویدیو را بفرست یا یکی از گزینه‌های زیر را انتخاب کن.\n'
        f'👛 موجودی کیف پول: <b>{balance:,} تومان</b>'
    )


def pricing_text(subtitle: int, dub: int) -> str:
    return (
        "💎 <b>تعرفهٔ خدمات</b>\n\n"
        f"📝 زیرنویس فارسی · <b>{subtitle:,} تومان</b> به‌ازای هر دقیقه\n"
        f"🎙 دوبلهٔ فارسی · <b>{dub:,} تومان</b> به‌ازای هر دقیقه\n\n"
        "هزینهٔ نهایی پیش از ثبت سفارش نمایش داده می‌شود."
    )


def wallet_text(balance: int) -> str:
    return f"👛 <b>کیف پول</b>\n\nموجودی فعلی: <b>{balance:,} تومان</b>"


def mode_keyboard(token: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [button('📝 زیرنویس فارسی', f'mode:{token}:subtitle', style='primary')],
        [button('🎙 دوبلهٔ فارسی', f'mode:{token}:dub')],
        [button('‹ بازگشت (لغو سفارش)', f'order_cancel:{token}', style='danger')],
    ])


def quality_keyboard(token: str, heights: list[int]) -> InlineKeyboardMarkup:
    buttons = [button(f'{height}p' if height else 'انتخاب خودکار', f'quality:{token}:{height}')
               for height in (heights or [0])]
    return InlineKeyboardMarkup([buttons[i:i + 2] for i in range(0, len(buttons), 2)] + [
        [button('‹ تغییر نوع خروجی', f'order_back:{token}'),
         button('✕ لغو', f'order_cancel:{token}', style='danger')],
    ])


def confirmation_keyboard(token: str, package_id: str | None = None) -> InlineKeyboardMarkup:
    purchase = [button('✓ پرداخت از کیف پول', f'confirm:{token}', style='success')]
    if package_id:
        purchase.append(button('🎟 استفاده از بسته', f'confirm:{token}:{package_id}', style='primary'))
    return InlineKeyboardMarkup([
        purchase,
        [button('‹ تغییر کیفیت', f'order_quality_back:{token}'),
         button('✕ لغو سفارش', f'order_cancel:{token}', style='danger')],
    ])


def wallet_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [button('➕ شارژ کیف پول', 'wallet:topup', style='success')],
        [button('📒 گردش حساب', 'menu:history')],
        [button('‹ بازگشت', 'menu:home')],
    ])


def back_keyboard(action: str = 'menu:home') -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[button('‹ بازگشت', action)]])


def cancel_keyboard(cancel_action: str, back_action: str | None = None) -> InlineKeyboardMarkup:
    rows = [[button('✕ لغو', cancel_action, style='danger')]]
    if back_action:
        rows.append([button('‹ بازگشت', back_action)])
    return InlineKeyboardMarkup(rows)


def job_keyboard(job_id: str, *, cancellable: bool = True) -> InlineKeyboardMarkup:
    rows = []
    if cancellable:
        rows.append([button('✕ لغو این سفارش', f'job_cancel:{job_id}', style='danger')])
    rows.append([button('📦 سفارش‌های من', 'orders:home'), button('‹ بازگشت', 'menu:home')])
    return InlineKeyboardMarkup(rows)
