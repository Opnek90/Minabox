# Service Documentation Template

Every service document under `docs/services/<name>/README.md` follows the
outline below — same headings, same order, same numbering, for all services.
The point is that a contributor (or an AI agent) who has read one service
document knows exactly where to look in every other one.

**Rules**

- Keep every numbered heading, in this order, even when a service has nothing
  to say under it. Write `None.` and one sentence explaining why rather than
  dropping the section — an absent section is indistinguishable from an
  oversight.
- Subsections (`### x.y`) are free: add what the service needs, drop what it
  does not have. Only the top level is fixed.
- Document what the code does today, not what it should do. Every table
  (topics, endpoints, config keys) is checked against the source, not against
  an older version of this document.
- Length follows the service. A small service produces a short document; that
  is correct, not a gap. What must never be missing is sections 1, 2, 4, 5
  and 9 — those are what someone needs before touching the code.
- Deep prose about one mechanism belongs in its own `###` subsection, not in a
  new top-level chapter.

The short `services/<name>-service/README.md` next to the code is **not** a
second copy of this. Its shape is fixed too, and defined at the bottom of this
file.

---

## The outline

```
# <Name> Service

<Lead paragraph + fact table>

## 1. Purpose & Responsibility
## 2. File & Folder Structure
## 3. Runtime Flow
## 4. Public Interfaces
## 5. Configuration
## 6. Dependencies
## 7. Errors, Health & Logging
## 8. Development & Tests
## 9. Extending the Service
## 10. Related Documents
```

### Lead paragraph + fact table

Two or three sentences: what the service is, and its role in the box. Then a
table with the facts a reader needs before anything else — no prose:

| | |
| --- | --- |
| Image | `ghcr.io/opnek90/minabox-<name>` |
| Source | `services/<name>-service/src/<package>/` |
| Version | `services/<name>-service/VERSION` |
| Compose service | `<name>` (profile `<profile>`, or "always on") |
| Runtime | Python 3.13, asyncio / React 19 + Vite / ... |
| Speaks | MQTT, REST on `:8000` (host `127.0.0.1:<port>`) |
| Needs | broker, backend, `/dev/i2c-1`, ... |

### 1. Purpose & Responsibility

What the service is responsible for — and, explicitly, what it is **not**.
The boundary is the most valuable sentence in the document: it stops the next
change from putting playlist logic into a hardware service. Name the service
that owns what this one does not.

### 2. File & Folder Structure

An annotated tree of the source, one line per file saying what lives there.
This is the map that turns "change the debounce" into a file name. Mark the
files that carry the actual behaviour, so a reader can tell them apart from
plumbing.

### 3. Runtime Flow

Startup order and why it is that order, the main loop, and shutdown. Include
the deliberate decisions: what is allowed to fail without taking the process
down, what runs in a thread, what is retried.

### 4. Public Interfaces

Everything another service or a user can reach. Use the subsections the
service actually has:

- `### 4.1 MQTT — published` — a table: topic, retained, QoS, payload fields.
- `### 4.2 MQTT — subscribed` — a table: topic, payload, effect.
- `### 4.3 REST` — a table or a block per endpoint: method, path, body,
  response, status codes.
- further subsections as needed (WebSocket, HTTP calls this service makes).

Payload field names must match the Pydantic models; state the type when it is
not obvious. Retained flags matter — say them.

### 5. Configuration

`### 5.1 Environment` — required and optional variables with defaults.
`### 5.2 config/<file>.json` — a full key table: key, default, meaning,
validation bounds. Say who writes the file (backend or human), whether the
mount is read-only, and whether a change needs a restart or a reload topic.

### 6. Dependencies

Hardware, system packages, Python/npm packages that matter, and the other
services this one needs at runtime. Say what happens when each is absent.

### 7. Errors, Health & Logging

Health states and what makes the service `degraded`. The error codes it emits
and what each one means. The log events worth grepping for. If the container
health check does not mean what it looks like it means, say so here.

### 8. Development & Tests

How to run the service without the hardware it normally needs, the test
command, what the test suite covers, and the build/lint commands. Anything a
contributor without a Raspberry Pi has to know.

### 9. Extending the Service

The section this template exists for. Two parts:

**Common changes** — a table mapping an intent to the files to touch:

| I want to ... | Start in | Also touch |
| --- | --- | --- |
| add a new reader type | `.../reader_factory.py` | `config_schema.py`, tests |

Cover the changes people actually make, not every theoretical one. Each row
must name a real path.

**Invariants** — the rules a change must not break, each with its reason. A
retained topic that must stay retained, an event another service depends on,
an ordering that exists for a reason. Without the reason a rule reads as
arbitrary and gets removed.

### 10. Related Documents

Links to the short README next to the code, the framework document, and any
other service document that shares a contract with this one.

---

## The short README next to the code

`services/<name>-service/README.md` is a signpost, not documentation. It is
the same in every service:

````markdown
# <Name> Service

<One or two sentences: what the service does.>

**Full documentation: [docs/services/<name>/](../../docs/services/<name>/README.md)**

| | |
| --- | --- |
| Image | `ghcr.io/opnek90/minabox-<name>` |
| Version | see `VERSION` |
| Compose | `<name>` (profile `<profile>`) |
| Interfaces | <one line> |
| Config | `config/<file>.json` |

## Tests

```bash
PYTHONPATH=$(ls -d services/*/src | tr '\n' ':') .venv/bin/python -m pytest services/<name>-service/tests -q
```

## Where to make changes

<Three to six lines: the files that carry the behaviour. Details in the
architecture document.>
````

Nothing else. Topic tables, config tables, endpoint lists and troubleshooting
live in `docs/services/<name>/` only — one place to keep correct.

Two allowances: the `Tests` heading becomes `Development` where the toolchain
is not pytest (webui), and a service may add **one** further section when
something genuinely has to sit next to the code rather than in the docs tree —
media-downloader carries its lawful-use notice that way. Anything beyond that
belongs in the architecture document.
