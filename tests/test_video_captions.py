import sys
import shutil
import subprocess
import tempfile
import threading
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from features.video_captions.ass_builder import _groups, write_ass
from features.video_captions.transcribe import Word, _model, transcribe
from features.video_captions.pipeline import probe, render


class CaptionBuilderTests(unittest.TestCase):
    def test_word_highlighting_and_rtl_logical_order(self):
        words = [Word("سلام", 0.0, 0.4), Word("دنیا", 0.4, 0.9)]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "caption.ass"
            write_ass(words, path, 1080, 1920, "fa", "yellow")
            text = path.read_text(encoding="utf-8")
        self.assertIn("Style: Default,Vazirmatn,", text)
        dialogues = [line for line in text.splitlines() if line.startswith("Dialogue:")]
        self.assertEqual(len(dialogues), 2)
        self.assertIn("0:00:00.00,0:00:00.40", dialogues[0])
        self.assertLess(dialogues[0].index("سلام"), dialogues[0].index("دنیا"))
        self.assertIn(r"\1c&H00FFFF&", dialogues[0])
        self.assertIn(r"\t(0,100,\fscx115\fscy115)", dialogues[0])

    def test_group_limits_and_ass_control_characters(self):
        words = [Word(word, index, index + .5) for index, word in enumerate(["one", "two", "three", "four", "five"])]
        self.assertTrue(all(len(group) <= 4 and len(" ".join(w.text for w in group)) <= 20 for group in _groups(words)))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "out.ass"
            write_ass([Word(r"{\pos(1,2)}", 0, 1)], path, 640, 360, "en", "blue")
            dialogue = next(line for line in path.read_text(encoding="utf-8").splitlines() if line.startswith("Dialogue:"))
        self.assertNotIn(r"{\pos(1,2)}", dialogue)


class TranscriptionTests(unittest.TestCase):
    def tearDown(self):
        _model.cache_clear()

    def test_singleton_vad_and_word_timestamps(self):
        calls = []
        class FakeModel:
            def __init__(self, path, **kwargs):
                calls.append((path, kwargs))
            def transcribe(self, path, **kwargs):
                self.options = kwargs
                segment = types.SimpleNamespace(words=[types.SimpleNamespace(word=" hello", start=.1, end=.5)])
                return iter([segment]), types.SimpleNamespace(language="en")
        module = types.SimpleNamespace(WhisperModel=FakeModel)
        with patch.dict(sys.modules, {"faster_whisper": module}):
            first, language = transcribe(Path("audio.mp4"), "/local/model")
            transcribe(Path("audio.mp4"), "/local/model")
            model = _model("/local/model")
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0][1]["local_files_only"])
        self.assertEqual(model.options, {"word_timestamps": True, "vad_filter": True})
        self.assertEqual((first[0].text, language), ("hello", "en"))


class ProbeTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg is unavailable")
    def test_uploaded_video_dimensions_duration_and_silent_audio(self):
        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "silent.mp4"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                            "color=black:size=64x96:rate=10", "-t", "1", "-c:v", "mpeg4", str(video)],
                           check=True, capture_output=True)
            metadata = probe(video)
        self.assertEqual((metadata["width"], metadata["height"]), (64, 96))
        self.assertAlmostEqual(metadata["duration"], 1.0, places=1)
        self.assertFalse(metadata["audio"])

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg is unavailable")
    def test_raw_frame_render_preserves_audio(self):
        class Frame:
            shape = (96, 64, 3)
            def tobytes(self):
                return bytes(64 * 96 * 3)
        class Capture:
            def __init__(self, path):
                self.count = 0
            def isOpened(self):
                return True
            def get(self, prop):
                return 10
            def read(self):
                self.count += 1
                return (True, Frame()) if self.count <= 10 else (False, None)
            def release(self):
                pass
        class FakeGrader:
            def __init__(self, settings):
                pass
            def frame(self, frame):
                return frame
            def close(self):
                pass
        with tempfile.TemporaryDirectory() as tmp:
            source, output = Path(tmp) / "source.mp4", Path(tmp) / "out.mp4"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=black:size=64x96:rate=10",
                            "-f", "lavfi", "-i", "sine=frequency=440", "-t", "1", "-c:v", "mpeg4", "-c:a", "aac", str(source)],
                           check=True, capture_output=True)
            cv2 = types.SimpleNamespace(VideoCapture=Capture, CAP_PROP_FPS=5)
            with patch.dict(sys.modules, {"cv2": cv2}), patch("features.video_captions.pipeline.Grader", FakeGrader):
                render(source, output, "color", "yellow", "/missing", Path(tmp), threading.Event(), lambda _: None)
            metadata = probe(output)
        self.assertTrue(metadata["audio"])
        self.assertEqual((metadata["width"], metadata["height"]), (64, 96))


if __name__ == "__main__":
    unittest.main()
