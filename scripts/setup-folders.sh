#!/usr/bin/env bash
# Create standard Minabox directory structure (e.g. after fresh clone).
# Run from repository root.

set -e
cd "$(dirname "$0")/.."

mkdir -p docs/services/{rfid,audio,webui,api,database,hardware,led,button,host-helper} \
         services/{rfid-service,audio-service,backend-service,webui-service,led-service,button-service,display-service,host-helper-service} \
         infrastructure/mosquitto/config \
         data \
         audio/tracks

echo "Directory structure created."
