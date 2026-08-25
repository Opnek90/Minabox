"""One unavailable pin must not take the other buttons -- or the pins -- with it.

Before this, GPIOInputManager.start() raised on the first button it could not
initialise. The caller in main.py caught that and dropped the manager without
closing it, so every other button was dead *and* the pins already claimed
stayed claimed until the container was restarted.
"""

from __future__ import annotations

import asyncio

import pytest
from button_service.core.gpio_input_manager import GPIOInputManager
from button_service.exceptions import GPIOInitError

from button_test_doubles import (
    FakePinRegistry,
    config,
    install_fake_gpio,
    push,
    rotary,
)


def _manager(cfg, loop):
    return GPIOInputManager(config=cfg, event_queue=asyncio.Queue(), loop=loop)


@pytest.fixture
def loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


def test_all_pins_free_brings_every_button_up(monkeypatch, loop):
    registry = FakePinRegistry()
    install_fake_gpio(monkeypatch, registry)

    manager = _manager(config(push("a", 5), push("b", 6)), loop)
    manager.start()

    assert manager.available_count == 2
    assert manager.configured_count == 2
    assert registry.held == {5, 6}


def test_one_busy_pin_leaves_the_other_buttons_working(monkeypatch, loop):
    registry = FakePinRegistry(busy={6})
    install_fake_gpio(monkeypatch, registry)

    manager = _manager(config(push("a", 5), push("b", 6), push("c", 12)), loop)
    manager.start()

    # The failing button is skipped; it does not abort the loop.
    assert manager.available_count == 2
    assert manager.configured_count == 3
    assert registry.held == {5, 12}


def test_every_pin_busy_is_reported_but_not_fatal(monkeypatch, loop):
    """No button comes up, yet the service stays alive to say so on /health."""
    registry = FakePinRegistry(busy={5, 6})
    install_fake_gpio(monkeypatch, registry)

    manager = _manager(config(push("a", 5), push("b", 6)), loop)
    manager.start()

    assert manager.available_count == 0
    assert manager.configured_count == 2
    assert registry.held == set()


def test_unusable_pin_factory_is_fatal_to_the_hardware_layer(monkeypatch, loop):
    """An image built without lgpio cannot drive anything -- that one raises."""
    from button_service.core import gpio_input_manager as mod

    registry = FakePinRegistry()
    install_fake_gpio(monkeypatch, registry)
    monkeypatch.setattr(mod.Device, "pin_factory", None, raising=False)

    def no_lgpio(self):
        raise GPIOInitError("lgpio module not found")

    monkeypatch.setattr(mod.GPIOInputManager, "_ensure_pin_factory", no_lgpio)

    manager = _manager(config(push("a", 5)), loop)
    with pytest.raises(GPIOInitError):
        manager.start()

    assert registry.held == set(), "no device may be created before the factory is up"


def test_rotary_releases_its_encoder_when_the_switch_pin_is_busy(monkeypatch, loop):
    """A half-built encoder must leave nothing behind.

    CLK and DT are claimed first, the switch last. If the switch pin belongs to
    someone else, the encoder pins have to go back.
    """
    registry = FakePinRegistry(busy={25})
    install_fake_gpio(monkeypatch, registry)

    manager = _manager(config(rotary("enc", clk=24, dt=23, sw=25)), loop)
    manager.start()

    assert manager.available_count == 0
    assert registry.held == set(), "CLK/DT stayed claimed after the switch failed"


def test_close_releases_every_pin(monkeypatch, loop):
    registry = FakePinRegistry()
    install_fake_gpio(monkeypatch, registry)

    manager = _manager(config(push("a", 5), rotary("enc", clk=24, dt=23, sw=25)), loop)
    manager.start()
    assert registry.held == {5, 24, 23, 25}

    manager.close()
    assert registry.held == set()
    assert manager.available_count == 0


def test_close_cancels_a_pending_short_press(monkeypatch, loop):
    """A reload must not fire an event for the configuration it replaced.

    The short press waits out the double-press window on a threading.Timer.
    Closing the devices while that timer runs used to leave it to fire into a
    loop that may be gone, for a button id the new config may not know.
    """
    registry = FakePinRegistry()
    install_fake_gpio(monkeypatch, registry)

    manager = _manager(config(push("a", 5)), loop)
    manager.start()

    emitted: list[str] = []
    classifier = manager._classifiers[0]
    classifier.emit = lambda event: emitted.append(event.event_type)

    classifier.on_pressed()
    classifier.on_released()
    timer = classifier._pending_short_timer
    assert timer is not None, "a short press should be waiting out the window"

    manager.close()

    assert classifier._pending_short_timer is None
    # Well past DOUBLE_PRESS_WINDOW_S: the cancelled timer never fires.
    timer.join(timeout=2.0)
    assert not timer.is_alive()
    assert emitted == []


def test_reinit_after_close_can_claim_the_same_pins(monkeypatch, loop):
    """The config-reload path: close, then build again on the very same pins."""
    registry = FakePinRegistry()
    install_fake_gpio(monkeypatch, registry)

    first = _manager(config(push("a", 5)), loop)
    first.start()
    first.close()

    second = _manager(config(push("a", 5)), loop)
    second.start()

    assert second.available_count == 1
    assert registry.held == {5}
