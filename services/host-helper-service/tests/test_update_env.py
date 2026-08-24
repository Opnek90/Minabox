"""Tests fuer das gezielte Update: Tag-Namen, .env-Schreiben, Log-Auswertung.

Die Funktionen entscheiden, welche Version eine Box nach dem Update faehrt.
Ein Fehler hier faellt erst auf, wenn ein Container mit dem falschen Abbild
startet - deshalb sind sie einzeln abgesichert.
"""

from __future__ import annotations

import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from fastapi import HTTPException

# Der Dienst laeuft im Container mit src/ auf dem Pfad.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from host_helper.api import routes  # noqa: E402


# ── Namen der Umgebungsvariablen ────────────────────────────────────────────


@pytest.mark.parametrize(
    ("service", "expected"),
    [
        ("backend", "MINABOX_BACKEND_TAG"),
        ("webui", "MINABOX_WEBUI_TAG"),
        # Der Bindestrich muss zum Unterstrich werden, sonst entsteht ein
        # Variablenname, den keine Shell und kein Compose je aufloest.
        ("host-helper", "MINABOX_HOST_HELPER_TAG"),
        ("media-downloader", "MINABOX_MEDIA_DOWNLOADER_TAG"),
    ],
)
def test_tag_var(service: str, expected: str) -> None:
    assert routes._tag_var(service) == expected


# ── .env schreiben und lesen ────────────────────────────────────────────────


def test_write_env_tags_replaces_and_appends(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "MQTT_BROKER=mqtt\nMINABOX_BACKEND_TAG=0.1.0\nLOG_LEVEL=INFO\n",
        encoding="utf-8",
    )

    routes._write_env_tags(env, {"backend": "0.1.4", "webui": "0.1.4"})

    lines = env.read_text(encoding="utf-8").splitlines()
    assert "MINABOX_BACKEND_TAG=0.1.4" in lines
    assert "MINABOX_WEBUI_TAG=0.1.4" in lines
    # Nur ein Eintrag je Dienst - sonst gewinnt die letzte Zeile und der
    # Zustand haengt von der Reihenfolge ab.
    assert sum(1 for line in lines if line.startswith("MINABOX_BACKEND_TAG=")) == 1
    # Alles andere bleibt unangetastet.
    assert "MQTT_BROKER=mqtt" in lines
    assert "LOG_LEVEL=INFO" in lines


def test_write_env_tags_creates_missing_file(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    routes._write_env_tags(env, {"audio": "0.2.0"})
    assert env.read_text(encoding="utf-8").strip() == "MINABOX_AUDIO_TAG=0.2.0"


def test_read_env_tags_ignores_comments(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(routes, "_service_names", lambda: ["backend", "webui"])
    env = tmp_path / ".env"
    env.write_text(
        "#MINABOX_BACKEND_TAG=0.0.1\nMINABOX_WEBUI_TAG=0.1.4\nMINABOX_AUDIO_TAG=9.9.9\n",
        encoding="utf-8",
    )

    tags = routes._read_env_tags(env)

    # Auskommentiert zaehlt nicht, und ein Dienst, den es nicht gibt, auch nicht.
    assert tags == {"webui": "0.1.4"}


# ── Fortschritt aus dem Log lesen ───────────────────────────────────────────


def test_parse_update_log_reports_the_last_step() -> None:
    log = "\n".join(
        [
            "=== MINABOX-STEP 1/5 backup",
            "  Sicherung: data/backups/pre-update-20260821.zip",
            "=== MINABOX-STEP 2/5 repo",
            "=== MINABOX-STEP 3/5 pull",
        ]
    )
    assert routes._parse_update_log(log) == {
        "step": 3,
        "step_count": 5,
        "step_key": "pull",
        "exit_code": None,
    }


def test_parse_update_log_reads_the_result() -> None:
    parsed = routes._parse_update_log(
        "=== MINABOX-STEP 5/5 verify\n=== MINABOX-DONE 0\n"
    )
    assert parsed["exit_code"] == 0


def test_parse_update_log_reads_a_failure() -> None:
    parsed = routes._parse_update_log(
        "=== MINABOX-STEP 3/5 pull\nfehler\n=== MINABOX-DONE 1\n"
    )
    assert parsed["exit_code"] == 1
    assert parsed["step_key"] == "pull"


def test_parse_update_log_of_an_empty_run() -> None:
    """Vor dem ersten Marker gibt es noch keinen Schritt - aber auch keinen Absturz."""
    parsed = routes._parse_update_log("")
    assert parsed["step"] is None
    assert parsed["exit_code"] is None


# ── Pfad-Allowlist der Sicherung ────────────────────────────────────────────

# Diese Funktion entscheidet, was ein hochgeladenes Archiv in den Arbeitsbaum
# schreiben darf. Sie war bis zum Go-Live-Review ungetestet.


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
    assert routes._backup_allowed_path(name, Path("/workspace")) is True


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
    assert routes._backup_allowed_path(name, Path("/workspace")) is False


def test_backup_allowed_path_rejects_windows_traversal() -> None:
    # Backslashes werden zu Schraegstrichen normalisiert, sonst rutscht
    # "data\..\..\etc" an der ..-Pruefung vorbei.
    name = "data\\..\\..\\etc\\shadow"
    assert routes._backup_allowed_path(name, Path("/workspace")) is False


# ── Allowlist der Container-Namen ───────────────────────────────────────────


@pytest.mark.parametrize("name", ["minabox-backend", "minabox-audio", "minabox-host-helper"])
def test_container_name_allowlist_accepts_own_containers(name: str) -> None:
    assert routes._is_allowed_container_name(name) is True


@pytest.mark.parametrize(
    "name",
    ["", "postgres", "minabox_backend", "minabox-../etc", "minabox-a/b", "minabox-a\\b", "MINABOX-backend"],
)
def test_container_name_allowlist_rejects_the_rest(name: str) -> None:
    assert routes._is_allowed_container_name(name) is False


# ── Pruefung des hochgeladenen Archivs ──────────────────────────────────────


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
    routes._validate_backup_archive(archive, Path("/workspace"))


def test_validate_backup_archive_rejects_a_path_outside_the_allowlist(
    tmp_path: Path,
) -> None:
    archive = _zip_with(
        tmp_path, {"data/minabox.db": b"sqlite", "docker-compose.yml": b"x"}
    )
    with pytest.raises(HTTPException) as excinfo:
        routes._validate_backup_archive(archive, Path("/workspace"))
    assert excinfo.value.status_code == 400


def test_validate_backup_archive_rejects_a_zip_bomb(
    tmp_path: Path, monkeypatch
) -> None:
    # Ein Megabyte Nullen packt sich auf wenige Bytes. Ohne Obergrenze fuer die
    # entpackte Groesse legt ein winziger Upload den Pi lahm.
    monkeypatch.setattr(routes, "RESTORE_MAX_UNPACKED_BYTES", 1024)
    archive = _zip_with(tmp_path, {"data/minabox.db": b"\0" * (1024 * 1024)})
    with pytest.raises(HTTPException) as excinfo:
        routes._validate_backup_archive(archive, Path("/workspace"))
    assert excinfo.value.status_code == 413


def test_validate_backup_archive_rejects_junk(tmp_path: Path) -> None:
    archive = tmp_path / "backup.zip"
    archive.write_bytes(b"this is not a zip file")
    with pytest.raises(HTTPException) as excinfo:
        routes._validate_backup_archive(archive, Path("/workspace"))
    assert excinfo.value.status_code == 400


# ── Compose auf dem Host ────────────────────────────────────────────────────


def test_compose_on_others_leaves_the_host_helper_alone(monkeypatch) -> None:
    """Sich selbst mitzustoppen wuerde den Vorgang abbrechen, der gerade laeuft."""
    captured: list[list[str]] = []

    def fake_nsenter(args: list[str], timeout: int = 30):
        captured.append(args)
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(routes, "_host_workspace", lambda: "/home/pi/minabox")
    monkeypatch.setattr(routes, "_run_on_host_via_nsenter", fake_nsenter)

    routes._run_compose_on_others(["stop"], timeout=10)

    script = captured[0][-1]
    assert "grep -vx host-helper" in script
    assert "cd /home/pi/minabox" in script
    assert "docker compose stop $others" in script


# ── Geraetenamen ────────────────────────────────────────────────────────────


@pytest.mark.parametrize("device_id", ["sda1", "sdb", "nvme0n1p2", "mmcblk0p1"])
def test_device_id_accepts_block_device_names(device_id: str) -> None:
    assert routes._validate_device_id(device_id) == device_id


@pytest.mark.parametrize(
    "device_id",
    ["", "  ", "..", "../../etc", "sda1/../x", "sda 1", "sda;reboot", "-rf", "a" * 33],
)
def test_device_id_rejects_anything_else(device_id: str) -> None:
    # Der Wert landet in /dev/<id>. Die drei USB-Routen pruefen ihn jetzt
    # gleich - vorher lehnte nur eine von ihnen einen Schraegstrich ab.
    with pytest.raises(HTTPException) as excinfo:
        routes._validate_device_id(device_id)
    assert excinfo.value.status_code == 400


# ── Symlinks beim USB-Import ────────────────────────────────────────────────


def test_copytree_filter_drops_symlinks(tmp_path: Path) -> None:
    stick = tmp_path / "stick"
    (stick / "album").mkdir(parents=True)
    (stick / "album" / "song.mp3").write_bytes(b"audio")
    (stick / "album" / "secrets").symlink_to(tmp_path / "elsewhere")

    ignored = routes._ignore_symlinks(str(stick / "album"), ["song.mp3", "secrets"])

    assert ignored == {"secrets"}


def test_copytree_filter_keeps_ordinary_files(tmp_path: Path) -> None:
    (tmp_path / "a.mp3").write_bytes(b"x")
    assert routes._ignore_symlinks(str(tmp_path), ["a.mp3"]) == set()


# ── Restore-Allowlist: nur das, was die Sicherung auch erzeugt ──────────────


@pytest.mark.parametrize(
    "name",
    [
        # Laufzeitzustand dieses Dienstes. minabox-update.sh fuehrt der Host
        # als root aus - ein Upload darf da nicht hinschreiben duerfen.
        "data/minabox-update.sh",
        "data/minabox-update.log",
        "data/minabox-update-state.json",
        "data/os-update.pid",
        "data/os-update.log",
        "data/backups/pre-update-20260823.zip",
        "data/static",  # das Verzeichnis selbst, ohne Inhalt darunter
        "services/audio-service/src/main.py",
        "services/config/x.json",  # kein <name>-service
        "services/audio-service/config",  # Verzeichnis ohne Datei darunter
    ],
)
def test_backup_allowlist_rejects_runtime_state_and_code(name: str) -> None:
    assert routes._backup_allowed_path(name, Path("/workspace")) is False


def test_backup_allowlist_accepts_everything_a_backup_produces(tmp_path: Path) -> None:
    """Die Allowlist und der Sicherungsbauer duerfen nie auseinanderlaufen."""
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

    produced = [arc for _src, arc in routes._backup_members(workspace, data_path)]

    assert produced  # sonst prueft der Test nichts
    for arcname in produced:
        assert routes._backup_allowed_path(arcname, workspace) is True, arcname
