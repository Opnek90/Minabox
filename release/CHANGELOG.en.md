# Changelog

Changes per service. Every service carries its own version number, so it also
carries its own list.

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

### 0.3.2 - 2026-09-01

#### Fixed
- No visible change: 0.3.1 was never published as an image, because the build
  was skipped after a red test run. This number ships it.

### 0.3.1 - 2026-09-01

#### Added
- Groundwork for the weekly review: the box condenses one week of listening
  data into a summary - total time, the change from the previous week, the
  spread across weekdays, the most played card and cards that have never been
  played.
- New "data retention" setting (52 weeks by default): playback and scan history
  older than that is deleted automatically every day. On existing boxes the
  first run removes everything older than a year, once.

### 0.3.0 - 2026-09-01

#### Added
- Uploads now read artist, album and the embedded cover art from the file -
  including FLAC, OGG and M4A files, not just MP3.
- New "Look up metadata online" switch (Maintenance -> Media, off by default):
  for files with no tags of their own, the box asks MusicBrainz and the Cover
  Art Archive. The track title and artist are sent to those services.
- "Fill in cover art & metadata" completes missing details and cover art for
  tracks already in the library, in the background.

### 0.2.14 - 2026-09-01

#### Added
- An update channel: "stable" only ever offers finished releases, "beta"
  additionally offers pre-releases to try out. Switchable under
  Maintenance -> Version & Update, and switching back is enough.
- "Back to the previous version" per service: the box remembers what ran
  before an update and can put it back without a console.
- A step back is refused when the update migrated the database - with the
  reason, instead of attempting it and losing data.

### 0.2.13 - 2026-08-31

#### Improved
- More markers in the diagnostics package log files are now in English.

### 0.2.12 - 2026-08-31

#### Improved
- The headers of the filtered log files in the diagnostics package are now in
  English.

### 0.2.11 - 2026-08-31

#### Improved
- The update check now reads the release manifest from the new `release/`
  folder in the repository.

### 0.2.10 - 2026-08-30

#### Improved
- The web password asks for eight characters instead of four - the same length
  as the system password.

### 0.2.9 - 2026-08-29

#### Added
- A new network status value (mode, address, setup hotspot) that the web UI
  and the display read.

### 0.2.8 - 2026-08-28

#### Improved
- The container's service user no longer has a home directory and can no
  longer be logged into (image hardening).

### 0.2.7 - 2026-08-27

#### Improved
- Optional components not selected during installation (RFID, LEDs, buttons,
  display, media download) are recognised server-side. Direct calls for them
  are rejected immediately and clearly instead of failing after a long wait.

### 0.2.6 - 2026-08-27

#### Added
- The allowed sources for media import are now configurable in the WebUI
  (Admin -> General -> media import). YouTube is no longer included by
  default.

#### Improved
- An allowed domain like "bandcamp.com" now automatically covers
  "www.bandcamp.com" too, instead of only the exact spelling entered.

### 0.2.5 - 2026-08-26

#### Added
- The debug package can now optionally include a sound test: the box plays an
  audible test tone once (administrators only, never part of a preset).
- The "Fix sound problem" button now reports the result of each individual
  repair step, not just a yes/no at the end.

### 0.2.4 - 2026-08-26

#### Added
- A service that reports it cannot do its job is now shown as degraded in the
  service list. It used to stay green as long as its container was running.
- Connects the new "Fix sound problem" button to the sound service and the box.

#### Fixed
- Restarting the sound service now asks for the administrator password if one
  is set.

### 0.2.3 - 2026-08-26

#### Improved
- The display settings are down to the connection and the brightness. The old
  element list is still accepted and ignored, so existing boxes keep running
  unchanged.
### 0.2.2 - 2026-08-25

#### Fixed
- An incomplete button configuration was saved and reported as successful even
  though the button service cannot load it. It is now rejected, naming the
  button and the missing field.

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

### 0.4.2 - 2026-09-01

#### Fixed
- Clicking a question mark twice in quick succession left the explanation
  stuck open - it only closed again once you moved the pointer away.
- Also ships 0.4.1, which was never published as an image.

### 0.4.1 - 2026-09-01

#### Added
- New "weekly review" card on the dashboard under Listening statistics: the
  week's listening time against the previous week, one bar per weekday, the
  most played card and an expandable list of cards that were never played. The
  arrows step through the weeks.
- New "data retention" setting under Rules: sets how many weeks of playback and
  scan history the box keeps (0 = keep forever).

### 0.4.0 - 2026-09-01

#### Improved
- The long explanations in the settings no longer sit permanently under every
  field. A question mark next to it shows them on hover or on tap; on a phone
  they arrive as a sheet from the bottom edge. Warnings, input rules and
  descriptions of the options you are choosing between stay visible.

### 0.3.0 - 2026-09-01

#### Added
- New "Media" section in the settings: a switch for the online metadata lookup
  and a "Fill in cover art & metadata" action that completes missing details
  and cover art for the existing library, with a progress display.

### 0.2.3 - 2026-09-01

#### Added
- A choice of update channel, and a "Back to <version>" button per service
  under Maintenance -> Version & Update. A running pre-release is marked
  "beta" in the version list.

#### Fixed
- Settings that were set and saved in one click wrote the previous value back.
  Among others this affected the "check for updates automatically" switch,
  which could be flipped without the setting ever arriving.

### 0.2.2 - 2026-09-01

#### Added
- New details view for tracks, streams and podcasts: a table with sortable
  columns (title, artist, duration, last played and more). Available on desktop
  via the third view button; narrow screens keep the list or card view.

### 0.2.1 - 2026-08-31

#### Fixed
- Three server errors showed up as a generic "something went wrong" because
  their text was missing: a failed restart of the audio service, and invalid
  button and display settings.
- The web server's error page was still sitting in the served folder as a
  foreign file, reachable under /50x.html.

### 0.2.0 - 2026-08-30

#### Added
- Repeat and shuffle are visible in the player: coloured means on, pale means
  off, a tap toggles.
- The sleep timer takes a freely entered duration next to 15, 30, 45 and 60
  minutes.
- Changes to lights and buttons can be discarded instead of only being
  undoable by reloading the page.
- When a fixed address is still sitting in the network profile despite DHCP,
  the page now says so - the box was silently answering on two addresses.

#### Improved
- The interface image shrank from 98 to 25 MB.
- The interface sends security headers and no longer reveals its web server's
  version.
- The web password asks for eight characters instead of four; the rule is
  stated at the field.
- "Parents -> Time and rules" is laid out like the settings pages.
- The icons in the app bar no longer touch the frame around them.

#### Fixed
- Large uploads no longer break off after 15 seconds - nor get uploaded three
  more times afterwards.
- A button press on the box and a change at the rotary knob reach the player
  again; the repeat and shuffle icons follow along.
- Editing one podcast no longer overwrites all the others.
- Removing cover art no longer closes the edit dialog.
- The network status card no longer goes stale after a hotspot switch.
- The button that sets the password did nothing.
- Downloading a backup reported the message meant for restoring one.

### 0.1.23 - 2026-08-29

#### Added
- The network settings now show the current state: mode, the address to reach
  the box on, and whether the setup hotspot is running.

### 0.1.22 - 2026-08-28

#### Improved
- With the log level set to "debug", the web interface shows missing
  translations as raw keys and reports them in the browser console instead of
  silently falling back to English. Nothing changes at any other log level.

### 0.1.21 - 2026-08-27

#### Improved
- The web interface hides navigation, settings and actions for components
  that were not selected during installation. An installed component that is
  currently unreachable stays visible.

### 0.1.20 - 2026-08-27

#### Fixed
- In the media area, an action in the plus menu turned transparent on hover,
  letting controls from the list behind it show through.
- After an update from the web interface, the "Update started" message
  appeared repeatedly after the restart instead of only once.

#### Improved
- Settings now have their own "Media" section (music folder, upload limit,
  allowed import sources, USB transfer); "Maintenance" only holds updates,
  backup and the setup wizard.

### 0.1.19 - 2026-08-27

#### Added
- The media import dialog now shows the individual steps while importing
  (reading metadata, downloading with speed and time remaining, converting,
  embedding cover/metadata, saving) instead of a single loading bar.
- New setting under Admin -> General: allowed domains for media import.

### 0.1.18 - 2026-08-26

#### Added
- The debug package dialog now has an option for a sound test with an audible
  test tone, visible to administrators only and never preselected.
- The "Fix sound problem" button now shows, collapsed by default, which
  repair step ran, was fixed, or failed.

### 0.1.17 - 2026-08-26

#### Fixed
- "Up next" showed the wrong order during a running playlist: already-played
  tracks were listed ahead of the upcoming ones.

### 0.1.16 - 2026-08-26

#### Added
- *Maintenance* has a **Fix sound problem** button. The box checks everything
  that can silence the sound, one thing after another, repairs what it can
  repair itself, plays a test tone and asks in plain words whether you hear
  anything. Say no and it goes on: restart the sound service, then the cable,
  the power, and last a restart of the box.
- Services that report they cannot do their job now show amber in the service
  list instead of green.

#### Improved
- The LED repeats field now explains that it counts whole cycles and that 0
  means forever.

#### Fixed
- Deleting a medium left its assigned card half-linked: it went on pointing at
  a title that no longer existed.
- Some buttons lost their height, padding and font size as soon as their width
  was adjusted.

### 0.1.15 - 2026-08-26

#### Improved
- The volume reading in the player shows the same number as the display on the
  device.
- The display settings are down to the connection and the brightness; the
  element editor is gone, because it no longer affected anything.
### 0.1.14 - 2026-08-25

#### Improved
- Pin numbers and the action can no longer be forgotten in the buttons area -
  the fields are marked required, and Save stays disabled until they are
  filled in.
- When saving a button configuration fails, the message now says which button
  and which field is meant.

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

### 0.2.2 - 2026-08-31

#### Improved
- Logging is configured when the service starts rather than when the module is
  loaded. No visible change in operation; it used to reconfigure logging for
  every other service in the shared test run.

### 0.2.1 - 2026-08-28

#### Improved
- The container's service user no longer has a home directory and can no
  longer be logged into (image hardening).

### 0.2.0 - 2026-08-27

#### Added
- Importing now shows real progress steps (reading metadata, downloading
  with speed and time remaining, converting, embedding cover and metadata,
  saving) instead of a single loading bar.

#### Improved
- An import now has an upper limit on file size (200 MB by default).

#### Fixed
- A longer import could block the service long enough for its own health
  check to fail, aborting the import partway through.
- An import with no known duration (e.g. a livestream) failed with an
  unclear error instead of an understandable message.

### 0.1.3 - 2026-08-26

#### Improved
- The download interface is reachable from the box only, no longer from the
  network. It asked for no password.

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

### 0.2.4 - 2026-09-01

#### Added
- The box now keeps an update history: every run records which versions were
  running before it. That is what the step back to the previous version rests
  on.

### 0.2.3 - 2026-08-30

#### Fixed
- Switching back to DHCP no longer leaves a fixed address in the profile. The
  box was otherwise reachable on two addresses, and the interface named the
  wrong one.

### 0.2.2 - 2026-08-29

#### Added
- When the box loses its connection for a while and has no network cable, it
  opens the "Minabox-Setup" Wi-Fi on its own (reachable at http://10.42.0.1)
  and shuts it down again once a known network is in reach.

### 0.2.1 - 2026-08-26

#### Added
- Checks the sound card and the system volume controls for the "Fix sound
  problem" button, and raises a control that sits at zero.
- Can restart the sound service on its own, without taking the web UI down
  with it.

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

### 0.2.4 - 2026-08-28

#### Improved
- The container's service user no longer has a home directory and can no
  longer be logged into (image hardening).

### 0.2.3 - 2026-08-26

#### Fixed
- The test tone was played through a separate, throwaway libVLC instance. On a
  real box, that output repeatedly lost sync with PipeWire and the playback
  broke off or sounded truncated. The test tone now travels the same path as
  the music, via paplay.

#### Improved
- More log messages for playback, pause, stop and volume changes - helps when
  reading a debug package.

### 0.2.2 - 2026-08-26

#### Fixed
- The box sometimes stayed silent after a restart although nobody had muted
  it. The system remembered a mute once it had been set and pushed it onto
  every new playback; neither restarting the box nor restarting the services
  cleared it.
- The test tone travelled a different path than the music, so it was audible
  even while the music stayed muted. It now takes the same path, which is what
  lets it show the fault at all.

#### Added
- The service reports itself as degraded when the configured speaker is no
  longer there. It used to report itself healthy while no sound was possible
  at all.
- The check chain behind the new "Fix sound problem" button in the web UI.

### 0.2.1 - 2026-08-26

#### Fixed
- The reported volume briefly jumped to a wrong value at the start and end of a
  track, which sent the slider in the interface to its left edge after every
  stop.
- Seeking within a track briefly reported the position from before the jump.
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

### 0.2.4 - 2026-08-31

#### Improved
- The runtime image is smaller: no packaging tools (pip, setuptools) and no
  `i2c-tools`, none of which the service ever calls.

### 0.2.3 - 2026-08-28

#### Improved
- The container's service user no longer has a home directory and can no
  longer be logged into (image hardening).

### 0.2.2 - 2026-08-28

#### Improved
- After a restart Docker reports the service ready about ten seconds sooner,
  in step with the other services.

### 0.2.1 - 2026-08-26

#### Improved
- The status port is reachable from the box only, no longer from the network.

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

### 0.2.3 - 2026-08-28

#### Improved
- The container health check runs the same way as on every other service
  again and uses less processing time doing so; the image gets a little smaller.

### 0.2.2 - 2026-08-28

#### Improved
- The container's service user no longer has a home directory and can no
  longer be logged into (image hardening).

### 0.2.1 - 2026-08-26

#### Improved
- The service permanently uses about five percent less processing time. Its
  regular health check cost more than the service itself.
- The status port is reachable from the box only, no longer from the network.

### 0.2.0 - 2026-08-25

#### Fixed
- A button pin already owned by another service used to take **every** button
  on the box down with it - and kept the pins until the container was
  restarted. Now only the affected button drops out and the others keep
  working.
- An incomplete button configuration could be saved but sent the service into
  a restart loop on its next start. It is now rejected on save, and the
  service starts even with a broken file so it can be repaired from the
  interface.

#### Improved
- The service status now reports "degraded" when a button cannot claim its pin
  or the configuration fails to load - a box with nothing but dead buttons
  used to look healthy.
- The service needs about 60 percent less idle CPU time and its image is
  68 MB smaller.

### 0.1.2 - 2026-08-23

### 0.1.1 - 2026-08-22

### 0.1.0 - 2026-08-20

#### Added
- The service reports its version.

---

## led

### 0.2.3 - 2026-08-28

#### Improved
- The container health check runs the same way as on every other service
  again and uses less processing time doing so; the image gets a little smaller.

### 0.2.2 - 2026-08-28

#### Improved
- The container's service user no longer has a home directory and can no
  longer be logged into (image hardening).

### 0.2.1 - 2026-08-26

#### Improved
- The service permanently uses about five percent less processing time. Its
  regular health check cost more than the service itself.

### 0.2.0 - 2026-08-25

#### Fixed
- An LED bound to a blocked card now reacts to one; until now nothing happened.
- Repeats count whole cycles everywhere: one blink is on and off again.
- The LED test blinks for the full five seconds, and the interface no longer
  waits for it but answers straight away.
- A pattern with unusable values no longer leaves the LED silently dark; it
  runs with a sensible default instead.
- Switching an LED off releases its GPIO pin again.
- Saving the LED settings no longer leaves error messages in the log.
- During playback the service stops writing the same line to the log once a
  second.

#### Improved
- The system overview now tells how many LEDs are configured apart from how
  many are actually reachable.
- The service image is about a quarter smaller, so updates download faster.

### 0.1.1 - 2026-08-23

### 0.1.0 - 2026-08-20

#### Added
- The service reports its version.

---

## display

### 0.3.0 - 2026-09-02

#### Improved
- The volume screen now shows Knuffel singing - the louder it is set, the more
  notes rise from him.
- While playing, Knuffel walks the progress bar and waves near the end; the
  remaining time makes way for him.
- The mute screen shows Knuffel with his mouth shut instead of a crossed-out
  speaker.

### 0.2.3 - 2026-08-29

#### Added
- Shows a dedicated screen when the box cannot be reached the usual way, with
  the SSID, password and address of the setup Wi-Fi.

### 0.2.2 - 2026-08-28

#### Improved
- The container's service user no longer has a home directory and can no
  longer be logged into (image hardening).

### 0.2.1 - 2026-08-26

#### Added
- On pause the creature now falls asleep, with Zs rising above it. It used to
  just say "Pause" - which only helps whoever can already read.

#### Improved
- The status port is reachable from the box only, no longer from the network.

### 0.2.0 - 2026-08-26

#### Added
- The display now shows a picture for each situation instead of a row of tiny
  icons: title, progress and remaining time while playing, and a small creature
  that wanders, blinks and waves while nothing does.
- Turning the volume knob briefly shows a large reading, one block per detent.
- An unknown figure, a blocked one and a reached daily limit each get their own
  picture - the display used to say nothing at all.
- At night the panel dims, and can switch off entirely while nothing happens.

#### Improved
- The volume reading shows the position within the allowed range. On a box with
  a maximum of 40 it used to read "40 %" while the knob was at its stop.
- Only the part of the picture that changed is sent to the panel. The reader on
  the same connection is blocked far less often as a result.

#### Fixed
- Taking a figure off, and putting one on, briefly raised the volume reading
  although nothing had changed.

### 0.1.1 - 2026-08-23

### 0.1.0 - 2026-08-20

#### Added
- The service reports its version.
