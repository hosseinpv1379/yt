from dataclasses import dataclass
import os

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    allowed_user_ids: frozenset[int]
    openai_api_key: str
    openai_admin_key: str
    openai_project_id: str
    openrouter_api_key: str
    openrouter_model: str
    openrouter_transcription_model: str
    openrouter_tts_model: str
    openrouter_tts_voice: str
    openrouter_rpm_limit: int
    openrouter_max_retries: int
    default_api_provider: str
    provider_control_user_id: int
    translation_model: str
    whisper_model: str
    video_max_minutes: int
    video_max_height: int
    max_file_bytes: int
    work_dir: str
    youtube_cookies_file: str
    instagram_cookies_file: str
    ytdlp_pot_base_url: str
    download_dir: str
    download_base_url: str
    download_ttl_hours: int
    database_url: str
    tts_model: str
    tts_voice: str
    watermark_text: str
    default_subtitle_price_toman_per_minute: int
    default_dub_price_toman_per_minute: int
    support_username: str
    card_to_card_number: str
    card_to_card_holder: str
    minimum_wallet_topup_toman: int
    dub_separator_url: str = ""


def load_settings() -> Settings:
    load_dotenv()
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    openrouter_api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    user_ids = os.getenv("ALLOWED_USER_IDS", "").strip()
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not token or not (api_key or openrouter_api_key) or not user_ids or not database_url:
        raise RuntimeError(
            "Set TELEGRAM_BOT_TOKEN, at least one provider API key, ALLOWED_USER_IDS, "
            "and DATABASE_URL in .env"
        )

    try:
        allowed = frozenset(int(item.strip()) for item in user_ids.split(",") if item.strip())
    except ValueError as exc:
        raise RuntimeError("ALLOWED_USER_IDS must be comma-separated numeric Telegram IDs") from exc
    if not allowed:
        raise RuntimeError("ALLOWED_USER_IDS must contain at least one Telegram user ID")

    default_control_id = int(next(item.strip() for item in user_ids.split(",") if item.strip()))
    control_id_value = os.getenv("PROVIDER_CONTROL_USER_ID", "").strip() or str(default_control_id)
    try:
        provider_control_user_id = int(control_id_value)
    except ValueError as exc:
        raise RuntimeError("PROVIDER_CONTROL_USER_ID must be a numeric Telegram ID") from exc
    if provider_control_user_id not in allowed:
        raise RuntimeError("PROVIDER_CONTROL_USER_ID must be included in ALLOWED_USER_IDS")
    provider_value = os.getenv("DEFAULT_API_PROVIDER", "").strip().lower()
    default_api_provider = provider_value or ("openrouter" if openrouter_api_key else "openai")
    if default_api_provider not in {"openai", "openrouter"}:
        raise RuntimeError("DEFAULT_API_PROVIDER must be openai or openrouter")

    return Settings(
        telegram_bot_token=token,
        allowed_user_ids=allowed,
        openai_api_key=api_key,
        openai_admin_key=os.getenv("OPENAI_ADMIN_KEY", "").strip(),
        openai_project_id=os.getenv("OPENAI_PROJECT_ID", "").strip(),
        openrouter_api_key=openrouter_api_key,
        openrouter_model=os.getenv("OPENROUTER_MODEL", "openai/gpt-6-luna").strip(),
        openrouter_transcription_model=os.getenv(
            "OPENROUTER_TRANSCRIPTION_MODEL", "openai/whisper-1"
        ).strip(),
        openrouter_tts_model=os.getenv(
            "OPENROUTER_TTS_MODEL", "google/gemini-3.8-flash-lite-tts"
        ).strip(),
        openrouter_tts_voice=os.getenv("OPENROUTER_TTS_VOICE", "Kore").strip(),
        openrouter_rpm_limit=max(1, min(60, int(os.getenv("OPENROUTER_RPM_LIMIT", "10")))),
        openrouter_max_retries=max(0, min(10, int(os.getenv("OPENROUTER_MAX_RETRIES", "8")))),
        default_api_provider=default_api_provider,
        provider_control_user_id=provider_control_user_id,
        translation_model=os.getenv("TRANSLATION_MODEL", "gpt-6-luna").strip(),
        whisper_model=os.getenv("WHISPER_MODEL", "whisper-1"),
        video_max_minutes=max(1, int(os.getenv("VIDEO_MAX_MINUTES", "60"))),
        video_max_height=max(144, int(os.getenv("VIDEO_MAX_HEIGHT", "720"))),
        max_file_bytes=max(1_000_000, int(os.getenv("MAX_FILE_BYTES", "1000000000"))),
        work_dir=os.getenv("WORK_DIR", "/data"),
        youtube_cookies_file=os.getenv("YOUTUBE_COOKIES_FILE", "").strip(),
        instagram_cookies_file=os.getenv("INSTAGRAM_COOKIES_FILE", "").strip(),
        ytdlp_pot_base_url=os.getenv("YTDLP_POT_BASE_URL", "http://pot-provider:4416").strip(),
        download_dir=os.getenv("DOWNLOAD_DIR", "/downloads"),
        download_base_url=os.getenv("DOWNLOAD_BASE_URL", "").strip().rstrip("/"),
        download_ttl_hours=max(1, int(os.getenv("DOWNLOAD_TTL_HOURS", "24"))),
        database_url=database_url,
        tts_model=os.getenv("TTS_MODEL", "gpt-realtime-2.1-mini").strip(),
        tts_voice=os.getenv("TTS_VOICE", "marin").strip(),
        watermark_text=os.getenv("WATERMARK_TEXT", "").strip(),
        default_subtitle_price_toman_per_minute=max(1, int(os.getenv("DEFAULT_SUBTITLE_PRICE_TOMAN_PER_MINUTE", "5000"))),
        default_dub_price_toman_per_minute=max(1, int(os.getenv("DEFAULT_DUB_PRICE_TOMAN_PER_MINUTE", "10000"))),
        support_username=os.getenv("SUPPORT_USERNAME", "").strip().removeprefix("@"),
        card_to_card_number="".join(c for c in os.getenv("CARD_TO_CARD_NUMBER", "") if c.isdigit()),
        card_to_card_holder=os.getenv("CARD_TO_CARD_HOLDER", "").strip(),
        minimum_wallet_topup_toman=max(1, int(os.getenv("MINIMUM_WALLET_TOPUP_TOMAN", "50000"))),
        dub_separator_url=os.getenv("DUB_SEPARATOR_URL", "").strip().rstrip("/"),
    )
