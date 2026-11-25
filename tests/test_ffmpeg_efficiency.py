import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.pipeline import _ffmpeg_preset, _ffmpeg_threads, _render, _run


class FFmpegEfficiencyTests(unittest.TestCase):
    def test_thread_cap_and_preset_are_configurable_and_bounded(self):
        with patch.dict(os.environ, {'FFMPEG_THREADS': '999', 'FFMPEG_PRESET': 'bad'}):
            self.assertEqual(_ffmpeg_threads(), 16)
            self.assertEqual(_ffmpeg_preset(), 'superfast')
        with patch.dict(os.environ, {'FFMPEG_THREADS': '3'}), patch('app.pipeline.subprocess.run', return_value=SimpleNamespace(returncode=0)) as run:
            _run(['ffmpeg', '-i', 'input'])
            self.assertEqual(run.call_args.args[0][1:7], ['-threads', '3', '-filter_threads', '3', '-filter_complex_threads', '3'])

    def test_aac_is_copied_and_probe_failure_falls_back_to_encoding(self):
        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / 'in.mp4'
            output = Path(tmp) / 'out.mp4'
            with patch('app.pipeline.subprocess.run', return_value=SimpleNamespace(stdout='aac\n')), patch('app.pipeline._run') as run:
                _render(video, 'fa.srt', output)
                cmd = run.call_args.args[0]
                self.assertEqual(cmd[cmd.index('-c:a') + 1], 'copy')
                self.assertIn('-threads', cmd)
            with patch('app.pipeline.subprocess.run', side_effect=subprocess.CalledProcessError(1, 'ffprobe')), patch('app.pipeline._run') as run:
                _render(video, 'fa.srt', output)
                cmd = run.call_args.args[0]
                self.assertEqual(cmd[cmd.index('-c:a') + 1], 'aac')
