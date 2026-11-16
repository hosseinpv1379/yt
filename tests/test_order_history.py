import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from telegram.error import BadRequest
from app.bot import BotState, _edit_query_screen, _order_active_link, orders_callback


class OrderLinkTests(unittest.TestCase):
    def test_link_expiry_status_and_file_presence(self):
        now = datetime.now(UTC); token = 'a' * 32
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = SimpleNamespace(download_dir=tmp, download_base_url='https://downloads.test')
            order = {'status': 'completed', 'links': [{'token': token, 'filename': 'video.mp4', 'expires_at': now + timedelta(hours=1)}]}
            self.assertIsNone(_order_active_link(order, 'processing', settings, now))
            (root / f'{token}.mp4').touch(); (root / f'{token}.html').touch()
            self.assertEqual(_order_active_link(order, 'processing', settings, now)[0], 'https://downloads.test/' + token)
            self.assertIsNone(_order_active_link(order, 'processing', settings, now + timedelta(hours=2)))
            order['status'] = 'failed'
            self.assertIsNone(_order_active_link(order, 'processing', settings, now))

    def test_download_link_uses_only_approved_extension_and_token(self):
        now = datetime.now(UTC)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); token = 'b' * 32
            (root / f'{token}.mp3').touch()
            settings = SimpleNamespace(download_dir=tmp, download_base_url='https://downloads.test')
            order = {'status': 'completed', 'token': token, 'extension': 'mp3', 'expires_at': now + timedelta(minutes=1)}
            self.assertEqual(_order_active_link(order, 'download', settings, now)[0], f'https://downloads.test/{token}.mp3')
            order['extension'] = 'html'
            self.assertIsNone(_order_active_link(order, 'download', settings, now))
            order['extension'] = 'mp3'; order['token'] = '../' + token
            self.assertIsNone(_order_active_link(order, 'download', settings, now))


class OrderHistoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_identical_edits_are_ignored_but_other_errors_propagate(self):
        query = SimpleNamespace(message=None, edit_message_text=AsyncMock(side_effect=BadRequest('Message is not modified')))
        await _edit_query_screen(query, 'same')
        query.edit_message_text.side_effect = BadRequest('Message to edit not found')
        with self.assertRaises(BadRequest):
            await _edit_query_screen(query, 'different')

    def context(self, db, user_id=11):
        state = BotState(SimpleNamespace(default_api_provider='openai', download_base_url='', download_dir='/tmp'), db)
        query = SimpleNamespace(data='', message=SimpleNamespace(chat=SimpleNamespace(type='private'), reply_text=AsyncMock()),
                                answer=AsyncMock(), edit_message_text=AsyncMock())
        return query, SimpleNamespace(callback_query=query, effective_user=SimpleNamespace(id=user_id)), SimpleNamespace(application=SimpleNamespace(bot_data={'state': state}))

    async def test_detail_is_scoped_to_current_user(self):
        db = SimpleNamespace(get_owned_order=AsyncMock(return_value=None))
        query, update, context = self.context(db)
        query.data = 'orders:detail:processing:' + 'a' * 32 + ':0'
        await orders_callback(update, context)
        db.get_owned_order.assert_awaited_once_with(11, 'processing', 'a' * 32)
        query.edit_message_text.assert_not_awaited()
        self.assertIn('پیدا نشد', query.answer.call_args.args[0])

    async def test_pages_have_next_and_no_other_users(self):
        now = datetime.now(UTC)
        rows = [{'id': f'{i:032x}', 'status': 'completed', 'kind': 'subtitle', 'created_at': now} for i in range(6)]
        db = SimpleNamespace(list_orders=AsyncMock(return_value=rows))
        query, update, context = self.context(db)
        query.data = 'orders:list:processing:0'
        await orders_callback(update, context)
        db.list_orders.assert_awaited_once_with(11, 'processing', 0, 6)
        markup = query.edit_message_text.call_args.kwargs['reply_markup'].to_dict()
        buttons = [b for row in markup['inline_keyboard'] for b in row]
        self.assertTrue(any(b.get('callback_data') == 'orders:list:processing:1' for b in buttons))
        self.assertTrue(all(len(b.get('callback_data', '').encode()) <= 64 for b in buttons))
