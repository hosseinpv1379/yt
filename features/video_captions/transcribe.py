"""Local speech recognition with one lazily loaded CPU model per process."""
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from threading import Lock


@dataclass(frozen=True)
class Word:
    text: str
    start: float
    end: float


_model_lock = Lock()


@lru_cache(maxsize=1)
def _model(model_path: str):
    from faster_whisper import WhisperModel
    # A path to a pre-provisioned model keeps requests independent of the network.
    return WhisperModel(model_path, device="cpu", compute_type="int8", local_files_only=True)


def transcribe(audio: Path, model_path: str) -> tuple[list[Word], str]:
    with _model_lock:
        segments, info = _model(model_path).transcribe(
            str(audio), word_timestamps=True, vad_filter=True,
        )
        words = []
        for segment in segments:
            for word in segment.words or []:
                text = word.word.strip()
                if text and word.start is not None and word.end is not None and word.end > word.start:
                    words.append(Word(text, float(word.start), float(word.end)))
    return words, info.language
