"""Host status and the settings the WebUI offers: log, clock, name, LEDs."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from host_helper.api.routes.deps import (
    _check_api_key,
    _host_root,
    _host_tool,
    get_config,
)
from host_helper.config import Config

logger = structlog.get_logger(__name__)

router = APIRouter()


def _read_host_status(cfg: Config) -> dict:
    """Read host status from mounted /host/proc, /host/etc/hostname, etc."""
    out: dict = {
        "hostname": None,
        "ip": cfg.host_ip,
        "uptime_seconds": None,
        "memory": None,
        "cpu": None,
        "disk": None,
        "temperature_celsius": None,
    }
    host_proc = cfg.host_proc
    host_etc_hostname = cfg.host_etc_hostname
    host_root = cfg.host_root

    # Host uptime from /proc/uptime (seconds since boot)
    try:
        uptime_path = Path(host_proc) / "uptime"
        if uptime_path.exists():
            line = uptime_path.read_text(encoding="utf-8", errors="replace").strip()
            if line:
                out["uptime_seconds"] = int(float(line.split()[0]))
    except (OSError, ValueError):
        pass

    # Hostname
    try:
        p = Path(host_etc_hostname)
        if p.exists():
            out["hostname"] = p.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        pass

    # Memory from /proc/meminfo
    try:
        meminfo = Path(host_proc) / "meminfo"
        if meminfo.exists():
            total_kb = available_kb = None
            for line in meminfo.read_text(
                encoding="utf-8", errors="replace"
            ).splitlines():
                if line.startswith("MemTotal:"):
                    total_kb = int(line.split()[1])
                elif line.startswith("MemAvailable:"):
                    available_kb = int(line.split()[1])
                if total_kb is not None and available_kb is not None:
                    break
            if total_kb is not None and total_kb > 0:
                total_mb = total_kb // 1024
                available_mb = (available_kb or 0) // 1024
                used_mb = total_mb - available_mb
                pct = round(100 * used_mb / total_mb) if total_mb else 0
                out["memory"] = {
                    "total_mb": total_mb,
                    "available_mb": available_mb,
                    "percent_used": pct,
                }
    except (OSError, ValueError):
        pass

    # CPU load from /proc/loadavg (1m, 5m, 15m)
    try:
        loadavg = Path(host_proc) / "loadavg"
        if loadavg.exists():
            parts = (
                loadavg.read_text(encoding="utf-8", errors="replace").strip().split()
            )
            load_1m = float(parts[0]) if len(parts) >= 1 else 0.0
            load_5m = float(parts[1]) if len(parts) >= 2 else 0.0
            load_15m = float(parts[2]) if len(parts) >= 3 else 0.0
            out["cpu"] = {
                "load_1m": load_1m,
                "load_5m": load_5m,
                "load_15m": load_15m,
                "percent_used": None,
            }
    except (OSError, ValueError):
        pass

    # Disk from host root mount
    if host_root:
        try:
            st = os.statvfs(host_root)
            total_gb = (st.f_blocks * st.f_frsize) / (1024**3)
            free_gb = (st.f_bfree * st.f_frsize) / (1024**3)
            used_gb = total_gb - free_gb
            pct = round(100 * used_gb / total_gb) if total_gb > 0 else 0
            out["disk"] = {
                "path": host_root,
                "total_gb": round(total_gb, 1),
                "used_gb": round(used_gb, 1),
                "percent_used": pct,
            }
        except OSError:
            pass

    # CPU/SoC temperature (e.g. Raspberry Pi thermal_zone0)
    try:
        if host_root:
            temp_path = (
                Path(host_root) / "sys" / "class" / "thermal" / "thermal_zone0" / "temp"
            )
        else:
            temp_path = Path("/sys/class/thermal/thermal_zone0/temp")
        if temp_path.exists():
            value = temp_path.read_text(encoding="utf-8", errors="replace").strip()
            if value:
                out["temperature_celsius"] = round(int(value) / 1000, 1)
    except (OSError, ValueError):
        pass

    return out


@router.get("/host-status")
def host_status(_: None = Depends(_check_api_key)) -> dict:
    """Return host info (hostname, IP, memory, CPU, disk) from mounted host paths."""
    cfg = get_config()
    return _read_host_status(cfg)


@router.get("/syslog")
def get_syslog(
    n: int = 200,
    source: str = "kernel",  # kernel | docker
    _: None = Depends(_check_api_key),
) -> dict:
    """Return the last N lines of the host kernel or docker unit log.

    The cap is generous on purpose: the debug export filters container-network
    noise out of the kernel log *before* it truncates, so it has to be able to
    ask for a window wide enough to still contain the last boot.
    """
    n = max(1, min(int(n), 20000))
    root_path = _host_root()
    # Run journalctl in host context via chroot so it sees host's journal
    journalctl_path = _host_tool("usr/bin/journalctl")
    if journalctl_path is not None:
        args = [
            "chroot",
            str(root_path),
            "journalctl",
            "-n",
            str(n),
            "--no-pager",
            "-o",
            "short-iso",
        ]
        if source == "docker":
            args.extend(["-u", "docker"])
        else:
            args.extend(["-k"])
        try:
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=15,
            )
            out = (result.stdout or "") + (result.stderr or "")
            lines = [s for s in out.strip().splitlines() if s.strip()]
            return {"lines": lines[-n:], "source": source}
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
            logger.warning("syslog_journalctl_failed", error=str(e))
    # Fallback: read host /var/log/syslog or kern.log
    log_paths = [
        root_path / "var/log/syslog",
        root_path / "var/log/kern.log",
    ]
    lines_list: list[str] = []
    for lp in log_paths:
        if lp.exists() and lp.is_file():
            try:
                content = lp.read_text(encoding="utf-8", errors="replace")
                lines_list = content.strip().splitlines()[-n:]
                break
            except OSError:
                continue
    return {"lines": lines_list, "source": source}


# ── Timezone & Time ───────────────────────────────────────────────────────


class TimezoneBody(BaseModel):
    timezone: str


@router.put("/system/timezone")
def set_timezone(
    body: TimezoneBody,
    _: None = Depends(_check_api_key),
) -> dict:
    """Set host timezone (e.g. Europe/Berlin). Runs timedatectl via chroot."""
    tz = (body.timezone or "").strip()
    if not tz or ".." in tz or "/" not in tz:
        raise HTTPException(status_code=400, detail="Invalid timezone")
    root_path = _host_root()
    timedatectl_path = root_path / "usr/bin/timedatectl"
    if not timedatectl_path.exists():
        raise HTTPException(status_code=503, detail="timedatectl not found on host")
    try:
        result = subprocess.run(
            ["chroot", str(root_path), "timedatectl", "set-timezone", tz],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            raise HTTPException(
                status_code=400,
                detail=(result.stderr or result.stdout or "Failed to set timezone")[
                    :500
                ],
            )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        logger.warning("set_timezone_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to set timezone") from e
    logger.info("timezone_set", timezone=tz)
    return {"ok": True, "timezone": tz}


@router.get("/system/time-status")
def get_time_status(_: None = Depends(_check_api_key)) -> dict:
    """Return host timezone, NTP sync status, and local time."""
    root_path = _host_root()
    timedatectl_path = root_path / "usr/bin/timedatectl"
    out = {"timezone": None, "ntp_sync": False, "local_time": None}
    if not timedatectl_path.exists():
        return out
    try:
        result = subprocess.run(
            ["chroot", str(root_path), "timedatectl", "status"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        text = (result.stdout or "") + (result.stderr or "")
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("Time zone:"):
                out["timezone"] = line.split(":", 1)[1].strip()
            elif "synchronized: yes" in line.lower():
                out["ntp_sync"] = True
            elif line.startswith("Local time:"):
                out["local_time"] = line.split(":", 1)[1].strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return out


# ── Hostname ───────────────────────────────────────────────────────────────


class HostnameBody(BaseModel):
    hostname: str


def _read_hostname(cfg: Config) -> str | None:
    """Read current hostname from /host/etc/hostname."""
    path = cfg.host_etc_hostname
    if not path.exists():
        return None
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None


@router.get("/system/hostname")
def get_hostname(_: None = Depends(_check_api_key)) -> dict:
    """Return current hostname."""
    cfg = get_config()
    return {"hostname": _read_hostname(cfg)}


@router.put("/system/hostname")
def set_hostname(
    body: HostnameBody,
    _: None = Depends(_check_api_key),
) -> dict:
    """Set host hostname and update /etc/hosts. Requires hostnamectl on host."""
    name = (body.hostname or "").strip().lower()
    if not name or len(name) > 63:
        raise HTTPException(status_code=400, detail="Hostname must be 1-63 characters")
    if not all(c.isalnum() or c == "-" for c in name):
        raise HTTPException(
            status_code=400, detail="Hostname may only contain a-z, 0-9, hyphen"
        )
    root_path = _host_root()
    hostnamectl = _host_tool("usr/bin/hostnamectl")
    if hostnamectl is None:
        raise HTTPException(status_code=503, detail="hostnamectl not found on host")
    old_name = _read_hostname(get_config())
    try:
        r = subprocess.run(
            ["chroot", str(root_path), "hostnamectl", "set-hostname", name],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if r.returncode != 0:
            raise HTTPException(
                status_code=400, detail=(r.stderr or r.stdout or "Failed")[:500]
            )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        logger.warning("set_hostname_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to set hostname") from e
    hosts_file = root_path / "etc/hosts"
    if hosts_file.exists():
        try:
            content = hosts_file.read_text(encoding="utf-8", errors="replace")
            lines = content.splitlines()
            new_lines = []
            replaced = False
            for line in lines:
                parts = line.split()
                if (
                    len(parts) >= 2
                    and parts[0] == "127.0.1.1"
                    and old_name
                    and parts[1] == old_name
                ):
                    new_lines.append("127.0.1.1\t" + name)
                    replaced = True
                else:
                    new_lines.append(line)
            if not replaced:
                new_lines.append("127.0.1.1\t" + name)
            hosts_file.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        except OSError as e:
            logger.warning("hosts_file_update_failed", error=str(e))
    logger.info("hostname_set", hostname=name)
    return {"ok": True, "hostname": name}


# ── Board LEDs (Stealth) ───────────────────────────────────────────────────


def _boot_config_path(root_path: Path) -> Path | None:
    """Return host boot config.txt path for persistent LED/stealth settings."""
    for name in ("boot/firmware/config.txt", "boot/config.txt"):
        p = root_path / name
        if p.exists():
            return p
    return None


def _set_stealth_persistent(root_path: Path, stealth: bool) -> None:
    """Persist the LED triggers in config.txt so stealth survives a reboot."""
    config_path = _boot_config_path(root_path)
    if not config_path:
        return
    try:
        content = config_path.read_text(encoding="utf-8", errors="replace")
        lines = content.splitlines()
        new_lines: list[str] = []
        seen_act = False
        seen_pwr = False
        act_none = "dtparam=act_led_trigger=none"
        pwr_none = "dtparam=pwr_led_trigger=none"
        for line in lines:
            stripped = line.strip()
            if "act_led_trigger" in stripped:
                seen_act = True
                new_lines.append(act_none if stealth else "# " + act_none)
                continue
            if "pwr_led_trigger" in stripped:
                seen_pwr = True
                new_lines.append(pwr_none if stealth else "# " + pwr_none)
                continue
            new_lines.append(line)
        if stealth:
            if not seen_act:
                new_lines.append(act_none)
            if not seen_pwr:
                new_lines.append(pwr_none)
        config_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    except OSError as e:
        logger.warning("board_leds_config_txt_failed", error=str(e))


def _board_led_paths(root_path: Path) -> tuple[Path | None, Path | None]:
    """The (power, activity) brightness paths. Tries PWR/ACT, then led0/led1."""
    sys_leds = root_path / "sys/class/leds"
    if not sys_leds.exists():
        return (None, None)
    power = activity = None
    for name in ("led1", "PWR", "ACT", "led0"):
        p = sys_leds / name / "brightness"
        if p.exists():
            if name in ("led1", "PWR"):
                power = p
            else:
                activity = p
            if power is not None and activity is not None:
                break
    if power is None and activity is None:
        for d in sys_leds.iterdir():
            if d.is_dir():
                b = d / "brightness"
                if b.exists():
                    if activity is None:
                        activity = b
                    else:
                        power = b
                    break
    return (power, activity)


@router.get("/system/board-leds")
def get_board_leds(_: None = Depends(_check_api_key)) -> dict:
    """Return current board LED state (stealth on/off)."""
    root_path = _host_root()
    power_path, activity_path = _board_led_paths(root_path)
    out = {"stealth": False, "power_led": "on", "activity_led": "on"}
    try:
        if power_path and power_path.exists():
            v = power_path.read_text(encoding="utf-8").strip()
            out["power_led"] = "off" if v == "0" else "on"
        if activity_path and activity_path.exists():
            v = activity_path.read_text(encoding="utf-8").strip()
            out["activity_led"] = "off" if v == "0" else "on"
        out["stealth"] = out["power_led"] == "off" and out["activity_led"] == "off"
    except OSError:
        pass
    return out


class BoardLedsBody(BaseModel):
    stealth: bool


@router.put("/system/board-leds")
def set_board_leds(
    body: BoardLedsBody,
    _: None = Depends(_check_api_key),
) -> dict:
    """Switch the board LEDs on or off (stealth mode).

    Written twice: to sysfs for the immediate effect, and to config.txt so it
    survives a reboot.
    """
    root_path = _host_root()
    power_path, activity_path = _board_led_paths(root_path)
    val = "0" if body.stealth else "1"
    try:
        for p in (power_path, activity_path):
            if p and p.exists():
                p.write_text(val, encoding="utf-8")
    except OSError as e:
        logger.warning("board_leds_write_failed", error=str(e))
        raise HTTPException(
            status_code=500, detail="Cannot write to LED brightness"
        ) from e
    _set_stealth_persistent(root_path, body.stealth)
    logger.info("board_leds_set", stealth=body.stealth)
    return {"ok": True, "stealth": body.stealth}
