# Minabox – documentation

Minabox is an alternative to the Toniebox: a child-friendly audio player with
RFID control, split into several small services that run in Docker on a
Raspberry Pi.

## For users

- **[INSTALLATION.md](INSTALLATION.md)** – set Minabox up on a Raspberry Pi
  (guided installer).
- **[Troubleshooting.md](Troubleshooting.md)** – known failure patterns and how
  to tell them apart.
- **[DebugExport.md](DebugExport.md)** – what is in the diagnostics package that
  the web UI produces under *Settings → Diagnostics*.

## Architecture

- **[services/](services/)** – one document per service: purpose, interfaces
  (REST, MQTT), structure and configuration. Overview in
  [services/README.md](services/README.md).

## Contributing

The development and release workflow and the technical standards are not kept
in the public repository. To contribute, get in touch via a
[GitHub issue](https://github.com/Opnek90/Minabox/issues).
