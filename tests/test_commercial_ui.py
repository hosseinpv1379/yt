import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app import model_catalog
from app.bot import BotState, content_callback, packages_callback, _job_refund_note, Job
from pathlib import Path


class CommercialUiTests(unittest.IsolatedAsyncioTestCase):
    async def test_disabled_content_never_charges(self):
        db = SimpleNamespace(owned_subtitle=AsyncMock(return_value='test'), get_setting=AsyncMock(return_value='0'), create_content_order=AsyncMock())
        state = BotState(SimpleNamespace(default_api_provider='openai'), db)
        query = SimpleNamespace(data='content:quote:summary:' + 'a' * 32, message=SimpleNamespace(chat=SimpleNamespace(type='private')), answer=AsyncMock(), edit_message_text=AsyncMock())
        update = SimpleNamespace(callback_query=query, effective_user=SimpleNamespace(id=1))
        await content_callback(update, SimpleNamespace(application=SimpleNamespace(bot_data={'state': state})))
        db.create_content_order.assert_not_awaited()
        self.assertIn('فعال نشده', query.answer.call_args.args[0])

    async def test_quote_user_binding_and_one_purchase(self):
        db = SimpleNamespace(get_setting=AsyncMock(return_value='100:400000:30'), purchase_minutes=AsyncMock(return_value='purchased'))
        state = BotState(SimpleNamespace(default_api_provider='openai'), db)
        msg = SimpleNamespace(chat=SimpleNamespace(type='private'))
        query = SimpleNamespace(data='packs:quote:subtitle', message=msg, answer=AsyncMock(), edit_message_text=AsyncMock())
        update = SimpleNamespace(callback_query=query, effective_user=SimpleNamespace(id=1))
        context = SimpleNamespace(application=SimpleNamespace(bot_data={'state': state}))
        await packages_callback(update, context)
        token = next(iter(state.package_quotes))
        query.data = 'packs:buy:' + token
        update.effective_user.id = 2
        await packages_callback(update, context)
        db.purchase_minutes.assert_not_awaited()
        update.effective_user.id = 1
        await packages_callback(update, context)
        await packages_callback(update, context)
        db.purchase_minutes.assert_awaited_once_with(1, 'subtitle', 100, 400000, 30)

    def test_package_refund_message_is_clear(self):
        job = Job(id='a', user_id=1, chat_id=1, url='u', message_id=1, directory=Path('/tmp'),
                  selected_height=None, mode='subtitle', api_provider='openai', draft_id=1, can_use_draft=False,
                  package_minutes=3)
        self.assertIn('بسته', _job_refund_note(job, True))
        self.assertNotIn('کیف پول', _job_refund_note(job, True))

    async def test_disabled_plan_cannot_be_purchased_from_old_quote(self):
        db = SimpleNamespace(get_setting=AsyncMock(return_value='0'), purchase_minutes=AsyncMock())
        state = BotState(SimpleNamespace(default_api_provider='openai'), db)
        state.package_quotes['token'] = (1, 'subtitle', 100, 400000, 30)
        query = SimpleNamespace(data='packs:buy:token', message=SimpleNamespace(chat=SimpleNamespace(type='private')),
                                answer=AsyncMock(), edit_message_text=AsyncMock())
        update = SimpleNamespace(callback_query=query, effective_user=SimpleNamespace(id=1))
        context = SimpleNamespace(application=SimpleNamespace(bot_data={'state': state}))
        await packages_callback(update, context)
        db.purchase_minutes.assert_not_awaited()
        self.assertIn('تغییر کرده', query.answer.call_args.args[0])
