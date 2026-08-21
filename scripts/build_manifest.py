#!/usr/bin/env python3
"""Erzeugt das Release-Manifest aus den beiden Changelog-Dateien.

Das Manifest ist die Datei, die eine Box beim Update-Check liest: welche
Version je Dienst aktuell ist und was sich seit der installierten Version
geaendert hat - in der Sprache, die der Nutzer eingestellt hat.

Warum eine eigene Datei und kein GitHub-Release-Text: mit einer Nummer je
Dienst (docs/Versionierung.md) passt "ein Release = eine Version" nicht mehr.
Neun Dienste bewegen sich unabhaengig; die Box soll trotzdem *einen* Abruf
machen.

    python3 scripts/build_manifest.py            # schreibt release-manifest.json
    python3 scripts/build_manifest.py --check    # prueft nur, ob es aktuell ist
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SERVICES_DIR = ROOT / "services"
MANIFEST = ROOT / "release-manifest.json"

# Sprache -> (Changelog-Datei, erlaubte Abschnittsueberschriften)
LANGUAGES: dict[str, tuple[str, tuple[str, ...]]] = {
    "de": ("CHANGELOG.md", ("Neu", "Verbessert", "Behoben")),
    "en": ("CHANGELOG.en.md", ("Added", "Improved", "Fixed")),
}

# Die Abschnitte stehen in beiden Sprachen in derselben Reihenfolge; darueber
# laufen sie zusammen, ohne dass eine Uebersetzungstabelle noetig waere.
CATEGORY_KEYS = ("added", "improved", "fixed")

SCHEMA_VERSION = 1

RE_SERVICE = re.compile(r"^##\s+(?P<name>[a-z0-9][a-z0-9-]*)\s*$")
RE_VERSION = re.compile(
    r"^###\s+(?P<version>\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?)\s+-\s+(?P<date>\d{4}-\d{2}-\d{2})\s*$"
)
RE_CATEGORY = re.compile(r"^####\s+(?P<name>.+?)\s*$")
RE_ITEM = re.compile(r"^-\s+(?P<text>.+?)\s*$")


class ChangelogError(Exception):
    """Ein Formatfehler, der benannt werden kann - mit Datei und Zeile."""


def parse_changelog(path: Path, categories: tuple[str, ...]) -> dict[str, dict[str, dict[str, list[str]]]]:
    """{dienst: {version: {kategorie: [eintrag, ...]}}}"""
    result: dict[str, dict[str, dict[str, list[str]]]] = {}
    service: str | None = None
    version: str | None = None
    category: str | None = None

    in_fence = False

    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.rstrip()

        # Der erklaerende Aufbau am Dateikopf steht in einem Codeblock und
        # sieht wie echte Ueberschriften aus - er darf nicht mitgelesen werden.
        if line.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue

        if m := RE_SERVICE.match(line):
            service, version, category = m.group("name"), None, None
            result.setdefault(service, {})
            continue

        if m := RE_VERSION.match(line):
            if service is None:
                raise ChangelogError(f"{path.name}:{number}: Version ohne Dienst darueber")
            version, category = m.group("version"), None
            result[service].setdefault(version, {"date": m.group("date")})
            continue

        if m := RE_CATEGORY.match(line):
            name = m.group("name")
            if name not in categories:
                raise ChangelogError(
                    f"{path.name}:{number}: Unbekannter Abschnitt {name!r}; "
                    f"erlaubt sind {', '.join(categories)}"
                )
            if version is None:
                raise ChangelogError(f"{path.name}:{number}: Abschnitt ohne Version darueber")
            category = CATEGORY_KEYS[categories.index(name)]
            continue

        if m := RE_ITEM.match(line):
            # Aufzaehlungen in der Kopf-Erklaerung stehen vor dem ersten "##"
            # und werden ignoriert.
            if service is None:
                continue
            if version is None or category is None:
                raise ChangelogError(
                    f"{path.name}:{number}: Eintrag ohne Version oder Abschnitt darueber"
                )
            result[service][version].setdefault(category, []).append(m.group("text"))
            continue

        # Fortsetzungszeile eines umbrochenen Eintrags.
        if line.startswith("  ") and service and version and category:
            items = result[service][version].get(category)
            if items:
                items[-1] = f"{items[-1]} {line.strip()}"

    return result


def known_services() -> set[str]:
    """Dienste, die es wirklich gibt - abgeleitet aus den VERSION-Dateien."""
    return {
        p.parent.name.removesuffix("-service")
        for p in SERVICES_DIR.glob("*-service/VERSION")
    }


def current_version(service: str) -> str:
    return (SERVICES_DIR / f"{service}-service" / "VERSION").read_text(
        encoding="utf-8"
    ).strip()


def sort_key(version: str) -> tuple:
    """Neueste zuerst; ein Vorab-Kennzeichen sortiert vor der fertigen Version."""
    core, _, pre = version.partition("-")
    numbers = tuple(int(part) for part in core.split("."))
    return (numbers, 1 if not pre else 0, pre)


def build() -> dict[str, Any]:
    parsed = {
        lang: parse_changelog(ROOT / filename, categories)
        for lang, (filename, categories) in LANGUAGES.items()
    }
    services = known_services()
    problems: list[str] = []

    # Ein Changelog-Abschnitt fuer einen Dienst, den es nicht gibt, ist fast
    # immer ein Tippfehler im Namen - und wuerde sonst stillschweigend nie
    # angezeigt.
    for lang, tree in parsed.items():
        for name in tree:
            if name not in services:
                problems.append(
                    f"{LANGUAGES[lang][0]}: '{name}' ist kein Dienst "
                    f"({', '.join(sorted(services))})"
                )

    manifest_services: dict[str, Any] = {}
    for service in sorted(services):
        version = current_version(service)
        entries = parsed["de"].get(service, {})
        other = parsed["en"].get(service, {})

        # Die aktuelle Version muss beschrieben sein, sonst laeuft ein Update
        # ohne ein Wort Erklaerung durch.
        if version not in entries:
            problems.append(
                f"CHANGELOG.md: {service} {version} fehlt "
                f"(VERSION sagt {version}, beschrieben sind: "
                f"{', '.join(sorted(entries, key=sort_key)) or 'keine'})"
            )
        for missing in sorted(set(entries) - set(other)):
            problems.append(f"CHANGELOG.en.md: {service} {missing} fehlt")
        for extra in sorted(set(other) - set(entries)):
            problems.append(f"CHANGELOG.md: {service} {extra} fehlt")

        releases = []
        for release_version in sorted(entries, key=sort_key, reverse=True):
            german = entries[release_version]
            english = other.get(release_version, {})
            notes = {
                key: {
                    "de": german.get(key, []),
                    "en": english.get(key, german.get(key, [])),
                }
                for key in CATEGORY_KEYS
                if german.get(key) or english.get(key)
            }
            releases.append(
                {
                    "version": release_version,
                    "date": german.get("date"),
                    "notes": notes,
                }
            )

        manifest_services[service] = {"latest": version, "releases": releases}

    if problems:
        raise ChangelogError("\n".join(f"  - {p}" for p in problems))

    return {
        "schema": SCHEMA_VERSION,
        "registry": "ghcr.io/opnek90",
        "services": manifest_services,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Nur pruefen, ob release-manifest.json zu den Changelogs passt",
    )
    args = parser.parse_args()

    try:
        manifest = build()
    except ChangelogError as exc:
        print(f"Changelog passt nicht:\n{exc}", file=sys.stderr)
        return 1

    text = json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=False) + "\n"

    if args.check:
        if not MANIFEST.exists():
            print(f"{MANIFEST.name} fehlt. Erzeugen mit: python3 scripts/build_manifest.py", file=sys.stderr)
            return 1
        if MANIFEST.read_text(encoding="utf-8") != text:
            print(
                f"{MANIFEST.name} ist nicht aktuell. Neu erzeugen mit: "
                "python3 scripts/build_manifest.py",
                file=sys.stderr,
            )
            return 1
        print(f"{MANIFEST.name} ist aktuell.")
        return 0

    MANIFEST.write_text(text, encoding="utf-8")
    print(f"{MANIFEST.name} geschrieben: {len(manifest['services'])} Dienste")
    for name, data in manifest["services"].items():
        print(f"  {name:18s} {data['latest']}  ({len(data['releases'])} Eintraege)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
