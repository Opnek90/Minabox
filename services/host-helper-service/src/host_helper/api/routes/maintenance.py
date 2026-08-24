"""Password, SSH, docker prune, factory reset."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from host_helper.api.routes.deps import (
    _check_api_key,
    _host_root,
    _host_tool,
    _nsenter_bin,
    _run_compose_on_others,
    get_config,
)
from host_helper.api.routes.network import (
    HOTSPOT_CONN_ID,
    _run_nmcli_host_network,
)

logger = structlog.get_logger(__name__)

router = APIRouter()


# ── System password (chpasswd in chroot) ──────────────────────────────────


def _default_system_user() -> str:
    return get_config().default_user


class PasswordBody(BaseModel):
    username: str
    new_password: str


@router.post("/system/password")
def set_system_password(
    body: PasswordBody,
    _: None = Depends(_check_api_key),
) -> dict:
    """Change the system password with chpasswd, writing the host /etc/shadow."""
    username = (body.username or "").strip()
    allowed = _default_system_user()
    if username != allowed:
        raise HTTPException(
            status_code=400, detail=f"Only user '{allowed}' can be changed"
        )
    password = (body.new_password or "").strip()
    if len(password) < 8:
        raise HTTPException(
            status_code=400, detail="Password must be at least 8 characters"
        )
    root_path = _host_root()
    chpasswd_path = _host_tool("usr/sbin/chpasswd")
    if chpasswd_path is None:
        raise HTTPException(status_code=503, detail="chpasswd not found on host")
    try:
        proc = subprocess.run(
            ["chroot", str(root_path), "chpasswd"],
            input=f"{username}:{password}\n",
            capture_output=True,
            text=True,
            timeout=10,
        )
        if proc.returncode != 0:
            raise HTTPException(
                status_code=400, detail=(proc.stderr or proc.stdout or "Failed")[:500]
            )
    except (subprocess.TimeoutExpired, OSError) as e:
        logger.warning("set_password_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to set password") from e
    logger.info("password_changed", user=username)
    return {"ok": True, "message": "Password updated"}


# ── Docker prune (on host via nsenter) ───────────────────────────────────────


@router.post("/system/docker-prune")
def docker_prune(_: None = Depends(_check_api_key)) -> dict:
    """Run docker system prune -f on the host. Keeps tagged images and cache."""
    try:
        nsenter_bin = _nsenter_bin()
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=503, detail="nsenter not available (run on host)"
        ) from e
    # With -m we are in the host mount namespace, so this is the host's docker.
    cmd = [
        str(nsenter_bin),
        "-t",
        "1",
        "-n",
        "-m",
        "--",
        "/usr/bin/docker",
        "system",
        "prune",
        "-f",
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
        )
        out = (result.stdout or "") + (result.stderr or "")
        if result.returncode != 0:
            raise HTTPException(status_code=502, detail=(out or "Prune failed")[-1000:])
        lines = [
            ln
            for ln in out.strip().splitlines()
            if "reclaimed" in ln.lower() or "freed" in ln.lower()
        ]
        summary = lines[-1] if lines else out.strip()[-200:] or "Done"
        logger.info("docker_prune_done", summary=summary[:200])
        return {
            "ok": True,
            "message": "Docker cleanup completed",
            "summary": summary[:500],
        }
    except subprocess.TimeoutExpired as e:
        raise HTTPException(status_code=504, detail="Docker prune timed out") from e
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=503, detail="Docker not available on host"
        ) from e


# ── SSH Toggle (systemctl on host; host-helper runs with pid=host) ───────────


def _run_host_systemctl(
    args: list[str], timeout: int = 15
) -> subprocess.CompletedProcess:
    """Run systemctl on the host via chroot. Requires pid=host."""
    host_root = str(_host_root())
    systemctl_path = Path(host_root) / "usr" / "bin" / "systemctl"
    if not systemctl_path.exists():
        systemctl_path = Path(host_root) / "bin" / "systemctl"
    path_in_chroot = (
        ("/" + str(systemctl_path.relative_to(host_root)))
        if systemctl_path.exists()
        else "/usr/bin/systemctl"
    )
    cmd = ["chroot", host_root, path_in_chroot] + args
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


@router.get("/system/ssh-status")
def get_ssh_status(_: None = Depends(_check_api_key)) -> dict:
    """Return whether SSH is enabled and active on the host."""
    out = {"enabled": False, "active": False}
    try:
        r = _run_host_systemctl(["is-enabled", "ssh"], timeout=5)
        r2 = _run_host_systemctl(["is-active", "ssh"], timeout=5)
        enabled_out = (r.stdout or "").strip().lower()
        active_out = (r2.stdout or "").strip().lower()
        out["enabled"] = enabled_out in ("enabled", "enabled-runtime", "indirect")
        out["active"] = active_out in ("active", "activating")
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return out


# systemctl answers in well under a second on the box. The generous cap is for
# a systemd that hangs, and it is deliberately small enough that four chained
# calls cannot occupy a worker thread for minutes on end.
SSH_UNIT_TIMEOUT = 30


class SshToggleBody(BaseModel):
    enable: bool


@router.post("/system/ssh-toggle")
def ssh_toggle(
    body: SshToggleBody,
    _: None = Depends(_check_api_key),
) -> dict:
    """Enable or disable SSH on the host (systemctl enable/disable, start/stop)."""
    try:
        if body.enable:
            for args in (["enable", "ssh"], ["start", "ssh"]):
                r = _run_host_systemctl(args, timeout=SSH_UNIT_TIMEOUT)
                if r.returncode != 0:
                    raise HTTPException(
                        status_code=502, detail=(r.stderr or r.stdout or "Failed")[:500]
                    )
        else:
            # The socket first: otherwise socket activation brings SSH back.
            for unit in ("ssh.socket", "ssh"):
                for args in (["stop", unit], ["disable", unit]):
                    r = _run_host_systemctl(args, timeout=SSH_UNIT_TIMEOUT)
                    if r.returncode != 0 and unit == "ssh":
                        raise HTTPException(
                            status_code=502,
                            detail=(r.stderr or r.stdout or "Failed")[:500],
                        )
        r_en = _run_host_systemctl(["is-enabled", "ssh"], timeout=5)
        r_ac = _run_host_systemctl(["is-active", "ssh"], timeout=5)
        enabled_out = (r_en.stdout or "").strip().lower()
        active_out = (r_ac.stdout or "").strip().lower()
        enabled = enabled_out in ("enabled", "enabled-runtime", "indirect")
        active = active_out in ("active", "activating")
        logger.info("ssh_toggled", enable=body.enable)
        return {"ok": True, "enabled": enabled, "active": active}
    except HTTPException:
        raise
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        logger.warning("ssh_toggle_failed", error=str(e))
        detail = f"Failed to toggle SSH: {e!s}"[:500]
        raise HTTPException(status_code=500, detail=detail) from e


# ── Factory Reset ──────────────────────────────────────────────────────────


class FactoryResetBody(BaseModel):
    delete_audio: bool = False


@router.post("/system/factory-reset")
def factory_reset(
    body: FactoryResetBody | None = None,
    _: None = Depends(_check_api_key),
) -> dict:
    """Reset DB, configs, optionally clear audio; start hotspot; restart containers."""
    cfg = get_config()
    workspace = cfg.workspace_path.resolve()
    data_path = cfg.data_path.resolve()
    audio_storage_path = Path(cfg.audio_storage_path).resolve()
    compose_file = workspace / "docker-compose.yml"

    # 1) Delete DB
    db_file = data_path / "minabox.db"
    if db_file.exists():
        try:
            db_file.unlink()
        except OSError as e:
            logger.warning("factory_reset_db_unlink_failed", error=str(e))

    # 2) Reset general_settings.json
    gs_file = data_path / "general_settings.json"
    try:
        gs_file.parent.mkdir(parents=True, exist_ok=True)
        gs_file.write_text("{}", encoding="utf-8")
    except OSError as e:
        logger.warning("factory_reset_gs_failed", error=str(e))

    # 3) Reset audio_state.json
    audio_state = workspace / "services/audio-service/state/audio_state.json"
    if audio_state.exists() or audio_state.parent.exists():
        try:
            audio_state.parent.mkdir(parents=True, exist_ok=True)
            audio_state.write_text("{}", encoding="utf-8")
        except OSError as e:
            logger.warning("factory_reset_audio_state_failed", error=str(e))

    # 4) Optional: clear audio storage (only if under allowed base)
    if body and body.delete_audio and audio_storage_path.exists():
        allowed_bases = [Path(b).resolve() for b in cfg.allowed_base_paths]
        allowed_bases.append(workspace)
        try:
            for base in allowed_bases:
                try:
                    audio_storage_path.relative_to(base)
                    break
                except ValueError:
                    continue
            else:
                raise ValueError("Audio path not under allowed base")
            for child in list(audio_storage_path.iterdir()):
                try:
                    if child.is_file():
                        child.unlink()
                    else:
                        shutil.rmtree(child, ignore_errors=True)
                except OSError as e:
                    logger.warning(
                        "factory_reset_audio_delete_failed",
                        path=str(child),
                        error=str(e),
                    )
        except (ValueError, OSError) as e:
            logger.warning("factory_reset_audio_clear_skipped", error=str(e))

    # 5) Start hotspot so box is reachable in setup mode
    try:
        _run_nmcli_host_network(["con", "down", HOTSPOT_CONN_ID], timeout=5)
    except Exception:
        pass
    try:
        _run_nmcli_host_network(["con", "delete", HOTSPOT_CONN_ID], timeout=5)
    except Exception:
        pass
    try:
        import secrets

        hotspot_pwd = secrets.token_hex(4)
        _run_nmcli_host_network(
            [
                "con",
                "add",
                "type",
                "wifi",
                "ifname",
                "wlan0",
                "autoconnect",
                "no",
                "con-name",
                HOTSPOT_CONN_ID,
                "ssid",
                "Minabox-Setup",
            ],
            timeout=10,
        )
        _run_nmcli_host_network(
            [
                "con",
                "modify",
                HOTSPOT_CONN_ID,
                "802-11-wireless.mode",
                "ap",
                "ipv4.method",
                "shared",
            ],
            timeout=5,
        )
        _run_nmcli_host_network(
            [
                "con",
                "modify",
                HOTSPOT_CONN_ID,
                "wifi-sec.key-mgmt",
                "wpa-psk",
                "wifi-sec.psk",
                hotspot_pwd,
            ],
            timeout=5,
        )
        _run_nmcli_host_network(["con", "up", HOTSPOT_CONN_ID], timeout=15)
    except (HTTPException, subprocess.TimeoutExpired, OSError) as e:
        logger.warning("factory_reset_hotspot_failed", error=str(e))

    # 6) Restart containers so DB/config are reloaded. Runs on the host and
    #    skips this service: restarting ourselves would cut the reply off.
    if compose_file.exists():
        try:
            result = _run_compose_on_others(["restart"], timeout=180)
            if result.returncode != 0:
                logger.warning(
                    "factory_reset_restart_failed",
                    error=(result.stderr or result.stdout or "").strip()[-500:],
                )
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
            logger.warning("factory_reset_restart_failed", error=str(e))

    logger.info("factory_reset_done", delete_audio=body.delete_audio if body else False)
    return {
        "ok": True,
        "message": "Factory reset complete. Reconnect via hotspot (Minabox-Setup).",
    }
