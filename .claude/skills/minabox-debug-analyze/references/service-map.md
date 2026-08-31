# Service map

Who does what - and where the fault really sits when a symptom shows up
somewhere else.

| Service | Container | Job | Typical failure patterns |
|---|---|---|---|
| backend | minabox-backend | REST API, database, MQTT hub, WebSocket | 5xx in `client/failed_requests.json`, DB errors, migration problems |
| webui | minabox-webui | interface (served statically) | blank page, JS errors in `client/console_errors.json` |
| audio | minabox-audio | playback via VLC/PipeWire | no sound, dropouts, wrong output device |
| rfid | minabox-rfid | card reader | card not recognised, double scans |
| button | minabox-button | GPIO buttons | button has no effect, fires constantly (pin conflict) |
| led | minabox-led | LED control | LED dark or wrong colour, pin conflict with buttons |
| display | minabox-display | display | image freezes, service missing |
| mqtt | minabox-mqtt | message bus between all services | **when it is gone, apparently nothing responds anymore** |
| host-helper | minabox-host-helper | host access: logs, network, updates, USB | network/log areas missing from the export |
| media-downloader | minabox-media-downloader | downloads (podcasts, streams) | missing files, full disk |

## Rules of thumb

- **Nothing responds anymore** → check MQTT in `services/health.json` first.
  Buttons, RFID and playback go over the bus; if it is gone, every service
  looks healthy on its own and yet nothing happens.
- **Symptom in the frontend** → first `client/console_errors.json`, then
  `services/backend/logs.txt`. A blank screen is often a JS error and not a
  backend problem.
- **Hardware symptom (sound, button, LED)** → first `system/boot_config.txt`
  (dtoverlay) and the service configuration, then the service itself. A missing
  overlay lets the service start cleanly and still do nothing.
- **Several services affected at once** → suspect a system cause: undervoltage,
  full disk, read-only filesystem, OOM.
