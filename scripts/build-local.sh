#!/usr/bin/env bash
# Baut Minabox-Images auf dieser Maschine - mit den Versionsnummern aus den
# VERSION-Dateien.
#
# Warum ein Skript und nicht "docker compose build": Compose kann keine Datei
# als Build-Arg lesen. Ohne die Argumente traegt jedes lokal gebaute Image
# 0.0.0-dev, und die Oberflaeche zeigt "Entwicklungsbuild" statt einer Nummer
# (docs/Versionierung.md).
#
#   ./scripts/build-local.sh                # alle Dienste
#   ./scripts/build-local.sh backend webui  # nur diese
#
# Die "+local"-Kennzeichnung im Versionsstring ist Absicht: das Image stammt
# aus diesem Arbeitsbaum, nicht aus der CI, und soll nicht mit dem Release
# gleicher Nummer verwechselt werden.

set -euo pipefail

cd "$(dirname "$0")/.."

ALL_SERVICES=(backend host-helper audio rfid button led display media-downloader webui)
SERVICES=("${@:-}")
if [ -z "${SERVICES[0]:-}" ]; then
  SERVICES=("${ALL_SERVICES[@]}")
fi

GIT_SHA="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
if ! git diff --quiet 2>/dev/null || ! git diff --cached --quiet 2>/dev/null; then
  GIT_SHA="${GIT_SHA}-dirty"
fi
BUILD_DATE="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

for name in "${SERVICES[@]}"; do
  dir="services/${name}-service"
  if [ ! -f "$dir/VERSION" ]; then
    echo "Kein $dir/VERSION - unbekannter Dienst: $name" >&2
    exit 1
  fi
  version="$(tr -d '[:space:]' < "$dir/VERSION")+local"

  # webui hat einen eigenen, engeren Build-Context (kein shared-lib) - genau
  # wie in der CI.
  context="./services"
  [ "$name" = "webui" ] && context="./services/webui-service"

  echo "==> ${name} ${version}"
  docker build \
    -f "$dir/Dockerfile" \
    --build-arg "APP_VERSION=$version" \
    --build-arg "GIT_SHA=$GIT_SHA" \
    --build-arg "BUILD_DATE=$BUILD_DATE" \
    -t "ghcr.io/opnek90/minabox-${name}:latest" \
    "$context"
done

echo
echo "Fertig. Uebernehmen mit:  docker compose up -d ${SERVICES[*]}"
