"""Shared fixtures for backend-service tests."""

from __future__ import annotations

import pytest

from backend_service.core import temperature_logger as tl


@pytest.fixture(autouse=True)
def _reset_current_alert():
    """The alert is module-level state; keep tests independent of each other."""
    tl._current_alert = None
    yield
    tl._current_alert = None
