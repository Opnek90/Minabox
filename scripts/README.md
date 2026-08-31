# Scripts

Helper scripts for development and setup. Run from the **repository root**:
`./scripts/<script>`.

| Script | Description |
|--------|-------------|
| `dev-tools.sh` | Linting, formatting, pre-commit, venv (e.g. `./scripts/dev-tools.sh format`) |
| `build-local.sh` | Build one or more service images locally under the `:local` tag, with the version passed as a build arg |
| `build_manifest.py` | Generate `release/release-manifest.json` from the changelogs; `--check` only verifies it is up to date |
| `run-tests.sh` | Run the service test suites (`all`, or a service name) |
| `setup-folders.sh` | Create the default folder structure (e.g. after a fresh clone) |
| `simulate-sound-fault.sh` | Deliberately trigger one of the sound-fault states that "Fix sound problem" detects and repairs |
| `test_display.py` | Manual OLED test (Adafruit SSD1306, I2C). Not part of the display service. |
