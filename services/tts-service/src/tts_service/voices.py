"""Which voice speaks which language.

The image ships one voice per language the WebUI has - German and English.
Both are Piper's "low" quality tier. Measured on a Raspberry Pi 4, a four-word
phrase costs it about 1.5 s of inference; the higher tiers are slower again for
a difference nobody notices in a four-word announcement, and the box would be
paying it on every card it has not said before.

The mapping is overridable through the environment so a box can be given a
different voice without a new image - the file only has to be in the voices
directory.
"""

from __future__ import annotations

import os
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)

#: Language -> the model file bundled for it, without the directory.
DEFAULT_VOICES: dict[str, str] = {
    "de": "de_DE-thorsten-low.onnx",
    "en": "en_US-lessac-low.onnx",
}

#: What a request that names no language, or an unknown one, is spoken in.
FALLBACK_LANGUAGE = "de"


def configured_voices() -> dict[str, str]:
    """The language -> model-file map, with the environment on top."""
    voices = dict(DEFAULT_VOICES)
    for lang in DEFAULT_VOICES:
        override = os.environ.get(f"TTS_VOICE_{lang.upper()}")
        if override:
            voices[lang] = override
    return voices


def normalize_language(lang: str | None) -> str:
    """``de-DE``, ``DE``, ``de`` -> ``de``; anything unknown -> the fallback.

    Deliberately forgiving: the language reaches this service from a settings
    field, and a box that says ``de-DE`` should be spoken to in German rather
    than told off.
    """
    if not lang:
        return FALLBACK_LANGUAGE
    base = lang.strip().lower().replace("_", "-").split("-")[0]
    return base if base in DEFAULT_VOICES else FALLBACK_LANGUAGE


def voice_path(lang: str, voices_dir: Path) -> Path | None:
    """The model file for *lang*, or None when this image has no voice for it.

    Missing is not an error worth raising here: the caller turns it into a
    "this box cannot speak that language" answer, and a box whose voice file
    failed to download should still be able to say the other one.
    """
    filename = configured_voices()[normalize_language(lang)]
    path = voices_dir / filename
    if not path.exists():
        logger.warning("voice_missing", language=lang, path=str(path))
        return None
    return path


def available_languages(voices_dir: Path) -> list[str]:
    """The languages this image can actually speak right now."""
    return [
        lang
        for lang in DEFAULT_VOICES
        if voice_path(lang, voices_dir) is not None
    ]
