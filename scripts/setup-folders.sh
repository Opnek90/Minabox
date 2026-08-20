#!/usr/bin/env bash
# Create the standard Minabox directory structure and seed the service configs
# that are gitignored (e.g. after a fresh clone). Run from anywhere.
#
# Idempotent: existing config files are never overwritten.

set -e
cd "$(dirname "$0")/.."

mkdir -p docs/services/{rfid,audio,webui,api,database,hardware,led,button,host-helper} \
         services/{rfid-service,audio-service,backend-service,webui-service,led-service,button-service,display-service,host-helper-service} \
         services/audio-service/state \
         infrastructure/mosquitto/config \
         data \
         audio/tracks

# Seed the gitignored per-service configs from their .example templates.
# Without these the containers start against a missing config file.
seed_config() {
    local target="$1"
    local template="${target}.example"

    if [ ! -f "$template" ]; then
        echo "  ! template missing: $template" >&2
        return 0
    fi
    if [ -f "$target" ]; then
        echo "  = kept existing $target"
        return 0
    fi
    cp "$template" "$target"
    echo "  + seeded $target"
}

seed_config services/audio-service/config/audio.json
seed_config services/led-service/config/leds.json
seed_config services/button-service/config/buttons.json
seed_config services/display-service/config/display.json

echo "Directory structure created."
