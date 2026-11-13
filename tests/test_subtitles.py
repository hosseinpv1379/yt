import tempfile
import asyncio
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import httpx
from openai import BadRequestError

from app.pipeline import _audio_chunk_offsets, _transcribe, _write_srt, _write_vtt, process_video
from app.subtitles import source_cues, caption_cues


class SubtitleTests(unittest.TestCase):
    def test_word_timestamps_produce_short_cues_aligned_to_speech(self):
        words = [dict(word=f'word{i}', start=i * 0.5, end=i * 0.5 + 0.4) for i in range(18)]
        text = ' '.join(word['word'] for word in words)
        cues, precise = source_cues([{'start': 0, 'end': 9, 'text': text}], words, text)
        self.assertTrue(precise)
        self.assertGreaterEqual(len(cues), 3)
        self.assertEqual(' '.join(c['text'] for c in cues), text)
        self.assertTrue(all(c['end'] - c['start'] <= 4 for c in cues))
        self.assertEqual(cues[1]['start'], words[len(cues[0]['text'].split())]['start'])

    def test_incomplete_word_timing_falls_back_without_dropping_text(self):
        text = 'one two three four five six seven eight nine ten eleven twelve'
        segments = [{'start': 2, 'end': 14, 'text': text}]
        words = [dict(word='one', start=2, end=2.5)]
        cues, precise = source_cues(segments, words, text)
        self.assertFalse(precise)
        self.assertEqual(' '.join(c['text'] for c in cues), text)
        self.assertGreater(len(cues), 1)
        self.assertAlmostEqual(cues[-1]['end'], 14)

    def test_incomplete_words_do_not_discard_other_segments_precise_times(self):
        segments = [{'start': 0, 'end': 3, 'text': 'hello world'},
                    {'start': 5, 'end': 10, 'text': 'one two three'}]
        words = [{'word': 'hello', 'start': 0.25, 'end': 0.6},
                 {'word': 'world', 'start': 1.1, 'end': 1.5},
                 {'word': 'one', 'start': 5.2, 'end': 5.4}]
        cues, precise = source_cues(segments, words, 'hello world one two three')
        self.assertFalse(precise)
        self.assertEqual(cues[0], {'start': 0.25, 'end': 1.5, 'text': 'hello world'})
        self.assertEqual(' '.join(cue['text'] for cue in cues), 'hello world one two three')
        self.assertEqual(cues[-1]['end'], 10)

    def test_short_speech_is_not_extended_into_silence(self):
        cue = caption_cues([{'start': 2, 'end': 2.08, 'text': 'بله'}])[0]
        self.assertAlmostEqual(cue['end'], 2.08)

    def test_chunk_offsets_use_actual_segment_boundaries(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            chunks = [root / 'part_000.mp3', root / 'part_001.mp3']
            (root / 'segments.csv').write_text('part_000.mp3,0,480.024\npart_001.mp3,480.024,960.048\n')
            offsets = _audio_chunk_offsets(root, chunks)
            self.assertEqual(offsets['part_001.mp3'], 480.024)
            (root / 'segments.csv').write_text('part_000.mp3,0,480\n')
            with self.assertRaises(RuntimeError):
                _audio_chunk_offsets(root, chunks)

    def test_subtitle_breaks_long_persian_and_prevents_overlap(self):
        original = ' '.join(['آزمایش'] * 60)
        cues = caption_cues([{'start': 0, 'end': 12, 'text': original},
                             {'start': 2, 'end': 12, 'text': 'جمله دوم را می‌گوید'}])
        self.assertGreater(len(cues), 2)
        self.assertEqual(' '.join(c['text'].replace('\n', ' ') for c in cues), original + ' جمله دوم را می‌گوید')
        self.assertTrue(all(len(c['text'].splitlines()) <= 2 for c in cues))
        self.assertTrue(all(len(line) <= 42 for c in cues for line in c['text'].splitlines()))
        self.assertTrue(all(a['end'] <= b['start'] for a, b in zip(cues, cues[1:])))
        self.assertLessEqual(cues[-1]['end'], 12.001)

    def test_later_segment_overlapping_multiple_split_cues_stays_inside_window(self):
        text = ' '.join(['آزمایش'] * 60)
        cues = caption_cues([{'start': 0, 'end': 12, 'text': text},
                             {'start': 2, 'end': 3, 'text': 'دوم'}])
        self.assertEqual(' '.join(c['text'].replace('\n', ' ') for c in cues), text + ' دوم')
        self.assertTrue(all(a['end'] <= b['start'] for a, b in zip(cues, cues[1:])))
        self.assertLessEqual(cues[-1]['end'], 12.001)

    def test_transcribe_requests_word_times_and_formats_match(self):
        words = [SimpleNamespace(word='Hello', start=0.0, end=0.4), SimpleNamespace(word='world.', start=0.5, end=1.0)]
        response = SimpleNamespace(text='Hello world.', words=words, segments=[SimpleNamespace(start=0, end=1, text='Hello world.')], usage=None)
        create = Mock(return_value=response)
        client = SimpleNamespace(audio=SimpleNamespace(transcriptions=SimpleNamespace(create=create)))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); audio = root / 'audio.mp3'; audio.touch()
            cues, _ = _transcribe(audio, client, 'whisper-1', word_timestamps=True)
            self.assertEqual(create.call_args.kwargs['timestamp_granularities'], ['segment', 'word'])
            captions = caption_cues([{'start': c['start'], 'end': c['end'], 'text': 'سلام دنیا'} for c in cues])
            _write_srt(captions, root / 'fa.srt')
            _write_vtt(captions, root / 'fa.vtt', isolate_ltr=False)
            self.assertIn('00:00:00,000 --> 00:00:01,000', (root / 'fa.srt').read_text())
            self.assertIn('00:00:00.000 --> 00:00:01.000', (root / 'fa.vtt').read_text())

    def test_timestamp_rejection_retries_with_segments(self):
        request = httpx.Request('POST', 'https://example.test/audio')
        error = BadRequestError('timestamp word unsupported', response=httpx.Response(400, request=request), body=None)
        response = SimpleNamespace(text='one two three four five six', words=None,
            segments=[SimpleNamespace(start=0, end=6, text='one two three four five six')], usage=None)
        create = Mock(side_effect=[error, response])
        client = SimpleNamespace(audio=SimpleNamespace(transcriptions=SimpleNamespace(create=create)))
        with tempfile.TemporaryDirectory() as tmp:
            audio = Path(tmp) / 'audio.mp3'; audio.write_bytes(b'audio')
            cues, _ = _transcribe(audio, client, 'whisper-1', word_timestamps=True)
        self.assertEqual(create.call_count, 2)
        self.assertEqual(create.call_args.kwargs['timestamp_granularities'], ['segment'])
        self.assertEqual(' '.join(c['text'] for c in cues), response.text)

    def test_two_line_layout_respects_word_boundaries(self):
        text = 'الف' * 10 + ' ' + 'ب' * 20 + ' ' + 'پ' * 30
        cues = caption_cues([{'start': 0, 'end': 6, 'text': text}])
        self.assertEqual(' '.join(c['text'].replace('\n', ' ') for c in cues), text)
        self.assertTrue(all(len(line) <= 42 for cue in cues for line in cue['text'].splitlines()))

    def test_full_subtitle_pipeline_outputs_matching_bounded_cues(self):
        from app.model_catalog import ModelSelection, StageSelection
        selected = ModelSelection(StageSelection('openrouter', 'stt'), StageSelection('openai', 'translation'),
                                  StageSelection('openrouter', 'tts'), 'Kore')
        settings = SimpleNamespace(openai_api_key='key', openrouter_api_key='key', watermark_text='', download_base_url='https://example.com')
        source = [{'start': 0, 'end': 12, 'text': 'english'}, {'start': 2, 'end': 3, 'text': 'more'}]
        translated = [{'start': 0, 'end': 12, 'text': ' '.join(['سلام'] * 70)}, {'start': 2, 'end': 3, 'text': 'ادامه'}]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); video = root / 'source.mp4'; video.touch()
            def run(_command):
                (root / 'audio' / 'part_000.mp3').touch()
                (root / 'audio' / 'segments.csv').write_text('part_000.mp3,0,12\n')
            with patch('app.pipeline._download', return_value=(video, '')), patch('app.pipeline._run', side_effect=run), \
                 patch('app.pipeline._openrouter_client', return_value=object()), patch('app.pipeline.OpenAI', return_value=object()), \
                 patch('app.pipeline._transcribe', return_value=(source, 0.0)) as transcribe, \
                 patch('app.pipeline._translate', return_value=(translated, 0.0)):
                _, srt, vtt, _ = process_video('https://youtu.be/test', root, settings, asyncio.Event(),
                                                mode='subtitle', model_selection=selected)
                self.assertTrue(transcribe.call_args.kwargs['word_timestamps'])
                srt_blocks = srt.read_text().strip().split('\n\n')
                vtt_blocks = vtt.read_text().strip().split('\n\n')[1:]
                self.assertEqual(len(srt_blocks), len(vtt_blocks))
                self.assertGreater(len(srt_blocks), 2)
                self.assertTrue(all(len(block.splitlines()[2:]) <= 2 for block in srt_blocks))

    def test_pipeline_applies_actual_second_chunk_start_to_subtitles(self):
        from app.model_catalog import ModelSelection, StageSelection
        selected = ModelSelection(StageSelection('openrouter', 'stt'), StageSelection('openai', 'translation'),
                                  StageSelection('openrouter', 'tts'), 'Kore')
        settings = SimpleNamespace(openai_api_key='key', openrouter_api_key='key', watermark_text='', download_base_url='https://example.com')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); video = root / 'source.mp4'; video.touch()
            def run(_command):
                for number in (0, 1):
                    (root / 'audio' / f'part_{number:03d}.mp3').touch()
                (root / 'audio' / 'segments.csv').write_text('part_000.mp3,0,480.024\npart_001.mp3,480.024,482\n')
            def translate(segments, *args, **kwargs):
                return ([{**item, 'text': 'متن فارسی'} for item in segments], 0.0)
            transcription = Mock(side_effect=[([{'start': 0, 'end': 1, 'text': 'first'}], 0),
                                                ([{'start': 0.2, 'end': 1, 'text': 'second'}], 0)])
            translator = Mock(side_effect=translate)
            with patch('app.pipeline._download', return_value=(video, '')), patch('app.pipeline._run', side_effect=run), \
                 patch('app.pipeline._openrouter_client', return_value=object()), patch('app.pipeline.OpenAI', return_value=object()), \
                 patch('app.pipeline._transcribe', transcription), patch('app.pipeline._translate', translator):
                _, srt, _, _ = process_video('https://youtu.be/test', root, settings, asyncio.Event(),
                                              mode='subtitle', model_selection=selected)
                self.assertAlmostEqual(translator.call_args.args[0][1]['start'], 480.224)
                self.assertIn('00:08:00,224', srt.read_text())

    def test_multiple_long_words_are_not_dropped(self):
        text = 'a' * 120 + ' ' + 'b' * 120
        cues = caption_cues([{'start': 0, 'end': 6, 'text': text}])
        self.assertEqual(' '.join(c['text'].replace('\n', ' ') for c in cues), text)
