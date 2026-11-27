import asyncio
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.bot import BotState, PendingQuality, choose_quality, confirm_order


class OrderTests(unittest.IsolatedAsyncioTestCase):
    async def test_separator_unavailable_never_charges_for_dubbing(self):
        settings = SimpleNamespace(default_api_provider='openai', dub_separator_url='')
        db = SimpleNamespace(create_wallet_job=AsyncMock(), create_package_job=AsyncMock())
        state = BotState(settings, db)
        state.pending_quality['token'] = PendingQuality(1, 1, 'https://youtu.be/example', 42, True,
            'openai', mode='dub', duration_seconds=61, quoted_rate=10000, stage='payment')
        state.pending_by_user[1] = 'token'
        query = SimpleNamespace(data='confirm:token', answer=AsyncMock(), edit_message_text=AsyncMock())
        update = SimpleNamespace(callback_query=query, effective_user=SimpleNamespace(id=1))
        context = SimpleNamespace(application=SimpleNamespace(bot_data={'state': state}))
        await confirm_order(update, context)
        db.create_wallet_job.assert_not_awaited()
        db.create_package_job.assert_not_awaited()
        self.assertFalse(state.pending_quality['token'].confirming)
        self.assertIn('جداسازی', query.answer.call_args.args[0])

    async def test_price_is_shown_before_single_charge(self):
        settings = SimpleNamespace(default_api_provider='openai', openai_api_key='key',
            openrouter_api_key='', default_subtitle_price_toman_per_minute=5000,
            default_dub_price_toman_per_minute=10000, work_dir='/tmp',
            whisper_model='whisper-1', translation_model='gpt-6-luna',
            tts_model='gpt-realtime-2.1-mini', tts_voice='marin')
        db = SimpleNamespace(has_accepted_terms=AsyncMock(return_value=True),
            get_setting=AsyncMock(side_effect=lambda name, default: '5000' if name == 'price_subtitle_toman_per_minute' else default), get_wallet_balance=AsyncMock(return_value=20000),
            create_wallet_job=AsyncMock(return_value=10000), team_info=AsyncMock(return_value=None), available_minutes=AsyncMock(return_value=[]))
        state = BotState(settings, db)
        state.pending_quality['token'] = PendingQuality(1, 1, 'https://youtu.be/example', 42, True, 'openai', mode='subtitle', duration_seconds=61, stage='quality')
        state.pending_by_user[1] = 'token'
        query = SimpleNamespace(data='quality:token:720', answer=AsyncMock(), edit_message_text=AsyncMock())
        update = SimpleNamespace(callback_query=query, effective_user=SimpleNamespace(id=1))
        context = SimpleNamespace(application=SimpleNamespace(bot_data={'state': state}))
        await choose_quality(update, context)
        db.create_wallet_job.assert_not_awaited()
        self.assertIn('10,000 تومان', query.edit_message_text.call_args.args[0])
        query.data = 'confirm:token'
        await confirm_order(update, context)
        await confirm_order(update, context)
        db.create_wallet_job.assert_awaited_once()
        self.assertEqual(db.create_wallet_job.call_args.kwargs['amount_toman'], 10000)
        self.assertEqual(state.queue.qsize(), 1)
