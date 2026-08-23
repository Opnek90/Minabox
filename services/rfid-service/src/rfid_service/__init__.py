"""Minabox RFID service package."""

from __future__ import annotations

from shared_lib.version import get_version

from .config import load_app_config
from .infrastructure import MQTTClient, create_reader

#: Build version of this service, injected by the Dockerfile. Kept out of the
#: source so it cannot drift from services/rfid-service/VERSION.
__version__ = get_version()
__all__ = ["MQTTClient", "create_reader", "load_app_config"]
