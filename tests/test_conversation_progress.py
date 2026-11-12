import asyncio
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from telegram.error import BadRequest

from app.bot import BotState, Job, PendingQuality, _probe_order, _publish_progress, cancel, cancel_job_callback


def make_job(job_id="a" * 32):
    return Job(id=job_id, user_id=1, chat_id=1, url="https://youtu.be/example", message_id=7,
               directory=Path("/tmp"), selected_height=None, mode="dub", api_provider="openai",
               draft_id=1, can_use_draft=True)


class ConversationProgressTests(unittest.IsolatedAsyncioTestCase):
    async def test_live_draft_and_durable_progress_are_monotonic(self):
        job = make_job()
        bot = SimpleNamespace(send_message_draft=AsyncMock(), edit_message_text=AsyncMock())
        app = SimpleNamespace(bot=bot)
        await _publish_progress(app, job, "دانلود", 28)
        await _publish_progress(app, job, "تفکیک", 20)
        self.assertEqual(job.progress_percent, 28)
        self.assertIn("28%", bot.send_message_draft.call_args.kwargs["text"])
        self.assertEqual(bot.send_message_draft.await_count, 2)
        self.assertIsNotNone(bot.edit_message_text.call_args.kwargs["reply_markup"])

    async def test_draft_rejection_falls_back_to_edit(self):
        job = make_job()
        bot = SimpleNamespace(send_message_draft=AsyncMock(side_effect=BadRequest("unsupported")),
                              edit_message_text=AsyncMock())
        await _publish_progress(SimpleNamespace(bot=bot), job, "ترجمه", 60)
        self.assertFalse(job.can_use_draft)
        self.assertIn("60%", bot.edit_message_text.call_args.args[0])

    async def test_stale_and_delivery_cancel_buttons_do_not_cancel(self):
        job = make_job()
        state = BotState(SimpleNamespace(default_api_provider="openai"), SimpleNamespace())
        state.active[1] = job
        query = SimpleNamespace(data="job_cancel:" + "b" * 32, answer=AsyncMock(),
                                message=SimpleNamespace(reply_text=AsyncMock()))
        update = SimpleNamespace(callback_query=query, effective_user=SimpleNamespace(id=1))
        context = SimpleNamespace(application=SimpleNamespace(bot_data={"state": state}))
        await cancel_job_callback(update, context)
        self.assertFalse(job.cancel_event.is_set())
        job.delivery_started = True
        query.data = "job_cancel:" + job.id
        await cancel_job_callback(update, context)
        self.assertFalse(job.cancel_event.is_set())
        job.delivery_started = False
        await cancel_job_callback(update, context)
        self.assertTrue(job.cancel_event.is_set())

    async def test_cancel_does_not_discard_a_confirming_order(self):
        db = SimpleNamespace(upsert_user=AsyncMock())
        state = BotState(SimpleNamespace(default_api_provider="openai"), db)
        selection = PendingQuality(1, 1, "https://youtu.be/example", 7, True, "openai", confirming=True)
        state.pending_quality["token"] = selection
        state.pending_by_user[1] = "token"
        message = SimpleNamespace(reply_text=AsyncMock())
        update = SimpleNamespace(effective_user=SimpleNamespace(id=1), effective_message=message)
        await cancel(update, SimpleNamespace(application=SimpleNamespace(bot_data={"state": state})))
        self.assertIs(state.pending_quality["token"], selection)
        self.assertEqual(state.pending_by_user[1], "token")

    async def test_probe_does_not_restore_cancelled_order(self):
        state = BotState(SimpleNamespace(default_api_provider="openai", video_max_minutes=60), SimpleNamespace())
        selection = PendingQuality(1, 1, "https://youtu.be/example", 7, True, "openai", mode="subtitle")
        state.pending_quality["token"] = selection
        state.pending_by_user[1] = "token"
        query = SimpleNamespace(edit_message_text=AsyncMock())
        bot = SimpleNamespace(edit_message_text=AsyncMock())
        context = SimpleNamespace(application=SimpleNamespace(bot_data={"state": state}, bot=bot))
        started, resume = asyncio.Event(), asyncio.Event()

        async def probe(*args):
            started.set()
            await resume.wait()
            return [720], 60

        with patch("app.bot.asyncio.to_thread", side_effect=probe):
            task = asyncio.create_task(_probe_order(query, context, selection, "token"))
            await started.wait()
            state.pending_quality.pop("token")
            state.pending_by_user.pop(1)
            resume.set()
            await task
        bot.edit_message_text.assert_not_awaited()

