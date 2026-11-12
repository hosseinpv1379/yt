import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from app.downloads import classify_link, download_media, resolve_spotify_track
from app.bot import BotState, PendingQuality, choose_download
from app.pipeline import cleanup_expired_downloads, publish_download


class LinkTests(unittest.TestCase):
    def test_allowlist_and_spotify_scope(self):
        self.assertEqual(classify_link('https://www.instagram.com/reel/abc/'), 'social')
        self.assertEqual(classify_link('https://vm.tiktok.com/example'), 'social')
        self.assertEqual(classify_link('https://open.spotify.com/track/0123456789abcdefghijkl'), 'spotify')
        self.assertEqual(classify_link('https://open.spotify.com/album/0123456789abcdefghijkl'), 'spotify_unsupported')
        for url in ('http://instagram.com/reel/a', 'https://instagram.com.evil.test/a',
                    'https://instagram.com@localhost/a', 'https://instagram.com:8080/a', 'https://127.0.0.1/'):
            self.assertIsNone(classify_link(url))

    def test_spotify_match_uses_fixed_host_and_video_id(self):
        response = Mock(); response.json.return_value = {'title': 'Song', 'author_name': 'Artist'}
        ydl = Mock(); ydl.__enter__ = Mock(return_value=ydl); ydl.__exit__ = Mock(return_value=False)
        ydl.extract_info.return_value = {'entries': [{'id': 'abcdefghijk', 'title': 'Song official'}]}
        settings = SimpleNamespace(ytdlp_pot_base_url='http://pot:4416')
        with patch('app.downloads.httpx.get', return_value=response), patch('app.downloads.yt_dlp.YoutubeDL', return_value=ydl):
            url, title = resolve_spotify_track('https://open.spotify.com/track/0123456789abcdefghijkl', settings)
        self.assertEqual(url, 'https://www.youtube.com/watch?v=abcdefghijk')
        self.assertEqual(title, 'Song official')

    def test_publication_and_cleanup_allow_mp3(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source = root / 'source.mp3'; source.write_bytes(b'audio')
            token = publish_download(source, root, 24, suffix='mp3')
            self.assertEqual((root / f'{token}.mp3').read_bytes(), b'audio')
            with self.assertRaises(ValueError):
                publish_download(source, root, 24, suffix='html')

    def test_download_audio_and_separate_cookies(self):
        settings = SimpleNamespace(video_max_height=720, video_max_minutes=60, max_file_bytes=1000000,
            youtube_cookies_file='/not/for/instagram', instagram_cookies_file='', ytdlp_pot_base_url='http://pot')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ydl = Mock(); ydl.__enter__ = Mock(return_value=ydl); ydl.__exit__ = Mock(return_value=False)
            def extract(url, download):
                if download: (root / 'source.mp3').write_bytes(b'audio')
                return {'duration': 60, 'title': 'test'}
            ydl.extract_info.side_effect = extract
            with patch('app.downloads.yt_dlp.YoutubeDL', return_value=ydl) as factory:
                result, title = download_media('https://www.instagram.com/reel/test', 'audio', root, settings, asyncio.Event())
            self.assertEqual(result.suffix, '.mp3')
            self.assertNotIn('cookiefile', factory.call_args.args[0])
            self.assertIn('allowed_extractors', factory.call_args.args[0])


class DownloadOrderTests(unittest.IsolatedAsyncioTestCase):
    async def test_download_queues_once_without_wallet_charge(self):
        state = BotState(SimpleNamespace(default_api_provider='openai', work_dir='/tmp'), SimpleNamespace(create_download_task=AsyncMock()))
        selection = PendingQuality(1, 1, 'https://www.instagram.com/reel/a', 22, True, 'openai', download_source='social')
        state.pending_quality['abc'] = selection; state.pending_by_user[1] = 'abc'
        query = SimpleNamespace(data='dl:abc:video', answer=AsyncMock(), edit_message_text=AsyncMock())
        context = SimpleNamespace(application=SimpleNamespace(bot_data={'state': state}))
        update = SimpleNamespace(callback_query=query, effective_user=SimpleNamespace(id=1))
        await choose_download(update, context)
        await choose_download(update, context)
        self.assertEqual(state.queue.qsize(), 1)
        self.assertEqual(state.active[1].kind, 'video')

class DownloadDeliveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_audio_delivery_and_queue_cleanup(self):
        from app.bot import DownloadJob, _run_download_job
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = BotState(SimpleNamespace(default_api_provider='openai'), SimpleNamespace(update_download_task=AsyncMock()))
            job = DownloadJob('job', 1, 2, 'https://www.instagram.com/reel/a', 3, root / 'job', 'audio', 'social')
            state.active[1] = job
            await state.queue.put(job)
            await state.queue.get()
            path = job.directory / 'source.mp3'
            def fake_download(*args):
                job.directory.mkdir(); path.write_bytes(b'audio')
                return path, 'sample'
            bot = SimpleNamespace(send_audio=AsyncMock(), edit_message_text=AsyncMock())
            app = SimpleNamespace(bot=bot)
            with patch('app.bot.download_media', side_effect=fake_download):
                await _run_download_job(app, state, job)
            bot.send_audio.assert_awaited_once()
            self.assertNotIn(1, state.active)
            self.assertFalse(job.directory.exists())
            self.assertEqual(state.queue._unfinished_tasks, 0)
