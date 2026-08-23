"""Shared fixtures for the RFID service tests."""

from __future__ import annotations

import pytest
from rfid_test_doubles import FakeMQTT


@pytest.fixture
def mqtt() -> FakeMQTT:
    return FakeMQTT()
