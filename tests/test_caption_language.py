"""Exercise the language selection through the paid job queue without network services."""
import asyncio
import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch


class CaptionLanguageFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_language_choice_reaches_queued_job(self):
        telegram = types.ModuleType("telegram")
        telegram.InlineKeyboardMarkup = lambda rows: types.SimpleNamespace(inline_keyboard=rows)
        ext = types.ModuleType("telegram.ext")
        ext.ApplicationHandlerStop = type("ApplicationHandlerStop", (Exception,), {})
        ext.CallbackQueryHandler = ext.MessageHandler = lambda *args, **kwargs: None
        ext.filters = types.SimpleNamespace()
        app = types.ModuleType("app")
        app.__path__ = []
        app.ui = types.SimpleNamespace(
            button=lambda text, action, **kwargs: types.SimpleNamespace(callback_data=action),
            job_keyboard=lambda job_id: None,
        )
        pipeline = types.ModuleType("app.pipeline")
        pipeline.publish_download = lambda *args, **kwargs: None
        name = "features.video_captions._handlers_language_test"
        path = Path(__file__).resolve().parents[1] / "features/video_captions/handlers.py"
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"telegram": telegram, "telegram.ext": ext, "app": app,
                                      "app.pipeline": pipeline, name: module}):
            spec.loader.exec_module(module)
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / "model.bin").touch()
                (root / "Vazirmatn-Bold.ttf").touch()
                (root / "Montserrat-ExtraBold.ttf").touch()
                for choice, expected in (("fa", "fa"), ("en", "en"), ("auto", None)):
                    with self.subTest(choice=choice):
                        database = types.SimpleNamespace(get_setting=AsyncMock(return_value="100"),
                            get_wallet_balance=AsyncMock(return_value=1000), available_minutes=AsyncMock(return_value=[]),
                            create_wallet_job=AsyncMock(return_value=900))
                        state = types.SimpleNamespace(active={}, pending_by_user={}, queue=asyncio.Queue(),
                            settings=types.SimpleNamespace(default_subtitle_price_toman_per_minute=100,
                                caption_model_path=str(root), caption_fonts_dir=str(root)),
                            database=database, api_provider="openai")
                        item = {"token": "abcd", "duration": 5, "file_id": "video"}
                        application = types.SimpleNamespace(bot_data={"state": state, "video_captions_pending": {42: item}})
                        query = types.SimpleNamespace(data="vclip:mode:abcd:both", answer=AsyncMock(),
                            edit_message_text=AsyncMock(), message=types.SimpleNamespace(
                                chat=types.SimpleNamespace(type="private"), chat_id=42, message_id=7))
                        update = types.SimpleNamespace(callback_query=query, effective_user=types.SimpleNamespace(id=42))
                        context = types.SimpleNamespace(application=application)
                        await module.callback(update, context)
                        self.assertTrue(any(button.callback_data.endswith(":fa") for row in
                            query.edit_message_text.call_args.kwargs["reply_markup"].inline_keyboard for button in row))
                        query.data = f"vclip:lang:abcd:{choice}"
                        await module.callback(update, context)
                        query.data = "vclip:color:abcd:yellow"
                        await module.callback(update, context)
                        query.data = "vclip:font:abcd:vazirmatn"
                        await module.callback(update, context)
                        query.data = "vclip:size:abcd:medium"
                        await module.callback(update, context)
                        query.data = "vclip:confirm:abcd"
                        await module.callback(update, context)
                        job = state.queue.get_nowait()
                        self.assertEqual(job.language, expected)
                        self.assertEqual(job.edit_mode, "both")
                        database.create_wallet_job.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
