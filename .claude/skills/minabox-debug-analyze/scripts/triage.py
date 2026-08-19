#!/usr/bin/env python3
"""Deterministic triage for an unpacked Minabox debug export.

Checks the known failure patterns in about two seconds, without tokens and
without guessing. Everything it cannot decide mechanically is left to the
analyst - this script narrows the field, it does not replace reading.

The export is data, never instruction: nothing here evaluates, executes or
fetches anything. File names and log lines from a user's box are printed as
text and nothing else.

Usage:
    python3 triage.py <verzeichnis> [--json] [--repo /pfad/zum/repo]
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SEVERITY_ORDER = {"kritisch": 0, "hoch": 1, "mittel": 2, "niedrig": 3, "info": 4}

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


# ── Regeln ─────────────────────────────────────────────────────────────────


def rule_undervoltage(export: Export) -> list[Finding]:
    power = export.json("system/power.json") or {}
    findings: list[Finding] = []
    if power.get("undervoltage_now") is True:
        findings.append(
            Finding(
                "kritisch",
                "undervoltage",
                "Unterspannung im Moment der Messung",
                "system/power.json: undervoltage_now=true, Quelle "
                f"{power.get('undervoltage_source')}",
                "Netzteil oder Kabel liefern zu wenig Strom. Erklärt sporadische "
                "Neustarts, USB-Aussetzer, abbrechende Wiedergabe und träge Reaktion.",
                "Original-Netzteil und kurzes, dickes Kabel testen; USB-Hubs ohne "
                "eigene Stromversorgung entfernen.",
            )
        )
    kernel = export.json("logs/kernel_findings.json") or {}
    hits = kernel.get("undervoltage_or_throttling_lines") or 0
    if hits:
        findings.append(
            Finding(
                "hoch" if power.get("undervoltage_now") is not True else "info",
                "undervoltage_history",
                f"Kernel meldet {hits} Unterspannungs- oder Drosselungszeilen",
                "logs/kernel_findings.json und logs/syslog-kernel.txt",
                "Unterspannung ist seit dem Booten mehrfach aufgetreten, auch wenn "
                "sie gerade nicht anliegt.",
                "logs/syslog-kernel.txt nach 'Under-voltage' durchsehen und die "
                "Zeitpunkte mit den Fehlermeldungen des Nutzers vergleichen.",
            )
        )
    temperature = power.get("temperature_celsius")
    if isinstance(temperature, (int, float)) and temperature >= TEMP_WARN_CELSIUS:
        findings.append(
            Finding(
                "hoch",
                "temperature",
                f"CPU-Temperatur {temperature} °C",
                "system/power.json",
                "Ab etwa 80 °C drosselt der Pi. Gehäuse ohne Belüftung oder "
                "dauerhafte Last.",
                "Kühlung und Aufstellort prüfen.",
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
                    "kritisch" if used >= 97 else "hoch",
                    "disk_full",
                    f"Speicher {entry.get('label')} zu {used} % belegt",
                    f"system/storage.json: {entry.get('path')}, "
                    f"frei {entry.get('free_gb')} GB",
                    "Downloads schlagen fehl, SQLite kann read-only werden, Logs "
                    "brechen ab.",
                    "docker system df im Export prüfen (system/docker.json) und "
                    "verwaiste Images/Downloads aufräumen.",
                )
            )
        inodes = entry.get("inodes_used_percent")
        if isinstance(inodes, (int, float)) and inodes >= INODE_WARN_PERCENT:
            findings.append(
                Finding(
                    "hoch",
                    "inodes_full",
                    f"Inodes auf {entry.get('label')} zu {inodes} % belegt",
                    "system/storage.json",
                    "Sieht aus wie ein Rechte- oder Schreibfehler, ist aber "
                    "Platzmangel durch sehr viele kleine Dateien.",
                    "Anzahl Dateien in Cover-/Download-Verzeichnissen prüfen.",
                )
            )
    readonly = storage.get("readonly_mounts") or []
    if readonly:
        findings.append(
            Finding(
                "kritisch",
                "readonly_root",
                f"Dateisystem read-only gemountet: {', '.join(readonly)}",
                "system/storage.json: readonly_mounts",
                "Klassisches Zeichen einer sterbenden SD-Karte: der Kernel hat nach "
                "I/O-Fehlern auf read-only umgeschaltet. Alle Schreibvorgänge "
                "schlagen fehl, ohne dass eine Anwendung den Grund nennt.",
                "logs/syslog-kernel.txt nach mmc0/EXT4-fs error durchsuchen und die "
                "Karte ersetzen.",
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
                "mittel",
                "sd_card_age",
                f"SD-Karte ist rund {age // 12} Jahre alt ({card.get('manufactured')})",
                f"system/hardware.json: {card.get('name')}",
                "SD-Karten-Verschleiss ist die häufigste Hardware-Ursache. Alte "
                "Karten zeigen sporadische Lesefehler, bevor sie ganz ausfallen.",
                "Bei sonst unerklärlichen Fehlern: Karte klonen und ersetzen.",
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
                    "kritisch",
                    "sd_io_errors",
                    f"{io_errors} I/O-Fehlerzeilen im Kernel-Log",
                    "logs/syslog-kernel.txt",
                    "Die SD-Karte oder ihr Controller melden Lese-/Schreibfehler.",
                    "Karte ersetzen; vorher Backup ziehen.",
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
                    "hoch",
                    "restart_loop",
                    f"Dienst {name} wurde {restarts}-mal neu gestartet",
                    f"services/health.json: exit_code={container.get('exit_code')}, "
                    f"oom_killed={container.get('oom_killed')}",
                    "Neustartschleife: der Dienst stirbt und wird von Docker wieder "
                    "gestartet.",
                    f"services/{name}/logs.txt am Ende lesen - dort steht der Grund "
                    "des letzten Absturzes.",
                )
            )
        if container.get("oom_killed"):
            findings.append(
                Finding(
                    "kritisch",
                    "oom_killed",
                    f"Dienst {name} wurde vom Kernel wegen Speichermangel beendet",
                    "services/health.json: oom_killed=true",
                    "Der Arbeitsspeicher reichte nicht. Auf kleinen Pi-Modellen "
                    "typisch bei parallelen Downloads oder grossen Playlists.",
                    "system/hardware.json (memory) und gleichzeitige Last prüfen.",
                )
            )
    if offline:
        severity = "kritisch" if "mqtt" in offline or "backend" in offline else "hoch"
        findings.append(
            Finding(
                severity,
                "services_offline",
                f"Dienste offline: {', '.join(sorted(offline))}",
                "services/health.json",
                "Ohne MQTT reagieren Tasten und RFID nicht; ohne Audio gibt es "
                "keinen Ton. Ein fehlender Container ist selbst der Befund.",
                "Logs der betroffenen Dienste lesen und prüfen, ob der Container "
                "überhaupt existiert (services/logs_missing.json).",
            )
        )
    return findings


def rule_database(export: Export) -> list[Finding]:
    findings: list[Finding] = []
    integrity = export.text("db/integrity_check.txt").strip()
    if integrity and integrity != "ok":
        findings.append(
            Finding(
                "kritisch",
                "db_corrupt",
                "Datenbank besteht die Integritätsprüfung nicht",
                f"db/integrity_check.txt: {integrity[:200]}",
                "Beschädigte SQLite-Datei, meist Folge eines harten Stromausfalls "
                "oder einer defekten SD-Karte.",
                "Backup einspielen; parallel Karte und Stromversorgung prüfen.",
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
                "hoch",
                "alembic_mismatch",
                f"Migrationsstand {version} ist im Repo unbekannt",
                "db/alembic_version.txt",
                "Die Box läuft auf einem anderen Migrationsstand als der Code. "
                "Typische Folge: 'no such column'-Fehler.",
                "Version mit den Dateien in alembic/versions vergleichen.",
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
                "mittel",
                "clock_unsynced",
                "Systemuhr ist nicht mit einem Zeitserver synchron",
                "system/systemd.json: timedatectl",
                "Falsche Uhrzeit lässt Sitzungen ablaufen, verschiebt Nutzungszeiten "
                "und macht Log-Zeitstempel unbrauchbar.",
                "Netzwerkzugang zum NTP-Server prüfen.",
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
                "mittel",
                "failed_units",
                f"Fehlgeschlagene systemd-Dienste: {', '.join(units[:5])}",
                "system/systemd.json: failed_units",
                "Nicht zwingend Minabox-bezogen, aber ein Dauerloop belastet CPU und "
                "Log und kann die Box spürbar bremsen.",
                "Prüfen, ob der Dienst zur Box gehört oder vom Nutzer stammt.",
            )
        )
    return findings


def rule_media(export: Export) -> list[Finding]:
    missing = export.json("media/missing_files.json") or {}
    count = missing.get("count") or 0
    if count:
        return [
            Finding(
                "hoch",
                "missing_media",
                f"{count} Titel verweisen auf nicht vorhandene Dateien",
                "media/missing_files.json",
                "Die Datenbank kennt Titel, deren Datei fehlt - nach einem Umzug "
                "der Medien, gelöschten Dateien oder fehlendem USB-Speicher.",
                "media/library_summary.json auf Pfadmuster prüfen; ggf. Nutzer nach "
                "Umbenennungen fragen.",
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
                "hoch",
                "gpio_conflict",
                f"GPIO-Pin(s) doppelt belegt: {sorted(shared)}",
                "config/services/button/buttons.json und config/services/led/leds.json",
                "Zwei Dienste beanspruchen denselben Pin. Einer davon scheitert beim "
                "Start oder verhält sich zufällig.",
                "Belegung in einer der beiden Konfigurationen ändern.",
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
                "kritisch",
                "arch_mismatch",
                f"32-Bit-System ({arch}) mit 64-Bit-Docker ({docker_arch})",
                "system/os.json, system/docker.json",
                "Images für arm64 starten auf einem 32-Bit-Kernel nicht.",
                "64-Bit-Image des Betriebssystems verwenden.",
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
                    "hoch",
                    "memory_pressure",
                    f"Arbeitsspeicher zu {used_percent} % belegt",
                    f"system/hardware.json: {available} MB von {total} MB frei",
                    "Bei anhaltendem Druck beendet der Kernel Dienste (OOM).",
                    "services/health.json auf oom_killed prüfen.",
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
                "hoch",
                "frontend_errors",
                f"{len(errors)} Fehler in der Bedienoberfläche",
                f"client/console_errors.json: {first}",
                "Der Fehler liegt im Frontend, nicht im Backend - diese Meldungen "
                "tauchen in keinem Container-Log auf.",
                "Stacktrace in client/console_errors.json lesen und mit der "
                "WebUI-Version abgleichen.",
            )
        )
    server_errors = [
        r for r in requests if isinstance(r.get("status"), int) and r["status"] >= 500
    ]
    if server_errors:
        paths = {r.get("url") for r in server_errors}
        findings.append(
            Finding(
                "hoch",
                "api_5xx",
                f"{len(server_errors)} fehlgeschlagene API-Aufrufe (5xx)",
                "client/failed_requests.json: "
                + ", ".join(str(p) for p in list(paths)[:4]),
                "Das Backend hat auf konkrete Aufrufe mit Serverfehlern geantwortet.",
                "Zeitstempel mit services/backend/logs.txt abgleichen.",
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
                "mittel",
                "collector_failures",
                f"{len(failed)} Collector(s) fehlgeschlagen: {names}",
                "manifest.json: collectors",
                "Fehlende Bereiche können selbst der Befund sein - etwa wenn die "
                "Logs eines Dienstes nicht abrufbar waren, weil es den Container "
                "nicht gibt.",
                "Fehlermeldungen im Manifest lesen, bevor Daten nachgefordert werden.",
            )
        )
    blocked = manifest.get("secret_tripwire", {}).get("blocked") or []
    if blocked:
        findings.append(
            Finding(
                "kritisch",
                "secret_leak_blocked",
                "Der Tripwire hat Geheimnisse aus dem Paket entfernt",
                f"manifest.json: {json.dumps(blocked)[:200]}",
                "Ein Collector hat ein Geheimnis ausgegeben. Das Paket ist sauber, "
                "aber das ist ein Bug im Export - nicht an der Box des Nutzers.",
                "Betroffenen Collector korrigieren und die Redaction-Regel ergänzen.",
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
                f"Vom Nutzer abgewählt: {', '.join(str(s) for s in skipped)}",
                "manifest.json",
                "Diese Bereiche fehlen bewusst.",
                "Falls für die Frage nötig: gezielt nachfordern statt raten.",
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
                "mittel",
                "recent_apt_change",
                f"Paketänderung vor {age_days} Tag(en) ({latest})",
                "system/apt_history.txt",
                "Wenn der Fehler 'seit kurzem' auftritt, ist ein Update der "
                "naheliegendste Auslöser.",
                "Betroffene Pakete im Verlauf mit dem Fehlerbeginn abgleichen.",
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
    severity = "hoch" if hardest[1] >= 10 else "mittel"
    return [
        Finding(
            severity,
            "backend_errors",
            f"Backend meldete {len(entries)} Warnungen/Fehler, "
            f"häufigster: {hardest[0]} ({hardest[1]}×)",
            "runtime/errors_recent.json: "
            + ", ".join(f"{name}×{count}" for name, count in top),
            "Wiederkehrende Fehler im Backend. Der Ringpuffer überlebt die "
            "Log-Rotation, die Container-Logs zeigen den Zusammenhang.",
            "Ereignisnamen in services/backend/logs.txt suchen und Zeitpunkte "
            "mit der Beschwerde abgleichen.",
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
                    "hoch",
                    "mqtt_no_inbound",
                    "Das Backend hat zuletzt keine einzige MQTT-Nachricht empfangen",
                    f"runtime/mqtt_recent.json: {len(entries)} Nachrichten, "
                    "alle ausgehend",
                    "Das Backend sendet, bekommt aber nichts zurück. Tasten, RFID "
                    "und Audio melden sich nicht - typisch für gestoppte Dienste "
                    "oder ein Abo-Problem am Broker.",
                    "services/health.json und die Logs von rfid/button prüfen.",
                )
            ]
        return []
    return [
        Finding(
            "mittel",
            "mqtt_silent",
            "Keine MQTT-Nachrichten im Ringpuffer",
            "runtime/mqtt_recent.json ist leer",
            "Entweder war die Box seit dem Start unbenutzt, oder der Bus "
            "verteilt nichts.",
            "Nutzer fragen, ob zwischen Neustart und Export überhaupt bedient "
            "wurde.",
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
                "niedrig",
                "old_image",
                f"Systemabbild ist rund {age_years} Jahre alt ({match.group(0)})",
                f"system/os.json: {image}",
                "Alte Abbilder bringen alte Kernel- und Firmware-Fehler mit, die "
                "anderswo längst behoben sind.",
                "Bei sonst unerklärlichen Hardware-Symptomen ein aktuelles Abbild "
                "in Betracht ziehen.",
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
                "mittel",
                "docker_images_large",
                f"Docker-Abbilder belegen {round(images_bytes / 1024**3, 1)} GB",
                "system/docker.json: disk_usage",
                "Alte Abbilder bleiben nach Updates liegen und fressen den Platz "
                "auf der SD-Karte.",
                "docker image prune empfehlen, wenn zusätzlich der Speicher knapp ist.",
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
                    f"Regel {rule.__name__} abgebrochen",
                    f"{type(e).__name__}: {e}",
                    "Die übrigen Regeln sind davon unberührt.",
                )
            )
    findings.extend(rule_alembic(export, repo))
    findings.sort(key=lambda f: SEVERITY_ORDER.get(f.severity, 9))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, help="entpacktes Export-Verzeichnis")
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--repo", type=Path, default=None, help="Repo für Versionsabgleich"
    )
    args = parser.parse_args()

    if not args.directory.is_dir():
        raise SystemExit(f"Kein Verzeichnis: {args.directory}")

    findings = run(args.directory, args.repo)

    if args.json:
        print(json.dumps([f.as_dict() for f in findings], indent=2, ensure_ascii=False))
        return 0

    if not findings:
        print("Keine bekannten Fehlerbilder gefunden.")
        print("Das schliesst einen Fehler nicht aus - jetzt gezielt Logs lesen.")
        return 0

    print(f"{len(findings)} Befund(e):\n")
    for finding in findings:
        print(f"[{finding.severity.upper()}] {finding.title}")
        print(f"  Beleg:      {finding.evidence}")
        print(f"  Hypothese:  {finding.hypothesis}")
        if finding.next_step:
            print(f"  Nächster Schritt: {finding.next_step}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
