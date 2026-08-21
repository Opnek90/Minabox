"""Shared fixtures for backend-service tests."""

from __future__ import annotations

import pytest

from backend_service.core import system_alerts


@pytest.fixture(autouse=True)
def _reset_current_alert():
    """The alert store is module-level state; keep tests independent."""
    system_alerts.clear_all()
    yield
    system_alerts.clear_all()
