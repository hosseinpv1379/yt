"""Startup credentials and defaults for settings managed by the Telegram admin panel."""
from dataclasses import dataclass
import os
import re
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.engine import URL

from .domain_names import normalize_public_domain


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    allowed_user_ids: frozenset[int]
    provider_control_user_id: int
    database_url: str
    openai_api_key: str = ""
    openai_admin_key: str = ""
    openai_project_id: str = ""
    openrouter_api_key: str = ""
    openrouter_model: str = "openai/gpt-6-luna"
    openrouter_transcription_model: str = "openai/whisper-1"
    openrouter_tts_model: str = "google/gemini-3.8-flash-lite-tts"
    openrouter_tts_voice: str = "Kore"
    openrouter_rpm_limit: int = 10
    openrouter_max_retries: int = 8
    default_api_provider: str = "openai"
    translation_model: str = "gpt-6-luna"
    whisper_model: str = "whisper-1"
    video_max_minutes: int = 60
    video_max_height: int = 720
    max_file_bytes: int = 1_000_000_000
    ffmpeg_threads: int = 2
    ffmpeg_preset: str = "superfast"
    work_dir: str = "/data"
    youtube_cookies_file: str = ""
    instagram_cookies_file: str = ""
    ytdlp_pot_base_url: str = "http://pot-provider:4416"
    download_dir: str = "/downloads"
    download_base_url: str = ""
    download_domain: str = ""
    download_ttl_hours: int = 24
    tts_model: str = "gpt-realtime-2.1-mini"
    tts_voice: str = "marin"
    watermark_text: str = ""
    default_subtitle_price_toman_per_minute: int = 5000
    default_dub_price_toman_per_minute: int = 10000
    support_username: str = ""
    card_to_card_number: str = ""
    card_to_card_holder: str = ""
    minimum_wallet_topup_toman: int = 50000
    dub_separator_url: str = ""
    dub_separator_backend: str = "local"
    lalal_license_key: str = ""
    telegram_upload_api_id: str = ""
    telegram_upload_api_hash: str = ""
    caption_model_path: str = "/data/models/whisper-medium"
    caption_fonts_dir: str = "/app/assets/fonts"
    caption_background_brightness: float = 0.55
    caption_background_saturation: float = 0.80
    caption_subject_saturation: float = 1.25
    caption_contrast: float = 1.10
    caption_mask_smoothing: float = 0.75


# These are copied to the database once, then edited from /admin. Keeping the
# dataclass attributes here makes old .env files migrate without keeping them
# in the runtime configuration path.
ADMIN_SETTING_FIELDS = (
    "openai_api_key", "openai_admin_key", "openai_project_id",
    "openrouter_api_key", "openrouter_model", "openrouter_transcription_model",
    "openrouter_tts_model", "openrouter_tts_voice", "openrouter_rpm_limit",
    "openrouter_max_retries", "translation_model", "whisper_model",
    "video_max_minutes", "video_max_height", "max_file_bytes", "ffmpeg_threads",
    "ffmpeg_preset", "youtube_cookies_file", "instagram_cookies_file",
    "ytdlp_pot_base_url", "download_base_url", "download_domain", "download_ttl_hours", "tts_model",
    "tts_voice", "watermark_text", "default_subtitle_price_toman_per_minute",
    "default_dub_price_toman_per_minute", "support_username", "card_to_card_number",
    "card_to_card_holder", "minimum_wallet_topup_toman", "dub_separator_url",
    "dub_separator_backend", "lalal_license_key",
    "telegram_upload_api_id", "telegram_upload_api_hash",
    "caption_model_path", "caption_background_brightness",
    "caption_background_saturation", "caption_subject_saturation",
    "caption_contrast", "caption_mask_smoothing",
)

def _env(name: str, default: str) -> str:
    return os.getenv(name, default).strip()


def _bounded_int(name: str, default: int, minimum: int, maximum: int | None = None) -> int:
    value = int(_env(name, str(default)))
    return max(minimum, min(maximum, value) if maximum is not None else value)


def load_settings() -> Settings:
    """Load the only required environment values plus backward-compatible defaults."""
    load_dotenv()
    token = _env("TELEGRAM_BOT_TOKEN", "")
    admin_value = _env("ADMIN_USER_ID", "")
    if not admin_value:
        # One-time compatibility with older deployments; new .env files use ADMIN_USER_ID.
        admin_value = (_env("PROVIDER_CONTROL_USER_ID", "")
                       or _env("ALLOWED_USER_IDS", "").split(",", 1)[0].strip())
    if not token or not admin_value:
        raise RuntimeError("Set TELEGRAM_BOT_TOKEN and ADMIN_USER_ID in .env")
    try:
        admin_id = int(admin_value)
        if admin_id <= 0:
            raise ValueError
    except ValueError as exc:
        raise RuntimeError("ADMIN_USER_ID must be a positive numeric Telegram ID") from exc

    openai_key = _env("OPENAI_API_KEY", "")
    openrouter_key = _env("OPENROUTER_API_KEY", "")
    provider_value = _env("DEFAULT_API_PROVIDER", "").lower()
    provider = provider_value or ("openrouter" if openrouter_key and not openai_key else "openai")
    if provider not in {"openai", "openrouter"}:
        raise RuntimeError("DEFAULT_API_PROVIDER must be openai or openrouter")
    db_secret = Path("/run/database-secret/postgres_password")
    db_host = "database"
    if not db_secret.is_file():
        db_secret = Path(__file__).resolve().parents[1] / "secrets" / "postgres_password"
        db_host = "127.0.0.1"
    if db_secret.is_file():
        db_default = URL.create(
            "postgresql+asyncpg", username="ytbot", password=db_secret.read_text().strip(),
            host=db_host, port=5432, database="ytbot",
        ).render_as_string(hide_password=False)
    else:
        db_default = "postgresql+asyncpg://ytbot:ytbot-local-internal@127.0.0.1:5432/ytbot"

    return Settings(
        telegram_bot_token=token,
        allowed_user_ids=frozenset({admin_id}),
        provider_control_user_id=admin_id,
        database_url=_env("DATABASE_URL", db_default),
        openai_api_key=openai_key,
        openai_admin_key=_env("OPENAI_ADMIN_KEY", ""),
        openai_project_id=_env("OPENAI_PROJECT_ID", ""),
        openrouter_api_key=openrouter_key,
        openrouter_model=_env("OPENROUTER_MODEL", "openai/gpt-6-luna"),
        openrouter_transcription_model=_env("OPENROUTER_TRANSCRIPTION_MODEL", "openai/whisper-1"),
        openrouter_tts_model=_env("OPENROUTER_TTS_MODEL", "google/gemini-3.8-flash-lite-tts"),
        openrouter_tts_voice=_env("OPENROUTER_TTS_VOICE", "Kore"),
        openrouter_rpm_limit=_bounded_int("OPENROUTER_RPM_LIMIT", 10, 1, 60),
        openrouter_max_retries=_bounded_int("OPENROUTER_MAX_RETRIES", 8, 0, 10),
        default_api_provider=provider,
        translation_model=_env("TRANSLATION_MODEL", "gpt-6-luna"),
        whisper_model=_env("WHISPER_MODEL", "whisper-1"),
        video_max_minutes=_bounded_int("VIDEO_MAX_MINUTES", 60, 1, 10000),
        video_max_height=_bounded_int("VIDEO_MAX_HEIGHT", 720, 144, 4320),
        max_file_bytes=_bounded_int("MAX_FILE_BYTES", 1_000_000_000, 1_000_000, 100_000_000_000),
        ffmpeg_threads=_bounded_int("FFMPEG_THREADS", 2, 1, 16),
        ffmpeg_preset=_env("FFMPEG_PRESET", "superfast"),
        work_dir=_env("WORK_DIR", "/data"),
        youtube_cookies_file=_env("YOUTUBE_COOKIES_FILE", ""),
        instagram_cookies_file=_env("INSTAGRAM_COOKIES_FILE", ""),
        ytdlp_pot_base_url=_env("YTDLP_POT_BASE_URL", "http://pot-provider:4416"),
        download_dir=_env("DOWNLOAD_DIR", "/downloads"),
        download_base_url=_env("DOWNLOAD_BASE_URL", "").rstrip("/"),
        download_domain=_env("DOWNLOAD_HOST", ""),
        download_ttl_hours=_bounded_int("DOWNLOAD_TTL_HOURS", 24, 1, 8760),
        tts_model=_env("TTS_MODEL", "gpt-realtime-2.1-mini"),
        tts_voice=_env("TTS_VOICE", "marin"),
        watermark_text=_env("WATERMARK_TEXT", ""),
        default_subtitle_price_toman_per_minute=_bounded_int("DEFAULT_SUBTITLE_PRICE_TOMAN_PER_MINUTE", 5000, 1, 1_000_000_000),
        default_dub_price_toman_per_minute=_bounded_int("DEFAULT_DUB_PRICE_TOMAN_PER_MINUTE", 10000, 1, 1_000_000_000),
        support_username=_env("SUPPORT_USERNAME", "").removeprefix("@"),
        card_to_card_number="".join(c for c in _env("CARD_TO_CARD_NUMBER", "") if c.isdigit()),
        card_to_card_holder=_env("CARD_TO_CARD_HOLDER", ""),
        minimum_wallet_topup_toman=_bounded_int("MINIMUM_WALLET_TOPUP_TOMAN", 50000, 1, 1_000_000_000),
        dub_separator_url=_env("DUB_SEPARATOR_URL", "http://dub-separator:8090").rstrip("/"),
        caption_model_path=_env("CAPTION_MODEL_PATH", "/data/models/whisper-medium"),
        caption_fonts_dir=_env("CAPTION_FONTS_DIR", "/app/assets/fonts"),
        caption_background_brightness=max(0.0, min(1.0, float(_env("CAPTION_BACKGROUND_BRIGHTNESS", "0.55")))),
        caption_background_saturation=max(0.0, min(2.0, float(_env("CAPTION_BACKGROUND_SATURATION", "0.80")))),
        caption_subject_saturation=max(0.0, min(2.0, float(_env("CAPTION_SUBJECT_SATURATION", "1.25")))),
        caption_contrast=max(0.0, min(2.0, float(_env("CAPTION_CONTRAST", "1.10")))),
        caption_mask_smoothing=max(0.0, min(0.99, float(_env("CAPTION_MASK_SMOOTHING", "0.75")))),
    )


def parse_admin_setting(settings: Settings, name: str, value: str):
    """Validate and normalize an admin-edited setting, returning its Python value."""
    if name not in ADMIN_SETTING_FIELDS:
        raise ValueError("تنظیم ناشناخته است.")
    raw = value.strip()
    current = getattr(settings, name)
    if isinstance(current, bool):
        raise ValueError("مقدار نامعتبر است.")
    if isinstance(current, int):
        try:
            parsed = int(raw.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")))
        except ValueError as exc:
            raise ValueError("یک عدد صحیح معتبر بفرست.") from exc
        limits = {
            "openrouter_rpm_limit": (1, 60), "openrouter_max_retries": (0, 10),
            "video_max_minutes": (1, 10000), "video_max_height": (144, 4320),
            "max_file_bytes": (1_000_000, 100_000_000_000), "ffmpeg_threads": (1, 16),
            "download_ttl_hours": (1, 8760),
            "default_subtitle_price_toman_per_minute": (1, 1_000_000_000),
            "default_dub_price_toman_per_minute": (1, 1_000_000_000),
            "minimum_wallet_topup_toman": (1, 1_000_000_000),
        }
        low, high = limits[name]
        if not low <= parsed <= high:
            raise ValueError(f"مقدار باید بین {low:,} و {high:,} باشد.")
        return parsed
    if isinstance(current, float):
        try:
            parsed = float(raw.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")))
        except ValueError as exc:
            raise ValueError("یک عدد معتبر بفرست.") from exc
        if not 0 <= parsed <= (0.99 if name == "caption_mask_smoothing" else 2):
            raise ValueError("مقدار خارج از محدوده است.")
        return parsed
    max_length = 254 if name == "download_domain" else 240
    if len(raw) > max_length:
        raise ValueError(f"متن حداکثر می‌تواند {max_length} نویسه باشد.")
    optional = {
        "openai_api_key", "openai_admin_key", "openai_project_id", "openrouter_api_key",
        "youtube_cookies_file", "instagram_cookies_file", "watermark_text",
        "download_base_url", "download_domain", "card_to_card_number", "card_to_card_holder",
        "support_username", "dub_separator_url", "lalal_license_key",
        "telegram_upload_api_id", "telegram_upload_api_hash",
    }
    if not raw and name not in optional:
        raise ValueError("این مقدار نمی‌تواند خالی باشد.")
    if name in optional and raw.lower() in {"پاک", "حذف", "clear", "none", "-"}:
        return ""
    if name == "download_domain":
        return normalize_public_domain(raw)
    if name == "telegram_upload_api_id":
        if raw and (not re.fullmatch(r"[0-9]{1,10}", raw) or not 0 < int(raw) <= 2_147_483_647):
            raise ValueError("API ID تلگرام باید یک عدد صحیح مثبت باشد.")
        return str(int(raw)) if raw else ""
    if name == "telegram_upload_api_hash":
        if raw and not re.fullmatch(r"[0-9a-fA-F]{32}", raw):
            raise ValueError("API Hash تلگرام باید ۳۲ نویسهٔ شانزده‌شانزدهی باشد.")
        return raw.lower()
    if name == "dub_separator_backend":
        if raw.lower() not in {"fast", "local", "lalal"}:
            raise ValueError("برای حالت سریع fast، مدل محلی local یا تفکیک ابری lalal بفرست.")
        return raw.lower()
    if name == "lalal_license_key":
        if raw and any(not 33 <= ord(char) <= 126 for char in raw):
            raise ValueError("کلید LALAL.AI را بدون فاصله یا خط اضافه بفرست.")
        return raw
    if name in {"openai_api_key", "openai_admin_key", "openai_project_id", "openrouter_api_key"}:
        return raw
    if name == "support_username":
        return raw.removeprefix("@").strip()
    if name == "card_to_card_number":
        digits = "".join(char for char in raw if char.isdigit())
        if raw and len(digits) < 10:
            raise ValueError("شماره کارت باید دست‌کم ۱۰ رقم داشته باشد؛ برای پاک‌کردن «پاک» بفرست.")
        return digits
    if name == "ffmpeg_preset" and raw not in {"ultrafast", "superfast", "veryfast", "faster", "fast", "medium"}:
        raise ValueError("یکی از این مقادیر را بفرست: ultrafast, superfast, veryfast, faster, fast, medium")
    if name in {"download_base_url", "dub_separator_url"}:
        if raw and not raw.startswith(("http://", "https://")):
            raise ValueError("نشانی باید با http:// یا https:// شروع شود.")
        return raw.rstrip("/")
    if name == "ytdlp_pot_base_url" and raw and not raw.startswith(("http://", "https://")):
        raise ValueError("نشانی باید با http:// یا https:// شروع شود.")
    return raw
