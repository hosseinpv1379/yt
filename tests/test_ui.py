import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app import ui
from app.bot import BotState, _prompt_topup, receive_link, payment_support


class KeyboardTests(unittest.TestCase):
    def test_home_and_order_buttons_have_telegram_styles(self):
        self.assertEqual(ui.home_keyboard().inline_keyboard[0][0].to_dict()['style'], 'primary')
        buttons = ui.confirmation_keyboard('abc').to_dict()['inline_keyboard']
        self.assertEqual(buttons[0][0]['style'], 'success')
        self.assertEqual(buttons[1][1]['style'], 'danger')
        self.assertEqual(buttons[0][0]['callback_data'], 'confirm:abc')


class InputFlowTests(unittest.IsolatedAsyncioTestCase):
    def make_context(self):
        settings = SimpleNamespace(default_api_provider='openai', card_to_card_number='1234567890123456',
            card_to_card_holder='Test', minimum_wallet_topup_toman=50000,
            provider_control_user_id=99, support_username='support')
        db = SimpleNamespace(upsert_user=AsyncMock(), has_accepted_terms=AsyncMock(return_value=True),
            get_user_pending_deposit=AsyncMock(return_value=None), create_deposit_request=AsyncMock(return_value=True))
        state = BotState(settings, db)
        message = SimpleNamespace(chat=SimpleNamespace(type='private'), chat_id=1, text='', reply_text=AsyncMock())
        user = SimpleNamespace(id=1, username='user')
        update = SimpleNamespace(effective_user=user, effective_message=message, callback_query=None)
        context = SimpleNamespace(application=SimpleNamespace(bot_data={'state': state}, bot=SimpleNamespace(send_message=AsyncMock())), args=[])
        return state, db, update, context

    async def test_topup_accepts_amount_without_command(self):
        state, db, update, context = self.make_context()
        await _prompt_topup(update, context)
        self.assertIn(1, state.awaiting_topup)
        update.effective_message.text = '۲۰۰٬۰۰۰'
        await receive_link(update, context)
        self.assertEqual(db.create_deposit_request.call_args.args[-1], 200000)
        self.assertNotIn(1, state.awaiting_topup)
        self.assertIn('شماره کارت', update.effective_message.reply_text.call_args.args[0])

    async def test_support_message_is_sent_once_and_exits_input_mode(self):
        state, db, update, context = self.make_context()
        await payment_support(update, context)
        self.assertIn(1, state.awaiting_support)
        update.effective_message.text = 'لطفاً پرداخت را بررسی کنید'
        await receive_link(update, context)
        context.application.bot.send_message.assert_awaited_once()
        self.assertNotIn(1, state.awaiting_support)
        db.create_deposit_request.assert_not_awaited()
