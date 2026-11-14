"""Download-only flows for supported social media links."""
import json
import re
import shutil
import zipfile
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request

import httpx
import yt_dlp

from .pipeline import JobCancelled, _run, validate_youtube_url

# Exact hosts only: do not allow arbitrary internet URLs or user-supplied ports.
EXTRACTOR_PATTERN = r'(?i)^(youtube|instagram|tiktok|twitter|facebook|vimeo|dailymotion|reddit|aparat|soundcloud)'

SOCIAL_HOSTS = {
    'instagram.com', 'www.instagram.com', 'm.instagram.com',
    'tiktok.com', 'www.tiktok.com', 'm.tiktok.com', 'vm.tiktok.com', 'vt.tiktok.com',
    'twitter.com', 'www.twitter.com', 'mobile.twitter.com', 'x.com', 'www.x.com', 'mobile.x.com',
    'facebook.com', 'www.facebook.com', 'm.facebook.com', 'web.facebook.com', 'fb.watch',
    'vimeo.com', 'www.vimeo.com', 'player.vimeo.com',
    'dailymotion.com', 'www.dailymotion.com', 'dai.ly',
    'reddit.com', 'www.reddit.com', 'old.reddit.com', 'v.redd.it',
    'aparat.com', 'www.aparat.com', 'soundcloud.com', 'www.soundcloud.com', 'on.soundcloud.com',
}


def classify_link(url: str) -> str | None:
    try:
        parsed = urlparse(url)
        if parsed.scheme != 'https' or parsed.username or parsed.password or parsed.port not in (None, 443):
            return None
        host = (parsed.hostname or '').lower()
    except ValueError:
        return None
    if validate_youtube_url(url):
        return 'youtube'
    if host == 'open.spotify.com':
        return 'spotify' if re.fullmatch(r'/(?:intl-[a-z]{2}/)?track/[A-Za-z0-9]{22}/?', parsed.path) else 'spotify_unsupported'
    if host in SOCIAL_HOSTS:
        return 'social'
    return None


def is_instagram_url(url: str) -> bool:
    try:
        return (urlparse(url).hostname or "").lower() in {
            "instagram.com", "www.instagram.com", "m.instagram.com",
        }
    except ValueError:
        return False


def is_instagram_media_url(url: str) -> bool:
    """Accept individual Instagram posts, reels, stories, and highlights."""
    if not is_instagram_url(url):
        return False
    parts = [part for part in urlparse(url).path.split("/") if part]
    if not parts:
        return False
    if parts[0] in {"p", "reel", "reels", "tv", "igtv", "live", "guide"}:
        return len(parts) >= 2
    if len(parts) >= 2 and parts[-1] == "live":
        return True
    if parts[0] == "stories":
        if len(parts) >= 2 and parts[1] == "highlights":
            return len(parts) >= 3
        return len(parts) >= 2
    if parts[0] == "share":
        return len(parts) >= 3 and parts[1] in {"p", "reel", "reels", "tv", "igtv"}
    return False


def resolve_spotify_track(url: str, settings) -> tuple[str, str]:
    """Resolve one Spotify track to a labelled public YouTube search result."""
    if classify_link(url) != 'spotify':
        raise RuntimeError('فقط لینک تک‌آهنگ Spotify پشتیبانی می‌شود.')
    response = httpx.get('https://open.spotify.com/oembed', params={'url': url},
                         timeout=20, follow_redirects=False)
    response.raise_for_status()
    data = response.json()
    title = str(data.get('title') or '').strip()
    artist = str(data.get('author_name') or '').strip()
    if not title:
        raise RuntimeError('مشخصات آهنگ از Spotify دریافت نشد.')
    options = {'quiet': True, 'no_warnings': True, 'noplaylist': True, 'socket_timeout': 30,
               'extract_flat': True, 'allowed_extractors': [r'(?i)^youtube'], 'extractor_args': {
                   'youtubepot-bgutilhttp': {'base_url': [settings.ytdlp_pot_base_url]}}}
    with yt_dlp.YoutubeDL(options) as ydl:
        found = ydl.extract_info(f'ytsearch1:{title} {artist} audio', download=False)
    entry = next(iter((found or {}).get('entries') or []), None)
    video_id = str((entry or {}).get('id') or '')
    if not re.fullmatch(r'[A-Za-z0-9_-]{11}', video_id):
        raise RuntimeError('نسخهٔ مشابه در YouTube پیدا نشد.')
    return f'https://www.youtube.com/watch?v={video_id}', str(entry.get('title') or title)[:200]


def _instagram_cookie_options(settings, directory: Path) -> dict:
    cookie_path = getattr(settings, "instagram_cookies_file", "")
    if not cookie_path:
        return {}
    source = Path(cookie_path)
    if not source.is_file():
        raise RuntimeError("فایل cookies اینستاگرام در دسترس نیست.")
    copy = directory / "instagram-cookies.txt"
    shutil.copyfile(source, copy)
    return {"cookiefile": str(copy)}


def _walk_story_media(value, seen: set[str] | None = None):
    """Find Instagram story media objects embedded in the story page JSON."""
    seen = seen if seen is not None else set()
    if isinstance(value, dict):
        videos = value.get("video_versions") or []
        images = (value.get("image_versions2") or {}).get("candidates") or []
        media_id = str(value.get("pk") or value.get("id") or "")
        carousel = value.get("carousel_media")
        if (videos or images) and not carousel and (not media_id or media_id not in seen):
            if media_id:
                seen.add(media_id)
            yield value
        for child in value.values():
            yield from _walk_story_media(child, seen)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_story_media(child, seen)


def _instagram_media_from_page(ydl, url: str, cancel_event) -> list[dict]:
    """Recover preloaded Instagram media JSON when yt-dlp returns no formats."""
    if cancel_event.is_set():
        raise JobCancelled()
    request = Request(url, headers={"Referer": "https://www.instagram.com/"})
    with ydl.urlopen(request) as response:
        page = response.read(8_000_001)
    if len(page) > 8_000_000:
        return []
    html = page.decode("utf-8", errors="replace")
    found: list[dict] = []
    seen: set[str] = set()
    for script in re.findall(r"<script\b[^>]*\bdata-sjs[^>]*>(\{.*?\})</script>", html, re.DOTALL):
        try:
            found.extend(_walk_story_media(json.loads(script), seen))
        except json.JSONDecodeError:
            continue
    markers = (
        '"xdt_api__v1__feed__reels_media":',
        '"xdt_api__v1__feed__reels_media__connection":',
        '"xig_polaris_media":',
    )
    decoder = json.JSONDecoder()
    for marker in markers:
        cursor = 0
        while (offset := html.find(marker, cursor)) >= 0:
            start = html.find("{", offset + len(marker))
            if start < 0:
                break
            try:
                payload, _ = decoder.raw_decode(html[start:])
            except json.JSONDecodeError:
                cursor = start + 1
                continue
            found.extend(_walk_story_media(payload, seen))
            cursor = start + 1
    path_parts = urlparse(url).path.strip("/").split("/")
    story_id = path_parts[2] if len(path_parts) >= 3 and path_parts[0] == "stories" and path_parts[1] != "highlights" else ""
    if story_id and found:
        matching = [item for item in found if str(item.get("pk") or item.get("id") or "") == story_id]
        if matching:
            return matching
        return []
    return found


def _best_media_url(items: list[dict], max_height: int | None = None) -> str | None:
    candidates = [item for item in items if isinstance(item, dict) and item.get("url")]
    if not candidates:
        return None

    if max_height:
        within_height = []
        for item in candidates:
            try:
                height = int(item.get("height") or 0)
            except (TypeError, ValueError):
                height = 0
            if not height or height <= max_height:
                within_height.append(item)
        if within_height:
            candidates = within_height
    def resolution(item: dict) -> int:
        try:
            return int(item.get("width") or 0) * int(item.get("height") or 0)
        except (TypeError, ValueError):
            return 0

    return max(enumerate(candidates), key=lambda pair: (resolution(pair[1]), pair[0]))[1]["url"]


def _download_instagram_asset(ydl, url: str, destination: Path, max_bytes: int, cancel_event) -> None:
    if cancel_event.is_set():
        raise JobCancelled()
    request = Request(url, headers={"Referer": "https://www.instagram.com/"})
    with ydl.urlopen(request) as response, destination.open("wb") as output:
        total = 0
        while chunk := response.read(1024 * 1024):
            if cancel_event.is_set():
                raise JobCancelled()
            total += len(chunk)
            if total > max_bytes:
                raise RuntimeError("حجم یکی از فایل‌های اینستاگرام از سقف مجاز بیشتر است.")
            output.write(chunk)
    if total == 0:
        destination.unlink(missing_ok=True)
        raise RuntimeError("فایل رسانهٔ اینستاگرام خالی دریافت شد.")


def _instagram_file_extension(url: str, is_video: bool) -> str:
    if is_video:
        return "mp4"
    path = urlparse(url).path.lower()
    for extension in (".jpeg", ".jpg", ".png", ".webp", ".avif"):
        if path.endswith(extension):
            return extension.removeprefix(".")
    return "jpg"


def _download_instagram_media(url: str, directory: Path, settings, cancel_event, progress=None) -> tuple[Path, str]:
    if not is_instagram_media_url(url):
        raise RuntimeError("لینک باید مربوط به یک پست، ریلز، استوری یا هایلایت اینستاگرام باشد.")
    directory.mkdir(parents=True, exist_ok=True)
    options = {
        "format": f"bestvideo[height<={settings.video_max_height}]+bestaudio/best[height<={settings.video_max_height}]/bestvideo/best",
        "outtmpl": str(directory / "media-%(id)s.%(ext)s"),
        "noplaylist": False,
        "max_filesize": settings.max_file_bytes,
        "socket_timeout": 30,
        "retries": 2,
        "quiet": True,
        "no_warnings": True,
        "merge_output_format": "mp4",
        "http_headers": {"Referer": "https://www.instagram.com/"},
    }

    def hook(data):
        if cancel_event.is_set():
            raise JobCancelled()
        if progress and data.get("status") == "downloading":
            total = data.get("total_bytes") or data.get("total_bytes_estimate")
            if total:
                progress("دانلود رسانه‌های اینستاگرام", min(90, round(90 * data.get("downloaded_bytes", 0) / total)))

    options["progress_hooks"] = [hook]
    options.update(_instagram_cookie_options(settings, directory))
    maximum = settings.max_file_bytes
    paths: list[Path] = []
    with yt_dlp.YoutubeDL(options) as ydl:
        media_items: list[dict] = []
        story_items = []
        if "/stories/" in urlparse(url).path:
            try:
                story_items = _instagram_media_from_page(ydl, url, cancel_event)
            except JobCancelled:
                raise
            except Exception:
                # The yt-dlp extractor below is the fallback for changed page layouts.
                story_items = []

        if story_items:
            path_parts = urlparse(url).path.strip("/").split("/")
            requested_id = path_parts[2] if len(path_parts) >= 3 and path_parts[0] == "stories" and path_parts[1] != "highlights" else ""
            if requested_id:
                matching = [item for item in story_items if str(item.get("pk") or item.get("id") or "") == requested_id]
                if matching:
                    story_items = matching
            title = f"Instagram Story · {path_parts[1] if len(path_parts) > 1 else 'story'}"
            media_items = story_items
        else:
            try:
                info = ydl.extract_info(url, download=False)
            except Exception as extract_error:
                if cancel_event.is_set():
                    raise JobCancelled()
                try:
                    media_items = _instagram_media_from_page(ydl, url, cancel_event)
                except JobCancelled:
                    raise
                except Exception:
                    media_items = []
                if not media_items:
                    raise extract_error
                info = None
            if info is None:
                title = "Instagram media"
            else:
                title = str(info.get("title") or info.get("id") or "Instagram media")[:200]
                entries = info.get("entries")
                media_items = [entry for entry in entries if entry] if entries is not None else [info]
            if not info:
                if not media_items:
                    raise RuntimeError("محتوای اینستاگرام پیدا نشد یا در دسترس نیست.")

        if not media_items:
            raise RuntimeError("در این لینک رسانهٔ قابل‌دریافتی پیدا نشد.")

        last_error = None

        def add_paths(new_paths: list[Path]) -> None:
            paths.extend(new_paths)
            if sum(path.stat().st_size for path in set(paths) if path.is_file()) > maximum:
                raise RuntimeError("مجموع حجم مدیاهای این پست از سقف مجاز بیشتر است.")

        for index, item in enumerate(media_items, start=1):
            if cancel_event.is_set():
                raise JobCancelled()
            duration = float(item.get("duration") or item.get("video_duration") or 0)
            if duration > settings.video_max_minutes * 60:
                raise RuntimeError("مدت یکی از ویدیوهای این لینک از سقف مجاز بیشتر است.")
            before = set(directory.glob("media-*"))
            formats = item.get("formats") or []
            if formats:
                ydl.params["outtmpl"] = str(directory / f"media-{index:03d}.%(ext)s")
                try:
                    ydl.process_ie_result(item, download=True)
                except JobCancelled:
                    raise
                except Exception as exc:
                    last_error = exc
                    continue
                created = [path for path in directory.glob("media-*") if path.is_file() and path not in before]
                if not created:
                    last_error = RuntimeError("ویدیوی یکی از بخش‌های پست ساخته نشد.")
                add_paths(created)
                continue

            video_url = _best_media_url(item.get("video_versions") or [], settings.video_max_height)
            if video_url:
                destination = directory / f"media-{index:03d}.mp4"
                try:
                    _download_instagram_asset(ydl, video_url, destination, maximum, cancel_event)
                except JobCancelled:
                    raise
                except Exception as exc:
                    last_error = exc
                    continue
                add_paths([destination])
                continue

            thumbnails = item.get("thumbnails") or (item.get("image_versions2") or {}).get("candidates") or []
            image_url = _best_media_url(thumbnails)
            if image_url:
                extension = _instagram_file_extension(image_url, False)
                destination = directory / f"media-{index:03d}.{extension}"
                try:
                    _download_instagram_asset(ydl, image_url, destination, maximum, cancel_event)
                except JobCancelled:
                    raise
                except Exception as exc:
                    last_error = exc
                    continue
                add_paths([destination])
            else:
                last_error = RuntimeError("یکی از بخش‌های پست قالب رسانهٔ قابل‌دریافت نداشت.")

        paths = sorted(set(paths))
        if last_error:
            raise RuntimeError("دانلود همهٔ رسانه‌های این لینک کامل نشد؛ ممکن است بخشی خصوصی، منقضی یا موقتاً پشتیبانی‌نشده باشد.") from last_error
        if not paths:
            raise RuntimeError("در این لینک قالب رسانهٔ قابل‌دانلود پیدا نشد.")
        if sum(path.stat().st_size for path in paths) > maximum:
            raise RuntimeError("مجموع حجم مدیاهای این پست از سقف مجاز بیشتر است.")
        if len(paths) == 1:
            return paths[0], title
        archive = directory / "instagram-media.zip"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as bundle:
            for path in paths:
                bundle.write(path, arcname=path.name)
        if archive.stat().st_size > maximum:
            archive.unlink(missing_ok=True)
            raise RuntimeError("حجم ZIP پست از سقف مجاز بیشتر است.")
        return archive, title


def download_media(url: str, kind: str, directory: Path, settings, cancel_event, progress=None) -> tuple[Path, str]:
    instagram = is_instagram_url(url)
    if classify_link(url) not in {'social', 'youtube'} or kind not in {'video', 'audio', 'media'}:
        raise RuntimeError('لینک یا نوع فایل معتبر نیست.')
    if kind == "media":
        if not instagram:
            raise RuntimeError("دانلود همهٔ مدیا با یک لینک فقط برای Instagram فعال است.")
        return _download_instagram_media(url, directory, settings, cancel_event, progress)
    directory.mkdir(parents=True, exist_ok=True)
    youtube = classify_link(url) == 'youtube'
    cap = settings.video_max_height
    selector = 'bestaudio/best' if kind == 'audio' else f'bestvideo[height<={cap}]+bestaudio/best[height<={cap}]/best'

    def hook(data):
        if cancel_event.is_set():
            raise JobCancelled()
        if progress and data.get('status') == 'downloading':
            total = data.get('total_bytes') or data.get('total_bytes_estimate')
            if total:
                progress('دانلود فایل', min(90, round(90 * data.get('downloaded_bytes', 0) / total)))

    options = {'format': selector, 'outtmpl': str(directory / 'source.%(ext)s'),
               'noplaylist': True, 'max_filesize': settings.max_file_bytes,
               'socket_timeout': 30, 'retries': 2, 'quiet': True, 'no_warnings': True,
               'merge_output_format': 'mp4', 'progress_hooks': [hook],
               'allowed_extractors': [EXTRACTOR_PATTERN]}
    if youtube:
        options['extractor_args'] = {'youtubepot-bgutilhttp': {'base_url': [settings.ytdlp_pot_base_url]}}
        if settings.youtube_cookies_file:
            source = Path(settings.youtube_cookies_file)
            if not source.is_file():
                raise RuntimeError('فایل cookies یوتیوب در دسترس نیست.')
            copy = directory / 'cookies.txt'
            shutil.copyfile(source, copy)
            options['cookiefile'] = str(copy)
    elif classify_link(url) == 'social':
        host = (urlparse(url).hostname or '').lower()
        if host in {'instagram.com', 'www.instagram.com', 'm.instagram.com'}:
            options.update(_instagram_cookie_options(settings, directory))
    if kind == 'audio':
        options['postprocessors'] = [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}]
    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=False)
        if not info or info.get('_type') in {'playlist', 'multi_video'}:
            raise RuntimeError('این لینک شامل چند فایل است؛ لینک یک ویدیو یا آهنگ بفرست.')
        duration = float(info.get('duration') or 0)
        if not duration or duration > settings.video_max_minutes * 60:
            raise RuntimeError('مدت فایل در دسترس نیست یا از سقف مجاز بیشتر است.')
        if cancel_event.is_set():
            raise JobCancelled()
        info = ydl.extract_info(url, download=True)
    if cancel_event.is_set():
        raise JobCancelled()
    if kind == 'audio':
        result = directory / 'source.mp3'
    else:
        result = directory / 'source.mp4'
        if not result.exists():
            source = next((p for p in directory.glob('source.*') if p.suffix.lower() in {'.webm', '.mkv', '.mov'}), None)
            if not source:
                raise RuntimeError('ویدیویی در این لینک پیدا نشد.')
            _run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-i', str(source),
                  '-c:v', 'libx264', '-c:a', 'aac', '-movflags', '+faststart', str(result)])
    if not result.is_file() or result.stat().st_size == 0:
        raise RuntimeError('فایل دانلودشده در دسترس نیست.')
    if result.stat().st_size > settings.max_file_bytes:
        raise RuntimeError('حجم خروجی از سقف مجاز بیشتر است.')
    return result, str((info or {}).get('title') or 'فایل دانلودشده')[:200]
