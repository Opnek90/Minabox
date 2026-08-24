"""Unit tests for the pure helpers of the host-helper service.

These functions decide which version a box runs after an update, what an
uploaded archive may write, and what a USB stick may hand over. A mistake in
any of them surfaces late - a container on the wrong image, a file where it
does not belong - so each one is pinned down on its own.
"""

from __future__ import annotations

import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from fastapi import HTTPException

# In the container the service runs with src/ on the path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from host_helper.api.routes import backup, deps, diagnostics, update, usb  # noqa: E402

# ── Environment variable names ──────────────────────────────────────────────


@pytest.mark.parametrize(
    ("service", "expected"),
    [
        ("backend", "MINABOX_BACKEND_TAG"),
        ("webui", "MINABOX_WEBUI_TAG"),
        # The hyphen has to become an underscore, otherwise the result is a
        # variable name that no shell and no compose will ever resolve.
        ("host-helper", "MINABOX_HOST_HELPER_TAG"),
        ("media-downloader", "MINABOX_MEDIA_DOWNLOADER_TAG"),
    ],
)
def test_tag_var(service: str, expected: str) -> None:
    assert update._tag_var(service) == expected


# ── Reading and writing .env ────────────────────────────────────────────────


def test_write_env_tags_replaces_and_appends(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "MQTT_BROKER=mqtt\nMINABOX_BACKEND_TAG=0.1.0\nLOG_LEVEL=INFO\n",
        encoding="utf-8",
    )

    update._write_env_tags(env, {"backend": "0.1.4", "webui": "0.1.4"})

    lines = env.read_text(encoding="utf-8").splitlines()
    assert "MINABOX_BACKEND_TAG=0.1.4" in lines
    assert "MINABOX_WEBUI_TAG=0.1.4" in lines
    # One entry per service - otherwise the last line wins and the result
    # depends on the order.
    assert sum(1 for line in lines if line.startswith("MINABOX_BACKEND_TAG=")) == 1
    # Everything else stays untouched.
    assert "MQTT_BROKER=mqtt" in lines
    assert "LOG_LEVEL=INFO" in lines


def test_write_env_tags_creates_missing_file(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    update._write_env_tags(env, {"audio": "0.2.0"})
    assert env.read_text(encoding="utf-8").strip() == "MINABOX_AUDIO_TAG=0.2.0"


def test_read_env_tags_ignores_comments(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(update, "_service_names", lambda: ["backend", "webui"])
    env = tmp_path / ".env"
    env.write_text(
        "#MINABOX_BACKEND_TAG=0.0.1\nMINABOX_WEBUI_TAG=0.1.4\nMINABOX_AUDIO_TAG=9.9.9\n",
        encoding="utf-8",
    )

    tags = update._read_env_tags(env)

    # A commented-out line does not count, and neither does a service that
    # does not exist.
    assert tags == {"webui": "0.1.4"}


# ── Reading progress from the log ───────────────────────────────────────────


def test_parse_update_log_reports_the_last_step() -> None:
    log = "\n".join(
        [
            "=== MINABOX-STEP 1/5 backup",
            "  Backup: data/backups/pre-update-20260821.zip",
            "=== MINABOX-STEP 2/5 repo",
            "=== MINABOX-STEP 3/5 pull",
        ]
    )
    assert update._parse_update_log(log) == {
        "step": 3,
        "step_count": 5,
        "step_key": "pull",
        "exit_code": None,
    }


def test_parse_update_log_reads_the_result() -> None:
    parsed = update._parse_update_log(
        "=== MINABOX-STEP 5/5 verify\n=== MINABOX-DONE 0\n"
    )
    assert parsed["exit_code"] == 0


def test_parse_update_log_reads_a_failure() -> None:
    parsed = update._parse_update_log(
        "=== MINABOX-STEP 3/5 pull\nfailed\n=== MINABOX-DONE 1\n"
    )
    assert parsed["exit_code"] == 1
    assert parsed["step_key"] == "pull"


def test_parse_update_log_of_an_empty_run() -> None:
    """Before the first marker there is no step yet - but no crash either."""
    parsed = update._parse_update_log("")
    assert parsed["step"] is None
    assert parsed["exit_code"] is None


# ── The backup path allowlist ───────────────────────────────────────────────

# This function decides what an uploaded archive may write into the work tree.
# It was untested until the go-live review.


@pytest.mark.parametrize(
    "name",
    [
        "data/minabox.db",
        "data/general_settings.json",
        "data/static/cover.jpg",
        "services/audio-service/state/audio_state.json",
        "services/led-service/config/leds.json",
    ],
)
def test_backup_allowed_path_accepts_the_backup_contents(name: str) -> None:
    assert backup._backup_allowed_path(name, Path("/workspace")) is True


@pytest.mark.parametrize(
    "name",
    [
        "../.env",
        "data/../../etc/shadow",
        "/etc/shadow",
        "docker-compose.yml",
        ".env",
        "services/backend-service/src/backend_service/main.py",
        "services/backend-service/Dockerfile",
        "",
        "   ",
    ],
)
def test_backup_allowed_path_rejects_everything_else(name: str) -> None:
    assert backup._backup_allowed_path(name, Path("/workspace")) is False


def test_backup_allowed_path_rejects_windows_traversal() -> None:
    # Backslashes are normalised to forward slashes; without that,
    # "data\..\..\etc" would slip past the .. check.
    name = "data\\..\\..\\etc\\shadow"
    assert backup._backup_allowed_path(name, Path("/workspace")) is False


# ── The container name allowlist ────────────────────────────────────────────


@pytest.mark.parametrize(
    "name", ["minabox-backend", "minabox-audio", "minabox-host-helper"]
)
def test_container_name_allowlist_accepts_own_containers(name: str) -> None:
    assert diagnostics._is_allowed_container_name(name) is True


@pytest.mark.parametrize(
    "name",
    [
        "",
        "postgres",
        "minabox_backend",
        "minabox-../etc",
        "minabox-a/b",
        "minabox-a\\b",
        "MINABOX-backend",
    ],
)
def test_container_name_allowlist_rejects_the_rest(name: str) -> None:
    assert diagnostics._is_allowed_container_name(name) is False


# ── Validating the uploaded archive ─────────────────────────────────────────


def _zip_with(tmp_path: Path, entries: dict[str, bytes]) -> Path:
    archive = tmp_path / "backup.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        for name, payload in entries.items():
            zf.writestr(name, payload)
    return archive


def test_validate_backup_archive_accepts_a_normal_backup(tmp_path: Path) -> None:
    archive = _zip_with(
        tmp_path, {"data/minabox.db": b"sqlite", "data/static/a.jpg": b"x"}
    )
    backup._validate_backup_archive(archive, Path("/workspace"))


def test_validate_backup_archive_rejects_a_path_outside_the_allowlist(
    tmp_path: Path,
) -> None:
    archive = _zip_with(
        tmp_path, {"data/minabox.db": b"sqlite", "docker-compose.yml": b"x"}
    )
    with pytest.raises(HTTPException) as excinfo:
        backup._validate_backup_archive(archive, Path("/workspace"))
    assert excinfo.value.status_code == 400


def test_validate_backup_archive_rejects_a_zip_bomb(
    tmp_path: Path, monkeypatch
) -> None:
    # A megabyte of zeroes compresses to a few bytes. Without a cap on the
    # unpacked size, a tiny upload takes the Pi down.
    monkeypatch.setattr(backup, "RESTORE_MAX_UNPACKED_BYTES", 1024)
    archive = _zip_with(tmp_path, {"data/minabox.db": b"\0" * (1024 * 1024)})
    with pytest.raises(HTTPException) as excinfo:
        backup._validate_backup_archive(archive, Path("/workspace"))
    assert excinfo.value.status_code == 413


def test_validate_backup_archive_rejects_junk(tmp_path: Path) -> None:
    archive = tmp_path / "backup.zip"
    archive.write_bytes(b"this is not a zip file")
    with pytest.raises(HTTPException) as excinfo:
        backup._validate_backup_archive(archive, Path("/workspace"))
    assert excinfo.value.status_code == 400


# ── Compose on the host ─────────────────────────────────────────────────────


def test_compose_on_others_leaves_the_host_helper_alone(monkeypatch) -> None:
    """Stopping ourselves along with the rest would abort the job in flight."""
    captured: list[list[str]] = []

    def fake_nsenter(args: list[str], timeout: int = 30):
        captured.append(args)
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(deps, "_host_workspace", lambda: "/home/pi/minabox")
    monkeypatch.setattr(deps, "_run_on_host_via_nsenter", fake_nsenter)

    deps._run_compose_on_others(["stop"], timeout=10)

    script = captured[0][-1]
    assert "grep -vx host-helper" in script
    assert "cd /home/pi/minabox" in script
    assert "docker compose stop $others" in script


# ── Device names ────────────────────────────────────────────────────────────


@pytest.mark.parametrize("device_id", ["sda1", "sdb", "nvme0n1p2", "mmcblk0p1"])
def test_device_id_accepts_block_device_names(device_id: str) -> None:
    assert usb._validate_device_id(device_id) == device_id


@pytest.mark.parametrize(
    "device_id",
    ["", "  ", "..", "../../etc", "sda1/../x", "sda 1", "sda;reboot", "-rf", "a" * 33],
)
def test_device_id_rejects_anything_else(device_id: str) -> None:
    # The value ends up in /dev/<id>. All three USB routes check it the same
    # way now - before, only one of them rejected a slash.
    with pytest.raises(HTTPException) as excinfo:
        usb._validate_device_id(device_id)
    assert excinfo.value.status_code == 400


# ── Symlinks on USB import ──────────────────────────────────────────────────


def test_copytree_filter_drops_symlinks(tmp_path: Path) -> None:
    stick = tmp_path / "stick"
    (stick / "album").mkdir(parents=True)
    (stick / "album" / "song.mp3").write_bytes(b"audio")
    (stick / "album" / "secrets").symlink_to(tmp_path / "elsewhere")

    ignored = usb._ignore_symlinks(str(stick / "album"), ["song.mp3", "secrets"])

    assert ignored == {"secrets"}


def test_copytree_filter_keeps_ordinary_files(tmp_path: Path) -> None:
    (tmp_path / "a.mp3").write_bytes(b"x")
    assert usb._ignore_symlinks(str(tmp_path), ["a.mp3"]) == set()


# ── Restore allowlist: only what the backup actually produces ───────────────


@pytest.mark.parametrize(
    "name",
    [
        # Runtime state of this service. The host executes minabox-update.sh
        # as root, so an upload must not be able to write there.
        "data/minabox-update.sh",
        "data/minabox-update.log",
        "data/minabox-update-state.json",
        "data/os-update.pid",
        "data/os-update.log",
        "data/backups/pre-update-20260823.zip",
        "data/static",  # the directory itself, with nothing below it
        "services/audio-service/src/main.py",
        "services/config/x.json",  # not a <name>-service directory
        "services/audio-service/config",  # a directory with no file below it
    ],
)
def test_backup_allowlist_rejects_runtime_state_and_code(name: str) -> None:
    assert backup._backup_allowed_path(name, Path("/workspace")) is False


def test_backup_allowlist_accepts_everything_a_backup_produces(tmp_path: Path) -> None:
    """The allowlist and the backup builder must never drift apart."""
    workspace = tmp_path
    data_path = workspace / "data"
    (data_path / "static" / "covers").mkdir(parents=True)
    (data_path / "minabox.db").write_bytes(b"sqlite")
    (data_path / "general_settings.json").write_text("{}")
    (data_path / "static" / "covers" / "c.png").write_bytes(b"png")
    for rel in (
        "services/audio-service/state/audio_state.json",
        "services/led-service/config/leds.json",
        "services/button-service/config/buttons.json",
        "services/display-service/config/display.json",
    ):
        target = workspace / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("{}")

    produced = [arc for _src, arc in backup._backup_members(workspace, data_path)]

    assert produced  # otherwise this test asserts nothing
    for arcname in produced:
        assert backup._backup_allowed_path(arcname, workspace) is True, arcname
