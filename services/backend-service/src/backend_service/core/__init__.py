"""Core functionality for Backend Service.

This package contains MQTT client, database manager, session manager,
and event handlers.
"""

from backend_service.core.db_manager import DatabaseManager, get_db, init_db
from backend_service.core.mqtt_client import MQTTClient
from backend_service.core.session_manager import (
    PlaybackSession,
    SessionManager,
    session_manager,
)

__all__ = [
    # Database
    "DatabaseManager",
    "init_db",
    "get_db",
    # MQTT
    "MQTTClient",
    # Session
    "PlaybackSession",
    "SessionManager",
    "session_manager",
]
