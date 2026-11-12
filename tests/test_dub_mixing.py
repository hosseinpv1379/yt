import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from app.pipeline import _media_duration, _mux_dubbed_video


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg required")
class DubMixingTests(unittest.TestCase):
    def test_mixes_both_original_and_separated_bed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            video, voice, background = root / "source.mp4", root / "voice.wav", root / "bed.wav"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=size=64x64:rate=10:duration=2", "-f", "lavfi", "-i", "sine=frequency=300:duration=2", "-c:v", "mpeg4", "-c:a", "aac", "-shortest", str(video)], check=True)
            for path, frequency in [(voice, 700), (background, 1000)]:
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"sine=frequency={frequency}:duration=2", str(path)], check=True)
            for bed in (None, background):
                output = root / ("smart.mp4" if bed else "simple.mp4")
                _mux_dubbed_video(video, voice, output, background=bed)
                self.assertAlmostEqual(_media_duration(output), 2, delta=0.2)
                self.assertGreater(output.stat().st_size, 1000)


if __name__ == "__main__":
    unittest.main()
