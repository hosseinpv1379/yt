import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.content import edit_subtitle_line, split_subtitle, generate_content
from app.pipeline import JobCancelled


class ContentTests(unittest.TestCase):
    def test_edit_preserves_timing_and_other_lines(self):
        srt = '1\n00:00:01,000 --> 00:00:02,000\nold\n\n2\n00:00:02,000 --> 00:00:03,000\nkeep\n'
        changed = edit_subtitle_line(srt, 1, 'جدید')
        self.assertIn('00:00:01,000 --> 00:00:02,000\nجدید', changed)
        self.assertIn('00:00:02,000 --> 00:00:03,000\nkeep', changed)
        with self.assertRaises(ValueError):
            edit_subtitle_line(srt, 1, 'bad\n00:00:00,000 --> 00:00:01,000')
        with self.assertRaises(ValueError):
            edit_subtitle_line(srt, 99, 'text')

    def test_split_removes_timestamps_and_respects_limit(self):
        chunks = split_subtitle('1\n00:00:00,000 --> 00:00:01,000\n' + 'x' * 21, size=10)
        self.assertEqual([len(x) for x in chunks], [10, 10, 1])
        self.assertNotIn('-->', ''.join(chunks))

    def test_numeric_dialogue_is_not_dropped(self):
        srt = '1\n00:00:00,000 --> 00:00:01,000\n2024\n\n2\n00:00:01,000 --> 00:00:02,000\nسلام'
        self.assertEqual(split_subtitle(srt), ['2024\nسلام'])

    def test_content_uses_configured_translation_client(self):
        create = Mock(return_value=SimpleNamespace(choices=[SimpleNamespace(
            finish_reason='stop', message=SimpleNamespace(refusal=None, content='خلاصه'))]))
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        selection = SimpleNamespace(translation=SimpleNamespace(provider='openrouter', model='test-model'))
        with patch('app.content._openrouter_client', return_value=client):
            output = generate_content('1\n00:00:00,000 --> 00:00:01,000\nمتن', 'summary', object(), selection, asyncio.Event())
        self.assertEqual(output, ('خلاصه', None))
        self.assertEqual(create.call_args.kwargs['model'], 'test-model')
        self.assertIn('untrusted', create.call_args.kwargs['messages'][0]['content'])

    def test_cancel_prevents_model_request(self):
        event = asyncio.Event(); event.set()
        selection = SimpleNamespace(translation=SimpleNamespace(provider='openrouter', model='test'))
        with patch('app.content._openrouter_client', return_value=object()):
            with self.assertRaises(JobCancelled):
                generate_content('1\n00:00:00,000 --> 00:00:01,000\nمتن', 'summary', object(), selection, event)

    def test_records_model_usage_cost(self):
        usage = SimpleNamespace(prompt_tokens=100, completion_tokens=50, prompt_tokens_details=None)
        create = Mock(return_value=SimpleNamespace(usage=usage, choices=[SimpleNamespace(
            finish_reason='stop', message=SimpleNamespace(refusal=None, content='خلاصه'))]))
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        selection = SimpleNamespace(translation=SimpleNamespace(provider='openrouter', model='openai/gpt-4o-mini'))
        with patch('app.content._openrouter_client', return_value=client):
            text, cost = generate_content('1\n00:00:00,000 --> 00:00:01,000\nمتن', 'summary', object(), selection, asyncio.Event())
        self.assertEqual(text, 'خلاصه')
        self.assertAlmostEqual(cost, 0.000045)
