import base64
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from app import image_generation as images
from app.bot import BotState, ImageJob, _receive_image_reference, _run_image_job, image_callback
from app.model_catalog import StageSelection

PNG = b"\x89PNG\r\n\x1a\n" + b"sample"


class ImageApiTests(unittest.TestCase):
    def test_openrouter_edit_sends_reference_and_records_cost(self):
        response = Mock()
        response.json.return_value = {"data": [{"b64_json": base64.b64encode(PNG).decode()}], "usage": {"cost": 0.04}}
        settings = SimpleNamespace(openrouter_api_key="key")
        with patch("app.image_generation.httpx.post", return_value=response) as post:
            data, media_type, cost = images.generate_image("edit", "change sky", "3:2", settings,
                images.BY_CODE["i4"], PNG, "image/png")
        self.assertEqual((data, media_type, cost), (PNG, "image/png", 0.04))
        body = post.call_args.kwargs["json"]
        self.assertTrue(body["input_references"][0]["image_url"]["url"].startswith("data:image/png;base64,"))
        self.assertEqual(body["aspect_ratio"], "3:2")

    def test_openai_edit_uses_edit_endpoint(self):
        client = Mock()
        client.images.edit.return_value.data = [SimpleNamespace(b64_json=base64.b64encode(PNG).decode())]
        with patch("app.image_generation.OpenAI", return_value=client):
            images.generate_image("brief", "prompt", "1:1", SimpleNamespace(openai_api_key="key"),
                                  images.BY_CODE["i1"], PNG, "image/png")
        client.images.edit.assert_called_once()
        client.images.generate.assert_not_called()
        self.assertEqual(client.images.edit.call_args.kwargs["image"][1], PNG)

    def test_optimizer_receives_reference_and_preserves_original(self):
        client = Mock()
        client.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="keep subject", refusal=None), finish_reason="stop")],
            usage=None)
        with patch("app.image_generation.OpenAI", return_value=client):
            result, _ = images.optimize_prompt("آسمان آبی", SimpleNamespace(openai_api_key="key", openrouter_api_key=""),
                                               StageSelection("openai", "gpt-4o-mini"), PNG, "image/png")
        self.assertEqual(result, "keep subject")
        content = client.chat.completions.create.call_args.kwargs["messages"][1]["content"]
        self.assertEqual(content[0]["text"], "آسمان آبی")
        self.assertTrue(content[1]["image_url"]["url"].startswith("data:image/png;base64,"))


class ImageFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_failed_generation_refunds(self):
        db = SimpleNamespace(set_image_prompt=AsyncMock(return_value=True), finish_image_order=AsyncMock(),
                             refund_image_order=AsyncMock(return_value=True))
        state = BotState(SimpleNamespace(default_api_provider="openai"), db)
        job = ImageJob("a" * 32, 1, 1, 7, "prompt", "1:1", images.BY_CODE["i1"], StageSelection("openai", "gpt-4o-mini"))
        state.active[1] = job
        await state.queue.put(job)
        app = SimpleNamespace(bot=SimpleNamespace(edit_message_text=AsyncMock()))
        with patch("app.bot.image_generation.optimize_prompt", return_value=("enhanced", 0.001)), \
             patch("app.bot.image_generation.generate_image", side_effect=RuntimeError("provider")):
            await _run_image_job(app, state, job)
        db.finish_image_order.assert_not_awaited()
        db.refund_image_order.assert_awaited_once_with(job.id)

    async def test_delivery_failure_keeps_completed_image_without_refund(self):
        db = SimpleNamespace(set_image_prompt=AsyncMock(return_value=True), finish_image_order=AsyncMock(return_value=True),
                             refund_image_order=AsyncMock())
        state = BotState(SimpleNamespace(default_api_provider="openai"), db)
        job = ImageJob("a" * 32, 1, 1, 7, "prompt", "1:1", images.BY_CODE["i1"], StageSelection("openai", "gpt-4o-mini"))
        state.active[1] = job
        await state.queue.put(job)
        app = SimpleNamespace(bot=SimpleNamespace(edit_message_text=AsyncMock(), send_document=AsyncMock(side_effect=RuntimeError("network"))))
        with patch("app.bot.image_generation.optimize_prompt", return_value=("enhanced", 0.001)), \
             patch("app.bot.image_generation.generate_image", return_value=(PNG, "image/png", None)):
            await _run_image_job(app, state, job)
        db.finish_image_order.assert_awaited_once()
        db.refund_image_order.assert_not_awaited()
        self.assertNotIn(1, state.active)

    async def test_aspect_selection_is_parsed_correctly(self):
        state = BotState(SimpleNamespace(default_api_provider="openai"), SimpleNamespace())
        quote = {"token": "abc", "prompt": "sun", "price": 1000, "aspect": "1:1", "reference": None}
        state.image_quotes["1"] = quote
        query = SimpleNamespace(data="image:aspect:abc:2:3", answer=AsyncMock(), edit_message_text=AsyncMock(),
                                message=SimpleNamespace(chat=SimpleNamespace(type="private")))
        update = SimpleNamespace(callback_query=query, effective_user=SimpleNamespace(id=1))
        await image_callback(update, SimpleNamespace(application=SimpleNamespace(bot_data={"state": state})))
        self.assertEqual(quote["aspect"], "2:3")

    async def test_photo_caption_creates_edit_quote_at_edit_price(self):
        db = SimpleNamespace(get_setting=AsyncMock(side_effect=lambda name, default: "9000" if name == "image_edit_price" else default))
        settings = SimpleNamespace(default_api_provider="openai", whisper_model="whisper-1",
            translation_model="gpt-4o-mini", tts_model="voice", tts_voice="marin")
        state = BotState(settings, db)
        state.awaiting_image_prompt.add(1)
        file = SimpleNamespace(download_as_bytearray=AsyncMock(return_value=bytearray(PNG)))
        bot = SimpleNamespace(get_file=AsyncMock(return_value=file))
        photo = SimpleNamespace(file_id="photo", file_size=len(PNG))
        message = SimpleNamespace(photo=[photo], document=None, caption="آسمان را آبی کن", reply_text=AsyncMock())
        update = SimpleNamespace(effective_user=SimpleNamespace(id=1), effective_message=message)
        context = SimpleNamespace(application=SimpleNamespace(bot_data={"state": state}, bot=bot))
        await _receive_image_reference(update, context)
        quote = state.image_quotes["1"]
        self.assertEqual(quote["prompt"], "آسمان را آبی کن")
        self.assertEqual(quote["reference"], (PNG, "image/png"))
        self.assertEqual(quote["price"], 9000)

