import asyncio
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from app import model_catalog as catalog
from app.bot import BotState, admin_callback
from app.pipeline import process_video


def settings():
    return SimpleNamespace(default_api_provider='openai', openai_api_key='oa', openrouter_api_key='or',
        whisper_model='whisper-1', translation_model='gpt-6-luna', tts_model='gpt-realtime-2.1-mini', tts_voice='marin',
        openrouter_transcription_model='openai/whisper-1', openrouter_model='openai/gpt-6-luna',
        openrouter_tts_model='google/gemini-3.8-flash-lite-tts', openrouter_tts_voice='Kore',
        provider_control_user_id=99, watermark_text='', download_base_url='https://example.com')


class MemoryDB:
    def __init__(self): self.data = {}
    async def get_setting(self, name, default): return self.data.get(name, default)
    async def set_setting(self, name, value): self.data[name] = value


class ModelSettingsTests(unittest.IsolatedAsyncioTestCase):
    async def test_choices_are_scoped_to_provider_and_legacy_choices_do_not_leak(self):
        db = MemoryDB()
        await db.set_setting('model_choice_stt', 's2')
        await db.set_setting('model_choice_translation', 't1')
        await db.set_setting('model_choice_tts', 'd2')
        await db.set_setting('model_voice_openrouter', 'Aoede')
        selected = await catalog.load_selection(db, settings(), 'openai')
        self.assertEqual(selected.stt.model, 'whisper-1')
        self.assertEqual(selected.translation.provider, 'openai')
        self.assertEqual(selected.tts.provider, 'openai')
        router = await catalog.load_selection(db, settings(), 'openrouter')
        self.assertEqual(router.stt.model, 'openai/whisper-large-v3-turbo')
        self.assertEqual(router.tts.provider, 'openrouter')
        self.assertEqual(router.voice, 'Aoede')
        await db.set_setting('model_choice_openrouter_stt', 's3')
        self.assertEqual(router.stt.model, 'openai/whisper-large-v3-turbo')
        self.assertEqual((await catalog.load_selection(db, settings(), 'openrouter')).stt.model, 'openai/whisper-large-v3')
        self.assertEqual((await catalog.load_selection(db, settings(), 'openai')).stt.model, 'whisper-1')

    async def test_admin_selection_and_access_control(self):
        db = MemoryDB()
        state = BotState(settings(), db)
        state.api_provider = 'openrouter'
        query = SimpleNamespace(data='admin:setmodel:s2', answer=AsyncMock(), edit_message_text=AsyncMock(), message=None)
        context = SimpleNamespace(application=SimpleNamespace(bot_data={'state': state}))
        update = SimpleNamespace(callback_query=query, effective_user=SimpleNamespace(id=1))
        await admin_callback(update, context)
        self.assertEqual(db.data, {})
        update.effective_user.id = 99
        await admin_callback(update, context)
        self.assertEqual(db.data['model_choice_openrouter_stt'], 's2')
        self.assertIn('whisper-large-v3-turbo', query.edit_message_text.call_args.args[0])
        state.api_provider = 'openai'
        await admin_callback(update, context)
        self.assertNotIn('model_choice_openai_stt', db.data)
        self.assertTrue(query.answer.call_args.kwargs['show_alert'])

    async def test_mixed_providers_route_to_correct_clients(self):
        config = settings()
        selected = catalog.ModelSelection(catalog.StageSelection('openrouter', 'stt-model'),
            catalog.StageSelection('openai', 'translation-model'),
            catalog.StageSelection('openrouter', 'tts-model'), 'Kore')
        with TemporaryDirectory() as temp:
            root = Path(temp)
            video = root / 'input.mp4'
            video.touch()
            or_client, oa_client = object(), object()
            def run(command):
                (root / 'audio' / 'part_000.mp3').touch()
                (root / 'audio' / 'segments.csv').write_text('part_000.mp3,0.000000,2.000000\n')
            transcribe = Mock(return_value=([{'start': 0, 'end': 2, 'text': 'hello'}], 0.1))
            translate = Mock(return_value=([{'start': 0, 'end': 2, 'text': 'سلام'}], 0.2))
            dub = Mock(return_value=(root / 'dub.wav', None, 0.0))
            bed = root / 'dub-background.wav'
            with patch('app.pipeline._download', return_value=(video, '')), patch('app.pipeline._run', side_effect=run), \
                 patch('app.pipeline._openrouter_client', return_value=or_client), patch('app.pipeline.OpenAI', return_value=oa_client), \
                 patch('app.pipeline._transcribe', transcribe), patch('app.pipeline._translate', translate), \
                 patch('app.pipeline._media_duration', return_value=2), \
                 patch('app.pipeline._create_openrouter_dubbed_audio', dub), patch('app.pipeline._mux_dubbed_video') as mux:
                process_video('https://youtu.be/a', root, config, asyncio.Event(), mode='dub',
                              model_selection=selected, local_separator=lambda *_: bed.touch())
            self.assertEqual(mux.call_args.kwargs['background'], bed)
            self.assertIs(transcribe.call_args.args[1], or_client)
            self.assertIs(translate.call_args.args[2], oa_client)
            self.assertIs(dub.call_args.args[3], or_client)
            self.assertIs(dub.call_args.args[-1], oa_client)
            self.assertEqual(dub.call_args.args[5], 'Kore')

class CostDisplayTests(unittest.TestCase):
    def test_dub_prices_distinguish_generated_audio_and_unknown_openai_rate(self):
        self.assertIn('$0.009 / دقیقه صدای خروجی', catalog.BY_CODE['d2'].price)
        self.assertIn('$0.0135 / دقیقه صدای خروجی', catalog.BY_CODE['d3'].price)
        self.assertIn('نامشخص', catalog.BY_CODE['d1'].price)

class MinuteEstimateTests(unittest.IsolatedAsyncioTestCase):
    async def test_summary_has_each_stage_and_both_totals(self):
        from app.bot import _show_model_settings
        db = MemoryDB()
        await db.set_setting('model_choice_stt', 's3')
        await db.set_setting('model_choice_translation', 't3')
        await db.set_setting('model_choice_tts', 'd2')
        state = BotState(settings(), db)
        state.api_provider = 'openrouter'
        query = SimpleNamespace(edit_message_text=AsyncMock())
        await _show_model_settings(query, state)
        text = query.edit_message_text.call_args.args[0]
        self.assertIn('$0.0004800', text)
        self.assertIn('$0.0001050', text)
        self.assertIn('$0.0091500', text)
        self.assertIn('جمع زیرنویس: حدود $0.0005850', text)
        self.assertIn('جمع دوبله: حدود $0.0097350', text)
        self.assertIn('۳۰۰ توکن', text)
        self.assertIn('تلاش مجدد', text)

    async def test_unknown_price_never_yields_fabricated_total(self):
        from app.bot import _show_model_settings
        state = BotState(settings(), MemoryDB())
        query = SimpleNamespace(edit_message_text=AsyncMock())
        await _show_model_settings(query, state)
        self.assertIn('جمع دوبله: نامشخص', query.edit_message_text.call_args.args[0])

    def test_scenario_prices(self):
        self.assertAlmostEqual(catalog.estimate_cents('stt', catalog.StageSelection('openrouter', 'openai/whisper-large-v3-turbo')), 0.06666666666666667)
        self.assertIsNone(catalog.estimate_cents('tts', catalog.StageSelection('openai', 'gpt-realtime-2.1-mini')))
