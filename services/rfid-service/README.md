# RFID Service

Hardware abstraction and MQTT publisher for RFID tags in Minabox. The RFID service reads tags via a configured reader (real PN532 or a mock), publishes tag events to MQTT, and supports a Backend-driven learning mode.

For the full interface/flow details (MQTT topics, payload shapes, and mode behavior), see [`docs/services/rfid/Architecture.md`](../../docs/services/rfid/Architecture.md).

## REST API

Service root endpoint:
- `GET /health`

Learning mode is controlled through the Backend:
- `POST /api/v1/rfid/learning-mode` (Backend publishes to `minabox/<id>/rfid/cmd/set-mode`)

## MQTT Topics

Topic prefix pattern:
- `minabox/<device-id>/...`

Published events:
- `.../rfid/tag-scanned` (payload: `{ tag_id, reader_id, timestamp }`)
- `.../rfid/tag-scanned-learning` (payload: `{ tag_id, reader_id, timestamp }`)
- `.../rfid/tag-removed` (payload: `{ tag_id, reader_id, timestamp }`)
- `.../rfid/status` (retained; payload includes `{ state, reader_id, error, timestamp }`)

Commands (subscribe):
- `.../rfid/cmd/set-mode` (payload: `{ "mode": "normal" | "learning" }`)

General config (subscribe for runtime log level):
- `.../config/general` (MQTT payload includes `log_level`)

## Configuration

Main config file: `config/rfid.json`

Reader configuration:
- `reader.reader_type`: `"pn532"` or `"mock"`
- `reader.interface`: `"i2c"`, `"spi"`, or `"uart"`
- `reader.scan_interval_ms`: scan loop interval
- `reader.duplicate_suppression_ms`: suppression window for repeated scans of the same tag

