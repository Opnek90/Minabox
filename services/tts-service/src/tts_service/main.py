"""FastAPI application entry point for the TTS Service.

The service does one thing: hand back the path to a WAV file that says what it
was given. It decides nothing - not whether a box speaks at all, not which
sentence belongs to which event, not the language. All of that is the backend's
(``core/announcements.py``), and it travels with the request.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from tts_service import cache, voices
from tts_service.config import load_config
from tts_service.models import (
    SpeakRequest,
    SpeakResponse,
    VoiceItem,
    VoicesResponse,
)
from tts_service.synthesizer import SynthesisError, VoicePool

config = load_config()

SERVICE_PORT = 8008


def setup_structlog() -> None:
    """Logging einrichten - bewusst als Funktion, nicht beim Import.

    DEBUG -> lesbare Konsolenausgabe; INFO und hoeher -> strukturiertes JSON,
    das Format, das die Log-Auswertung der uebrigen Dienste erwartet. Spiegelt
    shared_lib.logging.setup_structlog(); hier ausgeschrieben statt importiert,
    damit dieser Dienst ohne shared-lib auskommt - genau wie der
    media-downloader-service.

    Warum keine Modulebene: structlog.configure() wirkt global auf den ganzen
    Prozess und wuerde im gemeinsamen pytest-Lauf die Logger der anderen
    Dienste mitkonfigurieren.
    """
    log_level = getattr(logging, config.log_level.upper(), logging.INFO)
    renderer = (
        structlog.dev.ConsoleRenderer()
        if config.log_level.upper() == "DEBUG"
        else structlog.processors.JSONRenderer()
    )
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.stdlib.add_log_level,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
    )


logger = structlog.get_logger("tts_service")

_start_time = time.monotonic()

# One synthesis at a time. Piper saturates a Raspberry Pi core, and a card
# scan that arrives while the previous phrase is still being made would
# otherwise make both of them slower than either alone. The queue is never
# long: the phrases a box says repeat, so almost every request is a cache hit
# and never reaches this.
_synthesis_lock = asyncio.Lock()

# The running Piper processes. Long-lived on purpose - starting one per phrase
# means loading a 63 MB model per phrase, which on a Raspberry Pi is more time
# than the synthesis itself (see synthesizer.py).
voices_pool = VoicePool(
    binary=config.piper_binary,
    espeak_data=config.espeak_data_dir,
    timeout_sec=config.synthesis_timeout_sec,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    setup_structlog()
    config.cache_dir.mkdir(parents=True, exist_ok=True)
    available = voices.available_languages(config.voices_dir)
    logger.info(
        "service_startup",
        cache_dir=str(config.cache_dir),
        languages=available,
        piper=str(config.piper_binary),
    )
    if not available:
        # Not fatal on purpose: the container stays up and says so on /health,
        # which is a far better diagnosis than a restart loop.
        logger.error("no_voice_available", voices_dir=str(config.voices_dir))
    yield
    # No voice is started here and none is started at boot: a box has one
    # announcement language, so the other model normally never has to be read
    # into memory at all.
    await voices_pool.close()
    logger.info("service_shutdown")


app = FastAPI(
    title="TTS Service",
    description=(
        "Minabox microservice for spoken announcements. Synthesises short "
        "phrases locally with Piper and caches them on disk; it never reaches "
        "the network and never sees what is being played."
    ),
    version=os.environ.get("APP_VERSION", "0.0.0-dev"),
    lifespan=lifespan,
)


@app.get("/health")
async def health_check() -> JSONResponse:
    available = voices.available_languages(config.voices_dir)
    return JSONResponse(
        {
            # A box with no voice file can do nothing useful, but it is not
            # broken in a way a restart fixes - so "degraded", not "unhealthy".
            "status": "healthy" if available else "degraded",
            "service": "tts-service",
            # This service does not depend on shared-lib; the Dockerfile sets
            # this variable from its build arg.
            "version": os.environ.get("APP_VERSION", "0.0.0-dev"),
            "uptime_seconds": round(time.monotonic() - _start_time, 1),
            "languages": available,
            "piper_available": config.piper_binary.exists(),
        }
    )


@app.get("/voices", response_model=VoicesResponse)
async def get_voices() -> VoicesResponse:
    """The languages this box can speak, and the voice used for each."""
    configured = voices.configured_voices()
    return VoicesResponse(
        voices=[
            VoiceItem(language=lang, voice=configured[lang])
            for lang in voices.available_languages(config.voices_dir)
        ]
    )


@app.post("/speak", response_model=SpeakResponse)
async def speak(request: SpeakRequest) -> SpeakResponse:
    """Return the path to a clip that says *text*, making it if necessary."""
    text = request.text.strip()
    if not text:
        raise HTTPException(status_code=422, detail="text must not be empty")
    if len(text) > config.max_text_length:
        # An announcement is a sentence, not a chapter. The cap is here and not
        # only in the backend because this API has no authentication.
        raise HTTPException(
            status_code=422,
            detail=f"text is longer than {config.max_text_length} characters",
        )

    language = voices.normalize_language(request.language)
    model = voices.voice_path(language, config.voices_dir)
    if model is None:
        raise HTTPException(
            status_code=503, detail=f"No voice installed for '{language}'"
        )

    voice = model.name
    path = cache.clip_path(config.cache_dir, voice, text)

    if path.exists() and path.stat().st_size > 0:
        cache.touch(path)
        logger.debug("clip_cache_hit", language=language, path=str(path))
        return SpeakResponse(
            path=str(path),
            language=language,
            voice=voice,
            cached=True,
            bytes=path.stat().st_size,
        )

    async with _synthesis_lock:
        # Checked again under the lock: two scans of the same card in quick
        # succession would otherwise both synthesise the same phrase.
        if not (path.exists() and path.stat().st_size > 0):
            try:
                await voices_pool.synthesize(text, model=model, output=path)
            except SynthesisError as exc:
                logger.warning(
                    "synthesis_failed", language=language, error=str(exc)
                )
                raise HTTPException(status_code=503, detail=str(exc)) from exc

    await asyncio.to_thread(
        cache.prune,
        config.cache_dir,
        max_files=config.cache_max_files,
        max_bytes=config.cache_max_bytes,
    )

    logger.info("clip_created", language=language, voice=voice)
    return SpeakResponse(
        path=str(path),
        language=language,
        voice=voice,
        cached=False,
        bytes=path.stat().st_size,
    )


def run() -> None:
    # log_config=None: without it uvicorn installs its own plain-text formatter
    # and every health check prints a line in a different format from our
    # structlog JSON - the same pattern the media-downloader uses.
    uvicorn.run(app, host="0.0.0.0", port=SERVICE_PORT, log_config=None)


if __name__ == "__main__":
    run()
