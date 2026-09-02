#!/usr/bin/env python3
"""Decides which services this CI run has to build.

A service is built exactly when its ``VERSION`` file changed. That is the whole
rule, and it follows directly from the versioning model: every service carries
its own number, and an image tag is immutable - the same number must never point
at two different builds. So a build is only meaningful once the number has moved.

The practical effect: touching a comment, a README, a test or the CI itself does
*not* trigger a rebuild, because none of that changes the published number. When
a change to build inputs (Dockerfile, source, requirements) is worth shipping,
its ``VERSION`` gets bumped in the same commit and the service reappears here.

If the previous state cannot be determined (first push, force-push), everything
is built - a run that is too large costs time, one that is too small leaves an
image behind that nobody misses until it is gone.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

# Build order is not significant; the matrix runs them in parallel.
SERVICE_NAMES = [
    "backend",
    "host-helper",
    "audio",
    "rfid",
    "button",
    "led",
    "display",
    "media-downloader",
    "tts",
    "webui",
]


def _service_entry(name: str) -> tuple[str, str, str]:
    """(image name, build context, Dockerfile) for a service.

    Every service builds from ``./services`` because it needs shared-lib on the
    build context; webui is the exception with its own, narrower context.
    """
    context = "./services/webui-service" if name == "webui" else "./services"
    return (f"minabox-{name}", context, f"./services/{name}-service/Dockerfile")


SERVICES: dict[str, tuple[str, str, str]] = {
    n: _service_entry(n) for n in SERVICE_NAMES
}

# webui does not bundle shared-lib (its own context, no Python).
SHARED_LIB_DEPENDENTS = [n for n in SERVICE_NAMES if n != "webui"]

NULL_SHA = "0" * 40


def run(*args: str) -> str | None:
    try:
        return subprocess.run(
            args, capture_output=True, text=True, check=True
        ).stdout
    except subprocess.CalledProcessError:
        return None


def changed_files(base: str, head: str) -> list[str] | None:
    """Changed paths between two commits, or None if it cannot be determined."""
    if not base or base == NULL_SHA:
        return None
    if run("git", "cat-file", "-e", f"{base}^{{commit}}") is None:
        # After a force-push, or on the very first push, the old state is not
        # available here anymore.
        return None
    out = run("git", "diff", "--name-only", base, head)
    if out is None:
        return None
    return [line for line in out.splitlines() if line]


def select(files: list[str]) -> tuple[list[str], list[str]]:
    """Services to build, plus the reason for each.

    Selection is keyed on the ``VERSION`` file alone. A service whose Dockerfile
    or source changed without a version bump is deliberately *not* rebuilt: its
    published number would otherwise end up pointing at a new image. When such a
    change matters, the release commit bumps the number and the service lands
    here again.
    """
    changed = set(files)
    selected: set[str] = set()
    reasons: list[str] = []

    # A shared-lib version bump forces every dependent to rebuild. The release
    # checklist already bumps all dependent VERSION files alongside it, so they
    # would be picked up below too - this is the safety net that does not rely
    # on the checklist being followed perfectly.
    if "services/shared-lib/VERSION" in changed:
        selected.update(SHARED_LIB_DEPENDENTS)
        reasons.append("shared-lib VERSION bumped - all services except webui")

    for name in SERVICE_NAMES:
        if f"services/{name}-service/VERSION" in changed:
            selected.add(name)
            reasons.append(f"{name}: VERSION bumped")

    return sorted(selected), reasons


def main() -> int:
    head = os.environ.get("GITHUB_SHA", "HEAD")
    build_all = os.environ.get("BUILD_ALL", "").lower() == "true"

    if build_all:
        names, reasons = sorted(SERVICES), ["all services requested"]
    else:
        files = changed_files(os.environ.get("BEFORE", ""), head)
        if files is None:
            names, reasons = sorted(SERVICES), [
                "no comparison point to the previous state - building all services"
            ]
        else:
            names, reasons = select(files)

    include = [
        {
            "name": n,
            "image": SERVICES[n][0],
            "context": SERVICES[n][1],
            "dockerfile": SERVICES[n][2],
        }
        for n in names
    ]
    matrix = json.dumps({"include": include}, separators=(",", ":"))

    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as fh:
            fh.write(f"matrix={matrix}\n")
            fh.write(f"any={'true' if include else 'false'}\n")

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    lines = ["### Services to build", ""]
    lines += [f"- {r}" for r in reasons] or ["- no VERSION file changed"]
    lines += ["", f"**Selection:** {', '.join(names) if names else 'nothing to do'}"]
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
