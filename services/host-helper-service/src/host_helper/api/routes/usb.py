"""USB storage: listing, browsing, importing, ejecting."""

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
    get_config,
)

logger = structlog.get_logger(__name__)

router = APIRouter()


# ── USB ───────────────────────────────────────────────────────────────────


def _run_lsblk() -> list[dict]:
    """Run lsblk on host (chroot) and return list of block devices (USB-relevant)."""
    root_path = _host_root()
    lsblk_path = _host_tool("usr/bin/lsblk")
    if lsblk_path is None:
        return []
    try:
        r = subprocess.run(
            [
                "chroot",
                str(root_path),
                "lsblk",
                "-J",
                "-o",
                "NAME,SIZE,FSTYPE,MOUNTPOINT,LABEL,TRAN",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []
    if r.returncode != 0:
        return []
    try:
        import json as _json

        data = _json.loads(r.stdout or "{}")
        blockdevices = data.get("blockdevices") or []
    except (ValueError, TypeError):
        return []
    out: list[dict] = []

    def add_dev(dev: dict) -> None:
        name = dev.get("name") or ""
        if not name or name.startswith("loop"):
            return
        children = dev.get("children") or []
        # With partitions, list those (sda1) rather than the raw disk (sda).
        if children:
            for child in children:
                add_dev(child)
            return
        size = dev.get("size") or ""
        fstype = dev.get("fstype") or ""
        mountpoint = dev.get("mountpoint") or ""
        label = dev.get("label") or ""
        out.append(
            {
                "id": name,
                "device": f"/dev/{name}",
                "size": size,
                "fstype": fstype,
                "mountpoint": mountpoint if mountpoint else None,
                "label": label or None,
            }
        )

    for dev in blockdevices:
        if (dev.get("tran") or "").strip().lower() == "usb":
            add_dev(dev)
    return out


@router.get("/usb/devices")
def usb_devices(_: None = Depends(_check_api_key)) -> dict:
    """List USB (and other removable) block devices."""
    devices = _run_lsblk()
    return {"devices": devices}


def _validate_device_id(device_id: str) -> str:
    """A bare block device name such as sda1. Raises HTTPException otherwise.

    The three USB routes each carried their own version of this check and only
    one of them rejected a slash, so the same value was accepted in one place
    and refused in another. The name ends up in /dev/<id>, so it has to be a
    name and nothing else.
    """
    name = (device_id or "").strip()
    if not name or len(name) > 32 or not all(c.isalnum() for c in name):
        raise HTTPException(status_code=400, detail="Invalid device_id")
    return name


def _ignore_symlinks(directory: str, names: list[str]) -> set[str]:
    """copytree filter: never follow a link off the stick.

    The requested names are checked, but their targets come from the device. A
    prepared stick with '../../../etc/shadow' behind a symlink would otherwise
    have its content copied into the audio directory, because the stick is
    mounted under /host and the link resolves against the host tree.
    """
    base = Path(directory)
    return {name for name in names if (base / name).is_symlink()}


class UsbImportBody(BaseModel):
    device_id: str
    source_paths: list[str]


class UsbEjectBody(BaseModel):
    device_id: str


@router.get("/usb/{device_id}/files")
def usb_files(
    device_id: str,
    _: None = Depends(_check_api_key),
) -> dict:
    """List files/dirs on a mounted USB device. device_id e.g. sda1."""
    device_id = _validate_device_id(device_id)
    root_path = _host_root()
    devices = _run_lsblk()
    dev = next((d for d in devices if d.get("id") == device_id), None)
    if not dev:
        raise HTTPException(status_code=404, detail="Device not found")
    mountpoint = dev.get("mountpoint")
    if not mountpoint:
        # Try to mount
        udisks = root_path / "usr/bin/udisksctl"
        if udisks.exists():
            r = subprocess.run(
                [
                    "chroot",
                    str(root_path),
                    "udisksctl",
                    "mount",
                    "-b",
                    f"/dev/{device_id}",
                ],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if r.returncode == 0:
                for line in (r.stdout or "").splitlines():
                    if "mounted at" in line:
                        mountpoint = (
                            line.split("mounted at", 1)[1].strip().rstrip(".").strip()
                        )
                        break
            devices = _run_lsblk()
            dev = next((d for d in devices if d.get("id") == device_id), None)
            mountpoint = dev.get("mountpoint") if dev else None
    if not mountpoint:
        raise HTTPException(status_code=400, detail="Device not mounted")
    base = (
        Path(mountpoint)
        if not str(mountpoint).startswith("/")
        else root_path / mountpoint.lstrip("/")
    )
    if not base.exists():
        base = Path(mountpoint)
    entries: list[dict] = []
    try:
        for p in sorted(base.iterdir()):
            rel = p.name
            entries.append(
                {
                    "path": rel,
                    "name": rel,
                    "type": "dir" if p.is_dir() else "file",
                }
            )
    except OSError as e:
        raise HTTPException(status_code=502, detail="Cannot list directory") from e
    return {"path": str(base), "entries": entries}


@router.post("/usb/import")
def usb_import(
    body: UsbImportBody,
    _: None = Depends(_check_api_key),
) -> dict:
    """Copy selected paths from USB to AUDIO_STORAGE_PATH."""
    device_id = _validate_device_id(body.device_id)
    cfg = get_config()
    dest_base = cfg.audio_storage_path.resolve()
    root_path = _host_root()
    devices = _run_lsblk()
    dev = next((d for d in devices if d.get("id") == device_id), None)
    if not dev:
        raise HTTPException(status_code=404, detail="Device not found")
    mountpoint = dev.get("mountpoint")
    if not mountpoint:
        raise HTTPException(status_code=400, detail="Device not mounted")
    base = (
        root_path / mountpoint.lstrip("/")
        if mountpoint.startswith("/")
        else Path(mountpoint)
    )
    if not base.exists():
        base = Path(mountpoint)
    base_resolved = base.resolve()
    count = 0
    skipped = 0
    for rel in body.source_paths or []:
        if not rel or ".." in rel or rel.startswith("/"):
            skipped += 1
            continue
        src = base / rel
        # Resolve before use and require the result to still sit on the stick.
        # is_symlink() alone would miss a link somewhere along the path.
        try:
            src = src.resolve()
            src.relative_to(base_resolved)
        except (OSError, ValueError):
            logger.warning("usb_import_outside_device", entry=rel)
            skipped += 1
            continue
        if not src.exists():
            skipped += 1
            continue
        dst = dest_base / Path(rel).name
        try:
            if src.is_dir():
                shutil.copytree(src, dst, dirs_exist_ok=True, ignore=_ignore_symlinks)
                count += sum(
                    1 for f in src.rglob("*") if f.is_file() and not f.is_symlink()
                )
            else:
                shutil.copy2(src, dst)
                count += 1
        except OSError as e:
            logger.warning("usb_import_copy_failed", src=str(src), error=str(e))
            skipped += 1
    logger.info(
        "usb_import_done", device=device_id, files_copied=count, skipped=skipped
    )
    return {"ok": True, "files_copied": count, "skipped": skipped}


@router.post("/usb/eject")
def usb_eject(
    body: UsbEjectBody,
    _: None = Depends(_check_api_key),
) -> dict:
    """Unmount and power-off USB device."""
    device_id = _validate_device_id(body.device_id)
    root_path = _host_root()
    udisks = root_path / "usr/bin/udisksctl"
    if not udisks.exists():
        raise HTTPException(status_code=503, detail="udisksctl not found on host")
    r = subprocess.run(
        ["chroot", str(root_path), "udisksctl", "unmount", "-b", f"/dev/{device_id}"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    if r.returncode != 0 and "not mounted" not in (r.stderr or "").lower():
        raise HTTPException(
            status_code=502, detail=(r.stderr or r.stdout or "Unmount failed")[:500]
        )
    subprocess.run(
        ["chroot", str(root_path), "udisksctl", "power-off", "-b", f"/dev/{device_id}"],
        capture_output=True,
        timeout=10,
    )
    return {"ok": True, "message": "Ejected"}
