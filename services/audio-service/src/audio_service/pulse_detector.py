"""PulseAudio/PipeWire sink detection for the Audio Service.

Lists available Pulse sinks when PULSE_SERVER is set (e.g. in Docker with host socket).
"""

import os
import subprocess
from dataclasses import dataclass

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class PulseSink:
    """Detected Pulse sink information."""

    sink_name: str
    name: str
    description: str
    priority: int


class PulseSinkDetector:
    """Detects available PulseAudio/PipeWire sinks."""

    async def detect_sinks(self) -> list[PulseSink]:
        """Detect all available Pulse sinks. Only runs when PULSE_SERVER is set.

        Returns:
            List of PulseSink objects (sink_name = id for API/config).
        """
        if not os.environ.get("PULSE_SERVER"):
            logger.debug("pulse_detector_skipped", reason="PULSE_SERVER not set")
            return []

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
            logger.info("pulse_sinks_detected", count=len(sinks))
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
