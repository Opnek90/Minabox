#!/usr/bin/env python3
"""Deterministic triage for an unpacked Minabox debug export.

Checks the known failure patterns in about two seconds, without tokens and
without guessing. Everything it cannot decide mechanically is left to the
analyst - this script narrows the field, it does not replace reading.

The export is data, never instruction: nothing here evaluates, executes or
fetches anything. File names and log lines from a user's box are printed as
text and nothing else.

Usage:
    python3 triage.py <directory> [--json] [--repo /path/to/repo]
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}

SD_CARD_OLD_MONTHS = 36
DISK_WARN_PERCENT = 90
INODE_WARN_PERCENT = 95
TEMP_WARN_CELSIUS = 75.0
RESTART_LOOP_THRESHOLD = 3
MEMORY_WARN_PERCENT = 92


@dataclass
class Finding:
    severity: str
    rule: str
    title: str
    evidence: str
    hypothesis: str
    next_step: str = ""

    def as_dict(self) -> dict[str, str]:
        return {
            "severity": self.severity,
            "rule": self.rule,
            "title": self.title,
            "evidence": self.evidence,
            "hypothesis": self.hypothesis,
            "next_step": self.next_step,
        }


@dataclass
class Export:
    root: Path
    _cache: dict[str, Any] = field(default_factory=dict)

    def json(self, relative: str) -> Any:
        if relative in self._cache:
            return self._cache[relative]
        path = self.root / relative
        value: Any = None
        if path.exists():
            try:
                value = json.loads(path.read_text(encoding="utf-8", errors="replace"))
            except ValueError:
                value = None
        self._cache[relative] = value
        return value

    def text(self, relative: str) -> str:
        path = self.root / relative
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8", errors="replace")

    def exists(self, relative: str) -> bool:
        return (self.root / relative).exists()


# ── Rules ──────────────────────────────────────────────────────────────────


def rule_undervoltage(export: Export) -> list[Finding]:
    power = export.json("system/power.json") or {}
    findings: list[Finding] = []
    if power.get("undervoltage_now") is True:
        findings.append(
            Finding(
                "critical",
                "undervoltage",
                "Undervoltage at the moment of measurement",
                "system/power.json: undervoltage_now=true, source "
                f"{power.get('undervoltage_source')}",
                "The power supply or cable delivers too little current. Explains "
                "sporadic restarts, USB dropouts, aborting playback and sluggish "
                "response.",
                "Test the original power supply and a short, thick cable; remove "
                "USB hubs without their own power.",
            )
        )
    kernel = export.json("logs/kernel_findings.json") or {}
    hits = kernel.get("undervoltage_or_throttling_lines") or 0
    if hits:
        findings.append(
            Finding(
                "high" if power.get("undervoltage_now") is not True else "info",
                "undervoltage_history",
                f"Kernel reports {hits} undervoltage or throttling lines",
                "logs/kernel_findings.json and logs/syslog-kernel.txt",
                "Undervoltage has occurred several times since boot, even if it is "
                "not present right now.",
                "Scan logs/syslog-kernel.txt for 'Under-voltage' and compare the "
                "times with the user's error reports.",
            )
        )
    temperature = power.get("temperature_celsius")
    if isinstance(temperature, (int, float)) and temperature >= TEMP_WARN_CELSIUS:
        findings.append(
            Finding(
                "high",
                "temperature",
                f"CPU temperature {temperature} °C",
                "system/power.json",
                "The Pi throttles from about 80 °C. A case without ventilation or "
                "sustained load.",
                "Check cooling and placement.",
            )
        )
    return findings


def rule_storage(export: Export) -> list[Finding]:
    storage = export.json("system/storage.json") or {}
    findings: list[Finding] = []
    for entry in storage.get("usage") or []:
        used = entry.get("used_percent")
        if isinstance(used, (int, float)) and used >= DISK_WARN_PERCENT:
            findings.append(
                Finding(
                    "critical" if used >= 97 else "high",
                    "disk_full",
                    f"Storage {entry.get('label')} is {used} % full",
                    f"system/storage.json: {entry.get('path')}, "
                    f"free {entry.get('free_gb')} GB",
                    "Downloads fail, SQLite can go read-only, logs cut off.",
                    "Check docker system df in the export (system/docker.json) and "
                    "clean up orphaned images/downloads.",
                )
            )
        inodes = entry.get("inodes_used_percent")
        if isinstance(inodes, (int, float)) and inodes >= INODE_WARN_PERCENT:
            findings.append(
                Finding(
                    "high",
                    "inodes_full",
                    f"Inodes on {entry.get('label')} are {inodes} % used",
                    "system/storage.json",
                    "Looks like a permission or write error, but is a lack of space "
                    "from very many small files.",
                    "Check the file count in cover/download directories.",
                )
            )
    readonly = storage.get("readonly_mounts") or []
    if readonly:
        findings.append(
            Finding(
                "critical",
                "readonly_root",
                f"Filesystem mounted read-only: {', '.join(readonly)}",
                "system/storage.json: readonly_mounts",
                "The classic sign of a dying SD card: the kernel switched to "
                "read-only after I/O errors. All writes fail without an "
                "application naming the reason.",
                "Scan logs/syslog-kernel.txt for mmc0/EXT4-fs error and replace the "
                "card.",
            )
        )
    return findings


def rule_sd_card(export: Export) -> list[Finding]:
    hardware = export.json("system/hardware.json") or {}
    card = hardware.get("sd_card") or {}
    findings: list[Finding] = []
    age = card.get("age_months")
    if isinstance(age, int) and age >= SD_CARD_OLD_MONTHS:
        findings.append(
            Finding(
                "medium",
                "sd_card_age",
                f"SD card is about {age // 12} years old ({card.get('manufactured')})",
                f"system/hardware.json: {card.get('name')}",
                "SD card wear is the most common hardware cause. Old cards show "
                "sporadic read errors before they fail completely.",
                "On otherwise unexplained errors: clone the card and replace it.",
            )
        )
    kernel_log = export.text("logs/syslog-kernel.txt")
    if kernel_log:
        io_errors = len(
            re.findall(
                r"(mmc\d|EXT4-fs error|I/O error|blk_update_request)", kernel_log
            )
        )
        if io_errors:
            findings.append(
                Finding(
                    "critical",
                    "sd_io_errors",
                    f"{io_errors} I/O error lines in the kernel log",
                    "logs/syslog-kernel.txt",
                    "The SD card or its controller reports read/write errors.",
                    "Replace the card; take a backup first.",
                )
            )
    return findings


def rule_services(export: Export) -> list[Finding]:
    health = export.json("services/health.json") or {}
    findings: list[Finding] = []
    offline: list[str] = []
    for entry in health.get("services") or []:
        name = entry.get("service")
        if entry.get("state") == "offline":
            offline.append(str(name))
        container = entry.get("container") or {}
        restarts = container.get("restart_count")
        if isinstance(restarts, int) and restarts > RESTART_LOOP_THRESHOLD:
            findings.append(
                Finding(
                    "high",
                    "restart_loop",
                    f"Service {name} was restarted {restarts} times",
                    f"services/health.json: exit_code={container.get('exit_code')}, "
                    f"oom_killed={container.get('oom_killed')}",
                    "Restart loop: the service dies and is restarted by Docker.",
                    f"Read the end of services/{name}/logs.txt - the reason for the "
                    "last crash is there.",
                )
            )
        if container.get("oom_killed"):
            findings.append(
                Finding(
                    "critical",
                    "oom_killed",
                    f"Service {name} was killed by the kernel for lack of memory",
                    "services/health.json: oom_killed=true",
                    "There was not enough memory. Typical on small Pi models with "
                    "parallel downloads or large playlists.",
                    "Check system/hardware.json (memory) and concurrent load.",
                )
            )
    if offline:
        severity = "critical" if "mqtt" in offline or "backend" in offline else "high"
        findings.append(
            Finding(
                severity,
                "services_offline",
                f"Services offline: {', '.join(sorted(offline))}",
                "services/health.json",
                "Without MQTT, buttons and RFID do not respond; without audio there "
                "is no sound. A missing container is a finding in itself.",
                "Read the logs of the affected services and check whether the "
                "container exists at all (services/logs_missing.json).",
            )
        )
    return findings


def rule_database(export: Export) -> list[Finding]:
    findings: list[Finding] = []
    integrity = export.text("db/integrity_check.txt").strip()
    if integrity and integrity != "ok":
        findings.append(
            Finding(
                "critical",
                "db_corrupt",
                "Database fails the integrity check",
                f"db/integrity_check.txt: {integrity[:200]}",
                "A corrupted SQLite file, usually the result of a hard power loss "
                "or a faulty SD card.",
                "Restore a backup; also check the card and the power supply.",
            )
        )
    return findings


def rule_alembic(export: Export, repo: Path | None) -> list[Finding]:
    version = export.text("db/alembic_version.txt").strip()
    if not version or not repo:
        return []
    versions_dir = repo / "services/backend-service/alembic/versions"
    if not versions_dir.is_dir():
        return []
    revisions = set()
    for file in versions_dir.glob("*.py"):
        match = re.search(
            r"^revision\s*=\s*['\"]([^'\"]+)",
            file.read_text(errors="replace"),
            re.M,
        )
        if match:
            revisions.add(match.group(1))
    if revisions and version not in revisions:
        return [
            Finding(
                "high",
                "alembic_mismatch",
                f"Migration state {version} is unknown in the repo",
                "db/alembic_version.txt",
                "The box runs on a different migration state than the code. "
                "Typical result: 'no such column' errors.",
                "Compare the version with the files in alembic/versions.",
            )
        ]
    return []


def rule_clock(export: Export) -> list[Finding]:
    systemd = export.json("system/systemd.json") or {}
    commands = systemd.get("commands") or {}
    output = (commands.get("timedatectl") or {}).get("output") or ""
    if "NTPSynchronized=no" in output:
        return [
            Finding(
                "medium",
                "clock_unsynced",
                "System clock is not in sync with a time server",
                "system/systemd.json: timedatectl",
                "A wrong time expires sessions, shifts usage times and makes log "
                "timestamps useless.",
                "Check network access to the NTP server.",
            )
        ]
    return []


def rule_systemd(export: Export) -> list[Finding]:
    systemd = export.json("system/systemd.json") or {}
    commands = systemd.get("commands") or {}
    findings: list[Finding] = []
    failed = (commands.get("failed_units") or {}).get("output", "").strip()
    if failed:
        units = [line.split()[0] for line in failed.splitlines() if line.strip()]
        findings.append(
            Finding(
                "medium",
                "failed_units",
                f"Failed systemd services: {', '.join(units[:5])}",
                "system/systemd.json: failed_units",
                "Not necessarily Minabox-related, but a permanent loop loads the "
                "CPU and the log and can noticeably slow the box down.",
                "Check whether the service belongs to the box or comes from the "
                "user.",
            )
        )
    return findings


def rule_media(export: Export) -> list[Finding]:
    missing = export.json("media/missing_files.json") or {}
    count = missing.get("count") or 0
    if count:
        return [
            Finding(
                "high",
                "missing_media",
                f"{count} tracks point at files that do not exist",
                "media/missing_files.json",
                "The database knows tracks whose file is missing - after the media "
                "moved, deleted files or missing USB storage.",
                "Check media/library_summary.json for path patterns; ask the user "
                "about renames if needed.",
            )
        ]
    return []


def rule_gpio_conflicts(export: Export) -> list[Finding]:
    """Same GPIO pin claimed by buttons and LEDs - the classic silent hardware bug."""
    buttons = export.json("config/services/button/buttons.json") or {}
    leds = export.json("config/services/led/leds.json") or {}

    def pins(payload: Any) -> set[int]:
        found: set[int] = set()

        def walk(node: Any) -> None:
            if isinstance(node, dict):
                for key, value in node.items():
                    if "pin" in str(key).lower() and isinstance(value, int):
                        found.add(value)
                    else:
                        walk(value)
            elif isinstance(node, list):
                for item in node:
                    walk(item)

        walk(payload)
        return found

    shared = pins(buttons) & pins(leds)
    if shared:
        return [
            Finding(
                "high",
                "gpio_conflict",
                f"GPIO pin(s) assigned twice: {sorted(shared)}",
                "config/services/button/buttons.json and config/services/led/leds.json",
                "Two services claim the same pin. One of them fails at startup or "
                "behaves randomly.",
                "Change the assignment in one of the two configurations.",
            )
        ]
    return []


def rule_architecture(export: Export) -> list[Finding]:
    os_info = export.json("system/os.json") or {}
    docker = export.json("system/docker.json") or {}
    arch = str(os_info.get("architecture") or "")
    docker_arch = str(docker.get("arch") or "")
    if arch and docker_arch and arch.startswith("armv7") and "arm64" in docker_arch:
        return [
            Finding(
                "critical",
                "arch_mismatch",
                f"32-bit system ({arch}) with 64-bit Docker ({docker_arch})",
                "system/os.json, system/docker.json",
                "Images for arm64 do not start on a 32-bit kernel.",
                "Use the 64-bit image of the operating system.",
            )
        ]
    return []


def rule_memory(export: Export) -> list[Finding]:
    hardware = export.json("system/hardware.json") or {}
    memory = hardware.get("memory") or {}
    total = memory.get("total_mb")
    available = memory.get("available_mb")
    if isinstance(total, int) and isinstance(available, int) and total:
        used_percent = round(100 * (total - available) / total)
        if used_percent >= MEMORY_WARN_PERCENT:
            return [
                Finding(
                    "high",
                    "memory_pressure",
                    f"Memory is {used_percent} % used",
                    f"system/hardware.json: {available} MB of {total} MB free",
                    "Under sustained pressure the kernel kills services (OOM).",
                    "Check services/health.json for oom_killed.",
                )
            ]
    return []


def rule_client_errors(export: Export) -> list[Finding]:
    errors = (export.json("client/console_errors.json") or {}).get("entries") or []
    requests = (export.json("client/failed_requests.json") or {}).get("entries") or []
    findings: list[Finding] = []
    if errors:
        first = errors[0].get("message", "")[:160]
        findings.append(
            Finding(
                "high",
                "frontend_errors",
                f"{len(errors)} errors in the interface",
                f"client/console_errors.json: {first}",
                "The error is in the frontend, not the backend - these messages do "
                "not appear in any container log.",
                "Read the stack trace in client/console_errors.json and compare it "
                "with the web UI version.",
            )
        )
    server_errors = [
        r for r in requests if isinstance(r.get("status"), int) and r["status"] >= 500
    ]
    if server_errors:
        paths = {r.get("url") for r in server_errors}
        findings.append(
            Finding(
                "high",
                "api_5xx",
                f"{len(server_errors)} failed API calls (5xx)",
                "client/failed_requests.json: "
                + ", ".join(str(p) for p in list(paths)[:4]),
                "The backend answered specific calls with server errors.",
                "Compare the timestamps with services/backend/logs.txt.",
            )
        )
    return findings


def rule_manifest(export: Export) -> list[Finding]:
    manifest = export.json("manifest.json") or {}
    findings: list[Finding] = []
    failed = [c for c in manifest.get("collectors", []) if c.get("status") == "failed"]
    if failed:
        names = ", ".join(str(c.get("name")) for c in failed[:5])
        findings.append(
            Finding(
                "medium",
                "collector_failures",
                f"{len(failed)} collector(s) failed: {names}",
                "manifest.json: collectors",
                "Missing areas can be a finding in themselves - e.g. when a "
                "service's logs could not be retrieved because the container does "
                "not exist.",
                "Read the error messages in the manifest before asking for more "
                "data.",
            )
        )
    blocked = manifest.get("secret_tripwire", {}).get("blocked") or []
    if blocked:
        findings.append(
            Finding(
                "critical",
                "secret_leak_blocked",
                "The tripwire removed secrets from the package",
                f"manifest.json: {json.dumps(blocked)[:200]}",
                "A collector emitted a secret. The package is clean, but this is a "
                "bug in the export - not on the user's box.",
                "Fix the affected collector and add the redaction rule.",
            )
        )
    skipped = [
        c.get("name")
        for c in manifest.get("collectors", [])
        if c.get("status") == "skipped_by_user"
    ]
    if skipped:
        findings.append(
            Finding(
                "info",
                "user_skipped",
                f"Deselected by the user: {', '.join(str(s) for s in skipped)}",
                "manifest.json",
                "These areas are deliberately missing.",
                "If needed for the question: ask for it specifically instead of "
                "guessing.",
            )
        )
    return findings


def rule_apt_recent(export: Export) -> list[Finding]:
    history = export.text("system/apt_history.txt")
    if not history:
        return []
    dates = re.findall(r"Start-Date:\s*(\d{4}-\d{2}-\d{2})", history)
    if not dates:
        return []
    latest = max(dates)
    try:
        latest_date = datetime.strptime(latest, "%Y-%m-%d").date()
        age_days = (datetime.now(UTC).date() - latest_date).days
    except ValueError:
        return []
    if age_days <= 7:
        return [
            Finding(
                "medium",
                "recent_apt_change",
                f"Package change {age_days} day(s) ago ({latest})",
                "system/apt_history.txt",
                "If the error appeared 'recently', an update is the most likely "
                "trigger.",
                "Compare the affected packages in the history with the onset of "
                "the error.",
            )
        ]
    return []


def rule_backend_errors(export: Export) -> list[Finding]:
    """Grouped backend warnings from the in-memory ring buffer."""
    payload = export.json("runtime/errors_recent.json") or {}
    entries = payload.get("entries") or []
    if not entries:
        return []
    counts: dict[str, int] = {}
    for entry in entries:
        counts[str(entry.get("event", "?"))] = (
            counts.get(str(entry.get("event", "?")), 0) + 1
        )
    top = sorted(counts.items(), key=lambda item: item[1], reverse=True)[:3]
    hardest = top[0]
    severity = "high" if hardest[1] >= 10 else "medium"
    return [
        Finding(
            severity,
            "backend_errors",
            f"Backend reported {len(entries)} warnings/errors, "
            f"most frequent: {hardest[0]} ({hardest[1]}x)",
            "runtime/errors_recent.json: "
            + ", ".join(f"{name}x{count}" for name, count in top),
            "Recurring errors in the backend. The ring buffer survives log "
            "rotation, the container logs show the context.",
            "Search for the event names in services/backend/logs.txt and compare "
            "the times with the complaint.",
        )
    ]


def rule_mqtt_traffic(export: Export) -> list[Finding]:
    """No bus traffic at all is a stronger signal than any single error."""
    payload = export.json("runtime/mqtt_recent.json") or {}
    entries = payload.get("entries")
    if entries is None:
        return []
    if entries:
        inbound = sum(1 for e in entries if e.get("direction") == "in")
        if inbound == 0:
            return [
                Finding(
                    "high",
                    "mqtt_no_inbound",
                    "The backend received not a single MQTT message recently",
                    f"runtime/mqtt_recent.json: {len(entries)} messages, all "
                    "outbound",
                    "The backend sends but gets nothing back. Buttons, RFID and "
                    "audio do not report - typical for stopped services or a "
                    "subscription problem at the broker.",
                    "Check services/health.json and the logs of rfid/button.",
                )
            ]
        return []
    return [
        Finding(
            "medium",
            "mqtt_silent",
            "No MQTT messages in the ring buffer",
            "runtime/mqtt_recent.json is empty",
            "Either the box was unused since the start, or the bus distributes "
            "nothing.",
            "Ask the user whether the box was operated at all between the restart "
            "and the export.",
        )
    ]


def rule_image_age(export: Export) -> list[Finding]:
    """A very old system image brings its own set of solved-elsewhere bugs."""
    os_info = export.json("system/os.json") or {}
    image = str(os_info.get("image") or "")
    match = re.search(r"(20\d{2})-(\d{2})-(\d{2})", image)
    if not match:
        return []
    year = int(match.group(1))
    age_years = datetime.now(UTC).year - year
    if age_years >= 3:
        return [
            Finding(
                "low",
                "old_image",
                f"System image is about {age_years} years old ({match.group(0)})",
                f"system/os.json: {image}",
                "Old images bring old kernel and firmware bugs that were fixed "
                "elsewhere long ago.",
                "On otherwise unexplained hardware symptoms, consider a current "
                "image.",
            )
        ]
    return []


def rule_docker_disk(export: Export) -> list[Finding]:
    """Orphaned images fill a small card fast and look like a full disk."""
    docker = export.json("system/docker.json") or {}
    usage = docker.get("disk_usage") or {}
    images_bytes = usage.get("images_bytes")
    if isinstance(images_bytes, int) and images_bytes > 8 * 1024**3:
        return [
            Finding(
                "medium",
                "docker_images_large",
                f"Docker images take {round(images_bytes / 1024**3, 1)} GB",
                "system/docker.json: disk_usage",
                "Old images stay behind after updates and eat the space on the SD "
                "card.",
                "Recommend docker image prune if storage is also low.",
            )
        ]
    return []


RULES = (
    rule_undervoltage,
    rule_storage,
    rule_sd_card,
    rule_services,
    rule_database,
    rule_clock,
    rule_systemd,
    rule_media,
    rule_gpio_conflicts,
    rule_architecture,
    rule_memory,
    rule_client_errors,
    rule_manifest,
    rule_apt_recent,
    rule_backend_errors,
    rule_mqtt_traffic,
    rule_image_age,
    rule_docker_disk,
)


def run(root: Path, repo: Path | None) -> list[Finding]:
    export = Export(root)
    findings: list[Finding] = []
    for rule in RULES:
        try:
            findings.extend(rule(export))
        except Exception as e:  # a broken rule must not hide the other findings
            findings.append(
                Finding(
                    "info",
                    "rule_error",
                    f"Rule {rule.__name__} aborted",
                    f"{type(e).__name__}: {e}",
                    "The other rules are unaffected.",
                )
            )
    findings.extend(rule_alembic(export, repo))
    findings.sort(key=lambda f: SEVERITY_ORDER.get(f.severity, 9))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, help="unpacked export directory")
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--repo", type=Path, default=None, help="repo for the version comparison"
    )
    args = parser.parse_args()

    if not args.directory.is_dir():
        raise SystemExit(f"not a directory: {args.directory}")

    findings = run(args.directory, args.repo)

    if args.json:
        print(json.dumps([f.as_dict() for f in findings], indent=2, ensure_ascii=False))
        return 0

    if not findings:
        print("No known failure patterns found.")
        print("That does not rule out a fault - now read the logs specifically.")
        return 0

    print(f"{len(findings)} finding(s):\n")
    for finding in findings:
        print(f"[{finding.severity.upper()}] {finding.title}")
        print(f"  Evidence:   {finding.evidence}")
        print(f"  Hypothesis: {finding.hypothesis}")
        if finding.next_step:
            print(f"  Next step:  {finding.next_step}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
