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
