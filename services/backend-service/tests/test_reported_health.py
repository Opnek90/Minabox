"""A service that calls itself degraded has to reach the service overview.

From docs/services/Offene-Punkte.md 1.2: five services (audio, rfid, button,
display, led) answer /health with a status of their own, and nothing ever
looked at it. The container health check asks only whether the endpoint
answers with 2xx - and a degraded service answers 2xx on purpose, so a lost
broker does not make Docker restart something that is otherwise fine.

The result was a service reporting itself broken and being shown green: the
LED service with not a single usable GPIO pin after a wrong GPIO_GID, or any
service whose MQTT connection had gone while the container kept running.
"""

from __future__ import annotations

import pytest

from backend_service.api import routes_system as rs


def _entry(service: str, state: str = "online") -> dict:
    return {"service": service, "container": f"minabox-{service}", "state": state}


@pytest.fixture
def probe(monkeypatch):
    """Replace the HTTP probe with a lookup, and record who was asked."""
    asked: list[str] = []

    def _install(bodies: dict[str, dict | None]):
        async def _fake(sid, client=None):
            asked.append(sid)
            return bodies.get(sid)

        monkeypatch.setattr(rs, "_check_service_http", _fake)
        return asked

    return _install


@pytest.mark.asyncio
async def test_a_degraded_service_is_no_longer_shown_as_online(probe):
    probe({"led": {"status": "degraded", "gpio_available": False}})
    entries = [_entry("led")]

    await rs._apply_reported_health(entries)

    assert entries[0]["state"] == "degraded"
    assert entries[0]["service_status"] == "degraded"


@pytest.mark.asyncio
async def test_a_healthy_service_stays_online(probe):
    probe({"audio": {"status": "healthy"}})
    entries = [_entry("audio")]

    await rs._apply_reported_health(entries)

    assert entries[0]["state"] == "online"
    assert entries[0]["service_status"] == "healthy"


@pytest.mark.asyncio
async def test_error_outranks_degraded(probe):
    """An unhealthy container is the worse news; a service that still answers
    must not talk the entry back up into a milder state."""
    probe({"rfid": {"status": "degraded"}})
    entries = [_entry("rfid", state="error")]

    await rs._apply_reported_health(entries)

    assert entries[0]["state"] == "error"


@pytest.mark.asyncio
async def test_only_services_that_are_up_get_probed(probe):
    """A container already known to be down has nothing to add and would only
    spend HEALTH_TIMEOUT saying so."""
    asked = probe({})
    entries = [_entry("audio"), _entry("led", state="offline"), _entry("mqtt")]

    await rs._apply_reported_health(entries)

    assert asked == ["audio"], "probed a service that is down, or one with no endpoint"


@pytest.mark.asyncio
async def test_an_unknown_status_word_is_ignored(probe):
    """A typo in one service must not invent a state the UI cannot render."""
    probe({"display": {"status": "weird"}})
    entries = [_entry("display")]

    await rs._apply_reported_health(entries)

    assert entries[0]["state"] == "online"
    assert "service_status" not in entries[0]


@pytest.mark.asyncio
async def test_a_service_that_does_not_answer_keeps_its_docker_state(probe):
    """Docker says the container runs; a probe that times out is not proof of
    the opposite, and the container health check covers that case anyway."""
    probe({"button": None})
    entries = [_entry("button")]

    await rs._apply_reported_health(entries)

    assert entries[0]["state"] == "online"
    assert "service_status" not in entries[0]
