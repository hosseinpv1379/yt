import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from localweb.service import LocalService
from localweb.settings import DEFAULTS


class LocalWebServiceTests(unittest.TestCase):
    def test_download_saves_output_and_clears_running(self):
        with tempfile.TemporaryDirectory() as tmp:
            prefs = {**DEFAULTS, 'output_dir': tmp}
            service = LocalService()
            service.job['running'] = True
            def download(url, kind, directory, settings, cancel, progress):
                file = directory / 'source.mp3'
                file.write_bytes(b'audio')
                return file, 'test'
            with patch('localweb.settings.load_preferences', return_value=prefs), patch('app.downloads.download_media', side_effect=download):
                service._run('audio', 'https://example.com/video')
            self.assertFalse(service.status()['running'])
            self.assertEqual(service.status()['percent'], 100)
            outputs = list(Path(tmp).glob('job-*/source.mp3'))
            self.assertEqual(len(outputs), 1)
            self.assertEqual(outputs[0].read_bytes(), b'audio')

    def test_invalid_or_duplicate_job_is_rejected(self):
        service = LocalService()
        with self.assertRaises(ValueError):
            service.start('unknown', 'x')
        service.job['running'] = True
        with self.assertRaises(ValueError):
            service.start('video', 'https://example.com')
