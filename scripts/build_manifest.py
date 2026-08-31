#!/usr/bin/env python3
"""Builds the release manifest from the two changelog files.

The manifest is the file a box reads during an update check: which version each
service is at and what changed since the installed version - in the language
the user has chosen.

Why a separate file and not the GitHub release text: with a number per service,
"one release = one version" no longer fits. Nine services move independently;
the box should still make *one* request.

    python3 scripts/build_manifest.py          # writes release/release-manifest.json
    python3 scripts/build_manifest.py --check  # only checks whether it is up to date
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
MANIFEST = ROOT / "release" / "release-manifest.json"

# language -> (changelog file, allowed section headings)
LANGUAGES: dict[str, tuple[str, tuple[str, ...]]] = {
    "de": ("release/CHANGELOG.md", ("Neu", "Verbessert", "Behoben")),
    "en": ("release/CHANGELOG.en.md", ("Added", "Improved", "Fixed")),
}

# The sections appear in both languages in the same order; that is how they are
# joined, without needing a translation table.
CATEGORY_KEYS = ("added", "improved", "fixed")

SCHEMA_VERSION = 1

RE_SERVICE = re.compile(r"^##\s+(?P<name>[a-z0-9][a-z0-9-]*)\s*$")
RE_VERSION = re.compile(
    r"^###\s+(?P<version>\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?)\s+-\s+(?P<date>\d{4}-\d{2}-\d{2})\s*$"
)
RE_CATEGORY = re.compile(r"^####\s+(?P<name>.+?)\s*$")
RE_ITEM = re.compile(r"^-\s+(?P<text>.+?)\s*$")


class ChangelogError(Exception):
    """A format error that can be named - with file and line."""


def parse_changelog(
    path: Path, categories: tuple[str, ...]
) -> dict[str, dict[str, dict[str, list[str]]]]:
    """{service: {version: {category: [entry, ...]}}}"""
    result: dict[str, dict[str, dict[str, list[str]]]] = {}
    service: str | None = None
    version: str | None = None
    category: str | None = None

    in_fence = False

    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.rstrip()

        # The explanatory format at the top of the file is in a code block and
        # looks like real headings - it must not be read in.
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
                raise ChangelogError(
                    f"{path.name}:{number}: version with no service above it"
                )
            version, category = m.group("version"), None
            result[service].setdefault(version, {"date": m.group("date")})
            continue

        if m := RE_CATEGORY.match(line):
            name = m.group("name")
            if name not in categories:
                raise ChangelogError(
                    f"{path.name}:{number}: unknown section {name!r}; "
                    f"allowed are {', '.join(categories)}"
                )
            if version is None:
                raise ChangelogError(
                    f"{path.name}:{number}: section with no version above it"
                )
            category = CATEGORY_KEYS[categories.index(name)]
            continue

        if m := RE_ITEM.match(line):
            # Bullet points in the header explanation come before the first "##"
            # and are ignored.
            if service is None:
                continue
            if version is None or category is None:
                raise ChangelogError(
                    f"{path.name}:{number}: entry with no version or section above it"
                )
            result[service][version].setdefault(category, []).append(m.group("text"))
            continue

        # Continuation line of a wrapped entry.
        if line.startswith("  ") and service and version and category:
            items = result[service][version].get(category)
            if items:
                items[-1] = f"{items[-1]} {line.strip()}"

    return result


def known_services() -> set[str]:
    """The services that really exist - derived from the VERSION files."""
    return {
        p.parent.name.removesuffix("-service")
        for p in SERVICES_DIR.glob("*-service/VERSION")
    }


def current_version(service: str) -> str:
    return (SERVICES_DIR / f"{service}-service" / "VERSION").read_text(
        encoding="utf-8"
    ).strip()


def sort_key(version: str) -> tuple:
    """Newest first; a pre-release marker sorts before the finished version."""
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

    # A changelog section for a service that does not exist is almost always a
    # typo in the name - and would otherwise silently never be shown.
    for lang, tree in parsed.items():
        for name in tree:
            if name not in services:
                problems.append(
                    f"{LANGUAGES[lang][0]}: '{name}' is not a service "
                    f"({', '.join(sorted(services))})"
                )

    manifest_services: dict[str, Any] = {}
    for service in sorted(services):
        version = current_version(service)
        entries = parsed["de"].get(service, {})
        other = parsed["en"].get(service, {})

        # The current version must be described, otherwise an update runs
        # through without a word of explanation.
        de_file, en_file = LANGUAGES["de"][0], LANGUAGES["en"][0]
        if version not in entries:
            problems.append(
                f"{de_file}: {service} {version} missing "
                f"(VERSION says {version}, described are: "
                f"{', '.join(sorted(entries, key=sort_key)) or 'none'})"
            )
        for missing in sorted(set(entries) - set(other)):
            problems.append(f"{en_file}: {service} {missing} missing")
        for extra in sorted(set(other) - set(entries)):
            problems.append(f"{de_file}: {service} {extra} missing")

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
        help="only check whether release/release-manifest.json matches the changelogs",
    )
    args = parser.parse_args()

    try:
        manifest = build()
    except ChangelogError as exc:
        print(f"Changelog does not match:\n{exc}", file=sys.stderr)
        return 1

    text = json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=False) + "\n"

    if args.check:
        if not MANIFEST.exists():
            print(
                f"{MANIFEST.name} is missing. Create it with: "
                "python3 scripts/build_manifest.py",
                file=sys.stderr,
            )
            return 1
        if MANIFEST.read_text(encoding="utf-8") != text:
            print(
                f"{MANIFEST.name} is not up to date. Regenerate with: "
                "python3 scripts/build_manifest.py",
                file=sys.stderr,
            )
            return 1
        print(f"{MANIFEST.name} is up to date.")
        return 0

    MANIFEST.write_text(text, encoding="utf-8")
    print(f"{MANIFEST.name} written: {len(manifest['services'])} services")
    for name, data in manifest["services"].items():
        print(f"  {name:18s} {data['latest']}  ({len(data['releases'])} entries)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
