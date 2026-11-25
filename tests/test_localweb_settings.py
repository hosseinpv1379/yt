import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from localweb.settings import DEFAULTS, load_preferences, pipeline_settings, save_preferences


class LocalWebSettingsTests(unittest.TestCase):
    def test_preferences_never_save_unknown_fields_or_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'settings.json'
            save_preferences({**DEFAULTS, 'provider': 'openrouter', 'openrouter_api_key': 'secret'}, path)
            self.assertNotIn('secret', path.read_text())
            self.assertEqual(load_preferences(path)['provider'], 'openrouter')
            self.assertNotIn('openrouter_api_key', json.loads(path.read_text()))

    def test_pipeline_settings_are_independent_of_telegram(self):
        settings = pipeline_settings(DEFAULTS, {'openai': 'example'}, Path('/tmp'))
        self.assertEqual(settings.openai_api_key, 'example')
        self.assertEqual(settings.whisper_model, DEFAULTS['openai_stt'])
        with self.assertRaises(ValueError):
            pipeline_settings({**DEFAULTS, 'max_minutes': '0'}, {}, Path('/tmp'))

    def test_openrouter_client_tracks_changed_credentials(self):
        from app import pipeline
        from types import SimpleNamespace
        from unittest.mock import Mock
        first = SimpleNamespace(openrouter_api_key='first', openrouter_rpm_limit=10, openrouter_max_retries=2)
        second = SimpleNamespace(openrouter_api_key='second', openrouter_rpm_limit=10, openrouter_max_retries=2)
        with patch.object(pipeline, '_OPENROUTER_CLIENT', None), patch.object(pipeline, '_OPENROUTER_CLIENT_CONFIG', None), \
             patch.object(pipeline, 'OpenAI', side_effect=[Mock(), Mock()]) as factory:
            a = pipeline._openrouter_client(first)
            self.assertIs(a, pipeline._openrouter_client(first))
            self.assertIsNot(a, pipeline._openrouter_client(second))
            self.assertEqual(factory.call_count, 2)
