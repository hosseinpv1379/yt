"""Single-user jobs shared by the local HTTP interface."""
import shutil
import tempfile
import threading
import uuid
from pathlib import Path

from . import models, settings


class LocalService:
    def __init__(self):
        self.lock = threading.Lock()
        self.cancel = threading.Event()
        self.job = {"running": False, "message": "آماده", "percent": 0}

    def status(self):
        with self.lock:
            return self.job.copy()

    def update(self, message, percent=0):
        with self.lock:
            self.job.update(message=str(message), percent=percent)

    def start(self, kind, source):
        allowed = {"subtitle", "dub", "smart_dub", "video", "audio", "media", "profile",
                   "summary", "social", "image", "local_caption", "local_color", "local_both", "model"}
        if kind not in allowed or not isinstance(source, str) or not source.strip():
            raise ValueError("نوع عملیات یا ورودی معتبر نیست.")
        with self.lock:
            if self.job["running"]:
                raise ValueError("یک عملیات در حال اجراست.")
            self.job = {"running": True, "message": "در حال آماده‌سازی…", "percent": 0}
            self.cancel.clear()
        threading.Thread(target=self._run, args=(kind, source.strip()), daemon=True).start()

    def _run(self, kind, source):
        try:
            if kind == "model":
                path = models.download_whisper_model(source, progress=self.update, cancel_event=self.cancel)
                prefs = settings.load_preferences()
                prefs["caption_model_path"] = str(path)
                settings.save_preferences(prefs)
                self.update(f"مدل {source} آماده و انتخاب شد.", 100)
                return
            prefs = settings.load_preferences()
            provider = prefs["provider"]
            if provider not in ("openai", "openrouter"):
                raise ValueError("ارائه‌دهنده معتبر نیست.")
            needs_api = kind in {"subtitle", "dub", "smart_dub", "summary", "social", "image"}
            keys = {name: settings.get_key(name) for name in ("openai", "openrouter")} if needs_api else {}
            if needs_api and not keys[provider]:
                raise ValueError("کلید API ارائه‌دهنده را در تنظیمات ذخیره کنید.")
            with tempfile.TemporaryDirectory(prefix="yt-local-") as tmp:
                work = Path(tmp) / uuid.uuid4().hex
                work.mkdir()
                config = settings.pipeline_settings(prefs, keys, work)
                if kind in {"subtitle", "dub", "smart_dub"}:
                    from app.pipeline import process_video
                    local_separator = None
                    if kind == "smart_dub":
                        if not shutil.which("spleeter"):
                            raise ValueError("Spleeter برای دوبلهٔ هوشمند نصب نیست.")
                        from separator.server import separate
                        local_separator = lambda directory, video: separate(directory.name, video.name, root=directory.parent)
                    output, srt, vtt, _ = process_video(source, work, config, self.cancel,
                        progress_callback=self.update, mode="subtitle" if kind == "subtitle" else "dub",
                        dub_mode="smart" if kind == "smart_dub" else "simple", local_separator=local_separator,
                        provider=provider, original_audio_percent=int(prefs["original_audio_percent"]))
                    files = [output, srt, vtt]
                elif kind in {"summary", "social"}:
                    from app.content import generate_content
                    from app.model_catalog import defaults
                    text, _ = generate_content(Path(source).read_text(encoding="utf-8-sig"), kind, config,
                                               defaults(config, provider), self.cancel)
                    output = work / f"{kind}.txt"
                    output.write_text(text, encoding="utf-8")
                    files = [output]
                elif kind.startswith("local_"):
                    from features.video_captions.pipeline import render
                    source_file = Path(source).expanduser().resolve()
                    if not source_file.is_file():
                        raise ValueError("فایل ویدیوی محلی پیدا نشد.")
                    language = prefs["caption_language"]
                    if language not in {"auto", "fa", "en"}:
                        raise ValueError("زبان زیرنویس معتبر نیست.")
                    output = work / "captioned.mp4"
                    render(source_file, output, kind.removeprefix("local_"), prefs["caption_color"],
                        prefs["caption_model_path"], Path(prefs["caption_fonts_dir"]), self.cancel,
                        self.update, language=None if language == "auto" else language,
                        font=prefs["caption_font"], font_size=prefs["caption_font_size"])
                    files = [output]
                elif kind == "image":
                    from app.image_generation import BY_CODE, generate_image, image_type, optimize_prompt
                    from app.model_catalog import defaults
                    model = BY_CODE.get(prefs["image_model"])
                    if not model or not keys.get(model.provider):
                        raise ValueError("مدل تصویر یا کلید ارائه‌دهندهٔ آن معتبر نیست.")
                    ref = Path(prefs["image_reference"]).read_bytes() if prefs["image_reference"] else None
                    mime = image_type(ref) if ref else None
                    if ref and not mime:
                        raise ValueError("فرمت تصویر ورودی معتبر نیست.")
                    if prefs["image_aspect"] not in {"1:1", "2:3", "3:2"}:
                        raise ValueError("نسبت تصویر معتبر نیست.")
                    prompt, _ = optimize_prompt(source, config, defaults(config, provider).translation, ref, mime)
                    image, mime, _ = generate_image(prompt, source, prefs["image_aspect"], config, model, ref, mime)
                    output = work / ("image." + {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}[mime])
                    output.write_bytes(image)
                    files = [output]
                else:
                    from app.downloads import download_media
                    output, _ = download_media(source, kind, work, config, self.cancel, self.update)
                    files = [output]
                if self.cancel.is_set():
                    raise InterruptedError("پردازش لغو شد.")
                destination = Path(prefs["output_dir"]).expanduser() / f"job-{uuid.uuid4().hex[:12]}"
                destination.mkdir(parents=True, exist_ok=False)
                for file in files:
                    shutil.copy2(file, destination / file.name)
                self.update(f"خروجی ذخیره شد: {destination}", 100)
        except Exception as exc:
            self.update(f"عملیات ناموفق بود: {exc}")
        finally:
            with self.lock:
                self.job["running"] = False
