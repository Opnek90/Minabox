# Minabox – Dokumentation

Minabox ist eine Toniebox-Alternative: ein Audioplayer fuer Kinder mit
RFID-Steuerung, aufgeteilt in mehrere kleine Dienste, die auf einem Raspberry
Pi in Docker laufen.

## Fuer Nutzer

- **[INSTALLATION.md](INSTALLATION.md)** – Minabox auf einem Raspberry Pi
  einrichten (gefuehrter Assistent).
- **[Troubleshooting.md](Troubleshooting.md)** – bekannte Fehlerbilder und wie
  man sie auseinanderhaelt.
- **[DebugExport.md](DebugExport.md)** – was im Diagnose-Paket steckt, das die
  WebUI unter *Einstellungen → Diagnose* erzeugt.

## Architektur

- **[services/](services/)** – ein Dokument je Dienst: Aufgabe, Schnittstellen
  (REST, MQTT), Aufbau und Konfiguration. Uebersicht in
  [services/README.md](services/README.md).

## Mitwirken

Der Entwicklungs- und Release-Workflow sowie die technischen Standards werden
nicht im oeffentlichen Repository gepflegt. Wer beitragen moechte, meldet sich
ueber ein [GitHub-Issue](https://github.com/Opnek90/Minabox/issues).
