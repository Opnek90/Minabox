"""PulseAudio/PipeWire sink detection for the Audio Service.

Lists available Pulse sinks when PULSE_SERVER is set (e.g. in Docker with host socket).

Sink discovery shells out to `pactl`, which is expensive on a Raspberry Pi and
was previously called on every status publish (every 2 seconds, forever). The
detector now caches the result for CACHE_TTL_SECONDS and exposes invalidate()
for the moments where the sink list genuinely changes - device switch,
re-initialisation and config reload.
"""

import asyncio
import os
import subprocess
import time
from dataclasses import dataclass

import structlog

logger = structlog.get_logger(__name__)

# How long a detected sink list stays valid.
#
# The status loop asks every 2s, so this is what keeps pactl off the CPU:
# 30 calls/min before, 6 calls/min at this TTL. Raising it to 30s would only
# save another 4 calls/min, but the display-service derives its Bluetooth icon
# from this data - a speaker that was just connected would then take up to 30s
# to show up on the OLED. Not worth it for the remaining scraps of CPU.
#
# The exact fix would be event-driven invalidation on Bluetooth connect, which
# needs the host-helper to reach the audio service. Until then this TTL is the
# ceiling on how stale the icon can be.
CACHE_TTL_SECONDS = 10.0


@dataclass
class PulseSink:
    """Detected Pulse sink information."""

    sink_name: str
    name: str
    description: str
    priority: int


class PulseSinkDetector:
    """Detects available PulseAudio/PipeWire sinks, with a short-lived cache."""

    def __init__(self) -> None:
        self._cache: list[PulseSink] | None = None
        self._cached_at: float = 0.0
        self._lock = asyncio.Lock()

    def invalidate(self) -> None:
        """Drop the cached sink list, so the next detect_sinks() re-runs pactl."""
        self._cache = None
        self._cached_at = 0.0

    async def detect_sinks(self, *, force: bool = False) -> list[PulseSink]:
        """Detect all available Pulse sinks. Only runs when PULSE_SERVER is set.

        Args:
            force: Bypass the cache and always shell out to pactl.

        Returns:
            List of PulseSink objects (sink_name = id for API/config).
        """
        if not os.environ.get("PULSE_SERVER"):
            logger.debug("pulse_detector_skipped", reason="PULSE_SERVER not set")
            return []

        if not force and self._is_cache_fresh():
            return list(self._cache or [])

        async with self._lock:
            # Another waiter may have refreshed while we waited for the lock.
            if not force and self._is_cache_fresh():
                return list(self._cache or [])

            sinks = await asyncio.to_thread(self._detect_sinks_blocking)
            self._cache = sinks
            self._cached_at = time.monotonic()
            return list(sinks)

    def _is_cache_fresh(self) -> bool:
        return (
            self._cache is not None
            and (time.monotonic() - self._cached_at) < CACHE_TTL_SECONDS
        )

    def _detect_sinks_blocking(self) -> list[PulseSink]:
        """Run pactl and parse its output. Blocking - call via asyncio.to_thread."""
        try:
            result = subprocess.run(
                ["pactl", "list", "sinks"],
                capture_output=True,
                text=True,
                timeout=10,
                env=os.environ.copy(),
            )
            if result.returncode != 0:
                logger.warning(
                    "pulse_detector_failed",
                    returncode=result.returncode,
                    stderr=(result.stderr or "")[:200],
                )
                return []

            sinks = self._parse_pactl_output(result.stdout or "")
            logger.debug("pulse_sinks_detected", count=len(sinks))
            return sinks

        except FileNotFoundError:
            logger.warning("pulse_detector_pactl_not_found")
            return []
        except subprocess.TimeoutExpired:
            logger.warning("pulse_detector_timeout")
            return []
        except Exception as e:
            logger.warning("pulse_detector_error", error=str(e))
            return []

    def _parse_pactl_output(self, stdout: str) -> list[PulseSink]:
        """Parse 'pactl list sinks' output: Sink blocks with Name, Description, and Properties (node.nick/alsa.card_name)."""
        sinks = []
        current_name: str | None = None
        current_desc: str | None = None
        current_nick: str | None = None
        current_card_name: str | None = None
        in_properties = False
        priority = 0

        def flush_sink() -> None:
            nonlocal priority
            if current_name is None or not current_name:
                return
            # Prefer PipeWire/ALSA card name over generic Description so WM8960 etc. show correctly
            display = current_nick or current_card_name or current_desc or current_name
            sinks.append(
                PulseSink(
                    sink_name=current_name,
                    name=display,
                    description=current_desc or current_name,
                    priority=priority,
                )
            )
            priority += 1

        for line in stdout.splitlines():
            line_stripped = line.strip()
            if line_stripped.startswith("Name:"):
                flush_sink()
                current_name = line_stripped[5:].strip()
                current_desc = None
                current_nick = None
                current_card_name = None
                in_properties = False
            elif line_stripped.startswith("Description:") and current_name is not None:
                current_desc = line_stripped[12:].strip()
            elif line_stripped == "Properties:":
                in_properties = True
            elif in_properties and current_name is not None:
                if line_stripped.startswith("node.nick ="):
                    current_nick = self._parse_property_value(line_stripped[len("node.nick ="):])
                elif line_stripped.startswith("alsa.card_name ="):
                    current_card_name = self._parse_property_value(line_stripped[len("alsa.card_name ="):])

        flush_sink()
        return sinks

    @staticmethod
    def _parse_property_value(s: str) -> str:
        """Extract quoted value from ' "value" ' or ' "value with spaces" '."""
        s = s.strip()
        if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
            return s[1:-1].strip()
        return s.strip()
