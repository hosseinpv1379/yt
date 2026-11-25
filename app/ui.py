"""Reusable Telegram screens and button styles for the customer journey."""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def button(text: str, action: str, *, style: str | None = None) -> InlineKeyboardButton:
    return InlineKeyboardButton(text, callback_data=action, style=style)


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
        'لینک را بفرست یا از منو انتخاب کن.\n'
        f'👛 موجودی: <b>{balance:,} تومان</b>'
    )


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
