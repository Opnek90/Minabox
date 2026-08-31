#!/usr/bin/env bash
# Builds Minabox images on this machine - with the version numbers from the
# VERSION files.
#
# Why a script and not "docker compose build": Compose cannot read a file as a
# build arg. Without the arguments every locally built image carries 0.0.0-dev,
# and the interface shows "development build" instead of a number.
#
#   ./scripts/build-local.sh                # all services
#   ./scripts/build-local.sh backend webui  # just these
#
# Built under the ":local" tag, not ":latest". Two reasons:
#
#   1. Overwriting ":latest" would hide the local reference to the real image
#      from the registry.
#   2. After an update through the interface, .env holds a fixed version for
#      each service. Compose then pulls exactly that - a locally built ":latest"
#      would never be used, and you would unknowingly test the old state.
#
# To try it out, set the variable for that one call only; a shell variable
# beats .env, so no file has to be touched:
#
#   MINABOX_WEBUI_TAG=local docker compose up -d webui   # local build
#   docker compose up -d webui                           # back to the real state
#
# The "+local" marker in the version string is deliberate: the image comes from
# this working tree, not from CI, and must not be confused with the release of
# the same number.

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
    echo "No $dir/VERSION - unknown service: $name" >&2
    exit 1
  fi
  version="$(tr -d '[:space:]' < "$dir/VERSION")+local"

  # webui has its own, narrower build context (no shared-lib) - exactly as in
  # CI.
  context="./services"
  [ "$name" = "webui" ] && context="./services/webui-service"

  echo "==> ${name} ${version}"
  docker build \
    -f "$dir/Dockerfile" \
    --build-arg "APP_VERSION=$version" \
    --build-arg "GIT_SHA=$GIT_SHA" \
    --build-arg "BUILD_DATE=$BUILD_DATE" \
    -t "ghcr.io/opnek90/minabox-${name}:local" \
    "$context"
done

# Assemble the tag variables for the test call, so they do not have to be typed
# per service by hand.
overrides=""
for name in "${SERVICES[@]}"; do
  var="MINABOX_$(printf '%s' "$name" | tr '[:lower:]-' '[:upper:]_')_TAG"
  overrides="${overrides}${var}=local "
done

echo
echo "Done. To test:"
echo "  ${overrides}docker compose up -d ${SERVICES[*]}"
echo
echo "Afterwards, back to the published state:"
echo "  docker compose up -d ${SERVICES[*]}"
