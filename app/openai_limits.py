"""Read-only OpenAI project limits and recent request usage via the Admin API."""

from dataclasses import dataclass
import time

import httpx


OPENAI_API_BASE = "https://api.openai.com/v1"
USAGE_ENDPOINTS = {
    "completions": "/organization/usage/completions",
    "transcriptions": "/organization/usage/audio_transcriptions",
    "speeches": "/organization/usage/audio_speeches",
}


class OpenAILimitsUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class ModelLimit:
    model: str
    requests_last_24h: int | None
    max_requests_per_day: int | None
    max_requests_per_minute: int | None
    max_tokens_per_minute: int | None

    @property
    def remaining_today(self) -> int | None:
        if self.requests_last_24h is None or self.max_requests_per_day is None:
            return None
        return max(0, self.max_requests_per_day - self.requests_last_24h)


def get_openai_limits(settings) -> list[ModelLimit]:
    """Fetch project rate limits and last-24h usage for the bot's API models."""
    if not settings.openai_admin_key or not settings.openai_project_id:
        raise OpenAILimitsUnavailable(
            "OPENAI_ADMIN_KEY and OPENAI_PROJECT_ID are required for a live limit check"
        )

    now = int(time.time())
    params = [
        ("start_time", str(now - 24 * 60 * 60)),
        ("end_time", str(now)),
        ("bucket_width", "1h"),
        ("limit", "30"),
        ("group_by[]", "model"),
        ("project_ids[]", settings.openai_project_id),
    ]
    headers = {"Authorization": f"Bearer {settings.openai_admin_key}"}
    timeout = httpx.Timeout(15.0, connect=5.0)

    try:
        with httpx.Client(headers=headers, timeout=timeout) as client:
            rate_response = client.get(
                f"{OPENAI_API_BASE}/organization/projects/"
                f"{settings.openai_project_id}/rate_limits",
                params={"limit": 100},
            )
            _raise_for_admin_response(rate_response)
            rate_data = rate_response.json().get("data", [])
            limits_by_model = {
                item.get("model"): item for item in rate_data if item.get("model")
            }

            usage_by_model: dict[str, int] = {}
            usage_paths = {
                settings.translation_model: (USAGE_ENDPOINTS["completions"],),
                settings.whisper_model: (USAGE_ENDPOINTS["transcriptions"],),
                # Realtime speech can be reported with completions usage,
                # while the standalone speech endpoint uses audio_speeches.
                settings.tts_model: (
                    USAGE_ENDPOINTS["completions"],
                    USAGE_ENDPOINTS["speeches"],
                ),
            }
            for model, paths in usage_paths.items():
                counts = []
                for path in paths:
                    response = client.get(f"{OPENAI_API_BASE}{path}", params=params)
                    _raise_for_admin_response(response)
                    buckets = response.json().get("data", [])
                    model_requests = 0
                    found_model = False
                    for bucket in buckets:
                        for result in bucket.get("results", []):
                            if result.get("model") == model:
                                model_requests += int(result.get("num_model_requests", 0))
                                found_model = True
                    if found_model:
                        counts.append(model_requests)
                if counts:
                    usage_by_model[model] = max(counts)
    except OpenAILimitsUnavailable:
        raise
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        raise OpenAILimitsUnavailable(
            "OpenAI Admin API could not return rate-limit usage"
        ) from exc

    models = dict.fromkeys((settings.translation_model, settings.whisper_model, settings.tts_model))
    return [
        ModelLimit(
            model=model,
            requests_last_24h=usage_by_model.get(model),
            max_requests_per_day=_optional_int(limits_by_model.get(model, {}).get("max_requests_per_1_day")),
            max_requests_per_minute=_optional_int(limits_by_model.get(model, {}).get("max_requests_per_1_minute")),
            max_tokens_per_minute=_optional_int(limits_by_model.get(model, {}).get("max_tokens_per_1_minute")),
        )
        for model in models
    ]


def _optional_int(value) -> int | None:
    return int(value) if value is not None else None


def _raise_for_admin_response(response: httpx.Response) -> None:
    if response.is_success:
        return
    if response.status_code in {401, 403}:
        raise OpenAILimitsUnavailable(
            "Admin API key or project permissions are invalid"
        )
    raise OpenAILimitsUnavailable(
        f"OpenAI Admin API returned HTTP {response.status_code}"
    )
