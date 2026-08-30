#!/bin/bash
# Erzeugt gezielt einen der Fehlerzustaende, die "Ton-Problem beheben"
# erkennen und reparieren soll - zum Ausprobieren des Knopfs auf einer echten
# Box, ohne wirklich am Kabel zu wackeln.
#
# Laeuft direkt auf der Box (nicht im Container): braucht pactl, amixer,
# curl, jq und mosquitto_pub gegen die lokalen Dienste.
#
#   ./scripts/simulate-sound-fault.sh
#
# Zeigt ein Menu, wendet den gewaehlten Fehler an und sagt, was als naechstes
# zu tun ist. Ueber "r" laesst sich alles wieder in einen sauberen
# Ausgangszustand bringen, unabhaengig davon, ob der Reparatur-Knopf
# zwischendurch benutzt wurde.
#
# Zwei der sieben Kettenschritte fehlen bewusst:
#   - Schritt 1 (Soundkarte fehlt) laesst sich ohne Kernel-Modul-Eingriff und
#     Neustart nicht gefahrlos nachstellen - die App repariert ihn ohnehin
#     nicht automatisch.
#   - Schritt 6 (Dienst-Lautstaerke unter Minimum) klemmt der Dienst an jedem
#     Einstiegspunkt (Start, Config-Reload, set_volume) selbst auf min_volume -
#     mit dem aktuellen Code von aussen nicht reproduzierbar.

set -uo pipefail

BACKEND_URL="${BACKEND_URL:-http://localhost:8080}"
MQTT_HOST="${MQTT_HOST:-localhost}"
STATE_FILE="/tmp/minabox-fault-baseline.json"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

die() { echo -e "${RED}Fehler:${NC} $1" >&2; exit 1; }

for bin in curl jq pactl amixer mosquitto_pub; do
  command -v "$bin" >/dev/null 2>&1 || die "'$bin' fehlt - Skript läuft nur direkt auf der Box, nicht im Container."
done

DEVICE_ID="$(curl -sf "$BACKEND_URL/api/v1/system/status" | jq -r '.device_id // empty')"
[ -n "$DEVICE_ID" ] || die "Backend nicht erreichbar unter $BACKEND_URL (BACKEND_URL setzen?)."

CONFIG="$(curl -sf "$BACKEND_URL/api/v1/config/audio")" || die "Audio-Konfiguration nicht lesbar."
ORIG_OUTPUT_DEVICE="$(jq -r '.output_device_name // empty' <<<"$CONFIG")"
ORIG_MIN_VOLUME="$(jq -r '.min_volume // 0' <<<"$CONFIG")"
SINK="${ORIG_OUTPUT_DEVICE:-$(pactl get-default-sink 2>/dev/null)}"

CARD="$(aplay -l 2>/dev/null | grep -i wm8960 | head -1 | sed -n 's/^card \([0-9]*\).*/\1/p')"

WP_STATE="$HOME/.local/state/wireplumber/stream-properties"

# Nur beim ersten Start dieser Baseline schreiben, damit ein zweiter Fehler
# in derselben Sitzung nicht die urspruenglichen Werte ueberschreibt.
if [ ! -f "$STATE_FILE" ]; then
  jq -n --arg dev "$ORIG_OUTPUT_DEVICE" --arg minvol "$ORIG_MIN_VOLUME" \
    '{output_device_name: $dev, min_volume: ($minvol | tonumber)}' >"$STATE_FILE"
fi

status() { curl -sf "$BACKEND_URL/api/v1/audio/status"; }

set_config() { curl -sf -X PUT "$BACKEND_URL/api/v1/config/audio" -H 'Content-Type: application/json' -d "$1" >/dev/null; }

mute_role_music() {
  # Direkter Eingriff in WirePlumbers gemerkten Zustand - derselbe Mechanismus
  # wie der Rueckfall im Audio-Dienst, nur absichtlich ausgeloest.
  local target="$1"  # true|false
  [ -f "$WP_STATE" ] || die "WirePlumber-Zustandsdatei nicht gefunden: $WP_STATE"
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
  echo "-> output_device_name wird auf einen nicht existierenden Sink gesetzt."
  set_config "$(jq -n --arg dev "kaputter_sink_$RANDOM" '{output_device_name: $dev}')"
  echo -e "${YELLOW}Fehler aktiv:${NC} konfigurierter Lautsprecher ist weg. Erwartete Reparatur: Rueckfall auf einen vorhandenen Sink."
}

fault_sink_level() {
  [ -n "$SINK" ] || die "Kein Sink bekannt."
  echo "-> Sink '$SINK' wird stummgeschaltet und auf 10% gestellt."
  pactl set-sink-mute "$SINK" 1
  pactl set-sink-volume "$SINK" 10%
  echo -e "${YELLOW}Fehler aktiv:${NC} Sink stumm und leise. Erwartete Reparatur: entstummen, auf ~60% anheben."
}

fault_stream_state() {
  echo "-> Gemerkte Stummschaltung fuer die PipeWire-Rolle 'Music' wird gesetzt (WirePlumber-Neustart noetig)."
  mute_role_music true
  echo -e "${YELLOW}Fehler aktiv:${NC} jeder neue Music-Stream startet stumm. Erwartete Reparatur: laufenden Testton-Stream entstummen, WirePlumber merkt sich das."
}

fault_service_mute() {
  echo "-> Dienst wird ueber MQTT stummgeschaltet (wie am physischen Knopf)."
  ensure_service_muted true
  echo -e "${YELLOW}Fehler aktiv:${NC} self._muted=True im Audio-Dienst. Erwartete Reparatur: entstummen."
}

fault_alsa_mixer() {
  [ -n "$CARD" ] || die "wm8960-Karte nicht gefunden (aplay -l)."
  echo "-> ALSA-Regler 'Speaker' auf Karte $CARD wird auf 0% und stumm gesetzt."
  amixer -c "$CARD" sset Speaker 0% mute >/dev/null
  echo -e "${YELLOW}Fehler aktiv:${NC} Hardware-Mixer auf null. Erwartete Reparatur: auf ~80% anheben, entstummen."
}

reset_all() {
  echo "Setze alles zurueck..."
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
  echo -e "${GREEN}Zurueckgesetzt.${NC}"
}

print_menu() {
  echo ""
  echo -e "${BLUE}Minabox Ton-Fehler simulieren${NC}  (Sink: ${SINK:-?}, Karte: ${CARD:-?}, Geraet: $DEVICE_ID)"
  echo "  1) Konfigurierter Sink fehlt (sink_present)"
  echo "  2) Sink stumm/leise (sink_level)"
  echo "  3) Gemerkte Rollen-Stummschaltung in WirePlumber (stream_state)"
  echo "  4) Dienst selbst stummgeschaltet (service_mute)"
  echo "  5) ALSA-Mixer auf 0 (alsa_mixer)"
  echo "  r) Alles zuruecksetzen"
  echo "  q) Beenden"
  echo ""
  echo "Nach der Auswahl: WebUI -> Wartung -> \"Ton-Problem beheben\" klicken."
}

while true; do
  print_menu
  read -rp "Auswahl: " choice
  case "$choice" in
    1) fault_sink_present ;;
    2) fault_sink_level ;;
    3) fault_stream_state ;;
    4) fault_service_mute ;;
    5) fault_alsa_mixer ;;
    r|R) reset_all ;;
    q|Q) exit 0 ;;
    *) echo "Ungueltige Auswahl." ;;
  esac
done
