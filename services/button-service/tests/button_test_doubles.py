"""Test doubles for the button service tests.

Nothing here touches a GPIO pin. `FakeButton` and `FakeRotaryEncoder` stand in
for the gpiozero devices and, crucially, model the one failure that matters:
a pin another process already owns raises on construction, the way gpiozero
does with `lgpio.error('GPIO busy')`.
"""

from __future__ import annotations

from button_service.config_schema import ButtonConfig, ButtonServiceConfig


class PinBusyError(RuntimeError):
    """Stands in for the lgpio error gpiozero surfaces for a claimed pin."""


class FakePinRegistry:
    """Hands out pins and refuses the ones marked busy.

    Also records which pins are still held, which is how the tests check that
    a failed start does not leak the devices it managed to create.
    """

    def __init__(self, busy: set[int] | None = None) -> None:
        self.busy = busy or set()
        self.held: set[int] = set()
        self.closed: list[int] = []

    def claim(self, pin: int) -> None:
        if pin in self.busy or pin in self.held:
            raise PinBusyError(f"GPIO busy: {pin}")
        self.held.add(pin)

    def release(self, pin: int) -> None:
        self.held.discard(pin)
        self.closed.append(pin)


class _FakeDevice:
    def __init__(self, registry: FakePinRegistry, pin: int) -> None:
        self._registry = registry
        self.pin = pin
        self.closed = False
        registry.claim(pin)

    def close(self) -> None:
        if not self.closed:
            self.closed = True
            self._registry.release(self.pin)


class FakeButton(_FakeDevice):
    """gpiozero.Button stand-in: claims its pin, records the callbacks."""

    def __init__(self, pin: int, *, registry: FakePinRegistry, **kwargs: object) -> None:
        super().__init__(registry, pin)
        self.kwargs = kwargs
        self.when_pressed = None
        self.when_held = None
        self.when_released = None


class FakeRotaryEncoder(_FakeDevice):
    """gpiozero.RotaryEncoder stand-in: claims CLK, then DT."""

    def __init__(
        self, clk: int, dt: int, *, registry: FakePinRegistry, **kwargs: object
    ) -> None:
        super().__init__(registry, clk)
        self.dt = dt
        try:
            registry.claim(dt)
        except PinBusyError:
            self.close()
            raise
        self.kwargs = kwargs
        self.when_rotated_clockwise = None
        self.when_rotated_counter_clockwise = None

    def close(self) -> None:
        already_closed = self.closed
        super().close()
        if not already_closed:
            self._registry.release(self.dt)


class FakeLGPIOFactory:
    """Pin factory whose only job is to have the right class name."""

    def close(self) -> None:  # pragma: no cover - never exercised
        pass


def install_fake_gpio(monkeypatch, registry: FakePinRegistry) -> None:
    """Point gpio_input_manager at the fakes instead of real gpiozero."""
    from button_service.core import gpio_input_manager as mod

    monkeypatch.setattr(
        mod, "Button", lambda *a, **kw: FakeButton(*a, registry=registry, **kw)
    )
    monkeypatch.setattr(
        mod,
        "RotaryEncoder",
        lambda *a, **kw: FakeRotaryEncoder(*a, registry=registry, **kw),
    )
    # A factory that is already the right type, so _ensure_pin_factory() is a
    # no-op and no real gpiochip is ever opened.
    factory = FakeLGPIOFactory()
    factory.__class__.__name__ = "LGPIOFactory"
    monkeypatch.setattr(mod.Device, "pin_factory", factory, raising=False)


def push(button_id: str, gpio: int, *, action: str = "play_pause") -> ButtonConfig:
    return ButtonConfig(
        id=button_id, name=button_id, mode="basic", type="push", gpio=gpio, action=action
    )


def rotary(button_id: str, clk: int, dt: int, sw: int) -> ButtonConfig:
    return ButtonConfig(
        id=button_id,
        name=button_id,
        mode="advanced",
        type="rotary",
        clk=clk,
        dt=dt,
        sw=sw,
        actions={"rotate_cw": "volume_up", "press": "mute_toggle"},
    )


def config(*buttons: ButtonConfig) -> ButtonServiceConfig:
    return ButtonServiceConfig(buttons=list(buttons))
