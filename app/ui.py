"""Reusable Telegram screens and button styles for the customer journey."""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def button(text: str, action: str, *, style: str | None = None) -> InlineKeyboardButton:
    return InlineKeyboardButton(text, callback_data=action, style=style)


def home_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [button('🎬 سفارش جدید', 'menu:new', style='primary')],
        [button('👛 کیف پول', 'wallet:balance'), button('💎 تعرفه‌ها', 'menu:pricing')],
        [button('📦 سفارش من', 'menu:status'), button('📒 گردش حساب', 'menu:history')],
        [button('📝 خروجی‌های تکمیلی و ویرایش', 'content:list', style='primary')],
        [button('🎟 بسته‌های دقیقه', 'packs:list')],
        [button('👥 تیم', 'menu:team'), button('💬 پشتیبانی', 'menu:support')],
        [button('📖 راهنما و شرایط', 'menu:help')],
    ])


def home_text(balance: int) -> str:
    return (
        '🎬 <b>ویدیو فارسی</b>\n'
        'زیرنویس و دوبلهٔ یوتیوب · دانلود رسانه از شبکه‌های اجتماعی\n\n'
        '۱  لینک ویدیو یا آهنگ را بفرست\n'
        '۲  نوع خروجی را انتخاب کن\n'
        '۳  سفارش پردازش را تأیید کن یا دانلود را شروع کن\n\n'
        f'👛 موجودی شما: <b>{balance:,} تومان</b>\n'
        'برای شروع، لینک را همین‌جا بفرست یا از منوی زیر استفاده کن.'
    )


def mode_keyboard(token: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [button('📝 زیرنویس فارسی', f'mode:{token}:subtitle', style='primary')],
        [button('🎙 دوبلهٔ فارسی', f'mode:{token}:dub')],
        [button('✕ لغو سفارش', f'order_cancel:{token}', style='danger')],
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
        [button('‹ تغییر خروجی', f'order_back:{token}'),
         button('✕ لغو سفارش', f'order_cancel:{token}', style='danger')],
    ])


def wallet_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [button('➕ شارژ کیف پول', 'wallet:topup', style='success')],
        [button('📒 گردش حساب', 'menu:history'), button('⌂ منوی اصلی', 'menu:home')],
    ])


def back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[button('⌂ منوی اصلی', 'menu:home')]])
