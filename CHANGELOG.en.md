# Changelog

Changes per service. Every service carries its own version number
([docs/Versionierung.md](docs/Versionierung.md)), so it also carries its own
list.

The German version lives in [CHANGELOG.md](CHANGELOG.md). Both files share the
same structure; the release manifest the box reads during an update check is
generated from them. **Please keep the structure** - it is parsed:

```
## <service>                   Exactly the name from services/<service>-service/
### <version> - <YYYY-MM-DD>   SemVer, then a date
#### Added | Improved | Fixed
- One sentence from the user's point of view.
```

A version without a visible change may stay empty - the interface then says
"no release notes" instead of inventing a line.

---

## backend

### 0.2.1 - 2026-08-24

#### Improved
- Restoring a backup now runs in the background, and its progress can be
  queried.

### 0.2.0 - 2026-08-23

#### Fixed
- Deleting a track could, in rare cases, take the service's working directory
  with it when no file had been stored for that track.
- An unreachable podcast feed froze the box for up to 30 seconds per feed -
  interface, buttons and cards stopped responding for that time.
- On a fresh install the database migrations failed on every start. The
  database is now built entirely from the migrations; existing boxes are
  unaffected.
- A failed upload no longer leaves an unplayable entry in the media library.
- Saving the RFID settings no longer drops the other sections of the same
  file.

#### Added
- New protected area "Player and cards": covers playback, card management,
  history and the live connection. Off by default, so nothing changes about
  the current behaviour.
- The maximum upload size is now configurable and applies immediately.
- Playlists can play in order instead of shuffled - what an audio play in
  chapters needs.

#### Improved
- After five wrong passwords, signing in is locked for five minutes.
- Settings are written so a power cut mid-write cannot leave a damaged file.
- Uploads are bounded and no longer pass through memory in one piece; the
  same applies to backup and restore.
- Dashboard and history answer noticeably faster once data has accumulated.
- The image is about 38 MB smaller.

### 0.1.12 - 2026-08-23

### 0.1.11 - 2026-08-23

#### Fixed
- A pending update and an overheating warning could push each other aside,
  because the interface could only fetch the single most severe alert. Both
  are now available independently.

### 0.1.10 - 2026-08-22

#### Improved
- API error responses now carry a stable code, so the interface can reliably
  show every error message in the selected language instead of sometimes
  showing a raw technical string.

### 0.1.9 - 2026-08-22

#### Fixed
- The hint about an available update now also shows up in the header - it
  used to stay invisible there despite a running background scan and a
  manual check.

### 0.1.8 - 2026-08-21

#### Added
- Streams and podcasts can now be organized into folders just like tracks
  (each media type gets its own folder management).

### 0.1.7 - 2026-08-21

#### Added
- A periodic background scan can check for updates and reports one becoming
  ready through a hint, instead of only being noticed when opening the
  maintenance page.

### 0.1.6 - 2026-08-21

#### Added
- The database now carries a state number. When an older version meets a newer
  database - after restoring a backup, or when a service did not restart
  during an update - this is detected and reported instead of letting content
  silently appear to be missing.

#### Improved
- Several system alerts can now coexist. A temporary temperature warning used
  to push a permanent message aside.

### 0.1.5 - 2026-08-21

#### Improved
- Going back to a previous version is no longer offered.

### 0.1.4 - 2026-08-21

#### Added
- An update can target individual services instead of always touching all of
  them.

### 0.1.3 - 2026-08-21

#### Added
- The box compares its running versions against the published state and can
  say which service has something new.

### 0.1.2 - 2026-08-21

#### Fixed
- The memory percentage is no longer misleading: without a container limit it
  refers to total system memory.

### 0.1.1 - 2026-08-21

#### Improved
- Media import no longer refers to individual platforms; the wording is
  neutral.

### 0.1.0 - 2026-08-20

#### Added
- The service overview shows what actually runs on the box instead of a fixed
  list. Services a component selection never started no longer appear as
  "offline".
- Host helper and media import appear in the overview for the first time.
- CPU, memory and logs are available for every container, including the MQTT
  broker.
- Every service reports its version.

#### Fixed
- Memory was shown as "0 MB" on systems where it cannot be measured at all.
  The field now stays empty and the interface explains how to enable the
  measurement.

---

## webui

### 0.1.13 - 2026-08-24

#### Improved
- After uploading a backup the message now says "restore started" instead of
  "completed" - the box still needs a moment before every service is back.

### 0.1.12 - 2026-08-23

#### Added
- New switch for the "Player and cards" protected area.
- The maximum upload size can be set under Maintenance.
- New switch for whether playlists shuffle or play in order.

### 0.1.11 - 2026-08-23

#### Fixed
- The hint about an available update stayed invisible despite the 0.1.9 fix -
  it was completely hidden behind the header. It now shows as its own icon
  right in the header, linking to Maintenance -> Version & update.

### 0.1.10 - 2026-08-22

#### Fixed
- Error messages for WiFi, Bluetooth, backup/restore, system maintenance, and
  login often showed a wrong or unrelated message (e.g. always "logs not
  available", no matter which action failed) - every action now shows the
  matching, translated message.
- Track and subfolder counts in the media library incorrectly stayed
  singular for more than one item ("1 track" instead of "5 tracks").
- A few texts (sleep timer, output device switching, debug export among
  others) always showed German regardless of the selected language.

### 0.1.9 - 2026-08-22

#### Fixed
- "Last scanned" on RFID tags incorrectly showed "2 hours ago" right after
  scanning instead of "just now" (timezone offset).

### 0.1.8 - 2026-08-21

#### Added
- Streams and podcasts can now be organized with a folder tree, drag & drop,
  and a "move to" menu, just like tracks.
- The track list now shows pages of 25 or 50 entries instead of one long
  list, and the folder tree next to it can be collapsed.

#### Improved
- Track card and list views are more compact, and the page padding next to
  the navigation is narrower.

### 0.1.7 - 2026-08-21

#### Added
- Under Options -> Maintenance, the periodic background scan for updates can
  now be switched on or off; once one is ready, a hint appears in the header.

### 0.1.6 - 2026-08-21

#### Added
- The alert bar reports when the database comes from a newer version than the
  one running, and says what to do about it.

### 0.1.5 - 2026-08-21

#### Improved
- The "Back to the previous version" button is gone. A rollback is only safe
  when the older version can read everything the newer one wrote, and that
  cannot be promised today. To go back, restore the backup taken before the
  update.

### 0.1.4 - 2026-08-21

#### Added
- An update now only touches the services that actually have something new.
- After an update the step can be undone - the "Back to the previous version"
  button appears as long as there is something to undo.
- A backup is created automatically before every update; the dialog says so
  beforehand.

### 0.1.3 - 2026-08-21

#### Added
- "Version & update" now lists every active service with its version instead
  of a single meaningless identifier.
- A button checks for updates and shows what changes before updating.
- During an update a window shows the progress step by step; the full output
  can be expanded.

#### Improved
- Under "Restart" the two consequential actions now sit in their own row below
  the harmless restarts.
- The redundant "Select ZIP file" hint next to the backup buttons is gone; the
  selection happens in the dialog.

### 0.1.2 - 2026-08-21

#### Fixed
- Long service names were cut off in the overview ("Back...").

### 0.1.1 - 2026-08-21

#### Improved
- Importing from a URL now requires an explicit confirmation of the legal
  notice; "Check" and "Import" stay disabled until then.
- The notice no longer claims the application can verify whether an address
  is lawful.

### 0.1.0 - 2026-08-20

#### Added
- Every service card shows its version. A self-built image is marked as a
  development build.

---

## media-downloader

### 0.1.2 - 2026-08-23

### 0.1.1 - 2026-08-21

#### Improved
- Wording and example addresses are neutral; the domain list remains as a
  technical setting.

### 0.1.0 - 2026-08-20

#### Added
- The service reports its version.

---

## host-helper

### 0.2.0 - 2026-08-24

#### Fixed
- An uploaded backup was not actually restored: the services kept running, the
  database was swapped out underneath them, and an error appeared anyway.
- A factory reset did not restart the services afterwards.
- Importing from a USB stick could copy files from outside the stick along
  with the rest, by way of links stored on it.
- Whether a Bluetooth device was currently connected always showed as "not
  connected".

#### Improved
- The service shrank from 605 to 290 MB - an update downloads less than half
  of what it used to.
- The list of paired Bluetooth devices now takes the same time no matter how
  many devices the box remembers.
- Moving the audio folder answers immediately instead of waiting until every
  file has been counted.
- A second system update can no longer be started while one is still running.
- A damaged or oversized backup file is rejected before it changes anything.

### 0.1.5 - 2026-08-23

### 0.1.4 - 2026-08-21

#### Improved
- Going back to a previous version is no longer offered. Which versions ran
  before an update is still recorded - for support questions, not as a button.

### 0.1.3 - 2026-08-21

#### Added
- An update can bring individual services to specific versions. Every other
  service is pinned to what it currently runs, so a targeted update does not
  drag anything else along.
- A backup is written to data/backups before every update; the last five are
  kept. If it fails, no update happens.
- After the restart each affected service is checked for actually running the
  intended version - "running again" alone is not enough.

### 0.1.2 - 2026-08-21

#### Fixed
- During an update "git pull" ran as root and left root-owned files in the
  project folder. It now runs as that folder's owner.

### 0.1.1 - 2026-08-21

#### Fixed
- The Minabox update did nothing: it called the docker commands inside the
  container, where they do not exist. It now runs on the host and survives the
  service restarting itself along the way.

#### Added
- The progress of an update can be read: step, total and the full output.

### 0.1.0 - 2026-08-20

#### Added
- The service reports its version and appears in the service overview.

---

## audio

### 0.2.0 - 2026-08-23

#### Fixed
- Pressing the volume knob now really mutes the box. It previously only turned the volume down to the configured minimum while already reporting "muted".
- If the service crashes or the power is cut, the LED, display and web interface no longer keep showing playback forever.
- A freshly set up box now starts at the configured default volume instead of the maximum volume.
- After stopping, the interface no longer shows a track that is not playing any more.
- Switching the output no longer blocks the controls for several seconds.

#### Improved
- The service image shrank from 940 to 544 MB, so updates download noticeably faster.

### 0.1.1 - 2026-08-23

### 0.1.0 - 2026-08-20

#### Added
- The service reports its version.

---

## rfid

### 0.2.0 - 2026-08-23

#### Improved
- A card that shifts slightly on the reader no longer interrupts playback.
  A single dropped read used to stop the music, and the track restarted from
  the beginning seconds later.
- A reader that is not seated properly is now reported as an error and
  recovers on its own once it is back. The service used to restart endlessly
  with no visible sign of what was wrong.
- Learning mode returns to normal by itself after five minutes without a scan.
  Closing the learning dialog without finishing it used to leave the box
  unable to play anything from a card.
- Card presence and service status are available again after the messaging
  service restarts, instead of being gone for good.
- If the service crashes, the card counts as removed straight away. The box
  used to keep assuming a card was still on the reader.
- Every reader timing - debounce, scan interval, learning timeout and the
  PN532 settings - now lives in the configuration file and can be changed
  without a new image.
- The service status page now names the reader, the operating mode and the
  last error, which shortens fault finding considerably.

### 0.1.0 - 2026-08-20

#### Added
- The service reports its version.

---

## button

### 0.1.2 - 2026-08-23

### 0.1.1 - 2026-08-22

### 0.1.0 - 2026-08-20

#### Added
- The service reports its version.

---

## led

### 0.1.1 - 2026-08-23

### 0.1.0 - 2026-08-20

#### Added
- The service reports its version.

---

## display

### 0.1.1 - 2026-08-23

### 0.1.0 - 2026-08-20

#### Added
- The service reports its version.
