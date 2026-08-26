"""The host half of the sound-repair chain.

Steps 1 and 7 of docs/services/Offene-Punkte.md 1.7. The audio service walks
steps 2 to 6 itself - it talks to PulseAudio over the mounted socket anyway -
but `/proc/asound/cards` and `amixer` are not reachable from inside that
container. They need the host, which is this service's whole reason to exist.

Parameterless on purpose, like `/diagnostics/host`: nothing the caller sends
influences what runs here. The card numbers and control names that end up in
an `amixer` call are read off the host itself a moment earlier and validated
against a strict pattern before they are used again.
"""

from __future__ import annotations

import re
import subprocess
from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException

from host_helper.api.routes.deps import (
    _check_api_key,
    _run_compose_on_host,
    _run_on_host_via_nsenter,
)

logger = structlog.get_logger(__name__)

router = APIRouter()

# Mixer controls worth looking at, in the order they are tried. A box whose
# Speaker control sits at zero is broken; one whose "Mic Boost" does is not.
_MIXER_CONTROLS = ("Speaker", "PCM", "Master", "Headphone", "Digital")

# Below this, the mixer was not turned down, it was turned off. Same rule as in
# the audio service: only touch a value nobody could have meant.
_MIXER_FLOOR_PERCENT = 5
_MIXER_REPAIR_PERCENT = 80

# What a card line in /proc/asound/cards looks like:
#   " 3 [wm8960soundcar]: wm8960-soundcar - wm8960-soundcard"
_CARD_LINE = re.compile(r"^\s*(\d+)\s*\[")
_CONTROL_NAME = re.compile(r"^[A-Za-z0-9 _+-]{1,32}$")
_PERCENT = re.compile(r"\[(\d+)%\]")


def _step(step_id: str, ok: bool, fixed: bool = False, detail: str = "") -> dict:
    return {"id": step_id, "ok": ok, "fixed": fixed, "detail": detail}


def _amixer(args: list[str], timeout: int = 10) -> subprocess.CompletedProcess | None:
    """One amixer call on the host. Failures are data, not exceptions."""
    try:
        return _run_on_host_via_nsenter(["amixer", *args], timeout=timeout)
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        logger.warning("amixer_failed", args=args, error=str(e))
        return None


def _sound_cards() -> tuple[list[str], str]:
    """(card numbers, raw listing) from /proc/asound/cards."""
    try:
        result = _run_on_host_via_nsenter(["cat", "/proc/asound/cards"], timeout=10)
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        logger.warning("sound_card_listing_failed", error=str(e))
        return [], f"{type(e).__name__}: {e}"[:200]
    listing = (result.stdout or "").strip()
    cards = [
        m.group(1)
        for line in listing.splitlines()
        if (m := _CARD_LINE.match(line))
    ]
    return cards, listing


def _controls_of(card: str) -> list[str]:
    """Simple mixer controls of *card*, filtered to the ones worth touching."""
    result = _amixer(["-c", card, "scontrols"])
    if result is None or result.returncode != 0:
        return []
    # "Simple mixer control 'Speaker',0"
    found = re.findall(r"Simple mixer control '([^']+)'", result.stdout or "")
    names = [n for n in found if _CONTROL_NAME.match(n)]
    return [n for n in _MIXER_CONTROLS if n in names]


def _control_level(card: str, control: str) -> tuple[int | None, bool]:
    """(lowest channel percentage, muted) for one control."""
    result = _amixer(["-c", card, "sget", control])
    if result is None or result.returncode != 0:
        return None, False
    text = result.stdout or ""
    percents = [int(p) for p in _PERCENT.findall(text)]
    muted = "[off]" in text
    return (min(percents) if percents else None), muted


def _repair_mixer() -> dict:
    """Step 7: an ALSA mixer sitting at zero, or switched off.

    Only the controls in _MIXER_CONTROLS, only when they are at or below the
    floor or explicitly off, and only up to a level that makes the box audible
    rather than loud. Everything else is left exactly as it was.
    """
    cards, listing = _sound_cards()
    if not cards:
        return _step(
            "alsa_mixer", ok=False, detail=f"no sound card to check: {listing}"[:300]
        )

    repaired: list[str] = []
    inspected: list[str] = []
    for card in cards:
        for control in _controls_of(card):
            level, muted = _control_level(card, control)
            if level is None and not muted:
                continue
            inspected.append(f"card {card} {control}={level}%{' off' if muted else ''}")
            if muted or (level is not None and level <= _MIXER_FLOOR_PERCENT):
                result = _amixer(
                    ["-c", card, "sset", control, f"{_MIXER_REPAIR_PERCENT}%", "unmute"]
                )
                if result is not None and result.returncode == 0:
                    repaired.append(f"card {card} {control}")

    return _step(
        "alsa_mixer",
        ok=True,
        fixed=bool(repaired),
        detail=(
            "raised " + ", ".join(repaired)
            if repaired
            else "; ".join(inspected) or "nothing to check"
        ),
    )


@router.post("/audio/repair")
def audio_repair(_: None = Depends(_check_api_key)) -> dict:
    """Steps 1 and 7 of the sound-repair chain. Requires API key.

    Step 1 has no automatic repair on purpose. When the codec failed to probe
    at boot - which is how a real box lost its sound card - the driver does not
    try again, and only a restart of the box brings it back. Saying so honestly
    is better than a button that pretends to have done something.
    """
    cards, listing = _sound_cards()
    card_step = _step(
        "sound_card",
        ok=bool(cards),
        detail=listing[:500] if cards else f"no sound card found: {listing}"[:500],
    )

    steps = [card_step, _repair_mixer()]
    fixed = [s["id"] for s in steps if s["fixed"]]
    if fixed:
        logger.info("audio_repair_applied", steps=fixed)
    return {
        "collected_at": datetime.now(UTC).isoformat(),
        "steps": steps,
        "fixed": fixed,
    }


@router.post("/audio/restart")
def audio_restart(_: None = Depends(_check_api_key)) -> dict:
    """Restart only the audio container. Requires API key.

    The escalation step behind "no, still nothing" in the sound troubleshooter.
    Deliberately not the existing /restart, which restarts the whole stack:
    that takes the WebUI down with it, and the person waiting for an answer is
    looking at exactly that page.
    """
    try:
        result = _run_compose_on_host(["restart", "audio"], timeout=90)
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        logger.warning("audio_restart_failed", error=str(e))
        raise HTTPException(status_code=503, detail="Restart not possible") from e

    if result.returncode != 0:
        output = ((result.stdout or "") + (result.stderr or ""))[-1000:]
        raise HTTPException(status_code=502, detail=output or "Restart failed")
    logger.info("audio_service_restarted")
    return {"ok": True}
