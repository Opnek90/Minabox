# Export schema

The contract between the export (backend) and the analysis (this skill). The
contract test `services/backend-service/tests/test_debug_export_contract.py`
checks a really generated package against this document - add a collector and
forget the docs, and you get a red test.

## schema_version 1

### manifest.json

| Field | Meaning |
|---|---|
| `schema_version` | version of this contract (currently 1) |
| `created_at` | creation time, UTC |
| `device_id` | device identifier from the configuration |
| `export_id` | first 16 characters of the export salt (identifies the package, not the device) |
| `redaction_level` | currently always `standard` |
| `options` | the user's selection, unchanged |
| `versions` | backend version, schema, device, creation time |
| `uncompressed_bytes` | sum of the written files |
| `collectors[]` | `{name, status, ms, error?}` per collector |
| `files[]` | `{path, bytes}` per written file |
| `truncations[]` | truncated or omitted files with the reason |
| `secret_tripwire` | `{checked: [...], blocked: [...]}` |

A collector's `status`: `ok`, `empty`, `failed`, `skipped_by_user`.

### Collector names (allowlist)

`audio.sound_test`, `client.context`, `database.copy`, `db.meta`,
`history.usage`, `logs.host_diagnostics`, `logs.services`, `logs.syslog`,
`media.summary`, `network.status`, `services.health`, `settings.environment`,
`settings.general`, `system.apt_history`, `system.boot_config`,
`system.docker`, `system.hardware`, `system.kernel_modules`, `system.os`,
`system.packages`, `system.power`, `system.storage`, `system.usb`,
`runtime.buffers`

### Files

Which files are present depends on the selection; if one is missing, the
manifest says why.

```
manifest.json                      contract, always present
README.txt                         privacy notice for the user, always present

system/hardware.json               model, revision, CPU, RAM, SD card (serial numbers hashed)
system/power.json                  undervoltage (rpi_volt hwmon), temperature, clock
system/storage.json                usage[], mounts[] (from /proc/1/mounts), readonly_mounts[]
system/os.json                     distribution, image date, kernel, architecture, uptime
system/usb_devices.json            USB inventory from sysfs
system/kernel_modules.json         loaded modules
system/docker.json                 Docker version, storage driver, disk usage
system/packages.txt                full package list ("name version" per line)
system/packages_relevant.json      curated extract
system/apt_history.txt             recent apt activity
system/boot_config.txt             /boot/firmware/config.txt (raw)
system/boot_config_active.json     the same file without comments
system/boot_cmdline.txt            /boot/firmware/cmdline.txt
system/systemd.json                failed units, journalctl -p3, timedatectl
system/network.json                network status (SSID/MAC pseudonymised)
system/host_status.json            host basics from the host-helper
system/time_status.json            time zone and NTP status

services/health.json               per service: reachability, container metadata
services/<service>/logs.txt        container logs (tail)
services/logs_missing.json         services with no retrievable logs

logs/syslog-kernel.txt             host kernel log
logs/syslog-docker.txt             Docker unit log
logs/kernel_findings.json          counters for undervoltage/throttling lines
logs/syslog_unavailable.json       only if the host-helper is missing
```

### Headers of truncated logs

Every filtered or truncated log file begins with a comment block (`#` lines,
closed by a `#` line):

```
# Source: journalctl kernel
# Period covered: 2026-08-18T09:00:01+0200 to 2026-08-18T13:45:01+0200
# Lines: 84 of 4210 kept, 4126 dropped (noise: 4100, truncation: 26)
# Always kept: 8 line(s) about undervoltage, throttling, mmc/SD, I/O errors, OOM or boot
# Note: this file is filtered and truncated. A missing note here is not evidence
# that the problem did not occur.
```

For the kernel log, Docker veth/bridge noise is dropped *before* truncation;
lines about undervoltage, throttling, mmc/SD, I/O errors, OOM and boot are
always kept. The counter in `logs/kernel_findings.json` counts on the
unfiltered stream, so it is independent of the line budget.

```

config/general_settings.json       user settings
config/auth_settings.shape.json    structure only - never the hash
config/env.sanitized.json          variable names and whether set - never values
config/services/<service>/*.json   service configurations

db/schema.sql                      schema from sqlite_master
db/table_counts.json               row counts per table
db/alembic_version.txt             migration state
db/integrity_check.txt             PRAGMA quick_check
db/meta.json                       size, page size, journal mode
db/recent_scans.json               only with history: recent scans, card IDs hashed
db/playback_summary.json           only with history: aggregate of the last 14 days
db/minabox.db.sql                  only with include_db: full SQL dump

media/library_summary.json         counts, formats, source types
media/missing_files.json           entries with no file present
media/audio_state.json             state of the audio service

runtime/errors_recent.json         the backend's recent warnings and errors (ring buffer)
runtime/mqtt_recent.json           recent MQTT messages, in = received, out = sent
runtime/temperature_recent.json    only with history: recent temperature readings

client/browser.json                browser, viewport, language, PWA mode
client/console_errors.json         ring buffer of frontend errors
client/failed_requests.json        ring buffer of failed API calls

audio/sound_test.json              only with sound_test: result of the sound-repair chain (the
                                    same one as "Fix sound problem"), incl. whether the test tone
                                    played - audibly plays a tone while the package is created
```

### What is guaranteed NOT to be included

Audio and cover files, `HOST_HELPER_API_KEY`, `WEB_AUTH_SECRET`, the password
hash, Wi-Fi PSKs, values of environment variables. Serial numbers (Pi, SD),
SSIDs, MACs and card UIDs appear exclusively as `id:<12 hex>` - comparable
within one package, not across packages.
