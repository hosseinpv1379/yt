import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app import ui
from app.bot import BotState, admin_callback, orders_callback, receive_link


def callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


class BotScopeTests(unittest.IsolatedAsyncioTestCase):
    def test_menus_offer_subtitle_dubbing_and_payment_only(self):
        all_buttons = callbacks(ui.home_keyboard()) + callbacks(ui.services_keyboard()) + callbacks(ui.orders_keyboard()) + callbacks(ui.support_keyboard())
        self.assertIn('vclip:start', all_buttons)
        self.assertIn('wallet:balance', all_buttons)
        self.assertFalse(any(value.startswith(('image:', 'content:', 'dl:', 'team:')) or value == 'menu:team' for value in all_buttons))

    async def test_old_admin_image_button_is_rejected(self):
        state = BotState(SimpleNamespace(default_api_provider='openai', provider_control_user_id=1), SimpleNamespace())
        query = SimpleNamespace(data='admin:images', answer=AsyncMock(), edit_message_text=AsyncMock())
        await admin_callback(SimpleNamespace(callback_query=query, effective_user=SimpleNamespace(id=1)),
                             SimpleNamespace(application=SimpleNamespace(bot_data={'state': state})))
        self.assertTrue(query.answer.call_args.kwargs['show_alert'])
        query.edit_message_text.assert_not_awaited()

    async def test_old_download_order_button_is_rejected(self):
        db = SimpleNamespace(list_orders=AsyncMock())
        state = BotState(SimpleNamespace(default_api_provider='openai'), db)
        query = SimpleNamespace(data='orders:list:download:0', answer=AsyncMock(), message=SimpleNamespace(chat=SimpleNamespace(type='private')))
        await orders_callback(SimpleNamespace(callback_query=query, effective_user=SimpleNamespace(id=1)),
                              SimpleNamespace(application=SimpleNamespace(bot_data={'state': state})))
        db.list_orders.assert_not_awaited()
        self.assertTrue(query.answer.call_args.kwargs['show_alert'])

    async def test_non_youtube_link_does_not_open_download_flow(self):
        db = SimpleNamespace(upsert_user=AsyncMock(), get_user_pending_deposit=AsyncMock(return_value=None))
        state = BotState(SimpleNamespace(default_api_provider='openai'), db)
        message = SimpleNamespace(chat=SimpleNamespace(type='private'), text='https://www.instagram.com/p/abc/', reply_text=AsyncMock())
        update = SimpleNamespace(effective_user=SimpleNamespace(id=1), effective_message=message)
        await receive_link(update, SimpleNamespace(application=SimpleNamespace(bot_data={'state': state})))
        self.assertIn('یوتیوب', message.reply_text.call_args.args[0])
        self.assertFalse(state.pending_quality)

    async def test_old_color_only_callback_cannot_create_an_order(self):
        from features.video_captions.handlers import callback
        db = SimpleNamespace(create_wallet_job=AsyncMock())
        state = BotState(SimpleNamespace(default_api_provider='openai'), db)
        item = {'token': 'test', 'duration': 20, 'file_id': 'video'}
        app = SimpleNamespace(bot_data={'state': state, 'video_captions_pending': {1: item}})
        query = SimpleNamespace(data='vclip:mode:test:color', answer=AsyncMock(),
                                message=SimpleNamespace(chat=SimpleNamespace(type='private')))
        await callback(SimpleNamespace(callback_query=query, effective_user=SimpleNamespace(id=1)), SimpleNamespace(application=app))
        self.assertTrue(query.answer.call_args.kwargs['show_alert'])
        db.create_wallet_job.assert_not_awaited()
        self.assertNotIn('mode', item)
