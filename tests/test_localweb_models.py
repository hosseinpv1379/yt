import json
import tempfile
import unittest
from pathlib import Path
from threading import Event

from localweb.models import download_whisper_model, is_model_ready


def fake_download(name, output_dir):
    path = Path(output_dir)
    (path / 'model.bin').write_bytes(b'weights')
    for name in ('config.json', 'tokenizer.json'):
        (path / name).write_text(json.dumps({}), encoding='utf-8')
    (path / 'vocabulary.txt').write_text('token\n', encoding='utf-8')


class LocalWebModelsTests(unittest.TestCase):
    def test_json_vocabulary_also_supported(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake_download('small', tmp)
            path = Path(tmp)
            (path / 'vocabulary.txt').unlink()
            (path / 'vocabulary.json').write_text('{}')
            self.assertTrue(is_model_ready(path))
            (path / 'vocabulary.json').write_text('not json')
            self.assertFalse(is_model_ready(path))

    def test_download_is_installed_and_reused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = download_whisper_model('small', root, download=fake_download)
            self.assertEqual(path, root / 'small')
            self.assertTrue(is_model_ready(path))
            self.assertEqual(download_whisper_model('small', root, download=lambda *a, **k: self.fail('redownload')), path)

    def test_failure_preserves_partial_files_for_retry_and_existing_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            def fail(name, output_dir):
                (Path(output_dir) / 'model.bin').write_bytes(b'partial')
                raise RuntimeError('connection lost')
            with self.assertRaisesRegex(RuntimeError, 'connection lost'):
                download_whisper_model('small', root, download=fail)
            self.assertEqual((root / '.small-download' / 'model.bin').read_bytes(), b'partial')
            (root / 'small').mkdir()
            (root / 'small' / 'user-file').write_text('keep')
            with self.assertRaisesRegex(RuntimeError, 'ناقص'):
                download_whisper_model('small', root, download=fake_download)
            self.assertEqual((root / 'small' / 'user-file').read_text(), 'keep')

    def test_cancel_or_incomplete_download_never_becomes_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cancel = Event()
            def cancelled(name, output_dir):
                fake_download(name, output_dir)
                cancel.set()
            with self.assertRaises(InterruptedError):
                download_whisper_model('base', root, download=cancelled, cancel_event=cancel)
            self.assertFalse((root / 'base').exists())
            with self.assertRaisesRegex(RuntimeError, 'کامل'):
                download_whisper_model('tiny', root, download=lambda *a, **k: None)
            with self.assertRaises(ValueError):
                download_whisper_model('../other', root, download=fake_download)
