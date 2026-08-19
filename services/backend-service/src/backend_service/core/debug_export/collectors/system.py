"""System collectors: hardware, power, storage, OS, packages, boot config.

Everything here is a *file read* under the read-only host mounts - no command
runs in this module. That is the whole point: the export must not add an
execution path to a container that can reach the host (docs/DebugExport.md 4.3).

The sysfs paths were verified on a Raspberry Pi 4 running Debian 13.
"""

from __future__ import annotations

import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

from backend_service.core.debug_export import hostfiles
from backend_service.core.debug_export.framework import (
    BLOCK_SETTINGS,
    BLOCK_SYSTEM,
    ExportContext,
    register,
)
from backend_service.core.debug_export.redaction import pseudonymize

logger = structlog.get_logger(__name__)

# Packages worth calling out separately - the full list is long, and these are
# the ones a Minabox fault usually hangs on.
RELEVANT_PACKAGE_PREFIXES = (
    "docker",
    "containerd",
    "python3",
    "pipewire",
    "pulseaudio",
    "wireplumber",
    "vlc",
    "bluez",
    "network-manager",
    "firmware-",
    "libcamera",
    "raspi-",
    "alsa-",
    "systemd",
    "libc6",
    "ffmpeg",
    "mosquitto",
)


def _parse_key_values(text: str | None, separator: str = "=") -> dict[str, str]:
    result: dict[str, str] = {}
    if not text:
        return result
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or separator not in line:
            continue
        key, value = line.split(separator, 1)
        result[key.strip()] = value.strip().strip('"')
    return result


@register("system.hardware", BLOCK_SYSTEM, timeout=10.0)
def collect_hardware(ctx: ExportContext) -> dict[str, Any]:
    """Board model, CPU, RAM and - most valuable of all - the SD card's age."""
    cpuinfo = hostfiles.read_text("/proc/cpuinfo", max_bytes=64 * 1024) or ""
    fields = _parse_key_values(cpuinfo, separator=":")

    cpu_count = len(re.findall(r"^processor\s*:", cpuinfo, flags=re.MULTILINE)) or None
    meminfo = _parse_key_values(
        hostfiles.read_text("/proc/meminfo") or "", separator=":"
    )

    def _mb(key: str) -> int | None:
        raw = meminfo.get(key, "").split()
        return int(raw[0]) // 1024 if raw and raw[0].isdigit() else None

    data: dict[str, Any] = {
        "model": hostfiles.read_stripped("/sys/firmware/devicetree/base/model"),
        "revision_code": fields.get("Revision"),
        # The serial identifies the device; hashing keeps "same box as last
        # time" answerable without handing out the identifier itself.
        "serial_pseudonym": pseudonymize(fields.get("Serial"), ctx.salt),
        "cpu": {
            "model": fields.get("model name") or fields.get("Hardware"),
            "cores": cpu_count,
            "current_khz": hostfiles.read_int(
                "/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq"
            ),
            "max_khz": hostfiles.read_int(
                "/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq"
            ),
        },
        "memory": {
            "total_mb": _mb("MemTotal"),
            "available_mb": _mb("MemAvailable"),
            "swap_total_mb": _mb("SwapTotal"),
            "swap_free_mb": _mb("SwapFree"),
        },
        "sd_card": _sd_card(ctx),
        "bootloader_version": hostfiles.read_stripped(
            "/sys/firmware/devicetree/base/chosen/bootloader/version"
        ),
    }
    return {"system/hardware.json": data}


def _sd_card(ctx: ExportContext) -> dict[str, Any]:
    """SD card identity and age. Worn-out cards are the most common hardware fault."""
    base = "/sys/block/mmcblk0/device"
    card: dict[str, Any] = {
        "name": hostfiles.read_stripped(f"{base}/name"),
        "manufacturer_id": hostfiles.read_stripped(f"{base}/manfid"),
        "oem_id": hostfiles.read_stripped(f"{base}/oemid"),
        "manufactured": hostfiles.read_stripped(f"{base}/date"),
        "firmware_revision": hostfiles.read_stripped(f"{base}/fwrev"),
        "hardware_revision": hostfiles.read_stripped(f"{base}/hwrev"),
        "serial_pseudonym": pseudonymize(
            hostfiles.read_stripped(f"{base}/serial"), ctx.salt
        ),
    }
    manufactured = card.get("manufactured")
    if manufactured and "/" in str(manufactured):
        try:
            month, year = str(manufactured).split("/", 1)
            age_months = (datetime.now(UTC).year - int(year)) * 12 + (
                datetime.now(UTC).month - int(month)
            )
            card["age_months"] = max(age_months, 0)
        except (ValueError, TypeError):
            pass
    return card


@register("system.power", BLOCK_SYSTEM, timeout=10.0)
def collect_power(ctx: ExportContext) -> dict[str, Any]:
    """Under-voltage and temperature.

    Read from the rpi_volt hwmon driver rather than vcgencmd: /dev/vcio is not
    assigned to the container and we deliberately keep it that way (4.3). The
    trade-off is that this is the *current* state - the "since boot" bits live
    in the kernel log, which the log collector picks up.
    """
    undervoltage: bool | None = None
    hwmon_name: str | None = None
    for entry in hostfiles.list_dir("/sys/class/hwmon"):
        rel = f"/sys/class/hwmon/{entry.name}"
        name = hostfiles.read_stripped(f"{rel}/name")
        if name == "rpi_volt":
            hwmon_name = name
            alarm = hostfiles.read_int(f"{rel}/in0_lcrit_alarm")
            undervoltage = bool(alarm) if alarm is not None else None
            break

    temp_raw = hostfiles.read_int("/sys/class/thermal/thermal_zone0/temp")
    current_khz = hostfiles.read_int(
        "/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq"
    )
    max_khz = hostfiles.read_int(
        "/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq"
    )

    data = {
        "undervoltage_now": undervoltage,
        "undervoltage_source": hwmon_name or "nicht verfügbar",
        "temperature_celsius": round(temp_raw / 1000, 1) if temp_raw else None,
        "cpu_current_khz": current_khz,
        "cpu_max_khz": max_khz,
        "cpu_at_max": (
            None if not (current_khz and max_khz) else current_khz >= max_khz * 0.95
        ),
        "hinweis": (
            "undervoltage_now stammt aus dem rpi_volt-Treiber und beschreibt den "
            "Moment der Messung. Die Historie steht im Kernel-Log."
        ),
    }
    return {"system/power.json": data}


@register("system.storage", BLOCK_SYSTEM, timeout=15.0)
def collect_storage(ctx: ExportContext) -> dict[str, Any]:
    """Free space, inodes and read-only remounts.

    Two failure modes hide here that a plain "disk 52% full" misses: exhausted
    inodes, and a root filesystem that a dying SD card remounted read-only.

    The mount table is read from /proc/1/mounts, not /proc/mounts: the latter
    resolves via /proc/self and would describe *this container's* overlay view
    instead of the host - which is how an early version reported the backend's
    own read-only bind mounts as a failing SD card.
    """
    mounts_raw = (
        hostfiles.read_text("/proc/1/mounts", max_bytes=256 * 1024)
        or hostfiles.read_text("/proc/mounts", max_bytes=256 * 1024)
        or ""
    )
    virtual_fs = {
        "proc",
        "sysfs",
        "cgroup",
        "cgroup2",
        "devpts",
        "securityfs",
        "debugfs",
        "tracefs",
        "pstore",
        "bpf",
        "fusectl",
        "configfs",
        "mqueue",
        "hugetlbfs",
        "autofs",
        "nsfs",
        "binfmt_misc",
        "overlay",
        "devtmpfs",
        "ramfs",
    }

    filesystems: list[dict[str, Any]] = []
    readonly: list[str] = []
    for line in mounts_raw.splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        device, mountpoint, fstype, options = parts[0], parts[1], parts[2], parts[3]
        # /run holds systemd's credential and lock mounts: always tmpfs, always
        # read-only, and pure noise in a read-only-filesystem check.
        if fstype in virtual_fs or mountpoint.startswith(
            ("/proc", "/sys", "/dev", "/run")
        ):
            continue
        option_list = options.split(",")
        entry: dict[str, Any] = {
            "device": device,
            "mountpoint": mountpoint,
            "fstype": fstype,
            "readonly": "ro" in option_list,
        }
        if entry["readonly"] and fstype not in ("squashfs", "iso9660", "vfat", "tmpfs"):
            readonly.append(mountpoint)
        filesystems.append(entry)

    # Usage numbers only for paths this container can actually stat. The host
    # root is covered by the Host-Helper's /host-status, and /data sits on the
    # same SD card partition, so the card's fill level is still measured.
    usage: list[dict[str, Any]] = []
    for label, target in (
        ("data", Path(os.environ.get("DATA_PATH", "/data"))),
        ("audio", Path(os.environ.get("AUDIO_STORAGE_PATH", "/mnt/audio/tracks"))),
        ("boot", hostfiles.host_path("/boot")),
    ):
        try:
            st = os.statvfs(target)
        except OSError as e:
            usage.append({"label": label, "path": str(target), "error": str(e)})
            continue
        total = st.f_blocks * st.f_frsize
        free = st.f_bavail * st.f_frsize
        entry = {
            "label": label,
            "path": str(target),
            "total_gb": round(total / 1024**3, 2),
            "free_gb": round(free / 1024**3, 2),
            "used_percent": round(100 * (total - free) / total, 1) if total else None,
        }
        if st.f_files:
            entry["inodes_total"] = st.f_files
            entry["inodes_used_percent"] = round(
                100 * (st.f_files - st.f_ffree) / st.f_files, 1
            )
        usage.append(entry)

    data = {
        "usage": usage,
        "mounts": filesystems,
        "readonly_mounts": readonly,
        "hinweis": (
            "usage misst die Pfade, die der Backend-Container erreicht; der Host-"
            "Wurzelspeicher steht in system/host_status.json. readonly_mounts ist "
            "nur harmlos, wenn dort bewusst read-only gemountet wurde - ein "
            "read-only gewordenes / deutet auf eine defekte SD-Karte hin."
        ),
    }
    return {"system/storage.json": data}


@register("system.os", BLOCK_SYSTEM, timeout=10.0)
def collect_os(ctx: ExportContext) -> dict[str, Any]:
    """Distribution, image origin, kernel and architecture."""
    os_release = _parse_key_values(hostfiles.read_text("/etc/os-release"))
    rpi_issue = hostfiles.read_text("/etc/rpi-issue", max_bytes=8192)
    version = hostfiles.read_stripped("/proc/version", max_bytes=1024)
    uptime_raw = hostfiles.read_stripped("/proc/uptime")
    loadavg = hostfiles.read_stripped("/proc/loadavg")

    uptime_seconds = None
    if uptime_raw:
        try:
            uptime_seconds = int(float(uptime_raw.split()[0]))
        except (ValueError, IndexError):
            pass

    data = {
        "distribution": os_release.get("PRETTY_NAME"),
        "version_id": os_release.get("VERSION_ID"),
        "version_codename": os_release.get("VERSION_CODENAME"),
        # Which image was originally flashed - the answer to "works on mine".
        "image": (rpi_issue or "").strip().splitlines()[0] if rpi_issue else None,
        "kernel": version,
        "architecture": os.uname().machine,
        "uptime_seconds": uptime_seconds,
        "loadavg": loadavg,
        "timezone": hostfiles.read_stripped("/etc/timezone"),
        "container_time": datetime.now(UTC).isoformat(),
    }
    return {"system/os.json": data}


@register("system.usb", BLOCK_SYSTEM, timeout=10.0)
def collect_usb(ctx: ExportContext) -> dict[str, Any]:
    """USB inventory from sysfs - lsusb without running lsusb."""
    devices: list[dict[str, Any]] = []
    for entry in hostfiles.list_dir("/sys/bus/usb/devices"):
        rel = f"/sys/bus/usb/devices/{entry.name}"
        vendor = hostfiles.read_stripped(f"{rel}/idVendor")
        product_id = hostfiles.read_stripped(f"{rel}/idProduct")
        if not vendor or not product_id:
            continue
        devices.append(
            {
                "id": f"{vendor}:{product_id}",
                "product": hostfiles.read_stripped(f"{rel}/product"),
                "manufacturer": hostfiles.read_stripped(f"{rel}/manufacturer"),
                "speed_mbps": hostfiles.read_stripped(f"{rel}/speed"),
            }
        )
    return {"system/usb_devices.json": {"devices": devices, "count": len(devices)}}


@register("system.kernel_modules", BLOCK_SYSTEM, timeout=10.0)
def collect_kernel_modules(ctx: ExportContext) -> dict[str, Any]:
    """Loaded modules - shows whether a HAT's driver actually came up."""
    raw = hostfiles.read_text("/proc/modules", max_bytes=256 * 1024)
    if not raw:
        return {}
    modules = []
    for line in raw.splitlines():
        parts = line.split()
        if parts:
            modules.append(parts[0])
    return {
        "system/kernel_modules.json": {
            "count": len(modules),
            "modules": sorted(modules),
        }
    }


@register("system.packages", BLOCK_SETTINGS, timeout=20.0)
def collect_packages(ctx: ExportContext) -> dict[str, Any]:
    """Installed packages, parsed from the dpkg status file.

    Running dpkg-query would mean executing a command on the host; the status
    file carries the same information and stays a plain read.
    """
    raw = hostfiles.read_text("/var/lib/dpkg/status", max_bytes=8 * 1024 * 1024)
    if not raw:
        return {}

    packages: list[tuple[str, str]] = []
    name = version = status = None
    for line in raw.splitlines():
        if line.startswith("Package:"):
            name = line.split(":", 1)[1].strip()
            version = status = None
        elif line.startswith("Version:"):
            version = line.split(":", 1)[1].strip()
        elif line.startswith("Status:"):
            status = line.split(":", 1)[1].strip()
        elif not line.strip() and name:
            if (
                version
                and status
                and "installed" in status
                and "not-installed" not in status
            ):
                packages.append((name, version))
            name = version = status = None
    if (
        name
        and version
        and status
        and "installed" in status
        and "not-installed" not in status
    ):
        packages.append((name, version))

    packages.sort()
    relevant = {
        pkg: ver
        for pkg, ver in packages
        if any(pkg.startswith(prefix) for prefix in RELEVANT_PACKAGE_PREFIXES)
    }
    listing = "\n".join(f"{pkg} {ver}" for pkg, ver in packages)
    return {
        "system/packages.txt": listing,
        "system/packages_relevant.json": {"count": len(packages), "relevant": relevant},
    }


@register("system.apt_history", BLOCK_SETTINGS, timeout=10.0)
def collect_apt_history(ctx: ExportContext) -> dict[str, Any]:
    """Recent apt activity - "it broke yesterday" usually has its cause here."""
    history = hostfiles.read_text("/var/log/apt/history.log", max_bytes=512 * 1024)
    rotated = [
        entry.name
        for entry in hostfiles.list_dir("/var/log/apt")
        if entry.name.startswith("history.log.")
    ]
    if history is None and not rotated:
        return {}
    header = (
        "# /var/log/apt/history.log\n"
        f"# vorhandene ältere Dateien (nicht entpackt): {', '.join(sorted(rotated)) or 'keine'}\n\n"
    )
    return {"system/apt_history.txt": header + (history or "(leer)")}


@register("system.boot_config", BLOCK_SETTINGS, timeout=10.0)
def collect_boot_config(ctx: ExportContext) -> dict[str, Any]:
    """config.txt and cmdline.txt - dtoverlays explain most audio and GPIO faults."""
    files: dict[str, Any] = {}
    config = hostfiles.read_text("/boot/config.txt", max_bytes=128 * 1024)
    cmdline = hostfiles.read_stripped("/boot/cmdline.txt", max_bytes=8192)
    if config:
        active = [
            line.strip()
            for line in config.splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        files["system/boot_config.txt"] = config
        files["system/boot_config_active.json"] = {"lines": active}
    if cmdline:
        files["system/boot_cmdline.txt"] = cmdline
    return files
