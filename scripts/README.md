# Scripts

Helper scripts for development and setup. Run from the **repository root**:
`./scripts/<script>`.

| Script | Description |
|--------|-------------|
| `dev-tools.sh` | Linting, formatting, pre-commit, venv (e.g. `./scripts/dev-tools.sh format`) |
| `build-local.sh` | Build one or more service images locally under the `:local` tag, with the version passed as a build arg |
| `build_manifest.py` | Generate `release/release-manifest.json` from the changelogs; `--check` only verifies it is up to date. Both modes name the services still on a release candidate, and refuse one the project has already released past |
| `run-tests.sh` | Run the service test suites (`all`, or a service name) |
| `setup-folders.sh` | Create the default folder structure (e.g. after a fresh clone) |
| `simulate-sound-fault.sh` | Deliberately trigger one of the sound-fault states that "Fix sound problem" detects and repairs |
| `test_display.py` | Manual OLED test (Adafruit SSD1306, I2C). Not part of the display service. |

## Release candidates that nobody promoted

`build_manifest.py` ends every run by naming the services whose `VERSION` still
carries a pre-release marker:

```
Still on a release candidate - no stable image is being built:
  audio              0.3.0-rc.1  since 2026-09-03
  host-helper        0.3.1-rc.1  since 2026-09-03
```

That is a report, not a verdict — while a beta is being tried out this is
exactly the state things should be in. It exists because of an incident: the
announcements went out as a beta bundle and the release that followed promoted
only half of it. CI takes the image tag from the `VERSION` file, so no stable
image of the other half was ever built, and a box on the stable channel got a
feature it had no way to reach. The line is printed at the one moment somebody
could have noticed — a run of this script while promoting the rest.

Once another service has published a **finished** release on a *later day*, the
project has moved on and the candidate counts as forgotten: the run fails, and
with it the image build, since `build-images.yml` calls `--check`. One release
day of grace, so a bundle and its promotion on the same day stay quiet.

Read from the `VERSION` files, not from the changelog: promoting is written
sometimes as a second entry above the candidate and sometimes as a replacement
of it, so the changelog does not reliably say which candidates are still open.
