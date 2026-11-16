"""Curated models compatible with the pipeline and their indicative prices."""
from dataclasses import dataclass


@dataclass(frozen=True)
class ModelOption:
    code: str
    stage: str
    provider: str
    model: str
    price: str


OPTIONS = (
    ModelOption('s1', 'stt', 'openai', 'whisper-1', '$0.006 / دقیقه · توقف 2027-02-26'),
    ModelOption('s2', 'stt', 'openrouter', 'openai/whisper-large-v3-turbo', '$0.04 / ساعت صوت'),
    ModelOption('s3', 'stt', 'openrouter', 'openai/whisper-large-v3', '$0.0288 / ساعت صوت'),
    ModelOption('t1', 'translation', 'openai', 'gpt-6-luna', '$0.10 ورودی / $0.50 خروجی'),
    ModelOption('t2', 'translation', 'openai', 'gpt-4o-mini', '$0.15 ورودی / $0.60 خروجی'),
    ModelOption('t3', 'translation', 'openrouter', 'openai/gpt-6-luna', '$0.10 ورودی / $0.50 خروجی'),
    ModelOption('t4', 'translation', 'openrouter', 'openai/gpt-4o-mini', '$0.15 ورودی / $0.60 خروجی'),
    ModelOption('d1', 'tts', 'openai', 'gpt-realtime-2.1-mini', 'هزینهٔ دقیقه‌ای نامشخص · متن $0.60 / صوت خروجی $20 به‌ازای هر میلیون توکن'),
    ModelOption('d2', 'tts', 'openrouter', 'google/gemini-3.8-flash-lite-tts', 'حدود $0.009 / دقیقه صدای خروجی + هزینهٔ متن'),
    ModelOption('d3', 'tts', 'openrouter', 'google/gemini-3.8-flash-tts', 'حدود $0.0135 / دقیقه صدای خروجی + هزینهٔ متن'),
)
BY_CODE = {option.code: option for option in OPTIONS}
STAGE_LABELS = {'stt': 'رونویسی', 'translation': 'ترجمه و بازنویسی', 'tts': 'تولید صدای دوبله'}
VOICES = {
    'openai': ('marin', 'cedar', 'alloy', 'ash', 'ballad', 'coral', 'echo', 'sage', 'shimmer', 'verse'),
    'openrouter': ('Kore', 'Puck', 'Charon', 'Aoede', 'Zephyr', 'Leda', 'Orus', 'Fenrir'),
}


@dataclass(frozen=True)
class StageSelection:
    provider: str
    model: str


@dataclass(frozen=True)
class ModelSelection:
    stt: StageSelection
    translation: StageSelection
    tts: StageSelection
    voice: str


def defaults(settings, provider: str) -> ModelSelection:
    if provider == 'openrouter':
        return ModelSelection(StageSelection(provider, settings.openrouter_transcription_model),
                              StageSelection(provider, settings.openrouter_model),
                              StageSelection(provider, settings.openrouter_tts_model), settings.openrouter_tts_voice)
    return ModelSelection(StageSelection(provider, settings.whisper_model),
                          StageSelection(provider, settings.translation_model),
                          StageSelection(provider, settings.tts_model), settings.tts_voice)


async def load_selection(database, settings, fallback_provider: str) -> ModelSelection:
    base = defaults(settings, fallback_provider)
    selected = {}
    for stage in STAGE_LABELS:
        legacy = await database.get_setting(f'model_choice_{stage}', '')
        code = await database.get_setting(f'model_choice_{fallback_provider}_{stage}', legacy)
        option = BY_CODE.get(code)
        selected[stage] = StageSelection(option.provider, option.model) if option and option.stage == stage and option.provider == fallback_provider else getattr(base, stage)
    voice_provider = selected['tts'].provider
    default_voice = settings.openrouter_tts_voice if voice_provider == 'openrouter' else settings.tts_voice
    voice = await database.get_setting(f'model_voice_{voice_provider}', default_voice)
    return ModelSelection(selected['stt'], selected['translation'], selected['tts'], voice)

# Illustrative per-minute scenario: 300 uncached translation input tokens,
# 150 translation output tokens, and for dubbing 60 s of generated Gemini
# audio plus 300 text input tokens. This is not measured video usage.
TRANSLATION_INPUT_TOKENS_PER_MINUTE = 300
TRANSLATION_OUTPUT_TOKENS_PER_MINUTE = 150
TTS_INPUT_TOKENS_PER_MINUTE = 300
ESTIMATE_CENTS = {
    's1': 0.6,                # $0.006 per source minute
    's2': (0.04 / 60) * 100, # $0.04 per source hour
    's3': (0.0288 / 60) * 100,
    't1': (300 * 0.10 + 150 * 0.50) / 1_000_000 * 100,
    't2': (300 * 0.15 + 150 * 0.60) / 1_000_000 * 100,
    't3': (300 * 0.10 + 150 * 0.50) / 1_000_000 * 100,
    't4': (300 * 0.15 + 150 * 0.60) / 1_000_000 * 100,
    'd2': (1500 * 6.00 + 300 * 0.50) / 1_000_000 * 100,
    'd3': (1500 * 9.00 + 300 * 0.50) / 1_000_000 * 100,
}


def estimate_cents(stage: str, selection: StageSelection) -> float | None:
    option = next((item for item in OPTIONS if item.stage == stage
                   and item.provider == selection.provider and item.model == selection.model), None)
    return ESTIMATE_CENTS.get(option.code) if option else None


def format_dollars(amount_cents: float | None) -> str:
    return 'نامشخص' if amount_cents is None else f'حدود ${amount_cents / 100:.7f} / دقیقه'


def sum_estimates(*amounts: float | None) -> float | None:
    return sum(amounts) if all(amount is not None for amount in amounts) else None
