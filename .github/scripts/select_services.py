#!/usr/bin/env python3
"""Entscheidet, welche Dienste dieser CI-Lauf bauen muss.

Gebaut wird, was sich geaendert hat. Der Grund steht in
docs/Versionierung.md: jeder Dienst traegt seine eigene Versionsnummer, und
ein unveraenderter Dienst darf nicht erneut unter seiner alten Nummer in die
Registry wandern - sonst zeigt derselbe Tag auf verschiedene Staende.

Im Zweifel wird alles gebaut. Ein zu grosser Lauf kostet Zeit, ein zu kleiner
laesst ein Image zurueck, das niemand vermisst, bis es fehlt.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

# name -> (Image-Name, Build-Context, Dockerfile)
# Acht Dienste bauen aus ./services, weil sie shared-lib brauchen; webui hat
# einen eigenen, engeren Context.
SERVICES: dict[str, tuple[str, str, str]] = {
    "backend": ("minabox-backend", "./services", "./services/backend-service/Dockerfile"),
    "host-helper": ("minabox-host-helper", "./services", "./services/host-helper-service/Dockerfile"),
    "audio": ("minabox-audio", "./services", "./services/audio-service/Dockerfile"),
    "rfid": ("minabox-rfid", "./services", "./services/rfid-service/Dockerfile"),
    "button": ("minabox-button", "./services", "./services/button-service/Dockerfile"),
    "led": ("minabox-led", "./services", "./services/led-service/Dockerfile"),
    "display": ("minabox-display", "./services", "./services/display-service/Dockerfile"),
    "media-downloader": ("minabox-media-downloader", "./services", "./services/media-downloader-service/Dockerfile"),
    "webui": ("minabox-webui", "./services/webui-service", "./services/webui-service/Dockerfile"),
}

# webui bindet shared-lib nicht ein (eigener Context, kein Python).
SHARED_LIB_DEPENDENTS = [n for n in SERVICES if n != "webui"]

NULL_SHA = "0" * 40


def run(*args: str) -> str | None:
    try:
        return subprocess.run(
            args, capture_output=True, text=True, check=True
        ).stdout
    except subprocess.CalledProcessError:
        return None


def changed_files(base: str, head: str) -> list[str] | None:
    """Geaenderte Pfade zwischen zwei Commits, oder None wenn unbestimmbar."""
    if not base or base == NULL_SHA:
        return None
    if run("git", "cat-file", "-e", f"{base}^{{commit}}") is None:
        # Nach einem Force-Push oder beim ersten Push existiert der alte Stand
        # hier nicht mehr.
        return None
    out = run("git", "diff", "--name-only", base, head)
    if out is None:
        return None
    return [line for line in out.splitlines() if line]


def select(files: list[str]) -> tuple[list[str], list[str]]:
    """Zu bauende Dienste plus die Begruendungen dafuer."""
    selected: set[str] = set()
    reasons: list[str] = []

    # Der Workflow selbst loest bewusst keinen Rebuild aus. Er veraendert kein
    # Image-Inhalt; was ein Image wirklich aendert - Dockerfile, Quelltext,
    # Requirements - liegt unter services/<dienst>-service/ und wird unten
    # erfasst. Wuerde eine Aenderung an der Bauvorschrift alle neun Dienste
    # neu bauen, landeten unveraenderte Dienste erneut unter ihrer bereits
    # veroeffentlichten Nummer - genau das, was die Versionierung verhindern
    # soll. Ist ein Build-Umbau doch inhaltlich relevant, gehoert die VERSION
    # angehoben, und schon steht der Dienst hier wieder drin.
    shared = [f for f in files if f.startswith("services/shared-lib/")]
    if shared:
        selected.update(SHARED_LIB_DEPENDENTS)
        reasons.append("shared-lib geaendert - alle Dienste ausser webui")

    for name in SERVICES:
        prefix = f"services/{name}-service/"
        hits = [f for f in files if f.startswith(prefix)]
        if hits:
            selected.add(name)
            reasons.append(f"{name}: {len(hits)} Datei(en) geaendert")

    return sorted(selected), reasons


def main() -> int:
    head = os.environ.get("GITHUB_SHA", "HEAD")
    build_all = os.environ.get("BUILD_ALL", "").lower() == "true"

    if build_all:
        names, reasons = sorted(SERVICES), ["Alle Dienste angefordert"]
    else:
        files = changed_files(os.environ.get("BEFORE", ""), head)
        if files is None:
            names, reasons = sorted(SERVICES), [
                "Kein Vergleichspunkt zum vorherigen Stand - vorsichtshalber alle Dienste"
            ]
        else:
            names, reasons = select(files)

    include = [
        {"name": n, "image": SERVICES[n][0], "context": SERVICES[n][1], "dockerfile": SERVICES[n][2]}
        for n in names
    ]
    matrix = json.dumps({"include": include}, separators=(",", ":"))

    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as fh:
            fh.write(f"matrix={matrix}\n")
            fh.write(f"any={'true' if include else 'false'}\n")

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    lines = ["### Zu bauende Dienste", ""]
    lines += [f"- {r}" for r in reasons] or ["- Keine Aenderung an einem Dienst"]
    lines += ["", f"**Auswahl:** {', '.join(names) if names else 'nichts zu tun'}"]
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
