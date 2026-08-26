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
  ([Offene-Punkte 1.4](../Offene-Punkte.md)). The bus stays at 100 kHz, and §8
  reaches the same latency by sending less.
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

Derived from state, never configured.

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

### What is already on the wire, and what is not

The **screens** need no new data. The service polls `GET /api/v1/audio/session`
today and reads two fields from the answer, `repeat_mode` and `shuffle`; the
same response carries `queue`, a list of
`{track_id, title, artist, album, index, is_current}`. Together with
`position_ms` / `duration_ms` from `audio/status` that fills every screen above.

The **volume HUD does need three new fields**, and §5 explains why. They are
integers in an existing payload, not a new topic:

| Field | Today | Needed because |
| --- | --- | --- |
| `min_volume` | in the audio config only | the raw volume is not a percentage |
| `max_volume` | in the audio config only | same |
| `volume_step` | a constant in the audio service | the HUD renders one block per detent |

`rfid/presence` is retained, so the box knows whether a figure is on the reader
even after a restart.

## 4. The three playing styles

Configurable, because they serve different children — and the choice grows with
the child rather than with taste.

**`chapters` (default) — the wagon train.** One carriage per track, filled for
played, the current one filling up. A child who cannot read understands "we are
on the third wagon". Title small above, remaining time small below.

**`title` — the title large.** Two lines at 17 px, progress bar below. Classic
and safe; for a non-reader it is decoration.

**`remaining` — the time left.** "noch 12 Min." at 32 px. Answers the question
children actually ask, but does not show what is playing.

All three keep the same status strip and the same HUDs. They differ only in what
fills the middle.

## 5. The volume screen

This is the screen the box gets used for most, so it is specified rather than
sketched.

### The trap: `max_volume` is a clamp, not a scale

`services/audio-service/src/audio_service/core/service.py` pulls the running
volume into range with `min(max(current_volume, min_vol), config.max_volume)`.
With `max_volume: 40`, `audio/status` therefore reports `volume: 40` when the
knob is at its stop. A display showing "40 %" at maximum volume is worse than no
display at all.

The WebUI already gets this right — `PlayerPage.tsx` hands
`minVolume` / `maxVolume` to `VolumeControl`, so its slider spans the *allowed*
range. The display must do the same:

```
percent = (volume - min_volume) / (max_volume - min_volume) * 100
```

### One block per detent

`VolumeStepCommand.step` is 5, and the button service publishes an empty payload
so that default always applies. Over 0–40 that is **exactly 8 steps**. The HUD
therefore draws a row of blocks, one per detent, filled up to the current value:

```
steps  = (max_volume - min_volume) / volume_step
filled = (volume - min_volume) / volume_step
```

One click of the knob lights exactly one more block. It is countable from two
metres without reading the number, which is the point — the number is for the
parent, the blocks are for the child.

**Fallback.** With `4 ≤ steps ≤ 16` the blocks are legible; outside that range
(a box configured 0–100 at step 1 would want 100 of them) the same area renders
as a continuous bar. The renderer decides this from the numbers, so no setting
is needed.

### Three cases that need their own answer

| Case | What it shows | Why |
| --- | --- | --- |
| at maximum | all blocks filled + "MAX" | otherwise one keeps turning and wonders |
| at minimum | "0" + empty blocks + "leise" | zero is not muted, and the difference has to be visible |
| muted | crossed-out speaker, full screen | the mute HUD, on the same stage as the volume |

Three digits do not fit next to the speaker glyph at 42 px, so the number's font
size follows its value (42 px below 100, 32 px at 100).

## 6. Configuration

The old model let the user assemble a layout. Nine element types across three
areas is a space in which most combinations look bad and none were ever
reviewed — the service admits as much by logging `display_area_overcrowded`,
which is a UI telling the user it allowed a state it dislikes.

The layout is therefore not configurable any more. What remains is what someone
actually revisits:

```json
{
  "enabled": true,
  "i2c_bus": 1,
  "i2c_address": 60,
  "playing_style": "chapters",
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
| `enabled` | bool | panel on or off |
| `i2c_bus`, `i2c_address` | int | hardware; belongs in setup, not in settings |
| `playing_style` | `chapters` \| `title` \| `remaining` | §4 |
| `brightness` | see §9 | the one thing that is genuinely readjusted |

Gone, with a fixed default in their place: `font`, `font_size`, `status_icons`,
`hud_seconds`, `idle_screen`, and the whole `elements` / `area` / `order` grid.
Every one of them was a layout nobody had tested plus a control somebody had to
build.

**No migration path.** The box is in development and there is exactly one of
them; the config file is replaced, not converted.

## 7. What changes outside the display service

| Where | What |
| --- | --- |
| `audio-service` | `min_volume`, `max_volume`, `volume_step` into the `audio/status` payload and into `_status_fingerprint`, so a config change republishes |
| `routes_config.py` | `_validate_display_config()` rewritten for the small schema; `_DISPLAY_ELEMENT_TYPES` and `GET /display/element-types` retired |
| `test_display_config_validation.py` | rewritten, keeping the both-ends cross-check that holds backend and service together |
| WebUI display panel | the widget/area editor is replaced by one select, a brightness block and a checkbox — substantially less than what it replaces |
| `Architecture.md` | rewritten for the screen model |

## 8. Rendering: send less, not faster

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
  each. Twice per volume interaction is acceptable, and turning the knob and
  placing a figure are mutually exclusive anyway.
- **A value change within a screen is a partial frame.** The volume blocks
  moving, the clock ticking over, a chapter filling: 23–35 ms each.
- The existing fingerprint skip stays and becomes per-region: a region is pushed
  only when *its* content changed.

**Risk.** This reaches past luma's public API for `_const`, `_colstart`,
`_colend` and `_pages`. A luma upgrade could rename them. Mitigation: probe for
those attributes once at init and fall back to full-frame rendering if they are
missing, so an upgrade degrades to today's behaviour instead of breaking.

And item 2.1 of the [go-live review](GoLive-Review.md) becomes a prerequisite:
with screens changing and HUDs appearing, the panel write has to move off the
event loop (`asyncio.to_thread` plus a lock around the device).

## 9. Brightness and night

Found while checking the above: `device.contrast(0–255)` and `device.hide()` are
public, and a contrast change is **two bytes** on the bus — free next to a frame.

For a device that stands in a child's bedroom this is worth more than any
layout. A panel at full contrast at 20:00 is a light source. The proposal:
dim to `night` between `night_from` and `night_to`, and optionally switch the
panel off entirely (`off_at_night`) — a button press or a figure wakes it.

This was not part of the original brief and is the cheapest item in this
document.

## 10. What this does not do

- **No scrolling text and no animated mascot.** Both need a continuously busy
  bus, and the bus belongs to the reader. Long titles wrap to two or three
  lines and are trimmed at measured pixel width — which also settles item 1.7
  of the go-live review.
- **No cover art.** There is no image source, and 1-bit 128×64 would not carry
  it.
- **No new MQTT topics and no new endpoints.** The only addition anywhere is
  three integers in a payload that is already published (§3).

If full animation is ever wanted, the answer is not a faster bus but a
**separate** one: the Pi 4 can expose further I²C buses (`dtoverlay=i2c3`…`i2c6`
or `i2c-gpio`). The display would get its own, the reader keeps `i2c-1`, and the
contention disappears instead of being traded off. That costs two rewired
jumpers and is out of scope here.

## 11. Delivery

The volume screen comes first, as a **vertical slice**: it is the one screen
that is settled, and it exercises the whole architecture — screen precedence,
HUD timing, partial update, drawing off the event loop. If it looks right on the
real panel, everything else follows the same pattern.

1. **Volume HUD, headless.** The renderer, the range arithmetic, the detent
   blocks and the three edge cases of §5, with tests against rendered 1-bit
   frames. No hardware needed.
2. **The three fields** in `audio/status`, and the display consuming them.
3. **On the panel.** HUD precedence and timing over the existing render loop,
   still full-frame.
4. **Partial updates**, with the capability probe and the full-frame fallback,
   plus moving the write off the event loop.
5. **The remaining screens and the playing styles.**
6. **Small schema, backend and WebUI.**
7. **Brightness and night**, independent of the rest and shippable on its own.

Steps 1, 2 and 7 are safe to build and try at any point. Step 4 is the one that
wants careful testing on real hardware.

### Where this actually got to

Steps 1 to 5 are built, in a different order than planned: the volume overlay
first, then the playing screen, then partial updates - which turned out to be a
prerequisite rather than an optimisation, because the idle screen animates.

The idle screen is Knuffel, a creature that wanders, and the unknown-figure
screen is the same creature looking puzzled. Both are described in
[Architecture.md](Architecture.md).

What that leaves, and it is the larger half:

- The **widget grid is unreachable** but still in the tree, and `elements` in
  `display.json` is accepted and ignored. The WebUI's layout editor no longer
  affects the panel. Step 6 removes all of it.
- **Screens not built:** `boot`, `paused` as its own screen, `tag_removed`,
  `sleep`, `quota_over`, `offline`. Everything that is not playing currently
  falls through to Knuffel.
- **No status strip.** The grid used to carry the error flag, the sleep timer,
  Bluetooth, repeat and shuffle. Only mute survived, drawn on the playing
  screen. Layer 2 of §2 is still a proposal.
- **`rfid/tag-blocked`** has no screen. A barred figure is not an unknown one,
  and answering it with "Wer bist du?" would be a lie.
