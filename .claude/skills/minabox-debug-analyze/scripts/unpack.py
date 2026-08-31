#!/usr/bin/env python3
"""Unpack and validate a Minabox debug export.

The archive comes from a user's device, so it is treated as hostile input:

* every member path is normalised and must stay inside the target directory
  (zip-slip), absolute paths and ".." are rejected,
* the member count and the *uncompressed* total are capped (zip bomb),
* nothing from the archive is executed, and no network access happens here.

Usage:
    python3 unpack.py <archive.zip> [--into DIR] [--quiet]

Prints an overview of the manifest and the path of the unpacked directory.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import zipfile
from pathlib import Path

MAX_MEMBERS = 2000
MAX_TOTAL_UNCOMPRESSED = 256 * 1024 * 1024
MAX_SINGLE_FILE = 64 * 1024 * 1024
SUPPORTED_SCHEMA_VERSIONS = (1,)


def safe_members(archive: zipfile.ZipFile, target: Path) -> list[zipfile.ZipInfo]:
    """Return the members that are safe to extract, or raise."""
    infos = archive.infolist()
    if len(infos) > MAX_MEMBERS:
        raise ValueError(f"archive has {len(infos)} entries (limit {MAX_MEMBERS})")

    total = 0
    safe: list[zipfile.ZipInfo] = []
    resolved_target = target.resolve()
    for info in infos:
        name = info.filename
        if info.is_dir():
            continue
        if name.startswith("/") or ".." in Path(name).parts:
            raise ValueError(f"unsafe path in the archive: {name}")
        destination = (resolved_target / name).resolve()
        if resolved_target not in destination.parents:
            raise ValueError(f"path points outside the target directory: {name}")
        if info.file_size > MAX_SINGLE_FILE:
            raise ValueError(f"file too large: {name} ({info.file_size} bytes)")
        total += info.file_size
        if total > MAX_TOTAL_UNCOMPRESSED:
            raise ValueError("uncompressed total exceeds the limit")
        safe.append(info)
    return safe


def unpack(archive_path: Path, into: Path | None) -> Path:
    target = into or Path(tempfile.mkdtemp(prefix="minabox-debug-"))
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path) as archive:
        members = safe_members(archive, target)
        for info in members:
            archive.extract(info, target)
    return target


def summarize(root: Path, quiet: bool = False) -> dict:
    manifest_path = root / "manifest.json"
    if not manifest_path.exists():
        raise SystemExit("no manifest.json in the archive - is this a Minabox export?")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    version = manifest.get("schema_version")
    if version not in SUPPORTED_SCHEMA_VERSIONS:
        print(
            f"WARNING: schema_version {version} is newer/older than known "
            f"{SUPPORTED_SCHEMA_VERSIONS} - check references/export-schema.md.",
            file=sys.stderr,
        )

    if quiet:
        return manifest

    collectors = manifest.get("collectors", [])
    by_status: dict[str, list[str]] = {}
    for entry in collectors:
        status = entry.get("status", "?")
        by_status.setdefault(status, []).append(entry.get("name", "?"))

    print(f"Directory:     {root}")
    print(f"Device:        {manifest.get('device_id')}")
    print(f"Created:       {manifest.get('created_at')}")
    print(f"Schema:        {manifest.get('schema_version')}")
    options = json.dumps(manifest.get("options", {}), ensure_ascii=False)
    print(f"Options:       {options}")
    print(f"Files:         {len(manifest.get('files', []))}")
    print()
    for status in sorted(by_status):
        names = ", ".join(sorted(by_status[status]))
        print(f"  {status:<16} {names}")

    failed = [c for c in collectors if c.get("status") == "failed"]
    if failed:
        print("\nFailed collectors (a finding in itself):")
        for entry in failed:
            print(f"  - {entry.get('name')}: {entry.get('error')}")

    blocked = manifest.get("secret_tripwire", {}).get("blocked", [])
    if blocked:
        print("\nWARNING: the tripwire removed secrets - a collector bug:")
        for entry in blocked:
            print(
                f"  - {entry.get('path')} ({entry.get('collector')}): "
                f"{entry.get('secrets')}"
            )

    truncations = manifest.get("truncations", [])
    if truncations:
        print(
            f"\n{len(truncations)} file(s) truncated or omitted "
            "(size budget)."
        )

    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--into", type=Path, default=None)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    if not args.archive.exists():
        raise SystemExit(f"file not found: {args.archive}")

    root = unpack(args.archive, args.into)
    summarize(root, quiet=args.quiet)
    if args.quiet:
        print(root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
