"""WebSocket manager for real-time communication with WebUI."""

import json
from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import WebSocket, WebSocketDisconnect

logger = structlog.get_logger(__name__)


class WebSocketManager:
    """Manages WebSocket connections for broadcasting events."""

    def __init__(self) -> None:
        """Initialize WebSocket manager."""
        self.active_connections: list[WebSocket] = []
        self._last_audio_status_payload: dict[str, Any] | None = None
        logger.debug("websocket_manager_initialized")

    def set_last_audio_status_payload(self, payload: dict[str, Any]) -> None:
        """Store the last enriched audio_status payload for new-client greeting."""
        self._last_audio_status_payload = payload

    async def connect(self, websocket: WebSocket) -> None:
        """Accept and register new WebSocket connection.

        Immediately sends the last known audio_status so the Player page
        renders without waiting for the next MQTT broadcast cycle.

        Args:
            websocket: WebSocket connection
        """
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.debug(
            "websocket_client_connected", total_clients=len(self.active_connections)
        )
        if self._last_audio_status_payload is not None:
            try:
                greeting = {
                    "type": "audio_status",
                    "data": self._last_audio_status_payload,
                    "timestamp": datetime.now(UTC).isoformat(),
                }
                await websocket.send_json(greeting)
                logger.debug("websocket_initial_audio_status_sent")
            except Exception as e:
                logger.warning("websocket_initial_audio_status_failed", error=str(e))

    def disconnect(self, websocket: WebSocket) -> None:
        """Remove WebSocket connection.

        Args:
            websocket: WebSocket connection
        """
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.debug(
            "websocket_client_disconnected", total_clients=len(self.active_connections)
        )

    async def send_personal_message(
        self, message: dict[str, Any], websocket: WebSocket
    ) -> None:
        """Send message to specific WebSocket client.

        Args:
            message: Message data
            websocket: Target WebSocket connection
        """
        try:
            # Add timestamp if not present
            if "timestamp" not in message:
                message["timestamp"] = datetime.now(UTC).isoformat()

            await websocket.send_json(message)
            logger.debug("websocket_message_sent", type=message.get("type"))
        except Exception as e:
            logger.error("websocket_send_failed", error=str(e))

    async def broadcast(self, message: dict[str, Any]) -> None:
        """Broadcast message to all connected WebSocket clients.

        Args:
            message: Message data
        """
        if not self.active_connections:
            return

        # Add timestamp if not present
        if "timestamp" not in message:
            message["timestamp"] = datetime.now(UTC).isoformat()

        logger.debug(
            "websocket_broadcasting",
            type=message.get("type"),
            clients=len(self.active_connections),
        )

        # Send to all clients (remove failed connections)
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error("websocket_broadcast_failed", error=str(e))
                disconnected.append(connection)

        # Clean up disconnected clients
        for connection in disconnected:
            self.disconnect(connection)


# Global WebSocket manager instance
ws_manager = WebSocketManager()


async def websocket_endpoint(websocket: WebSocket) -> None:
    """WebSocket endpoint for real-time communication.

    Args:
        websocket: WebSocket connection
    """
    await ws_manager.connect(websocket)

    try:
        while True:
            # Receive messages from client (optional - currently not used)
            data = await websocket.receive_text()
            logger.debug("websocket_message_received", data=data)

            # Echo back or process command
            try:
                json.loads(data)
                await ws_manager.send_personal_message(
                    {"type": "ack", "message": "Received"},
                    websocket,
                )
            except json.JSONDecodeError:
                logger.warning("websocket_invalid_json", data=data)

    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
        logger.debug("websocket_client_disconnected_normally")
