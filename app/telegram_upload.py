"""Optional MTProto delivery for files above the HTTP Bot API limit."""
import asyncio
import logging
from pathlib import Path

from .config import Settings

logger = logging.getLogger(__name__)
BOT_API_MAX_BYTES = 48_000_000
LARGE_UPLOAD_MAX_BYTES = 2_000_000_000


class LargeFileUploader:
    """Reuse an in-memory bot session for uploads without consuming updates."""

    def __init__(self) -> None:
        self.client = None
        self._credentials = None

    async def close(self) -> None:
        client, self.client = self.client, None
        self._credentials = None
        if client is not None:
            await client.disconnect()

    async def send(self, settings: Settings, chat_id: int, path: Path, caption: str) -> bool:
        size = path.stat().st_size
        if (not BOT_API_MAX_BYTES < size <= LARGE_UPLOAD_MAX_BYTES or chat_id <= 0
                or not settings.telegram_upload_api_id or not settings.telegram_upload_api_hash):
            return False
        credentials = (
            int(settings.telegram_upload_api_id),
            settings.telegram_upload_api_hash,
            settings.telegram_bot_token,
        )
        try:
            from telethon import TelegramClient
            from telethon.sessions import MemorySession
            from telethon.tl.types import InputPeerUser

            if self.client is None or self._credentials != credentials:
                await self.close()
                self.client = TelegramClient(
                    MemorySession(), credentials[0], credentials[1],
                    receive_updates=False, flood_sleep_threshold=0,
                )
                self._credentials = credentials

            async with asyncio.timeout(45):
                await self.client.start(bot_token=credentials[2])
            async with asyncio.timeout(2 * 60 * 60):
                uploaded = await self.client.upload_file(
                    path, file_size=size, part_size_kb=512,
                )
                await self.client.send_file(
                    InputPeerUser(chat_id, 0), uploaded,
                    caption=caption, parse_mode=None, force_document=True,
                )
            return True
        except Exception as exc:
            # Avoid logging credentials, temporary paths, and raw RPC requests.
            logger.warning("Large Telegram upload failed (%s)", type(exc).__name__)
            return False


async def send_large_file(application, settings: Settings, chat_id: int, path: Path, caption: str) -> bool:
    uploader = application.bot_data.get("large_file_uploader")
    if uploader is None:
        uploader = application.bot_data["large_file_uploader"] = LargeFileUploader()
    return await uploader.send(settings, chat_id, path, caption)
