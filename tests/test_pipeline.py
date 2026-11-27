import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from pydub import AudioSegment
from pydub.generators import Sine
from app.pipeline import JobCancelled, _dub_group_slot, _fit_dub_speech, _synthesize_fitting_dub, _shorten_dub_text, _translate


class PipelineTests(unittest.TestCase):
    def test_translation_requests_english_only_for_specialist_terms_in_subtitle_and_dub(self):
        response = SimpleNamespace(usage=None, choices=[SimpleNamespace(finish_reason='stop',
            message=SimpleNamespace(refusal=None, content=json.dumps({'translations': {'0': 'از GPU استفاده کن'}})))])
        create = Mock(return_value=response)
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        for for_dubbing in (False, True):
            result, _ = _translate([{'start': 0, 'end': 2, 'text': 'use the GPU'}], '', client, 'test', for_dubbing=for_dubbing)
            self.assertEqual(result[0]['text'], 'از GPU استفاده کن')
            prompt = create.call_args.kwargs['messages'][0]['content']
            self.assertIn('specialized domain-specific technical terms only', prompt)
            self.assertIn('Translate ordinary nontechnical words naturally into Persian', prompt)

    def test_dub_rewrite_keeps_english_terms_even_if_model_omits_them(self):
        source = 'در این بخش از Machine Learning و GPU استفاده می‌کنیم'
        answer = SimpleNamespace(usage=None, choices=[SimpleNamespace(finish_reason='stop',
            message=SimpleNamespace(refusal=None, content=json.dumps({'text': 'از یادگیری ماشین و پردازنده استفاده می‌کنیم'}, ensure_ascii=False)))])
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=Mock(return_value=answer))))
        rewritten, _ = _shorten_dub_text(client, 'test', source, 1000, 2000)
        self.assertEqual(rewritten, source)
        answer.choices[0].message.content = json.dumps({'text': 'از Machine Learning و GPU استفاده می‌کنیم'}, ensure_ascii=False)
        rewritten, _ = _shorten_dub_text(client, 'test', source, 1000, 2000)
        self.assertEqual(rewritten, 'از Machine Learning و GPU استفاده می‌کنیم')
    def test_translation_keeps_neighboring_context_across_batches_and_retries(self):
        def answer(**kwargs):
            content = kwargs['messages'][1]['content']
            rows = json.loads(content.split('Segments:\n', 1)[1])
            result = {str(item['i']): 'ترجمه ' + item['text'] for item in rows}
            if len(rows) == 40:
                result.pop('1')
            return SimpleNamespace(usage=None, choices=[SimpleNamespace(finish_reason='stop',
                message=SimpleNamespace(refusal=None, content=json.dumps({'translations': result}, ensure_ascii=False)))])
        create = Mock(side_effect=answer)
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        segments = [{'start': i, 'end': i + 0.75, 'text': f'phrase{i}'} for i in range(42)]
        result, _ = _translate(segments, 'technical video', client, 'test')
        self.assertEqual(len(result), 42)
        self.assertEqual([(x['start'], x['end']) for x in result], [(x['start'], x['end']) for x in segments])
        retry = create.call_args_list[1].kwargs['messages'][1]['content']
        self.assertIn('phrase0', retry)
        self.assertIn('ترجمه phrase0', retry)
        following = create.call_args_list[2].kwargs['messages'][1]['content']
        self.assertIn('phrase39', following)
        self.assertIn('ترجمه phrase39', following)

    def test_translation_retries_only_missing_rows_and_preserves_timing(self):
        def answer(**kwargs):
            source = json.loads(kwargs['messages'][1]['content'].split('Segments:\n', 1)[1])
            rows = {str(item['i']): 'ترجمه ' + str(item['i']) for item in source}
            if len(source) > 1:
                rows.pop('1')
            return SimpleNamespace(usage=None, choices=[SimpleNamespace(
                finish_reason='stop', message=SimpleNamespace(refusal=None, content=json.dumps({'translations': rows})))])
        create = Mock(side_effect=answer)
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        segments = [{'start': 0, 'end': 2, 'text': 'hello'}, {'start': 2, 'end': 4, 'text': 'world'}]
        result, cost = _translate(segments, '', client, 'test')
        self.assertEqual([r['text'] for r in result], ['ترجمه 0', 'ترجمه 1'])
        self.assertEqual(result[1]['start'], 2)
        self.assertEqual(create.call_count, 2)
        self.assertIsNone(cost)
        self.assertEqual(json.loads(create.call_args_list[0].kwargs['messages'][1]['content'].split('Segments:\n', 1)[1])[0]['duration_seconds'], 2)

    def test_translation_honours_cancellation(self):
        event = asyncio.Event()
        event.set()
        with self.assertRaises(JobCancelled):
            _translate([{'start': 0, 'end': 1, 'text': 'test'}], '', None, 'test', cancel_event=event)

    def test_dub_regenerates_overlong_audio_using_shorter_text(self):
        generate = Mock(side_effect=[(AudioSegment.silent(duration=2200), 0.1),
                                     (AudioSegment.silent(duration=900), 0.2)])
        with patch('app.pipeline._shorten_dub_text', return_value=('متن کوتاه', 0.03)) as shorten:
            speech, tts_cost, rewrite_cost = _synthesize_fitting_dub(
                'متن طولانی برای گفتار', 1000, Path('/tmp'), 0, generate, object(), 'model')
        self.assertEqual(len(speech), 900)
        self.assertEqual(generate.call_args_list[1].args[0], 'متن کوتاه')
        self.assertAlmostEqual(tts_cost, 0.3)
        self.assertEqual(rewrite_cost, 0.03)
        shorten.assert_called_once()

    def test_unchanged_rewrite_does_not_abort_and_retries_speech(self):
        original = 'این متن کوتاه است'
        generate = Mock(side_effect=[(AudioSegment.silent(duration=2100), 0.1),
                                     (AudioSegment.silent(duration=900), 0.2)])
        response = SimpleNamespace(usage=None, choices=[SimpleNamespace(finish_reason='stop',
            message=SimpleNamespace(refusal=None, content=json.dumps({'text': original}, ensure_ascii=False)))])
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=Mock(return_value=response))))
        speech, tts_cost, rewrite_cost = _synthesize_fitting_dub(original, 1000, Path('/tmp'), 0,
                                                                  generate, client, 'test')
        self.assertEqual(len(speech), 900)
        self.assertEqual(generate.call_args_list[1].args[0], original)
        self.assertAlmostEqual(tts_cost, 0.3)
        self.assertIsNone(rewrite_cost)

    def test_longer_rewrite_keeps_original_and_accounts_usage(self):
        response = SimpleNamespace(usage=SimpleNamespace(prompt_tokens=100, completion_tokens=50, prompt_tokens_details=None),
            choices=[SimpleNamespace(finish_reason='stop', message=SimpleNamespace(refusal=None,
                content=json.dumps({'text': 'این متن از متن اولیه خیلی طولانی‌تر است'}, ensure_ascii=False)))])
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=Mock(return_value=response))))
        rewritten, cost = _shorten_dub_text(client, 'gpt-4o-mini', 'متن کوتاه', 1000, 2000)
        self.assertEqual(rewritten, 'متن کوتاه')
        self.assertAlmostEqual(cost, 0.000045)

    def test_fallback_accelerates_best_complete_audio_without_overlap(self):
        generate = Mock(side_effect=[(AudioSegment.silent(duration=1275, frame_rate=24000), 0.1),
                                     (AudioSegment.silent(duration=1400, frame_rate=24000), 0.1),
                                     (AudioSegment.silent(duration=1300, frame_rate=24000), 0.1)])
        with tempfile.TemporaryDirectory() as tmp, patch('app.pipeline._shorten_dub_text', return_value=('متن', 0.02)):
            speech, cost, rewrite = _synthesize_fitting_dub('متن', 1000, Path(tmp), 0, generate, object(), 'test')
        self.assertLessEqual(len(speech), 1000)
        self.assertGreater(len(speech), 700)
        self.assertAlmostEqual(cost, 0.3)
        self.assertAlmostEqual(rewrite, 0.04)

    def test_fallback_keeps_audible_end_of_speech(self):
        # A tone at the end represents a final spoken word: it must survive
        # tempo adjustment rather than being cut off at the slot boundary.
        speech = Sine(440, sample_rate=24000).to_audio_segment(duration=1100) + Sine(1000, sample_rate=24000).to_audio_segment(duration=180)
        generate = Mock(return_value=(speech, None))
        with tempfile.TemporaryDirectory() as tmp, patch('app.pipeline._shorten_dub_text', return_value=('متن', None)):
            fitted, _, _ = _synthesize_fitting_dub('متن', 1000, Path(tmp), 0, generate, object(), 'test')
        self.assertLessEqual(len(fitted), 1000)
        self.assertGreater(fitted[-80:].dBFS, -30)

    def test_dub_removes_long_silent_margins_before_fitting(self):
        speech = (AudioSegment.silent(duration=900, frame_rate=24000)
                  + Sine(440, sample_rate=24000).to_audio_segment(duration=600)
                  + AudioSegment.silent(duration=900, frame_rate=24000))
        generate = Mock(return_value=(speech, 0.1))
        with tempfile.TemporaryDirectory() as tmp:
            fitted, cost, _ = _synthesize_fitting_dub('متن', 1000, Path(tmp), 0, generate, object(), '')
        self.assertLessEqual(len(fitted), 1000)
        self.assertGreater(fitted[150:650].dBFS, -30)
        self.assertEqual(cost, 0.1)

    def test_dub_stops_after_bounded_retries(self):
        generate = Mock(return_value=(AudioSegment.silent(duration=3000), None))
        with patch('app.pipeline._shorten_dub_text', side_effect=[('کوتاه', None), ('کم', None)]):
            with self.assertRaisesRegex(RuntimeError, 'تلاش مجدد'):
                _synthesize_fitting_dub('متن خیلی طولانی', 1000, Path('/tmp'), 0, generate, object(), 'model')
        self.assertEqual(generate.call_count, 3)

    def test_dub_rejects_overflow_instead_of_overlapping_or_truncating(self):
        groups = [{'start_ms': 100}, {'start_ms': 200}]
        self.assertEqual(_dub_group_slot(groups, 0, 1000), 100)
        with self.assertRaises(RuntimeError):
            _fit_dub_speech(AudioSegment.silent(duration=1000), 100, Path('/tmp'), 0)
        with self.assertRaises(RuntimeError):
            _fit_dub_speech(AudioSegment.silent(duration=1), 0, Path('/tmp'), 0)


if __name__ == '__main__':
    unittest.main()
