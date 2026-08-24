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

### 0.2.1 - 2026-08-24

#### Verbessert
- Die Wiederherstellung einer Sicherung laeuft jetzt im Hintergrund, und ihr
  Stand laesst sich abfragen.

### 0.2.0 - 2026-08-23

#### Behoben
- Das Loeschen eines Titels konnte in seltenen Faellen das Arbeitsverzeichnis
  des Dienstes mitloeschen, wenn zu dem Titel keine Datei gespeichert war.
- Ein nicht erreichbarer Podcast-Feed legte die Box fuer bis zu 30 Sekunden
  je Feed lahm - Oberflaeche, Tasten und Karten reagierten in dieser Zeit
  nicht.
- Bei einer Neuinstallation schlugen die Datenbank-Migrationen bei jedem
  Start fehl. Die Datenbank wird jetzt vollstaendig ueber die Migrationen
  aufgebaut; bestehende Boxen bleiben unveraendert.
- Ein fehlgeschlagener Upload hinterlaesst keinen unabspielbaren Eintrag
  mehr in der Mediathek.
- Beim Speichern der RFID-Einstellungen gingen andere Abschnitte derselben
  Datei verloren.

#### Neu
- Neuer Schutzbereich "Player und Karten": schuetzt Wiedergabe, Karten-
  verwaltung, Verlauf und die Live-Verbindung. Standardmaessig aus, damit
  sich am bisherigen Verhalten nichts aendert.
- Die maximale Upload-Groesse laesst sich jetzt einstellen und wirkt sofort.
- Playlists lassen sich der Reihe nach abspielen statt zufaellig - passend
  fuer Hoerspiele in Kapiteln.

#### Verbessert
- Nach fuenf falschen Passwoertern ist die Anmeldung fuer fuenf Minuten
  gesperrt.
- Einstellungen werden so gespeichert, dass ein Stromausfall mitten im
  Schreiben keine beschaedigte Datei hinterlaesst.
- Uploads sind begrenzt und laufen nicht mehr komplett durch den
  Arbeitsspeicher; das gilt auch fuer Backup und Wiederherstellung.
- Dashboard und Verlauf antworten auf gewachsenen Datenbestaenden spuerbar
  schneller.
- Das Image ist rund 38 MB kleiner.

### 0.1.12 - 2026-08-23

### 0.1.11 - 2026-08-23

#### Behoben
- Ein bereitstehendes Update und eine Uebertemperatur-Warnung konnten sich
  gegenseitig verdraengen, weil die Oberflaeche nur den schwerwiegendsten
  Hinweis abrufen konnte. Beide stehen jetzt unabhaengig voneinander bereit.

### 0.1.10 - 2026-08-22

#### Verbessert
- Fehlerantworten der API tragen jetzt einen stabilen Code, damit die
  Oberflaeche jede Fehlermeldung zuverlaessig in der eingestellten Sprache
  zeigt statt manchmal einen rohen technischen Text.

### 0.1.9 - 2026-08-22

#### Behoben
- Der Hinweis auf ein verfuegbares Update erscheint jetzt auch in der
  Kopfzeile - bisher blieb er dort trotz laufendem Hintergrund-Scan und
  manueller Pruefung unsichtbar.

### 0.1.8 - 2026-08-21

#### Neu
- Streams und Podcasts lassen sich jetzt genau wie Tracks in Ordnern
  organisieren (eigene Ordnerverwaltung je Medientyp).

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

### 0.1.13 - 2026-08-24

#### Verbessert
- Nach dem Hochladen einer Sicherung steht jetzt "Wiederherstellung
  gestartet" statt "abgeschlossen" - die Box braucht danach noch einen Moment,
  bis alle Dienste wieder laufen.

### 0.1.12 - 2026-08-23

#### Neu
- Neuer Schalter fuer den Schutzbereich "Player und Karten".
- Die maximale Upload-Groesse laesst sich unter Wartung einstellen.
- Neuer Schalter, ob Playlists zufaellig oder der Reihe nach laufen.

### 0.1.11 - 2026-08-23

#### Behoben
- Der Hinweis auf ein verfuegbares Update blieb trotz der Behebung in 0.1.9
  weiterhin unsichtbar - er lag vollstaendig hinter der Kopfzeile verborgen.
  Er erscheint jetzt als eigenes Icon direkt in der Kopfzeile, mit Klick zu
  Wartung -> Version & Update.

### 0.1.10 - 2026-08-22

#### Behoben
- Fehlermeldungen bei WLAN, Bluetooth, Backup/Wiederherstellung,
  Systemwartung und Anmeldung zeigten oft eine falsche oder unpassende
  Meldung (z. B. immer "Protokolle nicht verfuegbar", egal welche Aktion
  fehlschlug) - jetzt erscheint ueberall die passende, uebersetzte Meldung.
- Die Anzahl der Tracks und Unterordner in der Mediathek stand bei mehr als
  einem Eintrag faelschlich in der Einzahl ("1 Track" statt "5 Tracks").
- Einzelne Texte (u. a. Sleep-Timer, Ausgabegeraet-Wechsel, Debug-Export)
  blieben unabhaengig von der eingestellten Sprache immer Deutsch.

### 0.1.9 - 2026-08-22

#### Behoben
- "Zuletzt gescannt" bei RFID-Tags zeigte direkt nach dem Scan faelschlich
  "vor 2 Stunden" statt "gerade eben" (Zeitzonen-Versatz).

### 0.1.8 - 2026-08-21

#### Neu
- Streams und Podcasts lassen sich jetzt genau wie Tracks per Ordnerbaum,
  Drag & Drop und "Verschieben"-Menü organisieren.
- Die Track-Liste zeigt jetzt Seiten mit 25 oder 50 Eintraegen statt einer
  langen Liste, der Ordnerbaum daneben laesst sich einklappen.

#### Verbessert
- Karten- und Listenansicht der Tracks sind kompakter, der Seitenabstand
  neben der Navigation ist schmaler.

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

### 0.1.2 - 2026-08-23

### 0.1.1 - 2026-08-21

#### Verbessert
- Texte und Beispieladressen sind neutral gefasst; die Domain-Liste bleibt
  als technische Einstellung bestehen.

### 0.1.0 - 2026-08-20

#### Neu
- Der Dienst meldet seine Version.

---

## host-helper

### 0.2.0 - 2026-08-24

#### Behoben
- Eine hochgeladene Sicherung wurde nicht wirklich eingespielt: die Dienste
  liefen dabei weiter, die Datenbank wurde unter ihnen ausgetauscht, und am
  Ende erschien trotzdem eine Fehlermeldung.
- Das Zuruecksetzen auf Werkseinstellungen hat die Dienste danach nicht neu
  gestartet.
- Beim Importieren von einem USB-Stick konnten ueber Verknuepfungen auf dem
  Stick auch Dateien von ausserhalb mitkopiert werden.
- Ob ein Bluetooth-Geraet gerade verbunden ist, wurde immer als "nicht
  verbunden" angezeigt.

#### Verbessert
- Der Dienst ist von 605 auf 290 MB geschrumpft - ein Update laedt weniger als
  die Haelfte der bisherigen Datenmenge.
- Die Liste gekoppelter Bluetooth-Geraete kommt jetzt gleich schnell,
  unabhaengig davon wie viele Geraete die Box kennt.
- Das Verschieben des Audio-Ordners meldet sich sofort, statt erst nachdem
  alle Dateien durchgezaehlt wurden.
- Ein zweites System-Update laesst sich nicht mehr starten, solange noch eines
  laeuft.
- Eine beschaedigte oder uebergrosse Sicherungsdatei wird abgewiesen, bevor
  sie etwas veraendert.

### 0.1.5 - 2026-08-23

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

### 0.2.0 - 2026-08-23

#### Behoben
- Ein Druck auf den Lautstaerkeregler schaltet die Box jetzt wirklich stumm. Bisher wurde nur bis zur eingestellten Mindestlautstaerke heruntergeregelt, waehrend die Anzeige bereits "stumm" meldete.
- Stuerzt der Dienst ab oder faellt der Strom aus, zeigen LED, Display und Oberflaeche nicht mehr endlos eine laufende Wiedergabe an.
- Eine frisch eingerichtete Box startet mit der eingestellten Standardlautstaerke statt mit der Maximallautstaerke.
- Nach dem Stoppen steht in der Oberflaeche kein Titel mehr, der gar nicht mehr spielt.
- Das Umschalten des Ausgangs blockiert die Bedienung nicht mehr fuer mehrere Sekunden.

#### Verbessert
- Das Abbild des Dienstes ist von 940 auf 544 MB geschrumpft, dadurch laedt ein Update deutlich schneller.

### 0.1.1 - 2026-08-23

### 0.1.0 - 2026-08-20

#### Neu
- Der Dienst meldet seine Version.

---

## rfid

### 0.2.0 - 2026-08-23

#### Verbessert
- Eine Karte, die auf dem Leser leicht verrutscht, unterbricht die Wiedergabe
  nicht mehr. Bisher genuegte ein einziger verlorener Lesevorgang, damit die
  Musik stoppte und der Titel Sekunden spaeter von vorn begann.
- Steckt der Kartenleser nicht richtig, zeigt die Box das jetzt als Fehler an
  und faengt sich von selbst, sobald er wieder da ist. Bisher startete der
  Dienst endlos neu, ohne dass irgendwo zu sehen war, woran es lag.
- Der Lern-Modus schaltet nach fuenf Minuten ohne Scan von selbst zurueck.
  Wer das Anlern-Fenster nur schloss, ohne es zu beenden, konnte danach keine
  Karte mehr zum Abspielen benutzen.
- Nach einem Neustart des Nachrichtendienstes stehen Kartenzustand und
  Dienststatus wieder zur Verfuegung, statt dauerhaft zu fehlen.
- Stuerzt der Dienst ab, gilt die Karte sofort als abgenommen. Bisher rechnete
  die Box weiter mit einer aufliegenden Karte.
- Alle Zeitwerte des Lesers - Entprellung, Scan-Intervall, Lern-Timeout und
  die PN532-Einstellungen - stehen jetzt in der Konfigurationsdatei und lassen
  sich ohne neues Abbild anpassen.
- Die Zustandsseite des Dienstes nennt jetzt Leser, Betriebsart und letzten
  Fehler, was die Fehlersuche deutlich abkuerzt.

### 0.1.0 - 2026-08-20

#### Neu
- Der Dienst meldet seine Version.

---

## button

### 0.1.2 - 2026-08-23

### 0.1.1 - 2026-08-22

### 0.1.0 - 2026-08-20

#### Neu
- Der Dienst meldet seine Version.

---

## led

### 0.1.1 - 2026-08-23

### 0.1.0 - 2026-08-20

#### Neu
- Der Dienst meldet seine Version.

---

## display

### 0.1.1 - 2026-08-23

### 0.1.0 - 2026-08-20

#### Neu
- Der Dienst meldet seine Version.
