"""The check chain behind "Fix sound problem" (docs/services/Offene-Punkte.md 1.7).

Nothing is more annoying than a box that suddenly makes no sound. Both faults
of that kind we have had so far were findable only with `aplay -l`, `pactl` and
a look into the WirePlumber database. Nobody who *uses* the box rather than
develops it can do that - and that is exactly the person standing in front of
it.

So this walks the chain from the bottom up and repairs what it can repair
safely, without asking. Two rules hold it together:

- **Idempotent.** Running it twice must do nothing the second time.
- **Touch only what is demonstrably wrong.** A box someone deliberately turned
  down quietly must not be turned back up. Every threshold here is therefore
  "so low that nobody meant it" rather than "not the value I would pick".

Every repair is recorded, so the debug export can still show afterwards what
the button actually did.

Steps 1 and 7 of the chain are not here: `/proc/asound/cards` and `amixer` are
not reachable from this container. They live in the host-helper, and the
backend stitches both halves together.
"""

from __future__ import annotations

import asyncio
import os
import re
import subprocess

import structlog

logger = structlog.get_logger(__name__)

# Below this, a sink is not "quiet", it is broken. Someone who wants it quiet
# uses the volume control, which cannot go this low without meaning to.
_SINK_VOLUME_FLOOR_PERCENT = 20
# What a sink that failed the floor is set to. Deliberately not 100: the point
# is to make the box audible, not loud.
_SINK_VOLUME_REPAIR_PERCENT = 60

_PACTL_TIMEOUT = 5


class Step:
    """One rung of the chain, and what happened on it."""

    def __init__(
        self, step_id: str, ok: bool, fixed: bool = False, detail: str | None = None
    ) -> None:
        self.step_id = step_id
        self.ok = ok
        self.fixed = fixed
        self.detail = detail

    def as_dict(self) -> dict:
        return {
            "id": self.step_id,
            # True when this rung is fine now - whether it always was or this
            # run repaired it.
            "ok": self.ok,
            "fixed": self.fixed,
            "detail": self.detail,
        }


def _pactl(args: list[str]) -> subprocess.CompletedProcess | None:
    """Run one pactl command. Returns None when it could not run at all."""
    if not os.environ.get("PULSE_SERVER"):
        return None
    try:
        return subprocess.run(
            ["pactl", *args], capture_output=True, text=True, timeout=_PACTL_TIMEOUT
        )
    except Exception as e:
        logger.warning("troubleshoot_pactl_failed", args=args, error=str(e))
        return None


def _sink_mute_and_volume(sink: str) -> tuple[bool | None, int | None]:
    """(muted, volume percent) for *sink*; None for what could not be read."""
    muted: bool | None = None
    volume: int | None = None

    result = _pactl(["get-sink-mute", sink])
    if result is not None and result.returncode == 0:
        muted = "yes" in (result.stdout or "").lower()

    result = _pactl(["get-sink-volume", sink])
    if result is not None and result.returncode == 0:
        # "Volume: front-left: 39321 /  60% / -13.68 dB,  front-right: ..."
        # The lowest channel decides: one silent channel is still a fault.
        percents = [int(m) for m in re.findall(r"(\d+)%", result.stdout or "")]
        if percents:
            volume = min(percents)
    return muted, volume


def _muted_sink_input_indices() -> list[str]:
    """Indices of currently muted playback streams.

    This is where a remembered role state shows itself: WirePlumber stores mute
    per media role and pushes it onto a stream the moment it opens the output.
    It can only be seen - and only be corrected - while a stream is running.
    """
    result = _pactl(["list", "sink-inputs"])
    if result is None or result.returncode != 0:
        return []
    muted: list[str] = []
    index: str | None = None
    for line in (result.stdout or "").splitlines():
        stripped = line.strip()
        match = re.match(r"Sink Input #(\d+)", stripped)
        if match:
            index = match.group(1)
        elif index and stripped.lower().startswith("mute:"):
            if "yes" in stripped.lower():
                muted.append(index)
            index = None
    return muted


class AudioTroubleshooter:
    """Steps 2 to 6 of the chain. Everything it needs is in the audio service."""

    def __init__(self, service) -> None:  # noqa: ANN001 - avoids a circular import
        self._service = service

    async def run(self) -> dict:
        """Walk the chain and return what was found and what was repaired."""
        steps: list[Step] = []

        sink = await self._step_sink_present(steps)
        await self._step_sink_level(steps, sink)
        await self._step_service_mute(steps)
        await self._step_service_volume(steps)

        # Step 4 last, because it only works *while* a stream runs: the test
        # tone is that stream.
        tone_played, tone_error = await self._step_stream_state(steps)

        fixed = [s.step_id for s in steps if s.fixed]
        if fixed:
            logger.info("audio_troubleshoot_repaired", steps=fixed)
        return {
            "steps": [s.as_dict() for s in steps],
            "fixed": fixed,
            # What the UI names as the cause, in one line. The first repair is
            # the one furthest down the chain and therefore the likeliest.
            "cause": fixed[0] if fixed else None,
            "tone_played": tone_played,
            "tone_error": tone_error,
        }

    # ── The rungs ────────────────────────────────────────────────────────────

    async def _step_sink_present(self, steps: list[Step]) -> str | None:
        """2. Is the configured sink there? Otherwise fall back to the first one."""
        config = self._service._get_audio_config()
        configured = (getattr(config, "output_device_name", None) or "").strip()
        try:
            devices = await self._service.get_audio_devices(force_refresh=True)
        except Exception as e:
            steps.append(Step("sink_present", ok=False, detail=f"lookup failed: {e}"))
            return configured or None

        available = [d.get("id") for d in devices if d.get("id")]
        if not available:
            # Nothing to fall back to. This is the sound card being gone, which
            # only a reboot fixes - step 1 says so, and it is not ours.
            steps.append(Step("sink_present", ok=False, detail="no sink at all"))
            return None

        if configured and configured in available:
            steps.append(Step("sink_present", ok=True, detail=configured))
            return configured

        if not configured:
            # Empty means "host default sink" - nothing is pinned down, so
            # nothing can be missing.
            steps.append(Step("sink_present", ok=True, detail="host default"))
            return available[0]

        fallback = available[0]
        await self._service.switch_output_device(sink_name=fallback)
        steps.append(
            Step(
                "sink_present",
                ok=True,
                fixed=True,
                detail=f"{configured} is gone, switched to {fallback}",
            )
        )
        return fallback

    async def _step_sink_level(self, steps: list[Step], sink: str | None) -> None:
        """3. Is the sink itself muted or turned down to nothing?"""
        if not sink:
            steps.append(Step("sink_level", ok=False, detail="no sink"))
            return

        muted, volume = await asyncio.to_thread(_sink_mute_and_volume, sink)
        if muted is None and volume is None:
            steps.append(Step("sink_level", ok=False, detail="could not read sink"))
            return

        repaired = []
        if muted:
            await asyncio.to_thread(_pactl, ["set-sink-mute", sink, "0"])
            repaired.append("unmuted")
        if volume is not None and volume < _SINK_VOLUME_FLOOR_PERCENT:
            await asyncio.to_thread(
                _pactl,
                ["set-sink-volume", sink, f"{_SINK_VOLUME_REPAIR_PERCENT}%"],
            )
            repaired.append(f"{volume}% -> {_SINK_VOLUME_REPAIR_PERCENT}%")

        steps.append(
            Step(
                "sink_level",
                ok=True,
                fixed=bool(repaired),
                detail=", ".join(repaired) or f"mute={muted}, volume={volume}%",
            )
        )

    async def _step_service_mute(self, steps: list[Step]) -> None:
        """5. Did somebody leave the service itself muted?"""
        if getattr(self._service, "_muted", False):
            await self._service.set_muted(False)
            steps.append(Step("service_mute", ok=True, fixed=True, detail="unmuted"))
        else:
            steps.append(Step("service_mute", ok=True))

    async def _step_service_volume(self, steps: list[Step]) -> None:
        """6. Is the service volume below its own minimum?"""
        config = self._service._get_audio_config()
        min_volume = getattr(config, "min_volume", 0) or 0
        default_volume = getattr(config, "default_volume", 40) or 40
        try:
            current = await self._service.get_volume()
        except Exception as e:
            steps.append(Step("service_volume", ok=False, detail=str(e)))
            return

        if current is not None and current < min_volume:
            await self._service.set_volume(default_volume)
            steps.append(
                Step(
                    "service_volume",
                    ok=True,
                    fixed=True,
                    detail=f"{current} -> {default_volume}",
                )
            )
        else:
            steps.append(Step("service_volume", ok=True, detail=str(current)))

    async def _step_stream_state(self, steps: list[Step]) -> tuple[bool, str | None]:
        """4. Play the tone, and unmute the stream while it runs.

        A remembered role state is only visible on a running stream, and only
        correctable there - WirePlumber writes the corrected value back by
        itself. The tone therefore has to go through libVLC, the same path the
        music takes: a tone played through paplay lands in a different role
        with its own healthy state and proves nothing.
        """
        tone = asyncio.create_task(self._service.play_troubleshoot_tone())

        # Give the stream a moment to open the output - that is when the
        # remembered state is applied, not before.
        await asyncio.sleep(1.0)
        muted_streams = await asyncio.to_thread(_muted_sink_input_indices)
        for index in muted_streams:
            await asyncio.to_thread(_pactl, ["set-sink-input-mute", index, "0"])

        tone_error: str | None = None
        try:
            await tone
            tone_played = True
        except Exception as e:
            tone_played = False
            tone_error = str(e)
            logger.warning("audio_troubleshoot_tone_failed", error=str(e))

        steps.append(
            Step(
                "stream_state",
                ok=tone_played,
                fixed=bool(muted_streams),
                detail=(
                    f"unmuted {len(muted_streams)} stream(s)"
                    if muted_streams
                    else tone_error or "stream was not muted"
                ),
            )
        )
        return tone_played, tone_error
