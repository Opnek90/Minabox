#!/bin/bash
# Deliberately produces one of the fault states that "Fix sound problem" is
# meant to detect and repair - to try the button on a real box without actually
# wiggling a cable.
#
# Runs directly on the box (not in the container): needs pactl, amixer, curl,
# jq and mosquitto_pub against the local services.
#
#   ./scripts/simulate-sound-fault.sh
#
# Shows a menu, applies the chosen fault and says what to do next. "r" brings
# everything back to a clean starting state, regardless of whether the repair
# button was used in between.
#
# Two of the seven chain steps are deliberately missing:
#   - Step 1 (sound card missing) cannot be reproduced safely without touching a
#     kernel module and rebooting - and the app does not repair it
#     automatically anyway.
#   - Step 6 (service volume below the minimum) is clamped by the service to
#     min_volume at every entry point (start, config reload, set_volume) - not
#     reproducible from the outside with the current code.

set -uo pipefail

BACKEND_URL="${BACKEND_URL:-http://localhost:8080}"
MQTT_HOST="${MQTT_HOST:-localhost}"
STATE_FILE="/tmp/minabox-fault-baseline.json"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

die() { echo -e "${RED}Error:${NC} $1" >&2; exit 1; }

for bin in curl jq pactl amixer mosquitto_pub; do
  command -v "$bin" >/dev/null 2>&1 || die "'$bin' missing - this script runs only directly on the box, not in the container."
done

DEVICE_ID="$(curl -sf "$BACKEND_URL/api/v1/system/status" | jq -r '.device_id // empty')"
[ -n "$DEVICE_ID" ] || die "Backend not reachable at $BACKEND_URL (set BACKEND_URL?)."

CONFIG="$(curl -sf "$BACKEND_URL/api/v1/config/audio")" || die "Audio configuration not readable."
ORIG_OUTPUT_DEVICE="$(jq -r '.output_device_name // empty' <<<"$CONFIG")"
ORIG_MIN_VOLUME="$(jq -r '.min_volume // 0' <<<"$CONFIG")"
SINK="${ORIG_OUTPUT_DEVICE:-$(pactl get-default-sink 2>/dev/null)}"

CARD="$(aplay -l 2>/dev/null | grep -i wm8960 | head -1 | sed -n 's/^card \([0-9]*\).*/\1/p')"

WP_STATE="$HOME/.local/state/wireplumber/stream-properties"

# Write this baseline only on the first start, so a second fault in the same
# session does not overwrite the original values.
if [ ! -f "$STATE_FILE" ]; then
  jq -n --arg dev "$ORIG_OUTPUT_DEVICE" --arg minvol "$ORIG_MIN_VOLUME" \
    '{output_device_name: $dev, min_volume: ($minvol | tonumber)}' >"$STATE_FILE"
fi

status() { curl -sf "$BACKEND_URL/api/v1/audio/status"; }

set_config() { curl -sf -X PUT "$BACKEND_URL/api/v1/config/audio" -H 'Content-Type: application/json' -d "$1" >/dev/null; }

mute_role_music() {
  # A direct edit of WirePlumber's remembered state - the same mechanism as the
  # fallback in the audio service, only triggered on purpose.
  local target="$1"  # true|false
  [ -f "$WP_STATE" ] || die "WirePlumber state file not found: $WP_STATE"
  systemctl --user stop wireplumber
  sleep 1
  python3 - "$WP_STATE" "$target" <<'PY'
import re, sys
path, target = sys.argv[1], sys.argv[2]
text = open(path, encoding="utf-8").read()
pattern = re.compile(r'(Output/Audio:media\.role:Music=\{.*?"mute":\s*)(true|false)')
if pattern.search(text):
    text = pattern.sub(rf'\g<1>{target}', text, count=1)
else:
    text += f'\nOutput/Audio:media.role:Music={{"mute":{target}}}\n'
open(path, "w", encoding="utf-8").write(text)
PY
  systemctl --user start wireplumber
  sleep 2
}

ensure_service_muted() {
  local target="$1"  # true|false
  local current
  current="$(status | jq -r '.status.muted // false')"
  if [ "$current" != "$target" ]; then
    mosquitto_pub -h "$MQTT_HOST" -t "minabox/$DEVICE_ID/audio/mute-toggle" -m '{}'
    sleep 1
  fi
}

fault_sink_present() {
  echo "-> output_device_name is set to a non-existent sink."
  set_config "$(jq -n --arg dev "broken_sink_$RANDOM" '{output_device_name: $dev}')"
  echo -e "${YELLOW}Fault active:${NC} the configured speaker is gone. Expected repair: fall back to an existing sink."
}

fault_sink_level() {
  [ -n "$SINK" ] || die "No sink known."
  echo "-> sink '$SINK' is muted and set to 10%."
  pactl set-sink-mute "$SINK" 1
  pactl set-sink-volume "$SINK" 10%
  echo -e "${YELLOW}Fault active:${NC} sink muted and quiet. Expected repair: unmute, raise to ~60%."
}

fault_stream_state() {
  echo "-> a remembered mute for the PipeWire role 'Music' is set (WirePlumber restart needed)."
  mute_role_music true
  echo -e "${YELLOW}Fault active:${NC} every new Music stream starts muted. Expected repair: unmute the running test-tone stream, WirePlumber remembers it."
}

fault_service_mute() {
  echo "-> the service is muted over MQTT (as with the physical button)."
  ensure_service_muted true
  echo -e "${YELLOW}Fault active:${NC} self._muted=True in the audio service. Expected repair: unmute."
}

fault_alsa_mixer() {
  [ -n "$CARD" ] || die "wm8960 card not found (aplay -l)."
  echo "-> the ALSA control 'Speaker' on card $CARD is set to 0% and muted."
  amixer -c "$CARD" sset Speaker 0% mute >/dev/null
  echo -e "${YELLOW}Fault active:${NC} hardware mixer at zero. Expected repair: raise to ~80%, unmute."
}

reset_all() {
  echo "Resetting everything..."
  local base_dev base_min
  base_dev="$(jq -r '.output_device_name' "$STATE_FILE" 2>/dev/null)"
  base_min="$(jq -r '.min_volume' "$STATE_FILE" 2>/dev/null)"
  if [ -n "$base_dev" ] && [ "$base_dev" != "null" ]; then
    set_config "$(jq -n --arg dev "$base_dev" '{output_device_name: $dev}')"
  fi
  if [ -n "$base_min" ] && [ "$base_min" != "null" ]; then
    set_config "$(jq -n --arg m "$base_min" '{min_volume: ($m | tonumber)}')"
  fi
  [ -n "$SINK" ] && pactl set-sink-mute "$SINK" 0 && pactl set-sink-volume "$SINK" 60%
  mute_role_music false
  ensure_service_muted false
  if [ -n "$CARD" ]; then
    amixer -c "$CARD" sset Speaker 80% unmute >/dev/null
  fi
  rm -f "$STATE_FILE"
  echo -e "${GREEN}Reset.${NC}"
}

print_menu() {
  echo ""
  echo -e "${BLUE}Simulate a Minabox sound fault${NC}  (sink: ${SINK:-?}, card: ${CARD:-?}, device: $DEVICE_ID)"
  echo "  1) Configured sink missing (sink_present)"
  echo "  2) Sink muted/quiet (sink_level)"
  echo "  3) Remembered role mute in WirePlumber (stream_state)"
  echo "  4) Service itself muted (service_mute)"
  echo "  5) ALSA mixer at 0 (alsa_mixer)"
  echo "  r) Reset everything"
  echo "  q) Quit"
  echo ""
  echo "After choosing: click WebUI -> Maintenance -> \"Fix sound problem\"."
}

while true; do
  print_menu
  read -rp "Choice: " choice
  case "$choice" in
    1) fault_sink_present ;;
    2) fault_sink_level ;;
    3) fault_stream_state ;;
    4) fault_service_mute ;;
    5) fault_alsa_mixer ;;
    r|R) reset_all ;;
    q|Q) exit 0 ;;
    *) echo "Invalid choice." ;;
  esac
done
