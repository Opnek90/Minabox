# Dienste

Minabox besteht aus mehreren kleinen Diensten, die ueber MQTT und eine
REST-API zusammenarbeiten. Jeder Dienst hat seine eigene Versionsnummer und
sein eigenes Image (`ghcr.io/opnek90/minabox-<dienst>`).

| Dienst | Aufgabe |
|---|---|
| [backend](backend/README.md) | Zentrale Orchestrierung und Datenhaltung. Einziger Dienst mit Datenbank; uebersetzt zwischen WebUI, MQTT und den uebrigen Diensten. |
| [webui](webui/README.md) | Browser-Oberflaeche. Statische React-SPA, von Nginx ausgeliefert. |
| [audio](audio/README.md) | Erzeugt den Ton. Nimmt Wiedergabebefehle ueber MQTT entgegen und spielt lokal ab. |
| [rfid](rfid/README.md) | Spricht mit dem RFID-Leser und macht aus Kartenwechseln MQTT-Ereignisse. |
| [button](button/README.md) | Liest Taster und Drehgeber, macht daraus logische Aktionen und schickt sie ueber MQTT. |
| [led](led/README.md) | Ausgabestufe fuer die einfarbigen Status-LEDs. |
| [display](display/README.md) | Ausgabestufe fuer das kleine I2C-OLED (SSD1306, 128x64). |
| [media-downloader](media-downloader/README.md) | Eigenstaendiger Dienst zum lokalen Medien-Import (Audiospur einer URL nach MP3). |
| [host-helper](host-helper/README.md) | Einziger Dienst, der auf dem Host selbst handeln darf (Dateien verschieben, Systemaktionen). Nur intern vom Backend angesprochen. |
| [shared-lib](shared-lib/README.md) | Gemeinsame Python-Bausteine (Config, MQTT-Basis, Logging, Health-Schemas). Kein eigener Dienst, sondern ein Paket. |

Ergaenzend: [webui/Setup-Wizard.md](webui/Setup-Wizard.md) – Konzept fuer den
Ersteinrichtungs-Assistenten.
