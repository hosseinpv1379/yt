"""Single-item download-only flows for supported public media links."""
import re
import shutil
from pathlib import Path
from urllib.parse import urlparse

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


def download_media(url: str, kind: str, directory: Path, settings, cancel_event, progress=None) -> tuple[Path, str]:
    if classify_link(url) not in {'social', 'youtube'} or kind not in {'video', 'audio'}:
        raise RuntimeError('لینک یا نوع فایل معتبر نیست.')
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
        cookie_path = getattr(settings, 'instagram_cookies_file', '')
        if host in {'instagram.com', 'www.instagram.com', 'm.instagram.com'} and cookie_path:
            source = Path(cookie_path)
            if not source.is_file():
                raise RuntimeError('فایل cookies اینستاگرام در دسترس نیست.')
            copy = directory / 'instagram-cookies.txt'
            shutil.copyfile(source, copy)
            options['cookiefile'] = str(copy)
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
