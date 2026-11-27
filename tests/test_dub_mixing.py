import math
import shutil
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

from app.pipeline import _media_duration, _mux_dubbed_video


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg required")
class DubMixingTests(unittest.TestCase):
    def test_mixes_only_persian_voice_and_separated_bed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            video, voice, background = root / "source.mp4", root / "voice.wav", root / "bed.wav"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=size=64x64:rate=10:duration=2", "-f", "lavfi", "-i", "sine=frequency=300:duration=2", "-c:v", "mpeg4", "-c:a", "aac", "-shortest", str(video)], check=True)
            for path, frequency in [(voice, 700), (background, 1000)]:
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"sine=frequency={frequency}:duration=2", str(path)], check=True)
            output = root / "dubbed.mp4"
            _mux_dubbed_video(video, voice, output, background=background)
            self.assertAlmostEqual(_media_duration(output), 2, delta=0.2)
            pcm = subprocess.check_output(["ffmpeg", "-v", "error", "-ss", "0.5", "-i", str(output),
                                           "-t", "0.5", "-map", "0:a:0", "-ac", "1", "-ar", "8000",
                                           "-f", "s16le", "-"])
            samples = struct.unpack(f"<{len(pcm) // 2}h", pcm)

            def amplitude(frequency):
                angle = 2 * math.pi * frequency / 8000
                real = sum(x * math.cos(i * angle) for i, x in enumerate(samples))
                imaginary = sum(x * math.sin(i * angle) for i, x in enumerate(samples))
                return math.hypot(real, imaginary) / len(samples)

            self.assertGreater(amplitude(700), 100)
            self.assertGreater(amplitude(1000), 100)
            self.assertLess(amplitude(300), 5)


if __name__ == "__main__":
    unittest.main()
