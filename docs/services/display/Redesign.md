# Display Service – Redesign

Proposal, not yet implemented. It replaces the render layer and the config
model; [Architecture.md](Architecture.md) describes what is running today.

## 1. The diagnosis

The current display is not a display, it is a **status bar**: nine widgets, all
visible at once, each in an 11 px cell. That is a desktop mental model. On
128×64 the arithmetic is unforgiving — you can show *one* thing large, or *nine*
things unreadably. There is no middle.

So the change is not "which icon goes where". It is: stop showing everything at
once.

Two further facts shape every decision below:

- **The reader shares the bus.** The panel, the PN532 and the audio codec all
  hang on `/dev/i2c-1` at 100 kHz. A full frame is 1024 bytes ≈ 92 ms, and for
  that time nothing else gets on the bus. Raising the clock to 400 kHz was tried
  on 2026-08-25 and **failed** — the PN532's clock stretching does not survive it
  ([Offene-Punkte 1.4](../Offene-Punkte.md)). The bus stays at 100 kHz.
- **The audience cannot read.** A four-year-old is the primary user. Text is for
  the parent and the older sibling.

## 2. The model: three layers

**Layer 1 — one screen per situation.** The box always knows what state it is
in. Each state gets its own layout with exactly one dominant element.

**Layer 2 — a thin status strip**, top right, only for exceptions: muted, sleep
timer, Bluetooth, repeat. Small icons are acceptable here precisely because you
only look when something is unusual.

**Layer 3 — transient full-screen HUDs** for whatever the user just changed.
Turn the volume knob → a huge number and bar for 1.5 s, then back to what was
there. This is the biggest single readability win, and it *frees* space:
volume, mute and track changes then need no permanent real estate at all —
which is three of the nine widgets that today take up room and are still too
small to read.

## 3. Screens

Derived from state, never configured. Nothing here is new data: every field
already arrives at the service today.

| Screen | When | Dominant element | Source |
| --- | --- | --- | --- |
| `boot` | service starting | wordmark + progress | — |
| `idle` | nothing playing | clock, ~38 px | container clock |
| `playing` | playing | one of three styles, §4 | `audio/status` + session queue |
| `paused` | paused | pause glyph, ~28 px | `audio/status` |
| `tag_removed` | figure lifted mid-play | struck-through figure | `rfid/tag-removed` |
| `sleep` | sleep timer running | waning moon + minutes | backend poll |
| `unknown_tag` | unknown figure | figure + "?" | `rfid/unknown-tag` |
| `quota_over` | daily limit reached | inverted "Zeit um!" | `led/usage-denied` |
| `offline` | backend unreachable | "!" + short text | `backend/unreachable` |

Transient HUDs, drawn over whatever screen is current:

| HUD | Trigger | Duration |
| --- | --- | --- |
| `volume` | volume changed | 1.5 s |
| `mute` | mute toggled | 1.5 s |
| `track_change` | track index changed | 1.2 s |
| `test_pattern` | `POST /test` | 6 s |

Priority: HUD beats transient state (`unknown_tag`, `quota_over`) beats steady
state. A HUD is never interrupted by a redraw underneath it — the mechanism the
current service already uses for the test pattern generalises to all of them.

### The data is already on the wire

The service polls `GET /api/v1/audio/session` today and reads exactly two fields
from the answer, `repeat_mode` and `shuffle`. The same response carries `queue`,
a list of `{track_id, title, artist, album, index, is_current}`. Together with
`position_ms` / `duration_ms` from `audio/status` that is everything the screens
above need. **No backend change is required to fill them.**

`rfid/presence` is retained, so the box knows whether a figure is on the reader
even after a restart.

## 4. The three playing styles

Configurable, because they serve different children.

**`chapters` (default) — the wagon train.** One carriage per track, filled for
played, the current one filling up. A child who cannot read understands "we are
on the third wagon". Title small above, remaining time small below.

**`title` — the title large.** Two lines at 17 px, progress bar below. Classic
and safe; for a non-reader it is decoration.

**`remaining` — the time left.** "noch 12 Min." at 32 px. Answers the question
children actually ask, but does not show what is playing.

All three keep the same status strip and the same HUDs. They differ only in what
fills the middle.

## 5. Configuration

The old model let the user assemble a layout. The new one lets them choose
between finished layouts — which is the whole point, so the config gets much
smaller.

```json
{
  "version": 2,
  "enabled": true,
  "i2c_bus": 1,
  "i2c_address": 60,
  "font": "sans",
  "playing_style": "chapters",
  "idle_screen": "clock",
  "hud_seconds": 1.5,
  "status_icons": ["mute", "sleep", "bluetooth", "repeat"],
  "brightness": {
    "day": 255,
    "night": 40,
    "night_from": "20:00",
    "night_to": "07:00",
    "off_at_night": false
  }
}
```

| Field | Values | Meaning |
| --- | --- | --- |
| `playing_style` | `chapters` \| `title` \| `remaining` | §4 |
| `idle_screen` | `clock` \| `quota` \| `blank` | What stands there when nothing plays |
| `hud_seconds` | 0.5–5.0 | 0 disables the transient overlays entirely |
| `status_icons` | subset, order matters | Omitting one hides it |
| `brightness` | see §8 | |

`font_size` disappears: each screen picks its own sizes, which is the point.
`elements`, `area` and `order` disappear with the grid.

### Migration and downgrade

`version` is absent in today's files, which identifies them as v1. The loader
accepts both: from a v1 file it keeps `enabled`, `i2c_bus`, `i2c_address` and
`font`, applies defaults for everything else, and logs `config_migrated_v1_v2`
once. The mapping is deliberately dumb — a widget grid does not translate into
screens, and pretending otherwise would produce surprises.

The other direction was checked rather than assumed. A **v2 file read by
today's service** validates cleanly: pydantic ignores the unknown keys and
`elements` defaults to an empty list. The result is a blank panel, not a restart
loop. That matters, because a blank panel after a downgrade is a nuisance while
a restart loop is a dead box — the failure this service was just fixed for.

## 6. What changes outside the display service

This is the larger half of the work, and the reason the redesign is not a
display-only change.

| Where | What |
| --- | --- |
| `routes_config.py` | `_validate_display_config()` rewritten for v2; `_DISPLAY_ELEMENT_TYPES` and `GET /display/element-types` retired, replaced by the style lists |
| `test_display_config_validation.py` | rewritten against the v2 schema, keeping the both-ends cross-check that holds backend and service together |
| WebUI display panel | the widget/area editor is replaced by three selects, a brightness block and a checkbox row — substantially simpler than what it replaces |
| `Architecture.md` | rewritten for the screen model |

## 7. Rendering: send less, not faster

The mistake in the earlier plan was trying to move 1024 bytes *faster*. The
SSD1306 can address a window instead — one need not send the whole frame to
change one line.

`ssd1306.display()` issues `PAGEADDR, 0, 7` and pushes all eight pages. The same
call with a narrower page range and the matching slice of the buffer costs
proportionally less. Both `command()` and `data()` are public on the device.

| Region | Bytes | at 100 kHz |
| --- | --- | --- |
| full frame, 8 pages | 1024 | 92 ms |
| 4 pages (32 px) | 512 | 46 ms |
| 3 pages (24 px) | 384 | 35 ms |
| 2 pages (16 px) | 256 | **23 ms** |

23 ms is exactly the number the 400 kHz experiment was chasing — reached at
unchanged clock, by sending a quarter of the data, with no effect on the other
two devices on the bus.

The working rule that follows:

- **A screen change is a full frame.** Entering and leaving a HUD costs 92 ms
  each. Twice per volume interaction is acceptable.
- **A value change within a screen is a partial frame.** The volume bar moving,
  the clock ticking over, a chapter filling: 23–35 ms each.
- The existing fingerprint skip stays and becomes per-region: a region is pushed
  only when *its* content changed.

**Risk.** This reaches past luma's public API for `_const`, `_colstart`,
`_colend` and `_pages`. A luma upgrade could rename them. Mitigation: probe for
those attributes once at init and fall back to full-frame rendering if they are
missing, so an upgrade degrades to today's behaviour instead of breaking.

And item 2.1 of the [go-live review](GoLive-Review.md) becomes a prerequisite:
with screens changing and HUDs appearing, the panel write has to move off the
event loop (`asyncio.to_thread` plus a lock around the device).

## 8. Brightness and night

Found while checking the above: `device.contrast(0–255)` and `device.hide()` are
public, and a contrast change is **two bytes** on the bus — free next to a frame.

For a device that stands in a child's bedroom this is worth more than any
layout. A panel at full contrast at 20:00 is a light source. The proposal:
dim to `night` between `night_from` and `night_to`, and optionally switch the
panel off entirely (`off_at_night`) — a button press or a figure wakes it.

This was not part of the original brief and is the cheapest item in this
document.

## 9. What this does not do

- **No scrolling text and no animated mascot.** Both need a continuously busy
  bus, and the bus belongs to the reader. Long titles wrap to two or three
  lines and are trimmed at measured pixel width — which also settles item 1.7
  of the go-live review.
- **No cover art.** There is no image source, and 1-bit 128×64 would not carry
  it.
- **No new MQTT topics and no new backend endpoints.** Everything the screens
  need is already published.

If full animation is ever wanted, the answer is not a faster bus but a
**separate** one: the Pi 4 can expose further I²C buses (`dtoverlay=i2c3`…`i2c6`
or `i2c-gpio`). The display would get its own, the reader keeps `i2c-1`, and the
contention disappears instead of being traded off. That costs two rewired
jumpers and is out of scope here.

## 10. Delivery

1. **Render layer, headless.** Screens, status strip, HUDs, the three styles —
   with tests against rendered 1-bit frames, no hardware needed. The mockup
   renderer used for the proposal already does exactly this and becomes the test
   fixture.
2. **Partial updates**, with the capability probe and the full-frame fallback,
   plus moving the write off the event loop.
3. **Schema v2 and migration** in the service; the panel keeps working from a v1
   file throughout.
4. **Backend and WebUI**, once the service can serve both schema versions.
5. **Brightness and night**, independent of the rest and shippable on its own.

Steps 1 and 5 are safe to build and try on the box at any point. Step 2 is the
one that wants careful testing on real hardware.
