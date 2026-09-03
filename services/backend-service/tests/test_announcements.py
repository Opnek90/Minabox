"""What the box says, and - more often - what it deliberately does not.

An announcement is a courtesy. Every path through this module has to be able to
give up quietly: a card scan must not get slower, fail, or raise because the
voice component is switched off, the TTS service is down or a phrase is
missing.
"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from backend_service.core import announcements


class _MQTT:
    """Records what would have been published."""

    def __init__(self, fails: bool = False) -> None:
        self.published: list[tuple[str, dict]] = []
        self.fails = fails

    async def publish_audio_command(self, action: str, payload: dict) -> None:
        if self.fails:
            raise RuntimeError("broker gone")
        self.published.append((action, payload))


@pytest.fixture
def box(monkeypatch, tmp_path):
    """A box with the voice component and every announcement switched on."""
    monkeypatch.setenv("COMPOSE_PROFILES", "rfid,voice")
    settings_path = tmp_path / "general_settings.json"
    settings_path.write_text(
        json.dumps({"announcements_enabled": True}), encoding="utf-8"
    )
    monkeypatch.setenv("DATA_PATH", str(tmp_path))
    from backend_service.core import general_settings

    general_settings.invalidate()
    yield settings_path
    general_settings.invalidate()


def _write(path, **settings):
    from backend_service.core import general_settings

    path.write_text(json.dumps(settings), encoding="utf-8")
    general_settings.invalidate()


def _tts(monkeypatch, *, path="/announcements/abc.wav", status=200):
    """Stand in for the TTS service at the HTTP layer."""
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        if status != 200:
            return httpx.Response(status)
        return httpx.Response(200, json={"path": path})

    transport = httpx.MockTransport(handler)
    original = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = transport
        return original(*args, **kwargs)

    monkeypatch.setattr(announcements.httpx, "AsyncClient", factory)
    return seen


# --- the switches -----------------------------------------------------------


def test_nothing_is_said_until_announcements_are_switched_on(box, monkeypatch):
    """The default is silence: a box that starts talking after an update would
    be a surprise in a child's bedroom."""
    _write(box)  # no announcements_enabled
    _tts(monkeypatch)
    mqtt = _MQTT()

    assert announcements.read_settings().enabled is False
    assert asyncio.run(announcements.announce(mqtt, "card_unknown")) is False
    assert mqtt.published == []


def test_a_single_switch_can_be_turned_off(box, monkeypatch):
    _write(box, announcements_enabled=True, announce_card_name=False)
    _tts(monkeypatch)
    mqtt = _MQTT()

    assert asyncio.run(announcements.announce(mqtt, "card", name="Maus")) is False
    assert asyncio.run(announcements.announce(mqtt, "card_unknown")) is True


def test_a_phrase_without_a_switch_is_never_spoken(box):
    """The master switch is not blanket permission for an unmapped key."""
    settings = announcements.read_settings()
    assert settings.enabled is True
    assert settings.allows("something_new") is False


def test_a_box_without_the_voice_component_stays_silent(box, monkeypatch):
    monkeypatch.setenv("COMPOSE_PROFILES", "rfid,led")
    _tts(monkeypatch)
    mqtt = _MQTT()

    assert asyncio.run(announcements.announce(mqtt, "card_unknown")) is False
    assert mqtt.published == []


# --- what gets published ----------------------------------------------------


def test_the_clip_path_and_the_levels_travel_with_the_command(box, monkeypatch):
    _write(
        box,
        announcements_enabled=True,
        announce_duck_percent=20,
        announce_volume_percent=80,
    )
    _tts(monkeypatch, path="/announcements/deadbeef.wav")
    mqtt = _MQTT()

    assert asyncio.run(announcements.announce(mqtt, "card_unknown")) is True
    action, payload = mqtt.published[0]
    assert action == "announce"
    assert payload == {
        "source_uri": "/announcements/deadbeef.wav",
        "duck_percent": 20,
        "volume_percent": 80,
    }


def test_the_card_name_is_substituted_into_the_phrase(box, monkeypatch):
    seen = _tts(monkeypatch)
    asyncio.run(announcements.announce(_MQTT(), "card", name="Die Maus"))
    assert seen[0]["text"] == "Die Maus"


def test_the_language_reaches_the_tts_service(box, monkeypatch):
    _write(box, announcements_enabled=True, announce_language="en")
    seen = _tts(monkeypatch)
    asyncio.run(announcements.announce(_MQTT(), "card_unknown"))
    assert seen[0] == {"text": "I do not know this card.", "language": "en"}


# --- giving up quietly ------------------------------------------------------


def test_a_tts_service_that_is_down_costs_the_phrase_and_nothing_else(
    box, monkeypatch
):
    _tts(monkeypatch, status=503)
    mqtt = _MQTT()

    assert asyncio.run(announcements.announce(mqtt, "card_unknown")) is False
    assert mqtt.published == []


def test_a_broker_that_refuses_does_not_raise_into_the_card_scan(box, monkeypatch):
    _tts(monkeypatch)
    mqtt = _MQTT(fails=True)

    assert asyncio.run(announcements.announce(mqtt, "card_unknown")) is False


def test_an_unknown_phrase_key_is_not_an_error(box, monkeypatch):
    _tts(monkeypatch)
    assert (
        asyncio.run(announcements.announce(_MQTT(), "card_unknown", extra="x")) is True
    )
    assert announcements.render("no_such_phrase", "de") is None


def test_a_name_with_braces_does_not_take_the_phrase_down(box):
    """Card names are arbitrary user text; str.format would raise on this."""
    assert announcements.render("card", "de", name="{oops}") == "{oops}"


# --- settings clamping ------------------------------------------------------


def test_an_unknown_language_falls_back_to_german(box):
    _write(box, announcements_enabled=True, announce_language="fr")
    assert announcements.read_settings().language == "de"


def test_a_regional_language_tag_is_still_that_language(box):
    _write(box, announcements_enabled=True, announce_language="en-GB")
    assert announcements.read_settings().language == "en"


@pytest.mark.parametrize(
    ("stored", "expected"), [(-10, 0), (500, 100), ("loud", 30), (None, 30)]
)
def test_the_duck_level_is_clamped_into_range(box, stored, expected):
    _write(box, announcements_enabled=True, announce_duck_percent=stored)
    assert announcements.read_settings().duck_percent == expected


@pytest.mark.parametrize(("stored", "expected"), [(-5, 0), (999, 60), ("x", 10)])
def test_the_warning_lead_time_is_clamped(box, stored, expected):
    _write(box, announcements_enabled=True, announce_limit_warning_minutes=stored)
    assert announcements.read_settings().limit_warning_minutes == expected


def test_every_phrase_exists_in_both_languages():
    """A missing translation is a box that says nothing in one language."""
    for key in announcements.PHRASE_SWITCH:
        for language in announcements.LANGUAGES:
            assert announcements.render(key, language, name="x", minutes=1)


# --- not making the card scan wait ------------------------------------------


@pytest.mark.asyncio
async def test_announce_soon_returns_before_the_phrase_is_made(box, monkeypatch):
    """The play command follows in the next line; it must not wait for Piper."""
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow_clip(text, language):
        started.set()
        await release.wait()
        return "/announcements/slow.wav"

    monkeypatch.setattr(announcements, "_clip_path", slow_clip)
    mqtt = _MQTT()

    announcements.announce_soon(mqtt, "card", name="Die Maus")

    # Back immediately, with nothing published yet.
    assert mqtt.published == []
    await asyncio.wait_for(started.wait(), timeout=1)
    assert mqtt.published == []

    release.set()
    await asyncio.gather(*announcements._pending)
    assert mqtt.published[0][0] == "announce"


@pytest.mark.asyncio
async def test_a_pending_announcement_is_held_onto(box, monkeypatch):
    """asyncio.create_task keeps no reference; a dropped task can be collected
    halfway through being made."""
    release = asyncio.Event()

    async def slow_clip(text, language):
        await release.wait()
        return "/announcements/slow.wav"

    monkeypatch.setattr(announcements, "_clip_path", slow_clip)

    announcements.announce_soon(_MQTT(), "card_unknown")
    assert len(announcements._pending) == 1

    release.set()
    await asyncio.gather(*announcements._pending)
    assert announcements._pending == set()
