# First-run wizard (web UI)

Status: 2026-08-20 — implemented, not yet exercised on real hardware.

## Why

`install.sh` gets the stack running, nothing more. After the first visit to the
interface you are on the player and have to find everything else yourself.
Today there is no first-run setup at all: no `first_run` flag, no onboarding
route, no welcome step.

One aspect of this is more than convenience. In
[`routes_auth.py:59`](../../../services/backend-service/src/backend_service/api/routes_auth.py)
`auth_enabled` is derived from whether a password hash exists at all:

```python
auth_enabled = bool((settings.get("web_password_hash") or "").strip())
```

On a fresh install there is none. **Every newly set up box is unprotected and
open on the entire home network**, until someone sets a password on their own
initiative — including media management and the parent dashboard. That is
exactly what the wizard is meant to catch.

The second aspect: `install.sh` can only *configure* hardware, not *try it
out*. A test tone, a blinking LED, a scanned tag — none of that works in the
browser or the terminal. The CLI wizard and the web UI wizard therefore
complement each other, they do not overlap.

## Decisions

| Topic | Decision |
|---|---|
| Steps | language, access protection, audio with a test tone, confirm hardware, first content |
| Commitment | starts automatically, can be cancelled at any time; afterwards a hint stays until it is completed |
| Repeatable | yes, via an entry in the settings, with pre-filled values |

## What already exists

Most of the building blocks are there. The wizard should orchestrate them, not
build them anew.

| Building block | Where | Use in the wizard |
|---|---|---|
| `Stepper` pattern | [`ButtonConfigPanel.tsx:372`](../../../services/webui-service/src/components/admin/ButtonConfigPanel.tsx), [`LEDConfigPanel.tsx:350`](../../../services/webui-service/src/components/admin/LEDConfigPanel.tsx) | step navigation |
| Set password / protect areas | `routes_auth.py` | step 2 |
| Sink list, switch output | `GET /api/v1/audio/devices`, `POST /api/v1/audio/switch-device` | step 3 |
| Volume limits | `GET/PUT /api/v1/config/audio` | step 3 |
| LED test | `POST /api/v1/config/leds/test` | step 4 |
| Live button press | WS event `button_raw_event`, via `useWebSocketEvent` | step 4 |
| RFID learn mode | `POST /api/v1/rfid/learning-mode`, WS `rfid_scanned_learning` | step 5 |
| Media upload | `MediaPage` | step 5 |
| Service state | WS event `service_status` | step 4 (which hardware is running at all) |
| Settings index | [`settingsIndex.ts`](../../../services/webui-service/src/config/settingsIndex.ts) | entry to start again |

The hardware test mode is already laid out as a concept:
`handle_button_raw_event` in the button handler sends every physical button
press to the frontend, explicitly for buttons without an action mapping too.

## Implemented

**Backend**

- `setup_completed` and `setup_version` in the `allowed` set of
  `update_general_config` ([`routes_config.py`](../../../services/backend-service/src/backend_service/api/routes_config.py)),
  with type coercion as for the other fields.
- `POST /api/v1/audio/test-tone` (backend proxy) →
  `POST /api/v1/test-tone` in the audio service. The tone is played via
  `paplay`, **not** via the VLC backend: so it plays alongside a running
  playback instead of stopping it.
- A bundled asset `services/audio-service/assets/test-tone.wav` (1.4 s triad,
  copied to `/app/assets/` in the Dockerfile).
- `POST /api/v1/config/display/test` (backend proxy) → `POST /test` in the
  display service, analogous to the existing `leds/test`.

**Frontend**

- `pages/SetupWizardPage.tsx` with a stepper and six steps.
- `components/setup/{SecurityStep,AudioStep,HardwareStep,ContentStep}.tsx`.
- `hooks/useSetupStatus.ts` with detection of existing installations.
- Route `/setup` in `App.tsx`, deliberately **without** `ProtectedRoute`.
- A one-time redirect on the first visit plus a dismissible hint.
- `components/admin/SetupWizardRestart.tsx` and a `setup_wizard` section in
  `settingsIndex.ts` to start again.
- Namespace `setup` in `i18n.ts`, `public/locales/{de,en}/setup.json` (86 keys,
  matching).

### Two things that turned out different while building

**`paplay` does not report an unknown sink.** It silently falls back to the
default output and exits with 0. For the wizard that would be the worst variant:
the user picks output A, hears sound from B, and considers A verified. The sink
is therefore checked against the detected device list **before** playing, and
an unknown name is rejected with 404.

**The display render loop ticks every second.** A test image would have been
overwritten after a second at most and not readable. The loop therefore has a
lock (`_test_pattern_until`) during which it skips the normal frame.

There is no lock-out risk after the password step: `POST /auth/password` sets a
session cookie itself when the password is first set.

## Original gap analysis

**1. Persistence flag.** `update_general_config` in
[`routes_config.py:217`](../../../services/backend-service/src/backend_service/api/routes_config.py)
filters the request against a fixed `allowed` set:

```python
data = {k: v for k, v in body.items() if k in allowed}
```

A new key is therefore **silently dropped**. The set has to be extended with
`setup_completed` (bool) and `setup_version` (int). `setup_version` makes it
possible to offer the wizard again after a larger update, without forcing it on
existing users.

**2. Test tone.** There is no endpoint for it. Needed:
`POST /api/v1/audio/test-tone`, forwarded in the backend to the audio service —
analogous to `get_audio_devices`, which already proxies via `httpx`. The audio
service needs a short, bundled audio file in the image for this (a few seconds,
unobtrusive). It must not come from the library: on a fresh box it is empty.

**3. Display test.** The display service has only `/health` today
([`routes.py:28`](../../../services/display-service/src/display_service/api/routes.py)).
For an honest visual check a test image is missing. The model is `leds/test`:
an MQTT command `display/test` that shows a test pattern for a few seconds. If
that turns out to be too much, the fallback is a plain yes/no question ("Do you
see anything on the display?") combined with `service_status` — more honest
than a test that tests nothing.

**4. The wizard itself.**

- `SetupWizardPage.tsx` plus one component per step
- Route `/setup` in `MainLayout` ([`App.tsx:187`](../../../services/webui-service/src/App.tsx)) —
  **without** `ProtectedRoute`, otherwise the wizard locks itself out as soon
  as a password is set in step 2
- A hook that reads `setup_completed` and redirects once to `/setup` on the
  first visit
- A discreet, dismissible hint in `MainLayout` while not completed
- A new i18n namespace `setup.json` in `public/locales/{de,en}/`
- An entry in `settingsIndex.ts` to start again

## The steps in detail

**1. Language.** German/English. Sets `localStorage['minabox-language']` as
before. If `MINABOX_LANGUAGE` from `.env` is made reachable, it serves as the
preselection — the wizard in `install.sh` already asked the question, and
asking it a second time is only acceptable when it is pre-filled.

**2. Access protection.** Set a password, choose areas (`admin`, `media`,
`dashboard`). Skipping is possible, but with a clear statement of what that
means — not with a warning colour, but with a sentence.

**3. Audio.** Offer sinks from `GET /audio/devices`, activate the chosen sink
via `switch-device`, **play a test tone**, then "Did you hear anything?" On no:
offer the next sink instead of leaving the user alone. Then volume limits
(min/default/max) from `config/audio`.

This step justifies the wizard on its own. "No sound" is, according to
`.claude/skills/minabox-debug-analyze/references/known-issues.md`, the most
common failure pattern of all.

**4. Confirm hardware.** Only for services that are actually running — which
those are is told by `service_status`. Per LED a test via `leds/test` with a
follow-up question; for buttons the test mode with `button_raw_event`, which
shows which button was just pressed; for the display the test image.

This immediately reveals what otherwise stays unnoticed for weeks: swapped
pins, or the same GPIO twice in `buttons.json` and `leds.json` — a known
failure pattern.

**5. First content.** Turn on learn mode, place the first card, assign it to a
track or folder. Then upload music or choose a media path. This step is the
most dispensable and should be the most clearly marked as skippable.

**Finish.** Write `setup_completed: true` and `setup_version`, a short summary,
on to the player.

## Open check points

The wizard is built and translated, but **not yet exercised on real
hardware**. To check before shipping:

- [ ] Fresh box: the wizard pops up on the first visit. After cancelling, the
      hint appears, but **no** repeated redirect on a page change.
- [ ] Existing installation with existing cards: the wizard does **not** pop
      up. That is the assumption behind `useSetupStatus` and the only point
      that works without a migration script.
- [ ] After step 2 the session stays valid — then open `/admin` without having
      to sign in again.
- [ ] Test tone: trigger it during a running playback. The music must not stop.
- [ ] Test tone on a box with several outputs: switch the output, trigger the
      tone, and check that it really comes out of the chosen device.
- [ ] Hardware step on a box without LED/button/display: shows the hint and can
      be skipped.
- [ ] The display test image stays visible (the lock holds it for six
      seconds), then the normal display returns.
- [ ] Learn mode is turned off again when leaving the content step. Otherwise
      the box stays stuck in learn mode and plays nothing.
- [ ] Fully operable on the phone.
- [ ] After finishing: `data/general_settings.json` contains
      `"setup_completed": true` and `"setup_version": 1`.
