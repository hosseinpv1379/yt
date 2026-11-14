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


def transcribe(audio: Path, model_path: str, language: str | None = None) -> tuple[list[Word], str]:
    if language not in {None, "fa", "en"}:
        raise ValueError("زبان انتخاب‌شده معتبر نیست.")
    with _model_lock:
        model = _model(model_path)
        if not getattr(getattr(model, "model", None), "is_multilingual", True) and language != "en":
            raise ValueError("مدل نصب‌شده فقط انگلیسی است؛ برای فارسی یا تشخیص خودکار مدل چندزبانه نصب کن.")
        segments, info = model.transcribe(
            str(audio), language=language, word_timestamps=True, vad_filter=True,
            vad_parameters={"threshold": 0.4, "min_silence_duration_ms": 1000, "speech_pad_ms": 400},
            beam_size=8, language_detection_segments=3, language_detection_threshold=0.8,
        )
        words = []
        for segment in segments:
            for word in segment.words or []:
                text = word.word.strip()
                if text and word.start is not None and word.end is not None and word.end > word.start:
                    words.append(Word(text, float(word.start), float(word.end)))
    return words, info.language
