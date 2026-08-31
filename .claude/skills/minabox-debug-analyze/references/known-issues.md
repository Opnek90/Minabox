# Known cases

Every solved support case becomes an entry here. Format: **signature** (how to
recognise it in the export) → **cause** → **fix**. If the signature can be
checked mechanically, a rule in `scripts/triage.py` belongs with it too.

The list starts with the cases that follow from how the system is built. It
grows with practice - that is the part that compounds.

---

## Raspberry Pi undervoltage

**Signature:** `system/power.json` with `undervoltage_now: true`, or a match on
`Under-voltage detected` in `logs/syslog-kernel.txt`
(`logs/kernel_findings.json` counts them).
**Cause:** the power supply or cable delivers too little current. Often a phone
charger, a long thin cable, or a passive USB hub with a hard drive.
**Fix:** the original power supply (Pi 4: 5V/3A, Pi 5: 5V/5A), a short cable, a
powered hub. Resolve this before any further analysis - undervoltage produces
follow-on errors in every service and distorts every measurement.
**Triage rule:** `undervoltage`, `undervoltage_history`

## Root filesystem gone read-only

**Signature:** `system/storage.json` with a non-empty `readonly_mounts`, plus
I/O errors in `logs/syslog-kernel.txt`.
**Cause:** the SD card reports write errors and the kernel switches to
read-only. Applications then report permission or database errors without
naming the reason.
**Fix:** replace the card, take a backup first.
**Triage rule:** `readonly_root`, `sd_io_errors`

## No sound despite a running audio service

**Signature:** `services/health.json` shows audio online, `system/boot_config.txt`
has no `dtoverlay`, or the wrong one, for the installed audio HAT.
**Cause:** without the matching overlay the sound card does not exist; the
service still starts cleanly.
**Fix:** add the matching `dtoverlay` to `/boot/firmware/config.txt` and reboot.

## GPIO pin assigned twice

**Signature:** the same pin in `config/services/button/buttons.json` and
`config/services/led/leds.json`.
**Cause:** two services claim the same pin; one fails at startup or behaves
randomly.
**Fix:** change the assignment in one of the configurations.
**Triage rule:** `gpio_conflict`

## Tracks do not play after the media moved

**Signature:** `media/missing_files.json` with `count > 0`.
**Cause:** the database points at paths that no longer exist - media moved, USB
storage not mounted, files deleted.
**Fix:** correct the media path or re-scan the entries.
**Triage rule:** `missing_media`

## Errors since the last update

**Signature:** the most recent `Start-Date` in `system/apt_history.txt`
coincides with the onset of the error; or `db/alembic_version.txt` does not
match the code.
**Cause:** a package update on the host, or a half-finished Minabox update.
**Fix:** check the affected package; on a migration-state mismatch, catch the
migration up.
**Triage rule:** `recent_apt_change`, `alembic_mismatch`

## Apparently dead box with healthy services

**Signature:** `services/health.json` shows mqtt offline, all others online.
**Cause:** without the message bus, button and RFID events do not reach the
backend. Each service looks healthy on its own.
**Fix:** check the MQTT container and its logs.
**Triage rule:** `services_offline`
