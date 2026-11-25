"""Download and manage local multilingual faster-whisper models."""
import json
from pathlib import Path
from filelock import FileLock, Timeout
from .settings import config_path

# The names are deliberately restricted: no arbitrary repository or path input.
MODELS = ("tiny", "base", "small", "medium", "large-v3")
REQUIRED_FILES = ("model.bin", "config.json", "tokenizer.json")


def model_root():
    return config_path().parent / "models" / "whisper"


def is_model_ready(path):
    path = Path(path)
    try:
        for name in REQUIRED_FILES:
            item = path / name
            if not item.is_file() or item.stat().st_size == 0:
                return False
        for name in ("config.json", "tokenizer.json"):
            with (path / name).open(encoding="utf-8") as stream:
                json.load(stream)
        vocabulary = path / "vocabulary.txt"
        if not vocabulary.is_file() or vocabulary.stat().st_size == 0:
            vocabulary = path / "vocabulary.json"
            if not vocabulary.is_file() or vocabulary.stat().st_size == 0:
                return False
            with vocabulary.open(encoding="utf-8") as stream:
                json.load(stream)
    except (OSError, ValueError):
        return False
    return True


def download_whisper_model(name, root=None, progress=None, cancel_event=None, download=None):
    if name not in MODELS:
        raise ValueError("مدل انتخاب‌شده معتبر نیست.")
    root = Path(root) if root is not None else model_root()
    root.mkdir(parents=True, exist_ok=True)
    target = root / name
    try:
        with FileLock(str(root / f".{name}.lock"), timeout=0):
            if is_model_ready(target):
                return target
            if target.exists():
                raise RuntimeError(f"پوشهٔ مدل موجود ولی ناقص است: {target}")
            if cancel_event is not None and cancel_event.is_set():
                raise InterruptedError("دانلود لغو شد.")
            if download is None:
                from faster_whisper import download_model
                download = download_model
            if progress:
                progress("در حال دانلود مدل از Hugging Face؛ بسته به مدل و اینترنت ممکن است طول بکشد.")
            # Hugging Face keeps partial downloads here so retries can resume;
            # only a verified directory is renamed to the visible model path.
            folder = root / f".{name}-download"
            folder.mkdir(exist_ok=True)
            download(name, output_dir=str(folder))
            if cancel_event is not None and cancel_event.is_set():
                raise InterruptedError("دانلود لغو شد.")
            if not is_model_ready(folder):
                raise RuntimeError("دانلود کامل نبود یا فایل‌های مدل معتبر نیستند.")
            if progress:
                progress("دانلود تمام شد؛ در حال آماده‌سازی مدل…")
            folder.rename(target)
            return target
    except Timeout as exc:
        raise RuntimeError("دانلود همین مدل در برنامهٔ دیگری در حال انجام است.") from exc
