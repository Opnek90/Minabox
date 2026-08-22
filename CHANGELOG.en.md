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

### 0.1.1 - 2026-08-21

#### Improved
- Wording and example addresses are neutral; the domain list remains as a
  technical setting.

### 0.1.0 - 2026-08-20

#### Added
- The service reports its version.

---

## host-helper

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

### 0.1.0 - 2026-08-20

#### Added
- The service reports its version.

---

## rfid

### 0.1.0 - 2026-08-20

#### Added
- The service reports its version.

---

## button

### 0.1.1 - 2026-08-22

### 0.1.0 - 2026-08-20

#### Added
- The service reports its version.

---

## led

### 0.1.0 - 2026-08-20

#### Added
- The service reports its version.

---

## display

### 0.1.0 - 2026-08-20

#### Added
- The service reports its version.
