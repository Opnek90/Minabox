"""Audio device auto-detection for the Audio Service.

Detects available ALSA audio devices and prioritizes them based on
common hardware configurations (HATs, USB, onboard).
"""

import subprocess
from dataclasses import dataclass

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class AudioDevice:
    """Detected audio device information."""

    name: str
    card_name: str
    device_type: str
    alsa_device: str
    priority: int


class AudioDeviceDetector:
    """Detects and prioritizes available audio devices."""

    # Priority order (lower number = higher priority)
    DEVICE_PRIORITY = {
        "wm8960soundcard": 1,  # WM8960 Audio HAT (Waveshare/Seeed)
        "hifiberry": 2,  # HiFiBerry DAC/AMP
        "iqaudio": 3,  # IQaudio DAC/AMP
        "pisound": 4,  # Blokas Pisound
        "audioinjector": 5,  # Audio Injector HATs
        "USB": 6,  # USB Soundcards
        "Headphones": 7,  # Raspberry Pi 3.5mm jack
        "vc4hdmi": 8,  # HDMI audio (lower priority)
    }

    async def detect_devices(self) -> list[AudioDevice]:
        """Detect all available ALSA audio devices.

        Returns:
            List of detected AudioDevice objects, sorted by priority
        """
        try:
            result = subprocess.run(
                ["aplay", "-L"],
                capture_output=True,
                text=True,
                check=True,
                timeout=5,
            )

            devices = []
            lines = result.stdout.strip().split("\n")

            i = 0
            while i < len(lines):
                line = lines[i].strip()

                # Look for plughw devices (best compatibility with VLC)
                if line.startswith("plughw:CARD="):
                    try:
                        # Extract card name: plughw:CARD=wm8960soundcard,DEV=0
                        card_name = line.split("CARD=")[1].split(",")[0]

                        # Get description from next line
                        description = (
                            lines[i + 1].strip() if i + 1 < len(lines) else card_name
                        )

                        # Skip if description is another device identifier
                        if description.startswith(("hw:", "plughw:", "sysdefault:")):
                            description = card_name

                        device = AudioDevice(
                            name=description,
                            card_name=card_name,
                            device_type="alsa",
                            alsa_device=line,
                            priority=self._get_priority(card_name),
                        )
                        devices.append(device)

                        logger.debug(
                            "audio_device_found",
                            name=device.name,
                            card=card_name,
                            alsa_device=device.alsa_device,
                            priority=device.priority,
                        )

                    except Exception as e:
                        logger.warning(
                            "failed_to_parse_device",
                            line=line,
                            error=str(e),
                        )

                i += 1

            # Sort by priority (lower number first)
            devices.sort(key=lambda d: d.priority)

            logger.debug(
                "audio_devices_detected",
                count=len(devices),
                best=devices[0].card_name if devices else None,
            )

            return devices

        except subprocess.TimeoutExpired:
            logger.error("audio_device_detection_timeout")
            return []
        except Exception as e:
            logger.error("audio_device_detection_failed", error=str(e))
            return []

    def _get_priority(self, card_name: str) -> int:
        """Get priority for card name based on keyword matching.

        Args:
            card_name: ALSA card name (e.g., 'wm8960soundcard')

        Returns:
            Priority number (lower = higher priority)
        """
        card_lower = card_name.lower()

        for keyword, priority in self.DEVICE_PRIORITY.items():
            if keyword.lower() in card_lower:
                return priority

        # Unknown devices get lowest priority
        return 99

    async def get_best_device(self) -> AudioDevice | None:
        """Get the best available audio device based on priority.

        Returns:
            Best AudioDevice or None if no devices found
        """
        devices = await self.detect_devices()
        return devices[0] if devices else None

    async def get_device_by_card(self, card_name: str) -> AudioDevice | None:
        """Get device by card name.

        Args:
            card_name: ALSA card name to search for

        Returns:
            AudioDevice if found, None otherwise
        """
        devices = await self.detect_devices()
        for device in devices:
            if device.card_name.lower() == card_name.lower():
                return device
        return None
