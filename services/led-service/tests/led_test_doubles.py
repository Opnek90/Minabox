"""Test doubles for the LED service tests."""

from __future__ import annotations

import asyncio

from led_service.config_schema import (
    AppConfig,
    EnvConfig,
    LEDConfig,
    LEDPattern,
    LEDServiceConfig,
)


class FakeLED:
    """Records what a pattern does instead of touching a GPIO pin.

    Covers both gpiozero interfaces the service uses: ``on()``/``off()`` for a
    plain LED and the ``value`` property for a PWMLED.
    """

    def __init__(self, *, fail_on_switch: bool = False) -> None:
        self.transitions: list[str] = []
        self.values: list[float] = []
        self.is_lit = False
        self.closed = False
        self._fail_on_switch = fail_on_switch
        self._value = 0.0

    def on(self) -> None:
        if self._fail_on_switch:
            raise RuntimeError("pin is not available")
        self.is_lit = True
        self._value = 1.0
        self.transitions.append("on")

    def off(self) -> None:
        self.is_lit = False
        self._value = 0.0
        self.transitions.append("off")

    def close(self) -> None:
        self.closed = True

    @property
    def value(self) -> float:
        return self._value

    @value.setter
    def value(self, brightness: float) -> None:
        self._value = brightness
        self.is_lit = brightness > 0.0
        self.values.append(brightness)


class FakeClock:
    """Stand-in for ``_sleep_or_cancel`` that records waits instead of sleeping.

    Patterns are almost entirely timing, so testing them against the real clock
    means either slow tests or flaky ones. Recording the requested durations
    makes the assertions exact: a blink of ``repeat: 2`` must ask for four
    intervals, and the last pulse must not ask for a trailing gap.
    """

    def __init__(self, cancel_after: int | None = None) -> None:
        self.waits: list[float] = []
        self._cancel_after = cancel_after

    async def __call__(self, cancel_event: asyncio.Event, seconds: float) -> bool:
        self.waits.append(seconds)
        if self._cancel_after is not None and len(self.waits) >= self._cancel_after:
            return True
        return cancel_event.is_set()


class FakeMQTT:
    """Records publishes instead of talking to a broker."""

    def __init__(self, connected: bool = True) -> None:
        self.messages: list[tuple[str, object]] = []
        self.is_connected = connected

    async def publish(self, topic: str, payload: object, **kwargs: object) -> bool:
        self.messages.append((topic, payload))
        return True


DEVICE_ID = "test-box"


def make_env() -> EnvConfig:
    return EnvConfig(
        mqtt_broker="mqtt",
        mqtt_port=1883,
        minabox_device_id=DEVICE_ID,
        log_level="DEBUG",
    )


def make_config(leds: list[LEDConfig] | None = None) -> AppConfig:
    return AppConfig(env=make_env(), leds=LEDServiceConfig(leds=leds or []))


def make_led(
    led_id: str = "led_1",
    gpio: int = 17,
    enabled: bool = True,
    **bindings: LEDPattern,
) -> LEDConfig:
    return LEDConfig(
        id=led_id,
        name=f"LED {led_id}",
        gpio=gpio,
        enabled=enabled,
        bindings=dict(bindings),
    )
