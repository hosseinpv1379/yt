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
    ModelOption('d1', 'tts', 'openai', 'gpt-realtime-2.1-mini', '$0.60 متن ورودی / $20 صوت خروجی'),
    ModelOption('d2', 'tts', 'openrouter', 'google/gemini-3.8-flash-lite-tts', '$0.50 متن ورودی / $6 صوت خروجی'),
    ModelOption('d3', 'tts', 'openrouter', 'google/gemini-3.8-flash-tts', '$0.50 متن ورودی / $9 صوت خروجی'),
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
        code = await database.get_setting(f'model_choice_{stage}', '')
        option = BY_CODE.get(code)
        selected[stage] = StageSelection(option.provider, option.model) if option and option.stage == stage else getattr(base, stage)
    voice_provider = selected['tts'].provider
    default_voice = settings.openrouter_tts_voice if voice_provider == 'openrouter' else settings.tts_voice
    voice = await database.get_setting(f'model_voice_{voice_provider}', default_voice)
    return ModelSelection(selected['stt'], selected['translation'], selected['tts'], voice)
