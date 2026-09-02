"""What the box says out loud, and when.

A four-year-old cannot read the OLED and does not know the LED blink codes. An
unassigned card, an exhausted daily limit and a reader that is not answering
all look the same from the outside: nothing happens. This module is the one
place that decides a sentence is worth saying, turns it into text in the box's
language, has the TTS service make a clip of it and tells the audio service to
play it.

Three deliberate boundaries:

* **The phrases are not in this file.** They live in
  ``resources/announcements.json``, next to the component descriptions and for
  the same reason: a wording is content, it is translated, and correcting one
  should not need a Python change. It is also the only way the German phrases
  can carry real umlauts - a phrase spelled "Hoerzeit" is spoken "Ho-er-zeit".
* **Nothing here synthesises anything.** The TTS service owns Piper and the
  clip cache; this module only asks it for a path.
* **Every failure is quiet.** A box whose voice component is switched off, is
  starting up, or has no voice file must behave exactly like a box that was
  never asked to speak. An announcement is a courtesy - it never blocks a card
  scan and never turns into an error the user has to acknowledge.
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx
import structlog

from backend_service.core import capabilities
from backend_service.core.general_settings import read_general_settings

logger = structlog.get_logger(__name__)

PHRASES_PATH = (
    Path(__file__).resolve().parent.parent / "resources" / "announcements.json"
)

TTS_SERVICE_URL = os.environ.get("TTS_SERVICE_URL", "http://tts:8008")

#: The feature key the voice component carries in ``capabilities.py``.
FEATURE = "voice"

LANGUAGES = ("de", "en")
DEFAULT_LANGUAGE = "de"

#: Measured on a Raspberry Pi 4: 1.5 to 2.3 s the first time a phrase is said,
#: about 7 s for the very first one after the container started (it pays for
#: loading the voice model), and around 70 ms once it is cached - which is
#: every announcement a box has already made. The timeout is therefore a guard
#: against a wedged container, not a budget, and nothing that matters waits on
#: it: the calls inside a card scan or a message handler go through
#: `announce_soon`.
TTS_TIMEOUT_SEC = 10.0

#: Which switch each phrase hangs off. Several phrases share one on purpose -
#: a parent decides "tell them about cards the box does not know", not one
#: sentence at a time.
PHRASE_SWITCH: dict[str, str] = {
    "card": "card_name",
    "card_unknown": "unknown_card",
    "card_empty": "unknown_card",
    "card_blocked": "unknown_card",
    "limit_warning": "usage_limit",
    "limit_reached": "usage_limit",
    "usage_denied": "usage_limit",
    "muted": "mute",
}

DEFAULTS: dict[str, Any] = {
    # Off until somebody switches it on: a box that starts talking after an
    # update would be a surprise in a child's bedroom.
    "announcements_enabled": False,
    "announce_card_name": True,
    "announce_unknown_card": True,
    "announce_usage_limit": True,
    "announce_mute": True,
    "announce_language": DEFAULT_LANGUAGE,
    "announce_volume_percent": 90,
    # The music sits at 30 % of its level while a phrase runs. Low enough to
    # be spoken over, high enough that the music has not "stopped".
    "announce_duck_percent": 30,
    "announce_limit_warning_minutes": 10,
}


@dataclass(frozen=True)
class AnnouncementSettings:
    """What the box may say, how loudly, and in which language."""

    enabled: bool
    card_name: bool
    unknown_card: bool
    usage_limit: bool
    mute: bool
    language: str
    volume_percent: int
    duck_percent: int
    limit_warning_minutes: int

    def allows(self, key: str) -> bool:
        """Whether *key* is switched on right now.

        A phrase nobody mapped is never spoken - the master switch is not a
        blanket permission for a key that was added without a switch.
        """
        if not self.enabled:
            return False
        switch = PHRASE_SWITCH.get(key)
        return bool(switch) and bool(getattr(self, switch))


def clamp_language(value: Any) -> str:
    """``de-DE``, ``EN``, nonsense -> one of the languages that exist."""
    text = str(value or "").strip().lower().replace("_", "-").split("-")[0]
    return text if text in LANGUAGES else DEFAULT_LANGUAGE


def clamp_percent(value: Any, default: int) -> int:
    try:
        return max(0, min(100, int(value)))
    except (TypeError, ValueError):
        return default


def clamp_warning_minutes(value: Any) -> int:
    """Minutes of warning before the listening time runs out. 0 = no warning."""
    try:
        return max(0, min(60, int(value)))
    except (TypeError, ValueError):
        return int(DEFAULTS["announce_limit_warning_minutes"])


def read_settings() -> AnnouncementSettings:
    """The current announcement settings, defaults applied."""
    data = read_general_settings()

    def flag(key: str) -> bool:
        return bool(data.get(key, DEFAULTS[key]))

    return AnnouncementSettings(
        enabled=flag("announcements_enabled"),
        card_name=flag("announce_card_name"),
        unknown_card=flag("announce_unknown_card"),
        usage_limit=flag("announce_usage_limit"),
        mute=flag("announce_mute"),
        language=clamp_language(data.get("announce_language", DEFAULT_LANGUAGE)),
        volume_percent=clamp_percent(
            data.get("announce_volume_percent"),
            int(DEFAULTS["announce_volume_percent"]),
        ),
        duck_percent=clamp_percent(
            data.get("announce_duck_percent"), int(DEFAULTS["announce_duck_percent"])
        ),
        limit_warning_minutes=clamp_warning_minutes(
            data.get("announce_limit_warning_minutes")
        ),
    )


@lru_cache(maxsize=1)
def _phrases() -> dict[str, dict[str, str]]:
    """The wordings shipped in this image. Never raises - an unreadable file
    costs the announcements, not the box."""
    try:
        data = json.loads(PHRASES_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("announcement_phrases_unreadable", error=str(exc))
        return {}
    phrases = data.get("phrases")
    return phrases if isinstance(phrases, dict) else {}


def render(key: str, language: str, **params: Any) -> str | None:
    """The sentence for *key* in *language*, or None when there is none.

    Placeholders are substituted literally rather than through ``str.format``:
    a card name is arbitrary user text, and a name with a brace in it would
    otherwise take the announcement down with a KeyError.
    """
    entry = _phrases().get(key)
    if not isinstance(entry, dict):
        logger.debug("announcement_phrase_missing", key=key)
        return None
    text = entry.get(language) or entry.get(DEFAULT_LANGUAGE)
    if not isinstance(text, str) or not text.strip():
        return None
    for name, value in params.items():
        text = text.replace("{" + name + "}", str(value))
    return text.strip() or None


async def _clip_path(text: str, language: str) -> str | None:
    """Ask the TTS service for a clip of *text*; None when it cannot make one."""
    try:
        async with httpx.AsyncClient(timeout=TTS_TIMEOUT_SEC) as client:
            response = await client.post(
                f"{TTS_SERVICE_URL}/speak",
                json={"text": text, "language": language},
            )
            response.raise_for_status()
            path = response.json().get("path")
    except (httpx.HTTPError, ValueError) as exc:
        # Includes the component being switched off between the capability
        # check and this call - a connection refused is not worth a stack
        # trace on every card scan.
        logger.info("announcement_not_synthesized", error=str(exc))
        return None
    return path if isinstance(path, str) and path else None


async def announce(mqtt_client: Any, key: str, **params: Any) -> bool:
    """Say the phrase for *key*, if this box is set up to say it.

    Returns whether something was published - the caller does not have to look,
    and nothing downstream changes if it was not.
    """
    settings = read_settings()
    if not settings.allows(key):
        return False
    if FEATURE not in capabilities.installed_features():
        logger.debug("announcement_skipped_no_voice_component", key=key)
        return False

    text = render(key, settings.language, **params)
    if not text:
        return False

    path = await _clip_path(text, settings.language)
    if not path:
        return False

    try:
        await mqtt_client.publish_audio_command(
            "announce",
            {
                "source_uri": path,
                "duck_percent": settings.duck_percent,
                "volume_percent": settings.volume_percent,
            },
        )
    except Exception as exc:  # noqa: BLE001 - a courtesy never breaks a scan
        logger.warning("announcement_publish_failed", key=key, error=str(exc))
        return False

    logger.info("announcement_sent", key=key, language=settings.language)
    return True


#: Announcements still in flight. `asyncio.create_task` keeps no reference of
#: its own, so without this set a phrase could be garbage-collected halfway
#: through being made.
_pending: set[asyncio.Task[bool]] = set()


def announce_soon(mqtt_client: Any, key: str, **params: Any) -> None:
    """`announce`, without making the caller wait for it.

    This is the variant almost every caller wants. Making a phrase for the
    first time costs a couple of seconds on a Raspberry Pi, and the places that
    raise one are all places where seconds are expensive: inside a card scan,
    which holds a database session open and is followed by the play command, or
    inside an MQTT message handler, which is processing the box's status. None
    of them depends on the phrase having been said - the audio service ducks
    around it whenever it arrives.

    `announce` is awaited only where the announcement *is* the moment: the
    warning on its own timer, and the sentence before the box fades itself out.
    """
    task = asyncio.create_task(announce(mqtt_client, key, **params))
    _pending.add(task)
    task.add_done_callback(_pending.discard)
