import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from separator import server


@unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg required")
class SeparatorTests(unittest.TestCase):
    def test_separation_writes_complete_background(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            job = root / ("a" * 32)
            job.mkdir()
            source = job / "source.wav"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=duration=2", str(source)], check=True)
            actual_run = server.run

            def run(args):
                if args[0] == "spleeter":
                    chunk = Path(args[-1])
                    stem = Path(args[args.index("-o") + 1]) / chunk.stem / "accompaniment.wav"
                    stem.parent.mkdir(parents=True)
                    shutil.copyfile(chunk, stem)
                else:
                    actual_run(args)

            with patch.object(server, "ROOT", root), patch.object(server, "run", side_effect=run):
                server.separate(job.name, source.name)
                self.assertTrue((job / "dub-background.wav").is_file())
                self.assertFalse((job / "separator-work").exists())
                with self.assertRaises(ValueError):
                    server.separate(job.name, "../outside.wav")
            with patch.object(server, "ROOT", root / "other"), patch.object(server, "run", side_effect=run):
                server.separate(job.name, source.name, root=root)
                self.assertTrue((job / "dub-background.wav").is_file())

