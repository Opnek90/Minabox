#!/usr/bin/env bash
#
# Minabox installation wizard
# ==================================================
#
#   curl -fsSL https://raw.githubusercontent.com/Opnek90/Minabox/main/install.sh -o minabox-install.sh
#   bash minabox-install.sh
#
# Deliberately in two steps and not as "curl | bash": whiptail needs a real
# TTY on stdin, which a pipe does not provide. If someone does pipe it, we get
# stdin back from /dev/tty further down.
#
# A second run on an already installed system opens the maintenance menu
# instead of a fresh install.

set -euo pipefail

readonly REPO_URL="https://github.com/Opnek90/Minabox.git"
readonly DEFAULT_DIR="$HOME/minabox"
readonly LOGFILE="$HOME/minabox-install.log"
readonly SYSTEMD_UNIT="/etc/systemd/system/minabox.service"

# Pflichtkomponenten - ohne Profil in docker-compose.yml, laufen immer.
readonly REQUIRED_SERVICES="mqtt backend host-helper audio webui"

LANG_CODE="de"
LANG_SET=0
TARGET_DIR=""
UNATTENDED=0
DRY_RUN=0
COMPONENTS=""
COMPONENTS_SET=0
REBOOT_REQUIRED=0
USE_WHIPTAIL=1

# Filled by pin_service_versions(): a fixed version per service from
# release/release-manifest.json, ordered by PIN_ORDER (arrays are unsorted).
declare -A PINNED_TAGS=()
PIN_ORDER=()

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

log() { printf '[%s] %s\n' "$(date '+%F %T')" "$*" >>"$LOGFILE"; }

die() {
    log "FATAL: $*"
    if [ "$USE_WHIPTAIL" = "1" ] && command -v whiptail >/dev/null 2>&1; then
        whiptail --title "Minabox" --msgbox "$*" 12 70 || true
    fi
    printf '\n\033[31m%s\033[0m\n' "$*" >&2
    printf '%s\n' "$(t log_hint "$LOGFILE")" >&2
    exit 1
}

# On every abort, name the log path - that is the first question in a support case.
on_error() {
    local code=$?
    local line=${1:-?}
    log "ERROR: exit $code at line $line"
    printf '\n\033[31mFehler (Zeile %s, Code %s). Log: %s\033[0m\n' "$line" "$code" "$LOGFILE" >&2
}
trap 'on_error $LINENO' ERR

run() {
    log "RUN: $*"
    if [ "$DRY_RUN" = "1" ]; then
        printf '  [dry-run] %s\n' "$*"
        return 0
    fi
    "$@" >>"$LOGFILE" 2>&1
}

# ---------------------------------------------------------------------------
# Uebersetzungen
# ---------------------------------------------------------------------------

declare -A MSG_de=(
    [title]="Minabox Installation"
    [log_hint]="Vollstaendiges Protokoll: %s"
    [need_tty]="Dieser Wizard braucht ein interaktives Terminal.\n\nBitte so starten:\n\n  curl -fsSL %s -o minabox-install.sh\n  bash minabox-install.sh"
    [lang_prompt]="Sprache waehlen / Select language"
    [welcome]="Willkommen bei der Minabox-Installation.\n\nDieser Assistent richtet alles ein: Docker, Hardware-Zugriff, Container und Autostart.\n\nDauer: etwa 5-10 Minuten.\n\nProtokoll: %s"
    [pre_arch]="Nicht unterstuetzte Architektur: %s\n\nMinabox braucht ein 64-Bit-System (aarch64).\nBitte Raspberry Pi OS 64-bit installieren."
    [pre_nopi]="Das sieht nicht nach einem Raspberry Pi aus.\n\nDie Installation ist nur auf Raspberry Pi OS getestet. Trotzdem fortfahren?"
    [pre_nosudo]="Der Benutzer '%s' kann kein sudo ausfuehren.\n\nDie Installation braucht Administratorrechte."
    [pre_disk]="Zu wenig freier Speicher: %s GB frei, mindestens %s GB noetig."
    [pre_net]="Keine Internetverbindung.\n\nDer Wizard laedt Docker-Images aus dem Internet und braucht eine Verbindung."
    [pre_bash]="Bash %s ist zu alt. Mindestens Bash 4 noetig."
    [dir_prompt]="In welches Verzeichnis soll Minabox installiert werden?"
    [comp_prompt]="Welche Komponenten sollen mitlaufen?\n\nImmer aktiv: MQTT, Backend, Host-Helper, Audio, WebUI\n\nMit LEERTASTE aus- und abwaehlen, mit TAB zu OK."
    [comp_rfid]="RFID-Leser (PN532, I2C)"
    [comp_led]="LEDs (GPIO)"
    [comp_button]="Taster / Drehregler (GPIO)"
    [comp_display]="OLED-Display (I2C)"
    [comp_media]="Medienimport von URL"
    [dev_prompt]="Geraetename dieser Minabox\n\nWird in den MQTT-Topics verwendet. Nur Kleinbuchstaben, Ziffern und Bindestrich."
    [dev_invalid]="Ungueltiger Geraetename. Erlaubt sind Kleinbuchstaben, Ziffern und Bindestrich."
    [port_prompt]="Auf welchem Port soll die Bedienoberflaeche erreichbar sein?"
    [port_invalid]="'%s' ist keine gueltige Portnummer (1-65535)."
    [port_busy]="Port %s ist bereits belegt:\n\n%s\n\nTrotzdem verwenden?"
    [tz_prompt]="Zeitzone"
    [loglevel_prompt]="Wie ausfuehrlich sollen die Protokolle sein?"
    [loglevel_info]="Normal (empfohlen)"
    [loglevel_debug]="Ausfuehrlich (Fehlersuche)"
    [loglevel_warning]="Nur Warnungen und Fehler"
    [step_docker]="Docker wird installiert..."
    [step_docker_ok]="Docker ist bereits installiert."
    [step_groups]="Hardware-Zugriff wird eingerichtet..."
    [step_clone]="Minabox wird heruntergeladen..."
    [step_config]="Konfiguration wird erstellt..."
    [step_pull]="Container-Images werden geladen..."
    [pull_service]="Lade %s ..."
    [pull_failed]="Einige Images konnten nicht geladen werden:\n\n%s\n\nMoegliche Ursachen: keine Internetverbindung, oder die Images sind auf GitHub noch nicht veroeffentlicht.\n\nProtokoll: %s"
    [step_up]="Container werden gestartet..."
    [step_wait]="Warte darauf, dass die Dienste bereit sind..."
    [wait_timeout]="Die Dienste sind nach %s Sekunden noch nicht erreichbar.\n\nDas kann beim ersten Start dauern. Aktueller Stand:\n\n%s\n\nPruefen mit:\n  cd %s && docker compose logs -f"
    [docker_group_note]="Docker wurde installiert und '%s' der Gruppe 'docker' hinzugefuegt.\n\nDamit das ohne Neustart wirkt, laeuft der Rest der Installation ueber sudo."
    [audio_prompt]="Welcher Audio-Ausgang soll verwendet werden?\n\nGefundene Karten sind mit (*) markiert."
    [audio_onboard]="Kopfhoererbuchse 3,5 mm"
    [audio_hdmi]="HDMI"
    [audio_usb]="USB-Soundkarte"
    [audio_hifiberry]="HiFiBerry DAC / DAC+ / Amp"
    [audio_iqaudio]="IQaudio DAC / DAC+"
    [audio_wm8960]="WM8960 HAT (Waveshare / Seeed)"
    [audio_keep]="Nichts aendern"
    [audio_reboot]="Der Audio-Ausgang wurde in %s eingetragen.\n\nDamit er aktiv wird, ist ein Neustart noetig. Nach dem Neustart:\n\n  bash %s\n\nDort 'Audio neu einrichten' waehlen, um den Ausgang endgueltig festzulegen."
    [audio_wm8960_warn]="Der WM8960-Treiber wird aus dem Quelltext uebersetzt.\n\nDas dauert 10-20 Minuten, braucht eine Internetverbindung und kann je nach Kernel-Version fehlschlagen.\n\nFortfahren?"
    [audio_wm8960_fail]="Der WM8960-Treiber konnte nicht installiert werden.\n\nDie Installation laeuft weiter - der Ton bleibt vorerst stumm. Details im Protokoll:\n%s"
    [audio_sink_prompt]="Welcher Ausgang soll fuer die Wiedergabe verwendet werden?"
    [audio_sink_auto]="Automatisch erkennen (empfohlen)"
    [audio_no_sink]="Es wurde kein aktiver Audio-Ausgang gefunden.\n\nMinabox erkennt den Ausgang beim Start automatisch. Falls kein Ton kommt, den Wizard erneut starten und 'Audio neu einrichten' waehlen."
    [autostart_prompt]="Soll Minabox nach einem Stromausfall automatisch starten?\n\nDie Container starten ohnehin von allein neu. Der Systemdienst hilft zusaetzlich, wenn Minabox vorher von Hand gestoppt wurde."
    [done_title]="Installation abgeschlossen"
    [done]="Minabox laeuft.\n\nZum Einrichten im Browser oeffnen:\n\n    http://%s\n\nAlternativ:\n\n    http://%s\n\nInstalliert in: %s\nProtokoll:      %s"
    [done_reboot]="\n\nWICHTIG: Fuer die Audio-Einstellung ist ein Neustart noetig.\nJetzt neu starten?"
    [abort]="Installation abgebrochen."
    [confirm_yes]="Ja"
    [confirm_no]="Nein"
    [ok]="OK"
    [cancel]="Abbrechen"
    # Wartungsmenue
    [maint_title]="Minabox-Wartung"
    [maint_prompt]="Minabox ist bereits installiert in:\n%s\n\nWas moechtest du tun?"
    [maint_components]="Komponenten aendern"
    [maint_update]="Update einspielen"
    [maint_audio]="Audio neu einrichten"
    [maint_status]="Status und Diagnose"
    [maint_lang]="Sprache aendern"
    [maint_uninstall]="Minabox entfernen"
    [maint_exit]="Beenden"
    [maint_comp_done]="Die Komponenten wurden geaendert.\n\nAktiv: %s"
    [maint_update_run]="Update laeuft..."
    [maint_update_done]="Update abgeschlossen.\n\n%s"
    [maint_status_txt]="Container-Status:\n\n%s"
    [uninstall_confirm]="Alle Minabox-Container, Images und der Systemdienst werden entfernt.\n\nFortfahren?"
    [uninstall_data]="Sollen auch die BENUTZERDATEN geloescht werden?\n\n  - Datenbank mit allen Karten und Zuordnungen\n  - Musikbibliothek in %s\n\nDas kann nicht rueckgaengig gemacht werden."
    [uninstall_data2]="Letzte Warnung: Datenbank und Musikbibliothek werden unwiderruflich geloescht.\n\nWirklich?"
    [uninstall_done]="Minabox wurde entfernt.\n\nDas Verzeichnis %s ist noch vorhanden und kann von Hand geloescht werden."
)

declare -A MSG_en=(
    [title]="Minabox Installation"
    [log_hint]="Full log: %s"
    [need_tty]="This wizard needs an interactive terminal.\n\nPlease run it like this:\n\n  curl -fsSL %s -o minabox-install.sh\n  bash minabox-install.sh"
    [lang_prompt]="Sprache waehlen / Select language"
    [welcome]="Welcome to the Minabox installer.\n\nThis wizard sets everything up: Docker, hardware access, containers and autostart.\n\nTakes about 5-10 minutes.\n\nLog: %s"
    [pre_arch]="Unsupported architecture: %s\n\nMinabox needs a 64-bit system (aarch64).\nPlease install Raspberry Pi OS 64-bit."
    [pre_nopi]="This does not look like a Raspberry Pi.\n\nThe installer is only tested on Raspberry Pi OS. Continue anyway?"
    [pre_nosudo]="User '%s' cannot run sudo.\n\nThe installation needs administrator rights."
    [pre_disk]="Not enough free space: %s GB available, at least %s GB needed."
    [pre_net]="No internet connection.\n\nThe wizard downloads Docker images and needs a connection."
    [pre_bash]="Bash %s is too old. Bash 4 or newer required."
    [dir_prompt]="Which directory should Minabox be installed into?"
    [comp_prompt]="Which components should run?\n\nAlways active: MQTT, Backend, Host-Helper, Audio, WebUI\n\nUse SPACE to toggle, TAB to reach OK."
    [comp_rfid]="RFID reader (PN532, I2C)"
    [comp_led]="LEDs (GPIO)"
    [comp_button]="Buttons / rotary encoder (GPIO)"
    [comp_display]="OLED display (I2C)"
    [comp_media]="Media import from URL"
    [dev_prompt]="Device name for this Minabox\n\nUsed in the MQTT topics. Lowercase letters, digits and hyphens only."
    [dev_invalid]="Invalid device name. Use lowercase letters, digits and hyphens."
    [port_prompt]="Which port should the web interface listen on?"
    [port_invalid]="'%s' is not a valid port number (1-65535)."
    [port_busy]="Port %s is already in use:\n\n%s\n\nUse it anyway?"
    [tz_prompt]="Timezone"
    [loglevel_prompt]="How detailed should the logs be?"
    [loglevel_info]="Normal (recommended)"
    [loglevel_debug]="Verbose (troubleshooting)"
    [loglevel_warning]="Warnings and errors only"
    [step_docker]="Installing Docker..."
    [step_docker_ok]="Docker is already installed."
    [step_groups]="Setting up hardware access..."
    [step_clone]="Downloading Minabox..."
    [step_config]="Writing configuration..."
    [step_pull]="Downloading container images..."
    [pull_service]="Downloading %s ..."
    [pull_failed]="Some images could not be downloaded:\n\n%s\n\nLikely causes: no internet connection, or the images are not published on GitHub yet.\n\nLog: %s"
    [step_up]="Starting containers..."
    [step_wait]="Waiting for the services to become ready..."
    [wait_timeout]="The services are not reachable after %s seconds.\n\nThis can take a while on first start. Current state:\n\n%s\n\nCheck with:\n  cd %s && docker compose logs -f"
    [docker_group_note]="Docker was installed and '%s' added to the 'docker' group.\n\nSo this takes effect without a reboot, the rest of the installation runs via sudo."
    [audio_prompt]="Which audio output should be used?\n\nDetected cards are marked with (*)."
    [audio_onboard]="3.5 mm headphone jack"
    [audio_hdmi]="HDMI"
    [audio_usb]="USB sound card"
    [audio_hifiberry]="HiFiBerry DAC / DAC+ / Amp"
    [audio_iqaudio]="IQaudio DAC / DAC+"
    [audio_wm8960]="WM8960 HAT (Waveshare / Seeed)"
    [audio_keep]="Leave unchanged"
    [audio_reboot]="The audio output was written to %s.\n\nA reboot is needed for it to take effect. After the reboot run:\n\n  bash %s\n\nand choose 'Reconfigure audio' to finalise the output."
    [audio_wm8960_warn]="The WM8960 driver is compiled from source.\n\nThis takes 10-20 minutes, needs an internet connection and may fail depending on your kernel version.\n\nContinue?"
    [audio_wm8960_fail]="The WM8960 driver could not be installed.\n\nInstallation continues - there will be no sound for now. Details in the log:\n%s"
    [audio_sink_prompt]="Which output should be used for playback?"
    [audio_sink_auto]="Detect automatically (recommended)"
    [audio_no_sink]="No active audio output was found.\n\nMinabox detects the output automatically at startup. If there is no sound, run the wizard again and choose 'Reconfigure audio'."
    [autostart_prompt]="Should Minabox start automatically after a power cut?\n\nThe containers already restart on their own. The system service additionally helps when Minabox was stopped manually."
    [done_title]="Installation complete"
    [done]="Minabox is running.\n\nOpen this in your browser to set it up:\n\n    http://%s\n\nAlternatively:\n\n    http://%s\n\nInstalled in: %s\nLog:          %s"
    [done_reboot]="\n\nIMPORTANT: A reboot is needed for the audio setting.\nReboot now?"
    [abort]="Installation aborted."
    [confirm_yes]="Yes"
    [confirm_no]="No"
    [ok]="OK"
    [cancel]="Cancel"
    [maint_title]="Minabox maintenance"
    [maint_prompt]="Minabox is already installed in:\n%s\n\nWhat would you like to do?"
    [maint_components]="Change components"
    [maint_update]="Install update"
    [maint_audio]="Reconfigure audio"
    [maint_status]="Status and diagnostics"
    [maint_lang]="Change language"
    [maint_uninstall]="Remove Minabox"
    [maint_exit]="Exit"
    [maint_comp_done]="Components updated.\n\nActive: %s"
    [maint_update_run]="Update running..."
    [maint_update_done]="Update finished.\n\n%s"
    [maint_status_txt]="Container status:\n\n%s"
    [uninstall_confirm]="All Minabox containers, images and the system service will be removed.\n\nContinue?"
    [uninstall_data]="Should the USER DATA be deleted as well?\n\n  - Database with all cards and assignments\n  - Music library in %s\n\nThis cannot be undone."
    [uninstall_data2]="Final warning: database and music library will be permanently deleted.\n\nReally?"
    [uninstall_done]="Minabox has been removed.\n\nThe directory %s still exists and can be deleted manually."
)

# t <key> [printf-args...]
t() {
    local key="$1"; shift
    local val=""
    if [ "$LANG_CODE" = "de" ]; then
        val="${MSG_de[$key]-}"
    else
        val="${MSG_en[$key]-}"
    fi
    [ -z "$val" ] && val="${MSG_en[$key]-$key}"
    # shellcheck disable=SC2059
    printf "$val" "$@"
}

# ---------------------------------------------------------------------------
# Dialogs
#
# whiptail writes its result to stderr, hence the 3>&1 1>&2 2>&3 pattern
# everywhere. In unattended mode nothing is ever asked.
# ---------------------------------------------------------------------------

ui_info() {
    if [ "$USE_WHIPTAIL" = "1" ]; then
        whiptail --title "$(t title)" --infobox "$1" "${2:-8}" 70
    else
        printf '  %s\n' "$1"
    fi
}

ui_msg() {
    if [ "$USE_WHIPTAIL" = "1" ]; then
        whiptail --title "${2:-$(t title)}" --msgbox "$1" "${3:-14}" 74
    else
        printf '\n%s\n\n' "$1"
    fi
}

# ui_yesno <text> [default_no]  -> 0 = ja
ui_yesno() {
    local text="$1" defno="${2:-0}"
    if [ "$UNATTENDED" = "1" ]; then
        [ "$defno" = "1" ] && return 1 || return 0
    fi
    if [ "$USE_WHIPTAIL" = "1" ]; then
        local args=(--title "$(t title)" --yes-button "$(t confirm_yes)" --no-button "$(t confirm_no)")
        [ "$defno" = "1" ] && args+=(--defaultno)
        whiptail "${args[@]}" --yesno "$text" 14 74
        return $?
    fi
    local answer
    printf '\n%s\n' "$text"
    read -r -p "[y/N] " answer
    [[ "$answer" =~ ^[JjYy] ]]
}

# ui_input <text> <default>
ui_input() {
    local text="$1" default="$2"
    if [ "$UNATTENDED" = "1" ]; then
        printf '%s' "$default"
        return 0
    fi
    if [ "$USE_WHIPTAIL" = "1" ]; then
        whiptail --title "$(t title)" --ok-button "$(t ok)" --cancel-button "$(t cancel)" \
            --inputbox "$text" 12 74 "$default" 3>&1 1>&2 2>&3
        return $?
    fi
    local answer
    printf '\n%s\n' "$text" >&2
    read -r -p "[$default] " answer
    printf '%s' "${answer:-$default}"
}

# ui_menu <text> <height> <tag1> <label1> [<tag2> <label2> ...]
ui_menu() {
    local text="$1" items="$2"; shift 2
    if [ "$UNATTENDED" = "1" ]; then
        printf '%s' "$1"
        return 0
    fi
    if [ "$USE_WHIPTAIL" = "1" ]; then
        whiptail --title "$(t title)" --notags --ok-button "$(t ok)" --cancel-button "$(t cancel)" \
            --menu "$text" $((items + 10)) 74 "$items" "$@" 3>&1 1>&2 2>&3
        return $?
    fi
    local i=1 tag label
    printf '\n%s\n\n' "$text" >&2
    local tags=()
    while [ $# -gt 0 ]; do
        tag="$1"; label="$2"; shift 2
        tags+=("$tag")
        printf '  %d) %s\n' "$i" "$label" >&2
        i=$((i + 1))
    done
    local choice
    read -r -p "> " choice
    printf '%s' "${tags[$((choice - 1))]:-${tags[0]}}"
}

# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------

ensure_tty() {
    # "curl | bash" gives us a pipe on stdin - whiptail needs a TTY.
    if [ ! -t 0 ]; then
        if [ -r /dev/tty ] && exec </dev/tty 2>/dev/null; then
            log "stdin was not a tty, reopened /dev/tty"
        else
            USE_WHIPTAIL=0
            printf '%b\n' "$(t need_tty "https://raw.githubusercontent.com/Opnek90/Minabox/main/install.sh")" >&2
            exit 1
        fi
    fi
    if ! command -v whiptail >/dev/null 2>&1; then
        USE_WHIPTAIL=0
        log "whiptail not available, falling back to plain text prompts"
    fi
}

preflight() {
    if [ "${BASH_VERSINFO[0]:-0}" -lt 4 ]; then
        die "$(t pre_bash "${BASH_VERSION}")"
    fi

    local arch; arch="$(uname -m)"
    if [ "$arch" != "aarch64" ] && [ "$arch" != "arm64" ]; then
        die "$(t pre_arch "$arch")"
    fi

    if [ ! -f /etc/rpi-issue ] && ! grep -qi raspbian /etc/os-release 2>/dev/null; then
        ui_yesno "$(t pre_nopi)" 1 || die "$(t abort)"
    fi

    if ! sudo -n true 2>/dev/null && ! sudo -v 2>/dev/null; then
        die "$(t pre_nosudo "$USER")"
    fi

    local free_gb min_gb=4
    free_gb=$(df -BG --output=avail "$HOME" | tail -1 | tr -dc '0-9')
    if [ "${free_gb:-0}" -lt "$min_gb" ]; then
        die "$(t pre_disk "$free_gb" "$min_gb")"
    fi

    if ! curl -fsS --max-time 10 -o /dev/null https://github.com 2>>"$LOGFILE"; then
        die "$(t pre_net)"
    fi

    log "preflight ok: arch=$arch free=${free_gb}G user=$USER"
}

# ---------------------------------------------------------------------------
# Abfragen
# ---------------------------------------------------------------------------

ask_language() {
    # Before anything else, so everything from here on is translated.
    [ "$UNATTENDED" = "1" ] && return 0
    [ "$LANG_SET" = "1" ] && return 0
    local choice
    choice=$(ui_menu "$(t lang_prompt)" 2 \
        "de" "Deutsch" \
        "en" "English") || die "$(t abort)"
    LANG_CODE="$choice"
    log "language=$LANG_CODE"
}

ask_components() {
    [ "$COMPONENTS_SET" = "1" ] && return 0

    if [ "$UNATTENDED" = "1" ]; then
        COMPONENTS="rfid"
        return 0
    fi

    local -a on=() 
    IFS=',' read -ra on <<<"${COMPONENTS:-rfid}"
    state() {
        local want="$1" c
        for c in "${on[@]}"; do [ "$c" = "$want" ] && { echo ON; return; }; done
        echo OFF
    }

    local result
    if [ "$USE_WHIPTAIL" = "1" ]; then
        result=$(whiptail --title "$(t title)" --ok-button "$(t ok)" --cancel-button "$(t cancel)" \
            --checklist "$(t comp_prompt)" 18 74 5 \
            "rfid"    "$(t comp_rfid)"    "$(state rfid)" \
            "led"     "$(t comp_led)"     "$(state led)" \
            "button"  "$(t comp_button)"  "$(state button)" \
            "display" "$(t comp_display)" "$(state display)" \
            "media"   "$(t comp_media)"   "$(state media)" \
            3>&1 1>&2 2>&3) || die "$(t abort)"
    else
        printf '\n%s\n\n' "$(t comp_prompt)"
        local c answer
        result=""
        for c in rfid led button display media; do
            local def="n"; [ "$(state "$c")" = "ON" ] && def="j"
            read -r -p "$(t "comp_$c") [${def}] " answer
            answer="${answer:-$def}"
            [[ "$answer" =~ ^[JjYy] ]] && result="$result $c"
        done
    fi

    # whiptail returns "rfid" "led" - drop the quotes, add commas.
    COMPONENTS=$(printf '%s' "$result" | tr -d '"' | tr -s ' ' ',' | sed 's/^,//; s/,$//')
    log "components=$COMPONENTS"
}

has_component() {
    [[ ",$COMPONENTS," == *",$1,"* ]]
}

ask_basics() {
    # Device ID
    while true; do
        DEVICE_ID=$(ui_input "$(t dev_prompt)" "${DEVICE_ID:-box1}") || die "$(t abort)"
        [[ "$DEVICE_ID" =~ ^[a-z0-9][a-z0-9-]*$ ]] && break
        ui_msg "$(t dev_invalid)"
    done

    # Web UI port
    while true; do
        WEBUI_PORT=$(ui_input "$(t port_prompt)" "${WEBUI_PORT:-80}") || die "$(t abort)"
        if ! [[ "$WEBUI_PORT" =~ ^[0-9]+$ ]] || [ "$WEBUI_PORT" -lt 1 ] || [ "$WEBUI_PORT" -gt 65535 ]; then
            ui_msg "$(t port_invalid "$WEBUI_PORT")"
            continue
        fi
        local busy
        busy=$(ss -ltnH "sport = :$WEBUI_PORT" 2>/dev/null | head -3)
        if [ -n "$busy" ]; then
            ui_yesno "$(t port_busy "$WEBUI_PORT" "$busy")" 1 && break
            continue
        fi
        break
    done

    # Time zone
    local tz_default
    tz_default=$(timedatectl show -p Timezone --value 2>/dev/null || cat /etc/timezone 2>/dev/null || echo "Europe/Berlin")
    TZ_VALUE=$(ui_input "$(t tz_prompt)" "$tz_default") || die "$(t abort)"

    # Log-Level
    LOG_LEVEL=$(ui_menu "$(t loglevel_prompt)" 3 \
        "INFO"    "$(t loglevel_info)" \
        "DEBUG"   "$(t loglevel_debug)" \
        "WARNING" "$(t loglevel_warning)") || die "$(t abort)"

    log "device=$DEVICE_ID port=$WEBUI_PORT tz=$TZ_VALUE loglevel=$LOG_LEVEL"
}

# ---------------------------------------------------------------------------
# Systemvorbereitung
# ---------------------------------------------------------------------------

install_docker() {
    if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
        log "docker already present"
        ui_info "$(t step_docker_ok)"
        return 0
    fi

    ui_info "$(t step_docker)" 
    if ! command -v docker >/dev/null 2>&1; then
        run bash -c "curl -fsSL https://get.docker.com -o /tmp/get-docker.sh && sh /tmp/get-docker.sh"
    fi
    if ! docker compose version >/dev/null 2>&1; then
        run sudo apt-get update
        run sudo apt-get install -y docker-compose-plugin
    fi
    run sudo usermod -aG docker "$USER"
    run sudo systemctl enable --now docker

    # The new group membership only takes effect after a fresh login. Instead
    # of forcing a reboot, the docker calls of this session go through sudo
    # (see dc()).
    DOCKER_NEEDS_SUDO=1
    log "docker installed, sudo fallback active for this session"
    ui_msg "$(t docker_group_note "$USER")"
}

install_docker_daemon_config() {
    # Caps the container logs. Without it the SD card eventually fills up.
    local src="$TARGET_DIR/infrastructure/docker-daemon.json"
    [ -f "$src" ] || return 0
    [ -f /etc/docker/daemon.json ] && { log "daemon.json exists, kept"; return 0; }
    run sudo mkdir -p /etc/docker
    run sudo cp "$src" /etc/docker/daemon.json
    run sudo systemctl restart docker
    log "installed /etc/docker/daemon.json"
}

setup_hardware_access() {
    ui_info "$(t step_groups)"

    if has_component rfid || has_component display; then
        if command -v raspi-config >/dev/null 2>&1; then
            run sudo raspi-config nonint do_i2c 0 || log "do_i2c failed (non-fatal)"
        else
            log "raspi-config missing, skipping I2C enable"
        fi
    fi

    if has_component led || has_component button; then
        if command -v raspi-config >/dev/null 2>&1; then
            run sudo raspi-config nonint do_spi 0 || log "do_spi failed (non-fatal)"
        fi
    fi

    local g
    for g in gpio i2c spi audio; do
        if getent group "$g" >/dev/null 2>&1; then
            run sudo usermod -aG "$g" "$USER" || log "usermod $g failed (non-fatal)"
        fi
    done

    # Without linger, /run/user/<UID> does not exist after a reboot without a
    # login. That is exactly what the audio container talks to PipeWire over -
    # without it the box stays silent after every restart until someone logs in.
    run sudo loginctl enable-linger "$USER" || log "enable-linger failed (non-fatal)"
}

# manifest_service_version <manifest-file> <service>
# Prints the "latest" version of this service from release/release-manifest.json,
# empty if the service is missing there or the file is not valid JSON.
manifest_service_version() {
    python3 - "$1" "$2" <<'PY' 2>/dev/null
import json, sys

path, service = sys.argv[1], sys.argv[2]
try:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    version = data["services"][service]["latest"]
    if isinstance(version, str) and version:
        print(version)
except Exception:
    pass
PY
}

# image_tag_published <repository> <tag>
# Checks anonymously against ghcr.io whether this tag is really there yet. The
# manifest knows a version as soon as the commit has landed - the registry
# only once CI has finished building. On any doubt (network, timeout,
# unexpected response) it counts as "not confirmed": image_tag_published then
# returns false, see pin_service_versions().
image_tag_published() {
    local repo="$1" tag="$2" token
    token=$(curl -fsS --max-time 5 \
        "https://ghcr.io/token?scope=repository:${repo}:pull&service=ghcr.io" 2>/dev/null \
        | python3 -c 'import json, sys
try:
    print(json.load(sys.stdin).get("token", ""))
except Exception:
    pass' 2>/dev/null)
    [ -n "$token" ] || return 1
    curl -fsS --max-time 5 -o /dev/null \
        -H "Authorization: Bearer $token" \
        -H "Accept: application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.v2+json, application/vnd.oci.image.manifest.v1+json" \
        "https://ghcr.io/v2/${repo}/manifests/${tag}"
}

# pin_service_versions
# Determines a fixed version for every actually active service from the
# freshly cloned release/release-manifest.json - but only if the matching
# image really is in the registry. Every failure (manifest missing, service
# missing in it, tag not published yet) leaves that one service at
# MINABOX_IMAGE_TAG=latest: a failed pull would abort the whole install (see
# pull_images), whereas an unpinned service only stays on today's behaviour.
pin_service_versions() {
    PIN_ORDER=()
    PINNED_TAGS=()

    if [ "$DRY_RUN" = "1" ]; then
        log "dry-run: version pinning skipped"
        return 0
    fi

    local manifest="$TARGET_DIR/release/release-manifest.json"
    if [ ! -r "$manifest" ]; then
        log "no release/release-manifest.json found - staying on latest"
        return 0
    fi

    # Always-active services from REQUIRED_SERVICES (without mqtt - it runs on
    # eclipse-mosquitto, not a Minabox image) plus the chosen profiles.
    local -a services=()
    local s
    for s in $REQUIRED_SERVICES; do
        [ "$s" = "mqtt" ] || services+=("$s")
    done
    has_component rfid    && services+=(rfid)
    has_component led     && services+=(led)
    has_component button  && services+=(button)
    has_component display && services+=(display)
    has_component media   && services+=(media-downloader)

    local service version repo
    for service in "${services[@]}"; do
        version=$(manifest_service_version "$manifest" "$service")
        if [ -z "$version" ]; then
            log "pin: $service not in the manifest - stays latest"
            continue
        fi
        repo="opnek90/minabox-$service"
        if image_tag_published "$repo" "$version"; then
            PIN_ORDER+=("$service")
            PINNED_TAGS[$service]="$version"
            log "pin: $service -> $version"
        else
            log "pin: $service $version not in the registry yet - stays latest"
        fi
    done
}

clone_repo() {
    ui_info "$(t step_clone)"
    if [ -d "$TARGET_DIR/.git" ]; then
        log "repo already present at $TARGET_DIR"
        return 0
    fi
    if ! command -v git >/dev/null 2>&1; then
        run sudo apt-get update
        run sudo apt-get install -y git
    fi
    run git clone --depth 1 "$REPO_URL" "$TARGET_DIR"
}

seed_configs() {
    ui_info "$(t step_config)"
    run bash "$TARGET_DIR/scripts/setup-folders.sh"
    # Everything belongs to the calling user - the containers run as their UID.
    run sudo chown -R "$(id -u):$(id -g)" "$TARGET_DIR"
}

# gid_of <group> <fallback>
gid_of() {
    local gid
    gid=$(getent group "$1" 2>/dev/null | cut -d: -f3)
    printf '%s' "${gid:-$2}"
}

write_env() {
    local env_file="$TARGET_DIR/.env"

    local boot_dir="/boot/firmware"
    [ -d "$boot_dir" ] || boot_dir="/boot"

    local secret web_secret
    secret=$(openssl rand -hex 32)
    web_secret=$(openssl rand -hex 32)

    if [ "$DRY_RUN" = "1" ]; then
        printf '  [dry-run] write .env to %s\n' "$env_file"
        return 0
    fi

    cat >"$env_file" <<ENV
# Created by install.sh on $(date '+%F %T').
# Not overwritten on an update.

MINABOX_DEVICE_ID=$DEVICE_ID
MINABOX_LANGUAGE=$LANG_CODE

MQTT_BROKER=mqtt
MQTT_PORT=1883

HOST_HELPER_API_KEY=$secret
WEB_AUTH_SECRET=$web_secret

LOG_LEVEL=$LOG_LEVEL
TZ=$TZ_VALUE

WEBUI_PORT=$WEBUI_PORT
BACKEND_PORT=8080

AUDIO_FILES_PATH=./audio
ALLOWED_AUDIO_PATHS=/media,/mnt,$HOME

# Component selection. Removing a profile does not stop a running container by
# itself - use 'docker compose down --remove-orphans' for that.
COMPOSE_PROFILES=$COMPONENTS

# Fallback: applies to every service without its own MINABOX_<SERVICE>_TAG
# below. 'latest' follows the main branch.
MINABOX_IMAGE_TAG=latest

# Host-specific - determined by the wizard here, do not guess by hand.
HOST_UID=$(id -u)
DOCKER_GID=$(gid_of docker 984)
I2C_GID=$(gid_of i2c 988)
GPIO_GID=$(gid_of gpio 986)
BOOT_CONFIG_DIR=$boot_dir
ENV

    if [ "${#PIN_ORDER[@]}" -gt 0 ]; then
        {
            printf '\n# Fixed versions per service, determined from release/release-manifest.json\n'
            printf '# at install time. Overrides MINABOX_IMAGE_TAG for that service; change by\n'
            printf '# hand to roll exactly this service back.\n'
            local service upper
            for service in "${PIN_ORDER[@]}"; do
                upper=$(printf '%s' "$service" | tr '[:lower:]-' '[:upper:]_')
                printf 'MINABOX_%s_TAG=%s\n' "$upper" "${PINNED_TAGS[$service]}"
            done
        } >>"$env_file"
    fi

    chmod 600 "$env_file"
    log ".env written (boot_dir=$boot_dir docker_gid=$(gid_of docker 984) i2c=$(gid_of i2c 988) gpio=$(gid_of gpio 986))"
}

# ---------------------------------------------------------------------------
# Audio
#
# Two layers that must not be mixed:
#   1. Hardware on the host - dtoverlay in config.txt, usually needs a reboot.
#   2. PulseAudio sink     - can only be chosen once the card is active.
# ---------------------------------------------------------------------------

boot_config_path() {
    local d="/boot/firmware"
    [ -d "$d" ] || d="/boot"
    printf '%s/config.txt' "$d"
}

# audio_apply_overlay <overlay|"">   "" = onboard headphone jack
audio_apply_overlay() {
    local overlay="$1"
    local cfg; cfg="$(boot_config_path)"
    [ -f "$cfg" ] || { log "no config.txt at $cfg"; return 0; }

    if [ "$DRY_RUN" = "1" ]; then
        printf '  [dry-run] %s -> dtoverlay=%s\n' "$cfg" "${overlay:-<onboard>}"
        return 0
    fi

    # A one-time backup, never overwritten again.
    sudo cp -n "$cfg" "${cfg}.minabox-backup" 2>/dev/null || true

    # Idempotent: always remove our own block first, never append.
    sudo sed -i '/# >>> minabox audio/,/# <<< minabox audio/d' "$cfg"

    if [ -n "$overlay" ]; then
        # Silence onboard audio, otherwise the cards compete for card0.
        sudo sed -i 's/^dtparam=audio=on/#dtparam=audio=on/' "$cfg"
        printf '# >>> minabox audio\ndtoverlay=%s\n# <<< minabox audio\n' "$overlay" \
            | sudo tee -a "$cfg" >/dev/null
    else
        sudo sed -i 's/^[[:space:]]*#[[:space:]]*dtparam=audio=on/dtparam=audio=on/' "$cfg"
        grep -q '^dtparam=audio=on' "$cfg" \
            || printf 'dtparam=audio=on\n' | sudo tee -a "$cfg" >/dev/null
    fi

    REBOOT_REQUIRED=1
    log "audio overlay applied: ${overlay:-onboard} in $cfg"
}

audio_card_present() {
    aplay -l 2>/dev/null | grep -qi "$1"
}

# Marks detected cards with (*), so the selection does not have to guess.
audio_label() {
    local key="$1" pattern="$2"
    if audio_card_present "$pattern"; then
        printf '(*) %s' "$(t "$key")"
    else
        printf '    %s' "$(t "$key")"
    fi
}

setup_audio_hardware() {
    [ "$UNATTENDED" = "1" ] && return 0

    local choice
    choice=$(ui_menu "$(t audio_prompt)" 7 \
        "onboard"   "$(audio_label audio_onboard   'Headphones')" \
        "hdmi"      "$(audio_label audio_hdmi      'vc4hdmi')" \
        "usb"       "$(audio_label audio_usb       'USB')" \
        "wm8960"    "$(audio_label audio_wm8960    'wm8960')" \
        "hifiberry" "$(audio_label audio_hifiberry 'hifiberry')" \
        "iqaudio"   "$(audio_label audio_iqaudio   'iqaudio')" \
        "keep"      "$(t audio_keep)") || return 0

    case "$choice" in
        onboard)
            audio_apply_overlay ""
            ;;
        hdmi|usb|keep)
            # Neither needs an overlay - HDMI and USB announce themselves.
            log "audio: $choice selected, no overlay change"
            ;;
        hifiberry)
            local variant
            variant=$(ui_menu "$(t audio_hifiberry)" 5 \
                "hifiberry-dacplus"    "DAC+ / DAC+ Pro" \
                "hifiberry-dac"        "DAC (Mini / Zero)" \
                "hifiberry-dacplusadc" "DAC+ ADC" \
                "hifiberry-digi"       "Digi / Digi+" \
                "hifiberry-amp"        "Amp / Amp+") || return 0
            audio_apply_overlay "$variant"
            ;;
        iqaudio)
            audio_apply_overlay "iqaudio-dacplus"
            ;;
        wm8960)
            if audio_card_present "wm8960"; then
                # The driver is already running, just make sure of the overlay.
                audio_apply_overlay "wm8960-soundcard"
            else
                ui_yesno "$(t audio_wm8960_warn)" 1 || return 0
                install_wm8960 || ui_msg "$(t audio_wm8960_fail "$LOGFILE")"
            fi
            ;;
    esac
}

install_wm8960() {
    # Compiles a kernel module and can fail depending on the kernel. A failure
    # must not take the install down with it - hence a clean return value
    # everywhere instead of an abort.
    local tmp="/tmp/minabox-wm8960"
    rm -rf "$tmp"
    if [ "$DRY_RUN" = "1" ]; then
        printf '  [dry-run] WM8960-Treiber installieren\n'
        return 0
    fi
    {
        git clone --depth 1 https://github.com/waveshare/WM8960-Audio-HAT "$tmp" \
            && cd "$tmp" \
            && sudo ./install.sh
    } >>"$LOGFILE" 2>&1 || return 1
    REBOOT_REQUIRED=1
    return 0
}

# Layer 2: the PulseAudio sink. Only meaningful once the card is really active.
setup_audio_sink() {
    [ "$UNATTENDED" = "1" ] && return 0

    local audio_json="$TARGET_DIR/services/audio-service/config/audio.json"
    [ -f "$audio_json" ] || return 0

    local -a sinks=()
    mapfile -t sinks < <(pactl list short sinks 2>/dev/null | awk '{print $2}')

    if [ "${#sinks[@]}" -eq 0 ]; then
        ui_msg "$(t audio_no_sink)"
        return 0
    fi

    local -a args=("auto" "$(t audio_sink_auto)")
    local s
    for s in "${sinks[@]}"; do
        args+=("$s" "$s")
    done

    local choice
    choice=$(ui_menu "$(t audio_sink_prompt)" $(( ${#sinks[@]} + 1 )) "${args[@]}") || return 0

    if [ "$choice" = "auto" ]; then
        log "audio sink: autodetect"
        return 0
    fi

    if [ "$DRY_RUN" = "1" ]; then
        printf '  [dry-run] audio.json -> %s\n' "$choice"
        return 0
    fi

    python3 - "$audio_json" "$choice" <<'PY'
import json, sys
path, sink = sys.argv[1], sys.argv[2]
with open(path) as fh:
    cfg = json.load(fh)
cfg["output_device_type"] = "pulseaudio"
cfg["output_device_name"] = sink
enabled = cfg.get("enabled_output_devices") or []
if sink not in enabled:
    enabled.append(sink)
cfg["enabled_output_devices"] = enabled
with open(path, "w") as fh:
    json.dump(cfg, fh, indent=2)
    fh.write("\n")
PY
    log "audio sink set to $choice"
    dc restart audio >/dev/null 2>&1 || true
}

# ---------------------------------------------------------------------------
# Autostart
# ---------------------------------------------------------------------------

setup_autostart() {
    if [ "$UNATTENDED" != "1" ]; then
        ui_yesno "$(t autostart_prompt)" || { log "autostart declined"; return 0; }
    fi

    if [ "$DRY_RUN" = "1" ]; then
        printf '  [dry-run] write systemd unit %s\n' "$SYSTEMD_UNIT"
        return 0
    fi

    sudo tee "$SYSTEMD_UNIT" >/dev/null <<UNIT
[Unit]
Description=Minabox
Requires=docker.service
After=docker.service network-online.target
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=$TARGET_DIR
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
User=$USER
Group=$USER

[Install]
WantedBy=multi-user.target
UNIT

    run sudo systemctl daemon-reload
    run sudo systemctl enable minabox.service
    log "autostart enabled"
}

# ---------------------------------------------------------------------------
# Container starten
# ---------------------------------------------------------------------------

DOCKER_NEEDS_SUDO=0

# One uniform compose call. Right after the Docker install the new group
# membership does not apply in this shell yet - then via sudo.
dc() {
    if [ "$DOCKER_NEEDS_SUDO" = "1" ] || ! docker info >/dev/null 2>&1; then
        sudo docker compose --project-directory "$TARGET_DIR" "$@"
    else
        docker compose --project-directory "$TARGET_DIR" "$@"
    fi
}

pull_images() {
    if [ "$DRY_RUN" = "1" ]; then
        printf '  [dry-run] docker compose pull (Profile: %s)\n' "${COMPONENTS:--}"
        return 0
    fi

    local -a services=()
    mapfile -t services < <(dc config --services 2>/dev/null)
    local total="${#services[@]}"
    [ "$total" -eq 0 ] && die "docker compose config lieferte keine Services. Log: $LOGFILE"

    local failed_file; failed_file=$(mktemp)

    # Service by service instead of all at once: only this way can progress be
    # counted reliably without parsing the pull output.
    pull_loop() {
        local i=0 svc
        for svc in "${services[@]}"; do
            echo $(( i * 100 / total ))
            echo "XXX"; echo "$(t pull_service "$svc")"; echo "XXX"
            dc pull "$svc" >>"$LOGFILE" 2>&1 || printf '%s\n' "$svc" >>"$failed_file"
            i=$(( i + 1 ))
        done
        echo 100
    }

    if [ "$USE_WHIPTAIL" = "1" ]; then
        pull_loop | whiptail --title "$(t title)" --gauge "$(t step_pull)" 10 74 0
    else
        printf '%s\n' "$(t step_pull)"
        pull_loop >/dev/null
    fi

    if [ -s "$failed_file" ]; then
        local failed; failed=$(tr '\n' ' ' <"$failed_file")
        rm -f "$failed_file"
        die "$(t pull_failed "$failed" "$LOGFILE")"
    fi
    rm -f "$failed_file"
}

start_stack() {
    ui_info "$(t step_up)"
    if [ "$DRY_RUN" = "1" ]; then
        printf '  [dry-run] docker compose up -d\n'
        return 0
    fi
    dc up -d >>"$LOGFILE" 2>&1 || die "docker compose up ist fehlgeschlagen. Log: $LOGFILE"
}

wait_for_services() {
    [ "$DRY_RUN" = "1" ] && return 0
    local timeout=180 waited=0
    ui_info "$(t step_wait)"
    while [ "$waited" -lt "$timeout" ]; do
        if curl -fsS --max-time 3 -o /dev/null "http://localhost:${WEBUI_PORT}" 2>/dev/null \
           && curl -fsS --max-time 3 -o /dev/null "http://localhost:8080/health" 2>/dev/null; then
            log "services ready after ${waited}s"
            return 0
        fi
        sleep 5
        waited=$(( waited + 5 ))
    done
    local status; status=$(dc ps 2>&1 | head -15)
    ui_msg "$(t wait_timeout "$timeout" "$status" "$TARGET_DIR")" "$(t title)" 20
    return 0
}

show_done() {
    local ip host
    ip=$(hostname -I 2>/dev/null | awk '{print $1}')
    host="$(hostname).local"
    local suffix=""
    [ "$WEBUI_PORT" != "80" ] && suffix=":$WEBUI_PORT"

    local text
    text="$(t done "${ip}${suffix}" "${host}${suffix}" "$TARGET_DIR" "$LOGFILE")"

    if [ "$REBOOT_REQUIRED" = "1" ]; then
        if ui_yesno "${text}$(t done_reboot)"; then
            log "rebooting on user request"
            sudo reboot
            return 0
        fi
    else
        ui_msg "$text" "$(t done_title)" 20
    fi

    printf '\n%s\n\n' "$text"
}

# ---------------------------------------------------------------------------
# Wartungsmenue
# ---------------------------------------------------------------------------

load_existing_env() {
    local env_file="$TARGET_DIR/.env"
    COMPONENTS=$(grep -E '^COMPOSE_PROFILES=' "$env_file" 2>/dev/null | cut -d= -f2- || true)
    WEBUI_PORT=$(grep -E '^WEBUI_PORT=' "$env_file" 2>/dev/null | cut -d= -f2- || true)
    WEBUI_PORT="${WEBUI_PORT:-80}"
    local lang
    lang=$(grep -E '^MINABOX_LANGUAGE=' "$env_file" 2>/dev/null | cut -d= -f2- || true)
    [ -n "$lang" ] && LANG_CODE="$lang"
}

# set_env_var <key> <value>
set_env_var() {
    local key="$1" value="$2" env_file="$TARGET_DIR/.env"
    if grep -qE "^${key}=" "$env_file"; then
        sed -i "s|^${key}=.*|${key}=${value}|" "$env_file"
    else
        printf '%s=%s\n' "$key" "$value" >>"$env_file"
    fi
    log "set $key=$value"
}

maint_components() {
    COMPONENTS_SET=0
    ask_components
    set_env_var COMPOSE_PROFILES "$COMPONENTS"
    # A deselected profile does NOT remove a running container by itself -
    # without this down it would keep running indefinitely.
    ui_info "$(t step_up)"
    dc down --remove-orphans >>"$LOGFILE" 2>&1 || true
    pull_images
    start_stack
    wait_for_services
    ui_msg "$(t maint_comp_done "${COMPONENTS:--}")"
}

maint_update() {
    ui_info "$(t maint_update_run)"
    local out=""
    out+=$(git -C "$TARGET_DIR" pull --ff-only 2>&1 || echo "git pull skipped")
    pull_images
    start_stack
    wait_for_services
    ui_msg "$(t maint_update_done "$(printf '%s' "$out" | tail -5)")"
}

maint_status() {
    local status; status=$(dc ps 2>&1 | head -20)
    ui_msg "$(t maint_status_txt "$status")" "$(t maint_title)" 22
}

maint_language() {
    local choice
    choice=$(ui_menu "$(t lang_prompt)" 2 "de" "Deutsch" "en" "English") || return 0
    LANG_CODE="$choice"
    set_env_var MINABOX_LANGUAGE "$choice"
}

maint_uninstall() {
    ui_yesno "$(t uninstall_confirm)" 1 || return 0

    dc down --remove-orphans >>"$LOGFILE" 2>&1 || true

    if [ -f "$SYSTEMD_UNIT" ]; then
        run sudo systemctl disable --now minabox.service || true
        run sudo rm -f "$SYSTEMD_UNIT"
        run sudo systemctl daemon-reload
    fi

    local img
    for img in $(docker images --format '{{.Repository}}:{{.Tag}}' 2>/dev/null | grep -E 'minabox' || true); do
        run docker rmi "$img" || true
    done

    # User data only after two explicit confirmations.
    if ui_yesno "$(t uninstall_data "$TARGET_DIR/audio")" 1; then
        if ui_yesno "$(t uninstall_data2)" 1; then
            dc down -v >>"$LOGFILE" 2>&1 || true
            run rm -rf "$TARGET_DIR/data" "$TARGET_DIR/audio"
            log "user data deleted"
        fi
    fi

    ui_msg "$(t uninstall_done "$TARGET_DIR")"
    exit 0
}

maintenance_menu() {
    load_existing_env

    # Without dialogs, ui_menu would always return the first entry and the loop
    # would run forever. Unattended, only an update makes sense here.
    if [ "$UNATTENDED" = "1" ]; then
        log "unattended on existing install -> update"
        maint_update
        exit 0
    fi

    while true; do
        local choice
        choice=$(ui_menu "$(t maint_prompt "$TARGET_DIR")" 7 \
            "components" "$(t maint_components)" \
            "update"     "$(t maint_update)" \
            "audio"      "$(t maint_audio)" \
            "status"     "$(t maint_status)" \
            "lang"       "$(t maint_lang)" \
            "uninstall"  "$(t maint_uninstall)" \
            "exit"       "$(t maint_exit)") || exit 0

        case "$choice" in
            components) maint_components ;;
            update)     maint_update ;;
            audio)      setup_audio_hardware; setup_audio_sink
                        [ "$REBOOT_REQUIRED" = "1" ] && ui_msg "$(t audio_reboot "$(boot_config_path)" "$0")" ;;
            status)     maint_status ;;
            lang)       maint_language ;;
            uninstall)  maint_uninstall ;;
            exit)       exit 0 ;;
        esac
    done
}

# ---------------------------------------------------------------------------
# Ablauf
# ---------------------------------------------------------------------------

usage() {
    cat <<USAGE
Minabox installation wizard

  --lang de|en          Sprache / language (default: interaktiv)
  --dir <pfad>          Zielverzeichnis (default: $DEFAULT_DIR)
  --components a,b,c    rfid,led,button,display,media
  --unattended          keine Rueckfragen, Standardwerte
  --dry-run             nur anzeigen, nichts aendern
  -h, --help            diese Hilfe

  curl -fsSL https://raw.githubusercontent.com/Opnek90/Minabox/main/install.sh -o minabox-install.sh
  bash minabox-install.sh
USAGE
}

parse_args() {
    while [ $# -gt 0 ]; do
        case "$1" in
            --lang)       LANG_CODE="${2:?}"; LANG_SET=1; shift 2 ;;
            --dir)        TARGET_DIR="${2:?}"; shift 2 ;;
            --components) COMPONENTS="${2:?}"; COMPONENTS_SET=1; shift 2 ;;
            --unattended) UNATTENDED=1; USE_WHIPTAIL=0; shift ;;
            --dry-run)    DRY_RUN=1; shift ;;
            -h|--help)    usage; exit 0 ;;
            *)            printf 'Unbekannte Option: %s\n\n' "$1" >&2; usage; exit 2 ;;
        esac
    done
}

main() {
    : >>"$LOGFILE"
    log "=== install.sh started (args: $*) ==="

    parse_args "$@"
    [ "$UNATTENDED" = "1" ] || ensure_tty

    ask_language
    TARGET_DIR="${TARGET_DIR:-$DEFAULT_DIR}"

    # Bestehende Installation -> Wartung statt Neuinstallation.
    if [ -f "$TARGET_DIR/.env" ] && [ -f "$TARGET_DIR/docker-compose.yml" ]; then
        log "existing installation detected at $TARGET_DIR"
        maintenance_menu
        exit 0
    fi

    preflight
    [ "$UNATTENDED" = "1" ] || ui_msg "$(t welcome "$LOGFILE")"

    TARGET_DIR=$(ui_input "$(t dir_prompt)" "$TARGET_DIR") || die "$(t abort)"
    ask_components
    ask_basics

    install_docker
    setup_hardware_access
    clone_repo
    install_docker_daemon_config
    seed_configs
    pin_service_versions
    write_env
    setup_audio_hardware
    setup_autostart

    pull_images
    start_stack
    wait_for_services

    if [ "$REBOOT_REQUIRED" = "1" ]; then
        ui_msg "$(t audio_reboot "$(boot_config_path)" "$0")"
    else
        setup_audio_sink
    fi

    show_done
    log "=== install.sh finished ==="
}

main "$@"
