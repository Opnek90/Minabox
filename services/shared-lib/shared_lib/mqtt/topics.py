from __future__ import annotations


def get_mqtt_topic(device_id: str, domain: str, action: str) -> str:
    """Build MQTT topic for given device, domain, and action.

    Example:
        get_mqtt_topic("box1", "audio", "status")
        -> "minabox/box1/audio/status"
    """
    return f"minabox/{device_id}/{domain}/{action}"

