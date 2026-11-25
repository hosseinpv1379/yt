"""Local web preferences and OS-managed credentials."""
import json
import os
from pathlib import Path
from types import SimpleNamespace

SERVICE = "yt-local"
DEFAULTS = {
    "provider": "openai", "output_dir": str(Path.home() / "Movies" / "YT Local"),
    "openai_stt": "whisper-1", "openai_translation": "gpt-6-luna",
    "openai_tts": "gpt-realtime-2.1-mini", "openai_voice": "marin",
    "openrouter_stt": "openai/whisper-1", "openrouter_translation": "openai/gpt-6-luna",
    "openrouter_tts": "google/gemini-3.8-flash-lite-tts", "openrouter_voice": "Kore",
    "max_minutes": "60", "max_height": "720", "max_bytes": "1000000000",
    "youtube_cookies": "", "instagram_cookies": "", "pot_url": "",
    "watermark": "", "separator_url": "", "original_audio_percent": "10",
    "image_model": "i3", "image_aspect": "1:1", "image_reference": "",
    "caption_model_path": "", "caption_fonts_dir": "assets/fonts", "caption_language": "auto",
    "caption_color": "yellow", "caption_font": "vazirmatn", "caption_font_size": "medium",
}


def config_path():
    base = os.environ.get("APPDATA") if os.name == "nt" else str(Path.home() / "Library" / "Application Support")
    return Path(base or Path.home()) / "YT Local" / "settings.json"


def load_preferences(path=None):
    path = path or config_path()
    if not path.exists():
        return DEFAULTS.copy()
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("فایل تنظیمات معتبر نیست.")
    return {**DEFAULTS, **{k: str(v) for k, v in data.items() if k in DEFAULTS}}


def save_preferences(data, path=None):
    path = path or config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    safe = {k: str(data.get(k, v)) for k, v in DEFAULTS.items()}
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(safe, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def get_key(provider):
    import keyring
    return keyring.get_password(SERVICE, provider) or ""


def set_key(provider, value):
    import keyring
    if value:
        keyring.set_password(SERVICE, provider, value)
    elif keyring.get_password(SERVICE, provider):
        keyring.delete_password(SERVICE, provider)


def pipeline_settings(prefs, keys, directory):
    def number(name, low, high):
        value = int(prefs[name])
        if not low <= value <= high:
            raise ValueError(f"مقدار {name} خارج از محدوده است.")
        return value
    return SimpleNamespace(
        openai_api_key=keys.get("openai", ""), openrouter_api_key=keys.get("openrouter", ""),
        whisper_model=prefs["openai_stt"], translation_model=prefs["openai_translation"],
        tts_model=prefs["openai_tts"], tts_voice=prefs["openai_voice"],
        openrouter_transcription_model=prefs["openrouter_stt"], openrouter_model=prefs["openrouter_translation"],
        openrouter_tts_model=prefs["openrouter_tts"], openrouter_tts_voice=prefs["openrouter_voice"],
        openrouter_rpm_limit=10, openrouter_max_retries=8,
        video_max_minutes=number("max_minutes", 1, 1440), video_max_height=number("max_height", 144, 4320),
        max_file_bytes=number("max_bytes", 1000000, 100000000000),
        youtube_cookies_file=prefs["youtube_cookies"], instagram_cookies_file=prefs["instagram_cookies"],
        ytdlp_pot_base_url=prefs["pot_url"], dub_separator_url=prefs["separator_url"].rstrip("/"),
        watermark_text=prefs["watermark"], download_base_url="", work_dir=str(directory),
    )
