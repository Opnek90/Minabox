# Changelog

Aenderungen je Dienst. Jeder Dienst hat seine eigene Versionsnummer
([docs/Versionierung.md](docs/Versionierung.md)), also auch seine eigene
Liste.

Die englische Fassung steht in [CHANGELOG.en.md](CHANGELOG.en.md). Beide
Dateien haben denselben Aufbau; aus ihnen entsteht das Release-Manifest, das
die Box beim Update-Check liest. **Aufbau bitte einhalten** - er wird
maschinell gelesen:

```
## <dienst>                    Genau der Name aus services/<dienst>-service/
### <version> - <JJJJ-MM-TT>   SemVer, dann ein Datum
#### Neu | Verbessert | Behoben
- Ein Satz aus Nutzersicht.
```

Eine Version ohne sichtbare Aenderung darf leer bleiben - dann zeigt die
Oberflaeche "keine Aenderungsnotizen" statt einer erfundenen Zeile.

---

## backend

### 0.1.2 - 2026-08-21

#### Behoben
- Der Prozentwert beim Arbeitsspeicher wird nicht mehr missverstaendlich
  angezeigt: ohne gesetztes Container-Limit bezieht er sich auf den gesamten
  Systemspeicher.

### 0.1.1 - 2026-08-21

#### Verbessert
- Der Medienimport spricht nicht mehr von einzelnen Plattformen; die Texte
  sind neutral gefasst.

### 0.1.0 - 2026-08-20

#### Neu
- Die Dienste-Uebersicht zeigt, was auf der Box wirklich laeuft, statt einer
  festen Liste. Dienste, die eine Komponentenauswahl nie gestartet hat,
  tauchen nicht mehr als "offline" auf.
- Host-Helper und Medien-Import erscheinen erstmals in der Uebersicht.
- CPU, Arbeitsspeicher und Protokolle gibt es fuer alle Container, auch fuer
  den MQTT-Broker.
- Jeder Dienst meldet seine Version.

#### Behoben
- Der Arbeitsspeicher wurde als "0 MB" angezeigt, wo er gar nicht messbar
  ist. Jetzt bleibt das Feld leer und die Oberflaeche erklaert, wie sich die
  Messung einschalten laesst.

---

## webui

### 0.1.2 - 2026-08-21

#### Behoben
- Lange Dienstnamen wurden in der Uebersicht abgeschnitten ("Back...").

### 0.1.1 - 2026-08-21

#### Verbessert
- Der Import von einer URL verlangt jetzt eine ausdrueckliche Bestaetigung
  des Rechtshinweises; "Pruefen" und "Importieren" sind vorher nicht
  benutzbar.
- Die Hinweistexte behaupten nicht mehr, die Anwendung koenne die
  Rechtmaessigkeit einer Adresse pruefen.

### 0.1.0 - 2026-08-20

#### Neu
- Jede Dienst-Karte zeigt ihre Version. Ein selbst gebautes Abbild wird als
  "Entwicklungsbuild" gekennzeichnet.

---

## media-downloader

### 0.1.1 - 2026-08-21

#### Verbessert
- Texte und Beispieladressen sind neutral gefasst; die Domain-Liste bleibt
  als technische Einstellung bestehen.

### 0.1.0 - 2026-08-20

#### Neu
- Der Dienst meldet seine Version.

---

## host-helper

### 0.1.0 - 2026-08-20

#### Neu
- Der Dienst meldet seine Version und erscheint in der Dienste-Uebersicht.

---

## audio

### 0.1.0 - 2026-08-20

#### Neu
- Der Dienst meldet seine Version.

---

## rfid

### 0.1.0 - 2026-08-20

#### Neu
- Der Dienst meldet seine Version.

---

## button

### 0.1.0 - 2026-08-20

#### Neu
- Der Dienst meldet seine Version.

---

## led

### 0.1.0 - 2026-08-20

#### Neu
- Der Dienst meldet seine Version.

---

## display

### 0.1.0 - 2026-08-20

#### Neu
- Der Dienst meldet seine Version.
