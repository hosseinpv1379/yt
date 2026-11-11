import asyncio
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from pydub import AudioSegment
from app.pipeline import JobCancelled, _dub_group_slot, _fit_dub_speech, _translate


class PipelineTests(unittest.TestCase):
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

    def test_dub_rejects_overflow_instead_of_overlapping_or_truncating(self):
        groups = [{'start_ms': 100}, {'start_ms': 200}]
        self.assertEqual(_dub_group_slot(groups, 0, 1000), 100)
        with self.assertRaises(RuntimeError):
            _fit_dub_speech(AudioSegment.silent(duration=1000), 100, Path('/tmp'), 0)
        with self.assertRaises(RuntimeError):
            _fit_dub_speech(AudioSegment.silent(duration=1), 0, Path('/tmp'), 0)


if __name__ == '__main__':
    unittest.main()
