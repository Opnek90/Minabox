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

# The catalogue of optional components. It lives in the backend, because the
# backend ships it inside its image and serves it to the WebUI even when the
# box has never reached the internet; the manifest carries a copy so a
# description can be corrected without a new backend image (#181).
COMPONENTS = (
    SERVICES_DIR
    / "backend-service"
    / "src"
    / "backend_service"
    / "resources"
    / "components.json"
)

# language -> (changelog file, allowed section headings)
LANGUAGES: dict[str, tuple[str, tuple[str, ...]]] = {
    "de": ("release/CHANGELOG.md", ("Neu", "Verbessert", "Behoben")),
    "en": ("release/CHANGELOG.en.md", ("Added", "Improved", "Fixed")),
}

# The sections appear in both languages in the same order; that is how they are
# joined, without needing a translation table.
CATEGORY_KEYS = ("added", "improved", "fixed")

# 3: the "components" block - what an optional component is for, what hardware
# it needs and whether it needs the network. Older boxes ignore the field;
# newer ones fall back to the copy in their own image when it is missing.
# 4: "requires" per release - what that version needs from the other services.
# A box that does not read the field behaves as it always did.
SCHEMA_VERSION = 4

# What a release needs from the other services. One optional file per service,
# next to its VERSION:
#
#     {"0.2.2": {"backend": ">=0.4.0"}}
#
# Keyed by version and not by service, because a requirement belongs to the
# release that introduced it: the manifest carries the older entries too, and
# they have to keep saying what was true when they were built. Next to VERSION
# and not in the changelogs, because it is read by machines - a line that has
# to be kept identical in two languages is a line that will drift.
REQUIRES_NAME = "requires.json"

RE_SERVICE = re.compile(r"^##\s+(?P<name>[a-z0-9][a-z0-9-]*)\s*$")
RE_VERSION = re.compile(
    r"^###\s+(?P<version>\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?)\s+-\s+(?P<date>\d{4}-\d{2}-\d{2})\s*$"
)
RE_CATEGORY = re.compile(r"^####\s+(?P<name>.+?)\s*$")
RE_ITEM = re.compile(r"^-\s+(?P<text>.+?)\s*$")

# The only expression a requirement may use: a minimum version. That covers
# what actually happens - new code needs an interface that exists from a
# certain version on - and nothing more. An upper bound would be a statement
# about a release nobody has seen yet, made by whoever happens to be writing
# the older one.
RE_REQUIREMENT = re.compile(r"^>=\s*(?P<version>\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?)$")


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


def channel_of(version: str) -> str:
    """Which update channel a version belongs to.

    The version string decides, nothing else: a pre-release marker
    (``0.3.0-rc1``) means beta, everything else is stable. That keeps the
    channel out of the changelog format - there is no second place where it
    could be set wrong, and a version cannot claim to be a finished release
    while carrying a release-candidate number.
    """
    return "beta" if "-" in version else "stable"


def read_requires(
    service: str, described: set[str], services: set[str]
) -> tuple[dict[str, dict[str, str]], list[str]]:
    """Per version of *service*, what it needs from the other services.

    The file is optional - most releases need nothing from anyone - but every
    key in one that exists is checked. A version no changelog entry describes,
    or a service name with a typo in it, would otherwise be a requirement that
    applies to nothing and never says so; the box would go on offering the
    combination the line was written to prevent.

    Returns the problems instead of raising, so a run names all of them at
    once, like the changelog checks above.
    """
    path = SERVICES_DIR / f"{service}-service" / REQUIRES_NAME
    if not path.exists():
        return {}, []

    where = f"{service}-service/{REQUIRES_NAME}"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as e:
        return {}, [f"{where}: not readable as JSON ({e})"]
    if not isinstance(data, dict):
        return {}, [f"{where}: expected an object of version -> requirements"]

    problems: list[str] = []
    result: dict[str, dict[str, str]] = {}
    for version, block in data.items():
        if version not in described:
            problems.append(
                f"{where}: {version} is not described in the changelog "
                f"({', '.join(sorted(described, key=sort_key)) or 'nothing is'})"
            )
        if not isinstance(block, dict) or not block:
            problems.append(
                f"{where}: {version} needs an object of service -> '>=version'"
            )
            continue

        entry: dict[str, str] = {}
        for other, expression in block.items():
            if other == service:
                problems.append(f"{where}: {version} requires itself")
            elif other not in services:
                problems.append(
                    f"{where}: '{other}' is not a service "
                    f"({', '.join(sorted(services))})"
                )
            elif not isinstance(expression, str) or not RE_REQUIREMENT.match(
                expression
            ):
                problems.append(
                    f"{where}: {version} -> {other}: expected a minimum version "
                    f"like '>=0.4.0', got {expression!r}"
                )
            else:
                entry[other] = expression
        if entry:
            result[version] = entry
    return result, problems


def base_version(version: str) -> str:
    """The version without its pre-release marker: 0.3.0-rc.1 -> 0.3.0."""
    return version.partition("-")[0]


def parked_candidates(
    tree: dict[str, dict[str, dict[str, Any]]], services: set[str]
) -> list[tuple[str, str, str | None]]:
    """The services whose VERSION is still a release candidate.

    This comes from an incident. The announcements went out as a beta bundle -
    backend, audio, webui and host-helper together - and the release that
    followed promoted only backend and webui. Audio and host-helper kept their
    candidate, so no stable image of them was ever built: CI takes the tag from
    the VERSION file, and it still said "-rc.1". A box on the stable channel got
    the feature in backend and webui, with an audio that could not play an
    announcement and a host-helper that did not know the profile to switch it
    on. Nothing said a word.

    Nothing about a candidate is wrong in itself, which is why this is a report
    and not a verdict: while a beta is being tried out, this is exactly the
    state the box is meant to be in. What went missing was somebody saying so
    at the moment the other half of the bundle was promoted - and that moment
    is a run of this script.

    Deliberately read from the VERSION files rather than from the changelog.
    Promoting a candidate is sometimes written as a second entry above it and
    sometimes as a replacement of it, so the changelog does not reliably say
    which candidates are still open - but the VERSION file always does.
    """
    parked: list[tuple[str, str, str | None]] = []
    for service in sorted(services):
        version = current_version(service)
        if channel_of(version) != "beta":
            continue
        date = (tree.get(service, {}).get(version) or {}).get("date")
        parked.append((service, version, date))
    return parked


def check_parked_candidates(
    tree: dict[str, dict[str, dict[str, Any]]], services: set[str]
) -> list[str]:
    """Refuse a candidate the project has already released past.

    One release day of grace: a bundle put out today, and a promotion later the
    same day, both stay quiet - the candidate is simply in flight. Once another
    service has published a *finished* release on a later day, the project has
    moved on and this one was forgotten. That is the point at which it stops
    being a beta and becomes a version whose image nobody will ever build.
    """
    last_stable_day = ""
    for versions in tree.values():
        for version, body in versions.items():
            if channel_of(version) == "stable":
                last_stable_day = max(last_stable_day, body.get("date") or "")

    problems: list[str] = []
    for service, version, date in parked_candidates(tree, services):
        if date and last_stable_day > date:
            problems.append(
                f"{service} is still on {version} from {date}, while other "
                f"services have published finished releases since "
                f"({last_stable_day}). Promote it, or take it back - a "
                f"candidate nobody promotes is a version whose image is "
                f"never built."
            )
    return problems


def read_components(services: set[str]) -> dict[str, Any]:
    """The component catalogue, checked against the services that exist.

    Checked here and not only in the backend: a typo in the service name would
    otherwise reach a box as a component whose version can never be found.

    Not every addon has a service, though: one whose ``install`` says
    ``{"type": "setting"}`` lives inside the backend image and is switched on
    by writing a field, not by pulling a container - it has no service to
    check the name of, on purpose (``core/component_catalog.py``).
    """
    data = json.loads(COMPONENTS.read_text(encoding="utf-8"))
    components = data.get("components")
    if not isinstance(components, dict):
        raise ChangelogError(f"  - {COMPONENTS.name}: no 'components' object")

    problems: list[str] = []
    for profile, entry in components.items():
        where = f"{COMPONENTS.name}: {profile}"
        service = entry.get("service")
        install = entry.get("install")
        is_setting = isinstance(install, dict) and install.get("type") == "setting"
        if is_setting:
            if service is not None:
                problems.append(f"{where}: a setting addon must not name a service")
        elif service not in services:
            problems.append(f"{where}: '{service}' is not a service")
        for field in ("name", "summary", "hardware"):
            value = entry.get(field)
            # hardware is null for a component that needs no accessory; name
            # and summary are not optional - a component the WebUI cannot even
            # name is worse than one it does not list.
            if value is None and field == "hardware":
                continue
            if not isinstance(value, dict) or not all(
                isinstance(value.get(lang), str) and value.get(lang)
                for lang in LANGUAGES
            ):
                problems.append(
                    f"{where}: {field} needs a text in "
                    f"{' and '.join(LANGUAGES)}"
                )
        if not isinstance(entry.get("network"), bool):
            problems.append(f"{where}: network has to be true or false")
    if problems:
        raise ChangelogError("\n".join(f"  - {p}" for p in problems))
    return components


def build() -> tuple[dict[str, Any], list[tuple[str, str, str | None]]]:
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

        # The newest described version has to be the one that is built.
        # Otherwise the manifest offers a tag that no CI run ever pushed -
        # and the registry check on the box would quietly hide it forever.
        if entries:
            newest_described = sorted(entries, key=sort_key)[-1]
            if newest_described != version:
                problems.append(
                    f"{de_file}: {service} describes {newest_described}, "
                    f"but VERSION says {version}"
                )

        requires, requires_problems = read_requires(service, set(entries), services)
        problems.extend(requires_problems)

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
            release: dict[str, Any] = {
                "version": release_version,
                "date": german.get("date"),
                "channel": channel_of(release_version),
            }
            # Left out where there is nothing to say, which is the normal
            # case: an empty object in every one of a hundred entries would
            # make the field look like a formality rather than a statement.
            if release_version in requires:
                release["requires"] = requires[release_version]
            release["notes"] = notes
            releases.append(release)

        # "latest" stays what it always was: the newest *finished* version. A
        # box that knows nothing about channels reads that field and therefore
        # never lands on a release candidate by accident. The beta channel is
        # a second field on top, and only appears when there is something in
        # it that stable does not have.
        stable = [r["version"] for r in releases if r["channel"] == "stable"]
        newest = releases[0]["version"] if releases else version
        entry: dict[str, Any] = {
            "latest": stable[0] if stable else None,
            "releases": releases,
        }
        if newest != entry["latest"]:
            entry["latest_beta"] = newest
        manifest_services[service] = entry

    # Last, so a run names the ordinary mistakes first: this one is about an
    # earlier release, not about the file being edited.
    problems.extend(check_parked_candidates(parsed["de"], services))

    if problems:
        raise ChangelogError("\n".join(f"  - {p}" for p in problems))

    return {
        "schema": SCHEMA_VERSION,
        "registry": "ghcr.io/opnek90",
        "services": manifest_services,
        "components": read_components(services),
    }, parked_candidates(parsed["de"], services)


def report_parked(parked: list[tuple[str, str, str | None]]) -> None:
    """Name the open candidates, every single run.

    The whole point: whoever promotes half a bundle reads this line while doing
    it. Printed rather than raised - a candidate in flight is a legitimate
    state, and a check that cries wolf gets ignored. check_parked_candidates()
    is what turns it into a refusal once the project has released past it.
    """
    if not parked:
        return
    print()
    print("Still on a release candidate - no stable image is being built:")
    for service, version, date in parked:
        since = f"  since {date}" if date else ""
        print(f"  {service:18s} {version}{since}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="only check whether release/release-manifest.json matches the changelogs",
    )
    args = parser.parse_args()

    try:
        manifest, parked = build()
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
        report_parked(parked)
        return 0

    MANIFEST.write_text(text, encoding="utf-8")
    print(
        f"{MANIFEST.name} written: {len(manifest['services'])} services, "
        f"{len(manifest['components'])} optional components"
    )
    for name, data in manifest["services"].items():
        print(f"  {name:18s} {data['latest']}  ({len(data['releases'])} entries)")
    report_parked(parked)
    return 0


if __name__ == "__main__":
    sys.exit(main())
