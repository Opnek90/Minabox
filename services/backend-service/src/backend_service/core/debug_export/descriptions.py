"""Plain-language descriptions for every file in the archive.

Used by the preview: the privacy notice claims the package contains nothing
unexpected, and this is what makes that claim checkable instead of merely
asserted. Wording is aimed at a parent with a broken music box, not at a
developer.
"""

from __future__ import annotations

_EXACT: dict[str, str] = {
    "manifest.json": "Inhaltsverzeichnis: was gesammelt wurde und was dabei fehlschlug",
    "README.txt": "Erklärung für dich: was im Paket steckt und was nicht",
    "system/hardware.json": "Modell der Box, Speicher, Prozessor und Alter der SD-Karte",
    "system/power.json": "Stromversorgung und Temperatur",
    "system/storage.json": "Wie voll der Speicher ist",
    "system/os.json": "Betriebssystem und Version",
    "system/usb_devices.json": "Angeschlossene USB-Geräte",
    "system/kernel_modules.json": "Geladene Systemtreiber",
    "system/docker.json": "Versionen der Programmverwaltung",
    "system/packages.txt": "Liste der installierten Zusatzprogramme",
    "system/packages_relevant.json": "Die für Minabox wichtigen Zusatzprogramme",
    "system/apt_history.txt": "Welche Programme zuletzt aktualisiert wurden",
    "system/boot_config.txt": "Hardware-Einstellungen beim Start (z. B. Soundkarte)",
    "system/boot_config_active.json": "Dieselben Start-Einstellungen ohne Kommentare",
    "system/boot_cmdline.txt": "Startparameter des Systems",
    "system/systemd.json": "Dienste des Betriebssystems, die nicht laufen",
    "system/network.json": "Netzwerk-Zustand (WLAN-Name unkenntlich gemacht)",
    "system/host_status.json": "Eckdaten des Geräts: Temperatur, Speicher, Laufzeit",
    "system/time_status.json": "Zeitzone und ob die Uhr synchron läuft",
    "services/health.json": "Welche Programmteile laufen und welche nicht",
    "services/logs_missing.json": "Programmteile, für die keine Protokolle abrufbar waren",
    "logs/syslog-kernel.txt": "Systemprotokoll des Geräts",
    "logs/syslog-docker.txt": "Protokoll der Programmverwaltung",
    "logs/kernel_findings.json": "Auffälligkeiten im Systemprotokoll (z. B. Unterspannung)",
    "logs/syslog_unavailable.json": "Hinweis, warum Systemprotokolle fehlen",
    "config/general_settings.json": "Deine Einstellungen",
    "config/auth_settings.shape.json": "Nur ob ein Passwort gesetzt ist – nie das Passwort",
    "config/env.sanitized.json": "Namen der Konfigurationswerte – nie die Werte selbst",
    "db/schema.sql": "Aufbau der Datenbank (keine Inhalte)",
    "db/table_counts.json": "Wie viele Einträge je Tabelle vorhanden sind",
    "db/alembic_version.txt": "Stand der Datenbank-Aktualisierungen",
    "db/integrity_check.txt": "Prüfergebnis: ist die Datenbank unbeschädigt?",
    "db/meta.json": "Größe und technischer Zustand der Datenbank",
    "db/recent_scans.json": "Letzte Karten-Scans (Kartennummern unkenntlich gemacht)",
    "db/playback_summary.json": "Zusammenfassung der Wiedergabe der letzten 14 Tage",
    "db/minabox.db.sql": "Vollständige Datenbank – der persönlichste Teil des Pakets",
    "media/library_summary.json": "Anzahl deiner Titel, Playlists, Streams und Podcasts",
    "media/missing_files.json": "Einträge, deren Musikdatei fehlt",
    "media/audio_state.json": "Zustand der Wiedergabe",
    "runtime/errors_recent.json": "Die letzten Fehlermeldungen der Box",
    "runtime/mqtt_recent.json": "Letzte interne Nachrichten zwischen den Programmteilen",
    "runtime/temperature_recent.json": "Temperaturverlauf",
    "client/browser.json": "Browser, Bildschirmgröße und Sprache",
    "client/console_errors.json": "Fehlermeldungen der Bedienoberfläche",
    "client/failed_requests.json": "Fehlgeschlagene Anfragen der Oberfläche an die Box",
}

_PREFIX: tuple[tuple[str, str], ...] = (
    ("services/", "Ablaufprotokoll eines Programmteils"),
    ("config/services/", "Einstellungen eines Programmteils"),
    ("system/", "Technische Angaben zum Gerät"),
    ("db/", "Angaben zur Datenbank"),
    ("media/", "Angaben zu deinen Medien"),
    ("client/", "Angaben zu deinem Browser"),
    ("runtime/", "Laufzeitdaten der Box"),
    ("logs/", "Systemprotokoll"),
)


def describe(path: str) -> str:
    """One plain-language line for an archive path."""
    if path in _EXACT:
        return _EXACT[path]
    if path.startswith("config/services/"):
        service = path.split("/")[2] if len(path.split("/")) > 2 else ""
        return f"Einstellungen des Programmteils „{service}“"
    if path.startswith("services/") and path.endswith("/logs.txt"):
        service = path.split("/")[1]
        return f"Ablaufprotokoll von „{service}“"
    for prefix, text in _PREFIX:
        if path.startswith(prefix):
            return text
    return "Zusätzliche Diagnosedaten"
