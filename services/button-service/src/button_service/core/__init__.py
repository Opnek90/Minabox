"""Core logic for the button service (hardware + event processing)."""

from __future__ import annotations

from .event_processor import run_event_processor
from .events import RawButtonEvent
from .gpio_input_manager import GPIOInputManager

__all__ = ["GPIOInputManager", "RawButtonEvent", "run_event_processor"]
