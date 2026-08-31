# Troubleshooting

Known failure patterns and how to tell them apart. Complements the analysis
guide in `.claude/skills/minabox-debug-analyze/` — that describes how a
diagnostics package is read, this describes what the findings mean.

## MQTT loss

**Symptom:** several services (audio, led, rfid, button) report
`"event": "service_crashed"` at the same time and are restarted by Docker.
Before that, `MqttError: Disconnected during message iteration` in the log;
afterwards, on restart, `[Errno 111] Connection refused` and
`[Errno -2] Name or service not known`.

**Cause (fixed):** up to and including the analysis from 2026-08-18 the
services connected at startup outside the supervised loop. If the broker was
gone, `connect()` gave up after five attempts, the error propagated up into
`main()` and ended the process. Docker restarted it, the broker was still
gone — a loop that only ended with the broker.

**Behaviour today:** the shared client in
`services/shared-lib/shared_lib/mqtt/base_client.py` connects inside the
supervised loop and never gives up (backoff from 1 s, cap 60 s, jitter).
Startup no longer depends on the broker. On reconnect, subscriptions and the
last reported status are re-published.

**How to see it working:** the service's `/health` reports
`"mqtt_connected": false` and `"status": "degraded"` during the outage, but the
container keeps running (`docker ps` shows no rising restart count). The log
has `mqtt_reconnect_scheduled` with a growing `delay_seconds` instead of
`service_crashed`.

`[Errno -2]` is normal here and not a separate fault: when the broker container
goes, its DNS name disappears from the Docker network too.

## Diagnostics package: Docker data missing

**Symptom:** `system/docker.json` contains only
`{"error": "DockerException: ... PermissionError(13, 'Permission denied')"}`.
Without this file the restart counts, OOM kills and container states are
missing, and triage wrongly reports "nothing found".

**Cause:** the backend container is in no group allowed to read
`/var/run/docker.sock`. The socket is owned by `root:docker` with mode 660; the
GID of the `docker` group is host-dependent.

**Fix:** find the GID on the host and put it in `.env`:

```bash
getent group docker | cut -d: -f3
```

```
DOCKER_GID=984
```

Then `docker compose up -d backend`. Nothing on the host is changed; the socket
stays mounted read-only.

**Check:**

```bash
docker compose exec backend python -c "import docker; print(docker.from_env().version()['Version'])"
```

A collector that returns only an error object is marked `failed` instead of
`ok` in `manifest.json` since the fix — so the status is reliable.

## Diagnostics package: kernel log looks empty

`logs/syslog-kernel.txt` is filtered: Docker veth and bridge lines are dropped
*before* truncation, so that boot, undervoltage and mmc lines do not fall out
of the window. The header of every truncated log file names the period covered
and the number of dropped lines.

If it says nothing about undervoltage, that does not mean there was none — only
that nothing was logged in the period covered. The counter in
`logs/kernel_findings.json` counts on the unfiltered stream and is independent
of the line budget.

## Environment: wayvnc in a restart loop

**Not a Minabox service.** On the device examined, `wayvnc.service` restarted
every 91 seconds, for hours, and kept the CPU maxed out. In diagnostics
packages this shows up as high load and as noise in the system log, and it can
cause or mask Minabox symptoms (sluggish web UI, stuttering playback).

The service belongs to the host's desktop/remote access, not to Minabox. It is
deliberately left untouched from here. To look at it on the host:

```bash
systemctl status wayvnc.service
journalctl -u wayvnc.service -n 100 --no-pager
```

If it is not needed: `sudo systemctl disable --now wayvnc.service`. That is a
decision about the host, not about Minabox.

## Box unreachable after a Wi-Fi change

**Symptom:** the box was running, then the router was swapped, the Wi-Fi
password changed or the box moved somewhere else. It can no longer be found at
its usual address or at `minabox.local`.

**Behaviour today:** the connectivity watchdog in the host-helper
(`services/host-helper-service/src/host_helper/netwatch.py`) checks via
NetworkManager every ~20 seconds whether the box has a usable connection. If it
is without a connection for more than 90 seconds and no network cable is
attached either, the box opens a Wi-Fi network of its own:

- **SSID:** `Minabox-Setup`
- **Password:** shown on the display; otherwise in the host-helper log in the
  diagnostics package (`hotspot_up`), or on the host with
  `nmcli -s -g 802-11-wireless-security.psk connection show Minabox-Setup`
- **Address:** `http://10.42.0.1`

In the web UI there, under *Maintenance → Network*, enter the new Wi-Fi. As
soon as the box is back online the watchdog turns the hotspot off on its own
(it retries the saved profiles every few minutes).

**How to see it working:** `GET /api/v1/system/network-status` (reachable
without a login) reports `"mode": "hotspot"` with SSID and password. The OLED
shows the network screen with the same details. The host-helper log has
`netwatch_offline_grace_started` and `netwatch_starting_fallback_hotspot`.

**If no hotspot appears:** `nmcli` is missing on the host (NetworkManager not
installed), or `wlan0` cannot be used in AP mode. `netwatch_op_failed` in the
log shows the `nmcli` error. An `eth0` that is plugged in but not routing
deliberately suppresses the hotspot — that is a LAN/DHCP problem, not a reason
to open a Wi-Fi.
