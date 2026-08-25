"""Data shapes the service hands to its API layer."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class HealthState:
    """What /health needs to know about the running service.

    ``buttons_configured`` counts entries in buttons.json, ``buttons_available``
    counts the ones that actually hold their GPIO pins. Reporting only the
    first made a service whose pins were all unclaimable look perfectly fine.
    """

    buttons_configured: int
    buttons_available: int
    gpio_enabled: bool
    config_error: str | None = None

    @property
    def buttons_usable(self) -> bool:
        """True unless buttons are configured that cannot be driven."""
        if self.config_error is not None:
            return False
        if not self.gpio_enabled:
            # DISABLE_GPIO is a deliberate setting, not a fault.
            return True
        return self.buttons_available == self.buttons_configured
