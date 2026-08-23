"""Tests for the container discovery behind the service overview.

The Docker socket itself is not exercised here - these cover the decisions the
module makes about what it reads: how a container status becomes one of the
three states the UI knows, which fields end up in an entry, and the case that
sent us looking in the first place, a host where per-container memory simply
cannot be measured.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend_service.core import container_registry as cr


def _container(
    name: str = "minabox-audio",
    *,
    status: str = "running",
    health: str | None = "healthy",
    labels: dict[str, str] | None = None,
    image: str = "ghcr.io/opnek90/minabox-audio:1.2.0",
    restart_count: int = 0,
    exit_code: int | None = 0,
    oom_killed: bool = False,
) -> SimpleNamespace:
    """A stand-in for a docker SDK container with the attrs we read."""
    state: dict[str, object] = {"Status": status, "ExitCode": exit_code}
    if health is not None:
        state["Health"] = {"Status": health}
    if oom_killed:
        state["OOMKilled"] = True
    if labels is None:
        labels = {
            cr.SERVICE_LABEL: "audio",
            cr.PROJECT_LABEL: "minabox",
            cr.VERSION_LABEL: "1.2.0",
            cr.REVISION_LABEL: "abc1234",
        }
    return SimpleNamespace(
        name=name,
        # The SDK offers both: .labels as a shortcut and the same values
        # unter attrs["Config"]["Labels"].
        labels=labels,
        attrs={
            "State": state,
            "RestartCount": restart_count,
            "Config": {"Image": image, "Labels": labels},
        },
    )


# ── State mapping ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("status", "health", "expected"),
    [
        ("running", "healthy", "online"),
        ("running", None, "online"),
        # During the start period the container is up and doing the right
        # thing - calling it offline would make every restart look like a
        # failure.
        ("running", "starting", "online"),
        ("running", "unhealthy", "error"),
        ("restarting", None, "error"),
        ("exited", None, "error"),
        ("dead", None, "error"),
        ("created", None, "offline"),
        ("paused", None, "offline"),
    ],
)
def test_map_state(status: str, health: str | None, expected: str) -> None:
    assert cr._map_state(status, health) == expected


# ── Describe ────────────────────────────────────────────────────────────────


def test_describe_reads_version_from_oci_label() -> None:
    entry = cr._describe(_container())
    assert entry["service"] == "audio"
    assert entry["container"] == "minabox-audio"
    assert entry["state"] == "online"
    assert entry["version"] == "1.2.0"
    assert entry["git_sha"] == "abc1234"


def test_describe_falls_back_to_container_name_without_compose_label() -> None:
    """A container started by hand still has a usable service id."""
    entry = cr._describe(_container(name="minabox-led", labels={}))
    assert entry["service"] == "led"
    assert entry["version"] is None


def test_describe_hides_exit_code_while_running() -> None:
    """A zero exit code on a running container is noise, not information."""
    assert "exit_code" not in cr._describe(_container())


def test_describe_reports_exit_code_and_oom_when_stopped() -> None:
    entry = cr._describe(
        _container(status="exited", health=None, exit_code=137, oom_killed=True)
    )
    assert entry["state"] == "error"
    assert entry["exit_code"] == 137
    assert entry["oom_killed"] is True


# ── Stats ───────────────────────────────────────────────────────────────────


def _raw_stats(memory: dict | None) -> dict:
    return {
        "cpu_stats": {
            "cpu_usage": {"total_usage": 2_000_000},
            "system_cpu_usage": 40_000_000,
            "online_cpus": 4,
        },
        "precpu_stats": {
            "cpu_usage": {"total_usage": 1_000_000},
            "system_cpu_usage": 30_000_000,
        },
        "memory_stats": memory if memory is not None else {},
    }


def test_parse_stats_computes_cpu_across_cores() -> None:
    # 1e6 of 10e6 system ticks across 4 cores -> 40 %
    assert cr.parse_stats(_raw_stats(None))["cpu_percent"] == 40.0


def test_parse_stats_reports_memory_without_cgroup_as_unknown() -> None:
    """Raspberry Pi OS ohne cgroup_memory=1 liefert keinen usage-Wert.

    This is exactly where the misleading "0.0 MB" came from: a missing
    reading looked like a measured zero.
    """
    stats = cr.parse_stats(_raw_stats({"stats": {"anon": 0, "file": 0}}))
    assert stats["memory_mb"] is None
    assert stats["memory_percent"] is None
    # The CPU stays measurable - only the memory reading is missing.
    assert stats["cpu_percent"] == 40.0


def test_parse_stats_subtracts_page_cache() -> None:
    stats = cr.parse_stats(
        _raw_stats(
            {
                "usage": 100 * 1024 * 1024,
                "limit": 400 * 1024 * 1024,
                "stats": {"inactive_file": 20 * 1024 * 1024},
            }
        )
    )
    assert stats["memory_mb"] == 80.0
    assert stats["memory_percent"] == 20.0


def test_parse_stats_omits_percentage_without_limit() -> None:
    """Without a memory limit there is no meaningful percentage."""
    stats = cr.parse_stats(
        _raw_stats({"usage": 50 * 1024 * 1024, "limit": 0, "stats": {}})
    )
    assert stats["memory_mb"] == 50.0
    assert stats["memory_percent"] is None


# ── Abgrenzung gegen fremde Container ────────────────────────────────────────
#
# Compose stamps project and service into the *image*. A container started by
# hand from a Minabox image therefore carries those labels too, and would
# otherwise turn up as a second "backend" in the list.


def _labels(**extra: str) -> dict[str, str]:
    base = {cr.PROJECT_LABEL: "minabox", cr.SERVICE_LABEL: "backend"}
    base.update(extra)
    return base


def test_compose_service_recognised() -> None:
    container = _container(labels=_labels(**{cr.CONTAINER_NUMBER_LABEL: "1"}))
    assert cr._is_compose_service(container) is True


def test_hand_started_container_is_not_a_service() -> None:
    """Only the image labels present - nobody started this through Compose."""
    assert cr._is_compose_service(_container(labels=_labels())) is False


def test_oneoff_container_is_not_a_service() -> None:
    """`docker compose run` makes throwaway containers; they do not belong."""
    container = _container(
        labels=_labels(**{cr.CONTAINER_NUMBER_LABEL: "1", cr.ONEOFF_LABEL: "True"})
    )
    assert cr._is_compose_service(container) is False


def test_pick_prefers_the_conventionally_named_container() -> None:
    real = cr._describe(_container(name="minabox-backend", labels=_labels()))
    stray = cr._describe(_container(name="epic_ganguly", labels=_labels()))
    assert cr._pick(stray, real)["container"] == "minabox-backend"
    assert cr._pick(real, stray)["container"] == "minabox-backend"


def test_pick_prefers_a_running_container_when_neither_is_named_normally() -> None:
    stopped = cr._describe(
        _container(name="old_backend", status="exited", health=None, labels=_labels())
    )
    running = cr._describe(_container(name="new_backend", labels=_labels()))
    assert cr._pick(stopped, running)["container"] == "new_backend"
