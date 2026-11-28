"""Cloud dialogue separation for the dubbing pipeline."""
import logging
import time
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit, urlunsplit

import httpx

logger = logging.getLogger(__name__)
API_URL = "https://www.lalal.ai/api/v1/"
POLL_SECONDS = 5
PROCESSING_TIMEOUT = 20 * 60
MAX_AUDIO_BYTES = 10_000_000_000


def _identifier(payload: dict, field: str) -> str:
    value = payload[field]
    if not isinstance(value, str) or not value:
        raise ValueError("Missing task or source identifier")
    return value


def _background_url(task: dict) -> str:
    track = next(track for track in task["result"]["tracks"]
                 if track["type"] == "back" and track["label"] == "no_voice")
    url = urlsplit(track["url"])
    # The API examples use HTTP for this CDN. Always download over HTTPS.
    if url.scheme not in {"http", "https"} or url.netloc != "d.lalal.ai":
        raise ValueError("Unexpected separation download host")
    return urlunsplit(("https", url.netloc, url.path, url.query, ""))


def download_background(
    audio: Path,
    output: Path,
    license_key: str,
    check_cancel: Callable[[], None],
) -> None:
    """Upload only audio, retrieve the background stem, and clean up the source."""
    size = audio.stat().st_size
    if not 0 < size <= MAX_AUDIO_BYTES:
        raise RuntimeError("حجم ترک صوتی خارج از محدودیت LALAL.AI است.")
    timeout = httpx.Timeout(30, connect=10)
    source_id = None
    try:
        with httpx.Client(base_url=API_URL, headers={"X-License-Key": license_key}, timeout=timeout) as api:
            try:
                check_cancel()
                with audio.open("rb") as stream:
                    def upload_chunks():
                        while chunk := stream.read(256 * 1024):
                            check_cancel()
                            yield chunk

                    response = api.post("upload/", content=upload_chunks(), headers={
                        "Content-Type": "application/octet-stream",
                        "Content-Disposition": 'attachment; filename="source.flac"',
                        "Content-Length": str(size),
                    })
                source_id = _identifier(response.raise_for_status().json(), "id")
                check_cancel()
                task_id = _identifier(api.post("split/voice_clean/", json={
                    "source_id": source_id,
                    "presets": {"stem": "voice", "encoder_format": "flac"},
                }).raise_for_status().json(), "task_id")
                deadline = time.monotonic() + PROCESSING_TIMEOUT
                next_poll = time.monotonic()
                while time.monotonic() < deadline:
                    check_cancel()
                    if time.monotonic() < next_poll:
                        time.sleep(0.25)
                        continue
                    response = api.post("check/", json={"task_ids": [task_id]})
                    next_poll = time.monotonic() + POLL_SECONDS
                    if response.status_code in {429, 502, 503, 504}:
                        continue
                    task = response.raise_for_status().json()["result"][task_id]
                    if task["status"] == "success":
                        url = _background_url(task)
                        break
                    if task["status"] != "progress":
                        raise ValueError("Separation task failed")
                else:
                    raise TimeoutError("Separation task timed out")

                check_cancel()
                # Do not put the API credential on CDN requests.
                with httpx.stream("GET", url, timeout=timeout) as response, output.open("wb") as file:
                    response.raise_for_status()
                    for chunk in response.iter_bytes(chunk_size=256 * 1024):
                        check_cancel()
                        if file.tell() + len(chunk) > MAX_AUDIO_BYTES:
                            raise ValueError("Separation result exceeds the size limit")
                        file.write(chunk)
            finally:
                if source_id:
                    try:
                        api.post("delete/", json={"source_id": source_id}, timeout=5).raise_for_status()
                    except httpx.HTTPError:
                        logger.warning("Could not remove temporary LALAL.AI source")
    except (httpx.HTTPError, KeyError, TypeError, ValueError, StopIteration, TimeoutError) as exc:
        status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
        logger.warning("LALAL.AI separation failed (%s, HTTP status %s)", type(exc).__name__, status)
        raise RuntimeError("تفکیک صدای پس‌زمینه با LALAL.AI ناموفق بود.") from None
