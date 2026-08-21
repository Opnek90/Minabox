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

### 0.1.7 - 2026-08-21

#### Neu
- Ein regelmaessiger Hintergrund-Scan kann auf Updates pruefen und meldet ein
  bereitstehendes Update ueber einen Hinweis, statt dass man ihn nur beim
  Aufruf der Wartungsseite bemerkt.

### 0.1.6 - 2026-08-21

#### Neu
- Die Datenbank fuehrt jetzt einen Stand mit. Trifft eine aeltere Fassung auf
  eine neuere Datenbank - etwa nach einer eingespielten Sicherung oder wenn
  ein Dienst beim Update nicht durchgestartet ist -, wird das erkannt und
  gemeldet, statt dass Inhalte stillschweigend als verschwunden gelten.

#### Verbessert
- Mehrere Systemwarnungen koennen nebeneinander bestehen. Bisher verdraengte
  eine voruebergehende Temperaturwarnung eine dauerhafte Meldung.

### 0.1.5 - 2026-08-21

#### Verbessert
- Der Rueckweg auf eine vorige Version wird nicht mehr angeboten.

### 0.1.4 - 2026-08-21

#### Neu
- Ein Update kann gezielt einzelne Dienste betreffen, statt immer alle
  anzufassen.

### 0.1.3 - 2026-08-21

#### Neu
- Die Box vergleicht ihre laufenden Versionen mit dem veroeffentlichten Stand
  und kann sagen, fuer welchen Dienst es etwas Neues gibt.

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

### 0.1.7 - 2026-08-21

#### Neu
- Unter Optionen -> Wartung laesst sich der regelmaessige Hintergrund-Scan auf
  Updates ein- und ausschalten; steht eines bereit, erscheint ein Hinweis in
  der Kopfzeile.

### 0.1.6 - 2026-08-21

#### Neu
- Der Hinweisbalken meldet, wenn die Datenbank aus einer neueren Version
  stammt als die laufende, und sagt, was zu tun ist.

### 0.1.5 - 2026-08-21

#### Verbessert
- Der Knopf "Zurueck auf die vorige Version" ist entfallen. Ein Rueckschritt
  ist nur harmlos, wenn die aeltere Fassung alle Daten der neueren lesen kann -
  das laesst sich derzeit nicht zusagen. Wer zurueck muss, spielt die
  Sicherung von vor dem Update ein.

### 0.1.4 - 2026-08-21

#### Neu
- Das Update betrifft nur noch die Dienste, fuer die es wirklich etwas Neues
  gibt.
- Nach einem Update laesst sich der Schritt rueckgaengig machen - der Knopf
  "Zurueck auf die vorige Version" erscheint, solange es etwas zurueckzunehmen
  gibt.
- Vor jedem Update entsteht automatisch eine Sicherung; der Dialog sagt das
  vorher.

### 0.1.3 - 2026-08-21

#### Neu
- Unter "Version & Update" steht jetzt jeder aktive Dienst mit seiner Version,
  statt einer einzelnen Kennnummer ohne Aussagekraft.
- Ein Knopf prueft auf Updates und zeigt vor dem Aktualisieren, was sich
  aendert.
- Waehrend des Updates zeigt ein Fenster den Fortschritt Schritt fuer Schritt;
  die vollstaendige Ausgabe laesst sich aufklappen.

#### Verbessert
- Unter "Neustart" liegen die beiden folgenschweren Aktionen jetzt in einer
  eigenen Reihe unter den harmlosen Neustarts.
- Der ueberfluessige Hinweis "ZIP-Datei waehlen" neben den Sicherungsknoepfen
  ist entfallen; die Auswahl passiert im Dialog.

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

### 0.1.4 - 2026-08-21

#### Verbessert
- Der Rueckweg auf eine vorige Version wird nicht mehr angeboten. Welche
  Versionen vor einem Update liefen, wird weiterhin festgehalten - fuer
  Supportanfragen, nicht als Knopf.

### 0.1.3 - 2026-08-21

#### Neu
- Ein Update kann gezielt einzelne Dienste auf bestimmte Versionen bringen.
  Alle uebrigen werden dabei auf ihrem laufenden Stand festgenagelt, damit ein
  gezieltes Update nichts anderes mitzieht.
- Vor jedem Update entsteht eine Sicherung unter data/backups; die letzten
  fuenf bleiben erhalten. Schlaegt sie fehl, wird nicht aktualisiert.
- Nach dem Neustart wird geprueft, ob jeder betroffene Dienst wirklich in der
  gewuenschten Version laeuft - "laeuft wieder" allein genuegt nicht.

### 0.1.2 - 2026-08-21

#### Behoben
- Beim Update lief "git pull" als root und hinterliess root-eigene Dateien im
  Projektordner. Es laeuft jetzt als dessen Eigentuemer.

### 0.1.1 - 2026-08-21

#### Behoben
- Das Minabox-Update lief ins Leere: es rief die docker-Befehle im Container
  auf, wo es sie gar nicht gibt. Es laeuft jetzt auf dem Host und ueberlebt,
  dass der Dienst sich dabei selbst neu startet.

#### Neu
- Der Fortschritt eines Updates ist abrufbar: Schritt, Gesamtzahl und die
  vollstaendige Ausgabe.

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
