"""Unit tests for adding and removing the optional components.

The route writes COMPOSE_PROFILES into the .env of a running box and then lets
compose act on it. Both halves are pinned down here: what ends up in the file,
and what the generated script does with the profiles that were switched off -
the one thing compose does *not* do on its own.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

# In the container the service runs with src/ on the path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from host_helper.api.routes import components  # noqa: E402

# ── Reading the choice out of .env ──────────────────────────────────────────


def test_read_profiles_reads_the_line(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("LOG_LEVEL=INFO\nCOMPOSE_PROFILES=led,rfid\n", encoding="utf-8")
    # Always in the order this module lists them, not in the order of the file.
    assert components.read_profiles(env) == ["rfid", "led"]


def test_read_profiles_ignores_whitespace_and_unknown_names(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("COMPOSE_PROFILES= rfid , , bogus ,media\n", encoding="utf-8")
    assert components.read_profiles(env) == ["rfid", "media"]


def test_read_profiles_without_the_line_reads_as_everything(tmp_path: Path) -> None:
    """Fail-open, like the backend: a .env from before the profiles ran it all."""
    env = tmp_path / ".env"
    env.write_text("LOG_LEVEL=INFO\n", encoding="utf-8")
    assert components.read_profiles(env) == list(components.PROFILE_SERVICES)


def test_read_profiles_of_a_missing_file(tmp_path: Path) -> None:
    assert components.read_profiles(tmp_path / ".env") == list(
        components.PROFILE_SERVICES
    )


def test_read_profiles_reads_the_marker_as_nothing(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("COMPOSE_PROFILES=none\n", encoding="utf-8")
    assert components.read_profiles(env) == []


# ── Writing it back ─────────────────────────────────────────────────────────


def test_write_profiles_replaces_the_line_and_leaves_the_rest(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "MQTT_BROKER=mqtt\nCOMPOSE_PROFILES=rfid,led,button\nLOG_LEVEL=INFO\n",
        encoding="utf-8",
    )

    components._write_profiles(env, ["rfid", "media"])

    lines = env.read_text(encoding="utf-8").splitlines()
    assert "COMPOSE_PROFILES=rfid,media" in lines
    # One line, not two - otherwise the last one wins and the result depends on
    # where compose stops reading.
    assert sum(1 for ln in lines if ln.startswith("COMPOSE_PROFILES=")) == 1
    assert "MQTT_BROKER=mqtt" in lines
    assert "LOG_LEVEL=INFO" in lines


def test_write_profiles_appends_when_the_line_is_missing(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("LOG_LEVEL=INFO\n", encoding="utf-8")
    components._write_profiles(env, ["led"])
    assert env.read_text(encoding="utf-8").splitlines()[-1] == "COMPOSE_PROFILES=led"


def test_write_profiles_writes_a_marker_for_nothing_selected(tmp_path: Path) -> None:
    """An empty value would read as "everything" on the next start (fail-open)."""
    env = tmp_path / ".env"
    env.write_text("COMPOSE_PROFILES=rfid\n", encoding="utf-8")

    components._write_profiles(env, [])

    assert "COMPOSE_PROFILES=none" in env.read_text(encoding="utf-8").splitlines()
    assert components.read_profiles(env) == []


# ── The generated script ────────────────────────────────────────────────────


def _script(**kwargs: str) -> str:
    defaults = {
        "log": "/home/pi/minabox/data/minabox-components.log",
        "workspace": "/home/pi/minabox",
        "removed_profiles": "",
        "removed_services": "",
        "added_services": "",
        "blocked_services": "",
        "want_running": "",
        "want_gone": "",
    }
    return components.COMPONENT_SCRIPT.format(**{**defaults, **kwargs})


def test_script_removes_the_containers_of_the_deselected_profiles() -> None:
    # The whole point of the route: without this, a switched-off component
    # keeps running until the next reboot.
    script = _script(
        removed_profiles="led,display",
        removed_services="led display",
        want_gone="led display",
    )
    assert 'OFF="led,display"' in script
    assert 'COMPOSE_PROFILES="$OFF" docker compose rm --stop --force $REMOVED' in script


def test_script_keeps_the_docker_format_placeholder_intact() -> None:
    """The doubled braces are for str.format, not for docker."""
    assert "'{{ .State.Status }}'" in _script(want_running="rfid")


def test_script_asks_docker_about_containers_only() -> None:
    """Without --type container, "docker inspect" also answers about images.

    A leftover "minabox-media-downloader:latest" from an old local build made
    a container that had just been removed look like it was still there, and
    the run reported a failure over it.
    """
    script = _script(want_running="rfid", want_gone="media-downloader")
    assert script.count("docker inspect --type container") == 2
    assert "docker inspect \"minabox-$name\"" not in script


def test_script_writes_the_markers_the_status_route_reads() -> None:
    script = _script()
    for index, key in enumerate(components.COMPONENT_STEPS, start=1):
        assert f"=== MINABOX-STEP {index}/4 {key}" in script
    assert "=== MINABOX-DONE $rc" in script


# ── The route itself ────────────────────────────────────────────────────────


@pytest.fixture
def box(tmp_path: Path, monkeypatch):
    """A box whose .env, host calls and paths all point into tmp_path."""
    env = tmp_path / ".env"
    env.write_text("COMPOSE_PROFILES=rfid,led\n", encoding="utf-8")

    class _Cfg:
        env_file_path = env
        data_path = tmp_path

    calls: list[list[str]] = []

    def fake_host_call(args: list[str], timeout: int = 30):
        calls.append(args)
        import subprocess

        # "is-active" for both units: nothing is running.
        return subprocess.CompletedProcess(args, 0, "inactive", "")

    monkeypatch.setattr(components, "get_config", lambda: _Cfg())
    monkeypatch.setattr(components, "_host_workspace", lambda: str(tmp_path))
    monkeypatch.setattr(components, "_run_on_host_via_nsenter", fake_host_call)
    monkeypatch.setattr(components, "_i2c_present", lambda: True)
    return env, calls


def test_put_components_rejects_an_unknown_component(box) -> None:
    with pytest.raises(HTTPException) as excinfo:
        components.put_components(components.ComponentsBody(profiles=["mixer"]))
    assert excinfo.value.status_code == 400


def test_put_components_does_nothing_when_nothing_changed(box) -> None:
    env, calls = box
    result = components.put_components(
        components.ComponentsBody(profiles=["led", "rfid"])
    )
    # Recreating containers for an unchanged choice would restart the box for
    # nothing.
    assert result["changed"] is False
    assert not any("systemd-run" in a[0] for a in calls)


def test_put_components_writes_the_choice_and_starts_the_run(box) -> None:
    env, calls = box

    result = components.put_components(
        components.ComponentsBody(profiles=["rfid", "media"])
    )

    assert result["changed"] is True
    assert result["profiles"] == ["rfid", "media"]
    assert "COMPOSE_PROFILES=rfid,media" in env.read_text(encoding="utf-8")
    assert any(a[0] == "systemd-run" for a in calls)
    script = (env.parent / "minabox-components.sh").read_text(encoding="utf-8")
    assert 'REMOVED="led"' in script
    assert 'ADDED="media-downloader"' in script


def test_put_components_asks_for_a_reboot_when_i2c_is_still_missing(
    box, monkeypatch
) -> None:
    """Switching the display on needs /dev/i2c-1, and that only appears on boot."""
    env, _calls = box
    # A box that was installed with the LEDs only: I2C was never switched on.
    env.write_text("COMPOSE_PROFILES=led\n", encoding="utf-8")
    monkeypatch.setattr(components, "_i2c_present", lambda: False)
    monkeypatch.setattr(components, "_enable_i2c", lambda: None)

    result = components.put_components(
        components.ComponentsBody(profiles=["rfid", "led", "display"])
    )

    assert result["reboot_required"] is True
    # Both I2C services stay out of this run - starting them against a missing
    # device would fail and take the rest of the run with it.
    assert result["blocked"] == ["rfid", "display"]
    script = (env.parent / "minabox-components.sh").read_text(encoding="utf-8")
    assert 'BLOCKED="rfid display"' in script
    # Only the LED service is expected to be running afterwards.
    assert "for name in led; do" in script
    # The choice is saved even so, so the reboot finishes the job.
    assert "COMPOSE_PROFILES=rfid,led,display" in env.read_text(encoding="utf-8")


def test_put_components_refuses_while_an_update_runs(box, monkeypatch) -> None:
    monkeypatch.setattr(
        components, "_unit_active", lambda unit: unit == components.UPDATE_UNIT
    )
    with pytest.raises(HTTPException) as excinfo:
        components.put_components(components.ComponentsBody(profiles=["rfid"]))
    assert excinfo.value.status_code == 409


def test_status_of_a_box_that_never_changed_anything(box) -> None:
    status = components.get_components_status()
    assert status["running"] is False
    assert status["step"] is None
    assert status["reboot_required"] is False


def test_status_reports_the_finished_run(box) -> None:
    env, _calls = box
    (env.parent / "minabox-components.log").write_text(
        "=== MINABOX-STEP 4/4 verify\n  rfid: running\n=== MINABOX-DONE 0\n",
        encoding="utf-8",
    )
    status = components.get_components_status()
    assert status["exit_code"] == 0
    assert status["step_key"] == "verify"
    assert status["running"] is False
