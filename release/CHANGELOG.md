# Changelog

Aenderungen je Dienst. Jeder Dienst hat seine eigene Versionsnummer, also
auch seine eigene Liste.

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

### 0.3.2 - 2026-09-01

#### Behoben
- Keine sichtbare Aenderung: 0.3.1 wurde nie als Abbild veroeffentlicht, weil
  der Bau nach einem roten Testlauf ausfiel. Diese Nummer holt ihn nach.

### 0.3.1 - 2026-09-01

#### Neu
- Grundlage fuer den Wochenrueckblick: die Box fasst eine Woche Hoerdaten zu
  einer Uebersicht zusammen - Gesamtzeit, Vergleich zur Vorwoche, Verteilung
  ueber die Wochentage, meistgespielte Karte und Karten, die noch nie
  abgespielt wurden.
- Neue Einstellung "Datenaufbewahrung" (Standard 52 Wochen): Wiedergabe- und
  Scan-Verlauf, der aelter ist, wird taeglich automatisch geloescht. Bestehende
  Boxen entfernen beim ersten Lauf einmalig alles, was aelter als ein Jahr ist.

### 0.3.0 - 2026-09-01

#### Neu
- Beim Hochladen liest die Box jetzt Interpret, Album und das eingebettete
  Titelbild aus der Datei - auch aus FLAC-, OGG- und M4A-Dateien, nicht nur MP3.
- Neuer Schalter "Metadaten online nachschlagen" (Wartung -> Medien,
  standardmaessig aus): fuer Dateien ohne eigene Angaben fragt die Box bei
  MusicBrainz und dem Cover Art Archive nach. Dabei werden Titel und Interpret
  an diese Dienste uebermittelt.
- "Cover & Metadaten nachtragen" ergaenzt fehlende Angaben und Titelbilder fuer
  bereits vorhandene Titel im Hintergrund.

### 0.2.14 - 2026-09-01

#### Neu
- Ein Update-Kanal: "Stabil" bietet nur fertige Versionen an, "Beta"
  zusaetzlich Vorabversionen zum Ausprobieren. Umschaltbar unter
  Wartung -> Version & Update, ein Zurueckschalten genuegt.
- "Zurueck auf die vorherige Version" je Dienst: die Box merkt sich, was vor
  einem Update lief, und kann es ohne Konsole wieder herstellen.
- Ein Rueckschritt wird abgelehnt, wenn das Update die Datenbank umgestellt
  hat - mit Begruendung, statt ihn zu versuchen und Daten zu verlieren.

### 0.2.13 - 2026-08-31

#### Verbessert
- Weitere Markierungen in den Log-Dateien des Diagnose-Pakets auf Englisch.

### 0.2.12 - 2026-08-31

#### Verbessert
- Die Kopfzeilen der gefilterten Log-Dateien im Diagnose-Paket sind jetzt
  auf Englisch.

### 0.2.11 - 2026-08-31

#### Verbessert
- Der Update-Check liest das Release-Manifest jetzt aus dem neuen Ordner
  `release/` im Repository.

### 0.2.10 - 2026-08-30

#### Verbessert
- Das Webpasswort verlangt acht statt vier Zeichen - dieselbe Laenge wie das
  Systempasswort.

### 0.2.9 - 2026-08-29

#### Neu
- Neuer Netzwerk-Statuswert (Modus, Adresse, Setup-Hotspot), den die
  Oberflaeche und das Display auslesen.

### 0.2.8 - 2026-08-28

#### Verbessert
- Der Dienst-Benutzer im Container hat kein Home-Verzeichnis mehr und ist
  nicht mehr anmeldbar (Haerten des Abbilds).

### 0.2.7 - 2026-08-27

#### Verbessert
- Optionale Komponenten, die bei der Installation nicht ausgewaehlt wurden
  (RFID, LEDs, Taster, Display, Medien-Download), werden serverseitig
  erkannt. Direktaufrufe dafuer werden sofort und eindeutig abgewiesen statt
  nach langem Warten fehlzuschlagen.

### 0.2.6 - 2026-08-27

#### Neu
- Die erlaubten Quellen fuer den Medien-Import sind jetzt in der
  Weboberflaeche einstellbar (Admin -> Allgemein -> Medien-Import). YouTube
  ist im Standard nicht mehr enthalten.

#### Verbessert
- Eine erlaubte Domain wie "bandcamp.com" deckt jetzt automatisch auch
  "www.bandcamp.com" ab, statt nur die exakt eingetragene Schreibweise.

### 0.2.5 - 2026-08-26

#### Neu
- Das Diagnose-Paket kann jetzt optional einen Ton-Test einschliessen: die Box
  spielt dabei einmal einen hoerbaren Testton (nur fuer Administratoren, nie
  Teil einer Vorauswahl).
- Der Knopf "Ton-Problem beheben" liefert jetzt das Ergebnis jedes einzelnen
  Reparaturschritts, nicht mehr nur ja/nein am Ende.

### 0.2.4 - 2026-08-26

#### Neu
- Ein Dienst, der selbst meldet, dass er seine Aufgabe nicht erfuellen kann,
  wird in der Diensteliste jetzt als eingeschraenkt angezeigt. Vorher stand er
  auf Gruen, solange sein Container lief.
- Vermittelt den neuen Knopf "Ton-Problem beheben" zwischen Oberflaeche,
  Ton-Dienst und Box.

#### Behoben
- Der Neustart des Ton-Dienstes verlangt jetzt das Administrator-Passwort,
  falls eines gesetzt ist.

### 0.2.3 - 2026-08-26

#### Verbessert
- Die Display-Einstellungen sind auf Anschluss und Helligkeit zusammengestrichen.
  Die alte Elementliste wird weiter angenommen und ignoriert, damit bestehende
  Boxen unveraendert weiterlaufen.
### 0.2.2 - 2026-08-25

#### Behoben
- Eine unvollstaendige Tasten-Konfiguration wurde gespeichert und als Erfolg
  gemeldet, obwohl der Tasten-Dienst sie nicht laden kann. Sie wird jetzt
  abgelehnt, mit Angabe der Taste und des fehlenden Feldes.

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

### 0.4.3 - 2026-09-02

#### Verbessert
- Titel, Sender und Podcasts stehen unter der Haube jetzt auf einer
  gemeinsamen Ansicht statt auf drei fast gleichen - sichtbar ist davon nur,
  dass die Knopfreihe in Listenzeilen bei allen dreien gleich breit ist und
  Titel-Karten etwas enger stehen. Neue Ansichten und Spalten muessen kuenftig
  nur noch einmal gebaut werden statt dreimal.

### 0.4.2 - 2026-09-01

#### Behoben
- Ein Klick auf ein Fragezeichen liess die Erklaerung offen stehen, wenn man
  zweimal schnell hintereinander klickte - sie ging erst wieder zu, nachdem
  man den Zeiger weggezogen hatte.
- Enthaelt ausserdem 0.4.1, das nie als Abbild veroeffentlicht wurde.

### 0.4.1 - 2026-09-01

#### Neu
- Neue Karte "Wochenrueckblick" im Dashboard unter Hoerstatistiken: Hoerzeit
  der Woche im Vergleich zur Vorwoche, ein Balken je Wochentag, die
  meistgespielte Karte und eine ausklappbare Liste nie gespielter Karten. Mit
  den Pfeilen blaettert man durch die Wochen.
- Neue Einstellung "Datenaufbewahrung" bei den Regeln: legt fest, wie viele
  Wochen Wiedergabe- und Scan-Verlauf die Box behaelt (0 = unbegrenzt).

### 0.4.0 - 2026-09-01

#### Verbessert
- Die langen Erklaertexte in den Einstellungen stehen nicht mehr dauerhaft
  unter jedem Feld, sondern hinter einem Fragezeichen daneben: Mauszeiger
  drueber oder antippen zeigt sie. Auf dem Handy erscheinen sie als Blatt vom
  unteren Rand. Warnungen, Eingaberegeln und Beschreibungen zur Auswahl
  bleiben sichtbar.

### 0.3.0 - 2026-09-01

#### Neu
- Neuer Bereich "Medien" in den Einstellungen: ein Schalter fuer die
  Online-Suche nach Metadaten und eine Aktion "Cover & Metadaten nachtragen",
  die fehlende Angaben und Titelbilder fuer die bestehende Mediathek ergaenzt -
  mit Fortschrittsanzeige.

### 0.2.3 - 2026-09-01

#### Neu
- Auswahl des Update-Kanals und ein Knopf "Zurueck auf <Version>" je Dienst
  unter Wartung -> Version & Update. Laeuft eine Vorabversion, ist sie in der
  Versionsliste als "beta" gekennzeichnet.

#### Behoben
- Einstellungen, die mit einem Klick gesetzt und gespeichert wurden, schrieben
  den vorherigen Wert zurueck. Betroffen war unter anderem der Schalter
  "automatisch nach Updates suchen", der sich umlegen liess, ohne dass die
  Einstellung ankam.

### 0.2.2 - 2026-09-01

#### Neu
- Neue Detailansicht fuer Tracks, Streams und Podcasts: eine Tabelle mit
  sortierbaren Spalten (Titel, Kuenstler, Dauer, zuletzt gespielt und mehr).
  Am Desktop ueber den dritten Ansichts-Knopf erreichbar, auf schmalen
  Bildschirmen bleibt es bei Listen- oder Kartenansicht.

### 0.2.1 - 2026-08-31

#### Behoben
- Drei Fehlermeldungen des Servers erschienen als allgemeines "Ein Fehler ist
  aufgetreten", weil ihr Text fehlte: fehlgeschlagener Neustart des
  Audio-Dienstes sowie ungueltige Tasten- und Display-Einstellungen.
- Die Fehlerseite des Webservers lag noch als fremde Datei im Auslieferungs-
  ordner und war unter /50x.html abrufbar.

### 0.2.0 - 2026-08-30

#### Neu
- Wiederholen und Zufallswiedergabe stehen sichtbar im Player: eingefaerbt
  heisst an, blass heisst aus, ein Tippen schaltet um.
- Der Einschlaf-Timer nimmt neben 15, 30, 45 und 60 Minuten auch eine frei
  eingegebene Dauer.
- Aenderungen an Lichtern und Tastern lassen sich verwerfen, statt sie nur
  ueber ein Neuladen der Seite loswerden zu koennen.
- Steht trotz DHCP noch eine feste Adresse im Netzwerkprofil, sagt die Seite
  das jetzt - die Box war sonst unbemerkt unter zwei Adressen erreichbar.

#### Verbessert
- Das Abbild der Oberflaeche ist von 98 auf 25 MB geschrumpft.
- Die Oberflaeche sendet Sicherheits-Kopfzeilen und verraet die Version ihres
  Webservers nicht mehr.
- Das Webpasswort verlangt acht statt vier Zeichen; die Regel steht am Feld.
- "Eltern -> Zeit und Regeln" ist so gegliedert wie die Einstellungsseiten.
- Die Symbole in der Kopfzeile kleben nicht mehr am Rahmen ihrer Umrandung.

#### Behoben
- Grosse Uploads brechen nicht mehr nach 15 Sekunden ab - und werden nicht
  mehr drei weitere Male hochgeladen.
- Ein Tastendruck an der Box und ein Umschalten am Drehregler erreichen den
  Player wieder; die Symbole fuer Wiederholen und Zufall ziehen mit.
- Einen Podcast zu bearbeiten ueberschreibt nicht mehr alle anderen.
- Ein Titelbild zu entfernen schliesst den Bearbeiten-Dialog nicht mehr.
- Die Netzwerk-Statuskarte veraltet nicht mehr nach einem Hotspot-Wechsel.
- Der Knopf zum Setzen des Passworts tat nichts.
- Nach dem Herunterladen einer Sicherung erschien die Meldung der
  Wiederherstellung.

### 0.1.23 - 2026-08-29

#### Neu
- Die Netzwerk-Einstellungen zeigen den aktuellen Zustand: Modus, Adresse zum
  Erreichen der Box und ob der Setup-Hotspot laeuft.

### 0.1.22 - 2026-08-28

#### Verbessert
- Steht der Log-Level auf "debug", zeigt die Weboberflaeche fehlende
  Uebersetzungen als Rohschluessel an und meldet sie in der Browser-Konsole,
  statt still auf Englisch auszuweichen. Bei jedem anderen Log-Level aendert
  sich nichts.

### 0.1.21 - 2026-08-27

#### Verbessert
- Die Weboberflaeche blendet Navigation, Einstellungen und Aktionen fuer
  Komponenten aus, die bei der Installation nicht ausgewaehlt wurden. Eine
  installierte, aber gerade nicht erreichbare Komponente bleibt sichtbar.

### 0.1.20 - 2026-08-27

#### Behoben
- Im Medien-Bereich wurde eine Aktion im Plus-Menue beim Ueberfahren mit der
  Maus durchsichtig, sodass Bedienelemente der Liste dahinter durchschienen.
- Nach einem Update ueber die Weboberflaeche erschien die Meldung
  "Aktualisierung gestartet" nach dem Neustart wiederholt statt nur einmal.

#### Verbessert
- Die Einstellungen haben einen eigenen Bereich "Medien" (Musik-Ordner,
  Upload-Limit, erlaubte Import-Quellen, USB-Uebertragung); "Wartung"
  enthaelt nur noch Updates, Sicherung und den Ersteinrichtungs-Assistenten.

### 0.1.19 - 2026-08-27

#### Neu
- Der Dialog fuer den Medien-Import zeigt beim Import jetzt die einzelnen
  Schritte an (Metadaten lesen, Herunterladen mit Geschwindigkeit und
  Restzeit, Umwandeln, Cover/Metadaten einbetten, Speichern) statt eines
  einzelnen Ladebalkens.
- Neue Einstellung unter Admin -> Allgemein: erlaubte Domains fuer den
  Medien-Import.

### 0.1.18 - 2026-08-26

#### Neu
- Im Diagnose-Paket-Dialog gibt es jetzt eine Option fuer einen Ton-Test mit
  hoerbarem Testton, nur fuer Administratoren sichtbar und nie vorausgewaehlt.
- Der Knopf "Ton-Problem beheben" zeigt jetzt einklappbar, welcher
  Reparaturschritt lief, behoben wurde oder fehlgeschlagen ist.

### 0.1.17 - 2026-08-26

#### Behoben
- "Als Naechstes" zeigte bei einer laufenden Playlist die falsche Reihenfolge:
  bereits gespielte Titel standen vor den kommenden.

### 0.1.16 - 2026-08-26

#### Neu
- Unter *Wartung* gibt es den Knopf **Ton-Problem beheben**. Die Box prueft der
  Reihe nach alles, was den Ton stumm schalten kann, behebt was sie selbst
  beheben kann, spielt einen Testton und fragt in grossen Worten, ob du etwas
  hoerst. Sagst du Nein, geht es weiter ueber einen Neustart des Ton-Dienstes
  bis zu Kabel, Strom und zuletzt einem Neustart der Box.
- Dienste, die selbst melden, dass sie ihre Aufgabe nicht erfuellen koennen,
  stehen in der Diensteliste jetzt auf Bernstein statt auf Gruen.

#### Verbessert
- Das Feld fuer LED-Wiederholungen erklaert jetzt, dass es ganze Zyklen zaehlt
  und 0 endlos bedeutet.

#### Behoben
- Beim Loeschen eines Mediums blieb die zugeordnete Karte halb verknuepft: sie
  zeigte weiter auf einen Titel, den es nicht mehr gab.
- Einige Knoepfe verloren Hoehe, Innenabstand und Schriftgroesse, sobald sie in
  der Breite angepasst wurden.

### 0.1.15 - 2026-08-26

#### Verbessert
- Die Lautstaerkeanzeige im Player zeigt dieselbe Zahl wie das Display am Geraet.
- Die Display-Einstellungen bestehen nur noch aus Anschluss und Helligkeit; der
  Editor fuer Anzeige-Elemente ist entfallen, weil er auf nichts mehr wirkte.
### 0.1.14 - 2026-08-25

#### Verbessert
- Im Tasten-Bereich lassen sich Pin-Nummern und Aktion nicht mehr vergessen -
  die Felder sind als Pflicht gekennzeichnet, und "Speichern" bleibt gesperrt,
  bis sie ausgefuellt sind.
- Schlaegt das Speichern einer Tasten-Konfiguration fehl, steht jetzt in der
  Meldung, welche Taste und welches Feld gemeint ist.

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

### 0.2.2 - 2026-08-31

#### Verbessert
- Die Log-Einstellung wird erst beim Start des Dienstes gesetzt, nicht schon
  beim Laden des Moduls. Ohne sichtbare Aenderung im Betrieb; sie hatte im
  gemeinsamen Testlauf die Protokollierung der uebrigen Dienste mitverstellt.

### 0.2.1 - 2026-08-28

#### Verbessert
- Der Dienst-Benutzer im Container hat kein Home-Verzeichnis mehr und ist
  nicht mehr anmeldbar (Haerten des Abbilds).

### 0.2.0 - 2026-08-27

#### Neu
- Der Import zeigt jetzt echte Fortschrittsschritte an (Metadaten lesen,
  Herunterladen mit Geschwindigkeit und Restzeit, Umwandeln, Cover und
  Metadaten einbetten, Speichern) statt eines einzelnen Ladebalkens.

#### Verbessert
- Ein Import hat jetzt eine Obergrenze fuer die Dateigroesse (Standard
  200 MB).

#### Behoben
- Ein laengerer Import konnte den Dienst so lange blockieren, dass der
  eigene Gesundheitscheck fehlschlug und der Import mitten drin abgebrochen
  wurde.
- Ein Import ohne bekannte Laufzeit (z. B. ein Livestream) schlug mit einem
  unklaren Fehler fehl statt mit einer verstaendlichen Meldung.

### 0.1.3 - 2026-08-26

#### Verbessert
- Die Download-Schnittstelle ist nur noch von der Box aus erreichbar, nicht
  mehr aus dem Netzwerk. Sie verlangte kein Passwort.

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

### 0.2.4 - 2026-09-01

#### Neu
- Die Box fuehrt jetzt eine Update-Historie: zu jedem Lauf wird festgehalten,
  welche Versionen vorher liefen. Das ist die Grundlage fuer den Rueckschritt
  auf die vorherige Version.

### 0.2.3 - 2026-08-30

#### Behoben
- Beim Zurueckschalten auf DHCP bleibt keine feste Adresse mehr im Profil
  stehen. Die Box war sonst unter zwei Adressen erreichbar, und die
  Oberflaeche nannte die falsche.

### 0.2.2 - 2026-08-29

#### Neu
- Verliert die Box laenger ihre Verbindung und haengt kein Netzwerkkabel,
  oeffnet sie selbst das Setup-WLAN "Minabox-Setup" (erreichbar unter
  http://10.42.0.1) und schaltet es wieder ab, sobald ein bekanntes WLAN
  erreichbar ist.

### 0.2.1 - 2026-08-26

#### Neu
- Prueft fuer den Knopf "Ton-Problem beheben" die Soundkarte und die
  Lautstaerkeregler des Systems und stellt einen Regler gerade, der auf null
  steht.
- Kann den Ton-Dienst allein neu starten, ohne die Oberflaeche mitzunehmen.

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

### 0.2.4 - 2026-08-28

#### Verbessert
- Der Dienst-Benutzer im Container hat kein Home-Verzeichnis mehr und ist
  nicht mehr anmeldbar (Haerten des Abbilds).

### 0.2.3 - 2026-08-26

#### Behoben
- Der Testton wurde ueber eine eigene, kurzlebige libVLC-Instanz abgespielt.
  Auf einer echten Box verlor die dabei zum Einsatz kommende libVLC-Ausgabe
  wiederholt die Synchronisation mit PipeWire und liess die Wiedergabe
  abbrechen oder abgeschnitten klingen. Der Testton laeuft jetzt ueber
  paplay, auf demselben Weg wie die Musik.

#### Verbessert
- Mehr Meldungen im Protokoll fuer Wiedergabe, Pause, Stopp und
  Lautstaerkeaenderungen - hilft bei der Fehlersuche im Diagnose-Paket.

### 0.2.2 - 2026-08-26

#### Behoben
- Die Box blieb nach einem Neustart manchmal stumm, obwohl niemand sie
  stummgeschaltet hatte. Das System merkte sich eine einmal gesetzte
  Stummschaltung dauerhaft und legte sie auf jede neue Wiedergabe; weder ein
  Neustart der Box noch der der Dienste raeumte das weg.
- Der Testton lief ueber einen anderen Weg als die Musik und war deshalb auch
  dann zu hoeren, wenn die Musik stumm blieb. Er nimmt jetzt denselben Weg und
  kann den Fehler damit ueberhaupt erst zeigen.

#### Neu
- Der Dienst meldet sich als eingeschraenkt, wenn der eingestellte Lautsprecher
  gar nicht mehr vorhanden ist. Vorher gab er sich als gesund aus, waehrend gar
  kein Ton moeglich war.
- Die Pruefkette hinter dem neuen Knopf "Ton-Problem beheben" in der WebUI.

### 0.2.1 - 2026-08-26

#### Behoben
- Die gemeldete Lautstaerke sprang beim Starten und beim Beenden eines Titels
  kurz auf einen falschen Wert. Der Regler in der Oberflaeche sprang dadurch
  nach jedem Stopp an sein linkes Ende.
- Nach einem Sprung an eine andere Stelle im Titel wurde kurz die alte Position
  gemeldet.
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

### 0.2.4 - 2026-08-31

#### Verbessert
- Das Laufzeit-Abbild ist kleiner: keine Paket-Werkzeuge (pip, setuptools) und
  kein `i2c-tools` mehr, das der Dienst ohnehin nie aufruft.

### 0.2.3 - 2026-08-28

#### Verbessert
- Der Dienst-Benutzer im Container hat kein Home-Verzeichnis mehr und ist
  nicht mehr anmeldbar (Haerten des Abbilds).

### 0.2.2 - 2026-08-28

#### Verbessert
- Docker meldet den Dienst nach einem Neustart rund zehn Sekunden frueher als
  betriebsbereit, im Gleichlauf mit den uebrigen Diensten.

### 0.2.1 - 2026-08-26

#### Verbessert
- Der Statusanschluss ist nur noch von der Box aus erreichbar, nicht mehr aus
  dem Netzwerk.

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

### 0.2.3 - 2026-08-28

#### Verbessert
- Die Zustandspruefung des Containers laeuft wieder wie bei allen anderen
  Diensten und braucht dabei weniger Rechenzeit; das Abbild wird etwas kleiner.

### 0.2.2 - 2026-08-28

#### Verbessert
- Der Dienst-Benutzer im Container hat kein Home-Verzeichnis mehr und ist
  nicht mehr anmeldbar (Haerten des Abbilds).

### 0.2.1 - 2026-08-26

#### Verbessert
- Der Dienst braucht dauerhaft rund fuenf Prozent weniger Rechenzeit. Seine
  regelmaessige Zustandspruefung kostete mehr als der Dienst selbst.
- Der Statusanschluss ist nur noch von der Box aus erreichbar, nicht mehr aus
  dem Netzwerk.

### 0.2.0 - 2026-08-25

#### Behoben
- Ein Tastendruck-Pin, der schon einem anderen Dienst gehoert, legte bisher
  **alle** Tasten der Box still - und gab die Pins bis zum Neustart des
  Containers nicht wieder her. Jetzt faellt nur die betroffene Taste aus, die
  uebrigen funktionieren weiter.
- Eine unvollstaendige Tasten-Konfiguration liess sich speichern, brachte den
  Dienst beim naechsten Start aber in eine Neustart-Schleife. Sie wird jetzt
  schon beim Speichern abgelehnt, und der Dienst startet auch mit einer
  fehlerhaften Datei, damit sie sich ueber die Oberflaeche reparieren laesst.

#### Verbessert
- Die Zustandsanzeige des Dienstes meldet jetzt "eingeschraenkt", wenn eine
  Taste ihren Pin nicht bekommt oder die Konfiguration nicht laedt - vorher
  sah eine Box mit lauter toten Tasten gesund aus.
- Der Dienst braucht rund 60 Prozent weniger Rechenzeit im Leerlauf und sein
  Abbild ist 68 MB kleiner.

### 0.1.2 - 2026-08-23

### 0.1.1 - 2026-08-22

### 0.1.0 - 2026-08-20

#### Neu
- Der Dienst meldet seine Version.

---

## led

### 0.2.3 - 2026-08-28

#### Verbessert
- Die Zustandspruefung des Containers laeuft wieder wie bei allen anderen
  Diensten und braucht dabei weniger Rechenzeit; das Abbild wird etwas kleiner.

### 0.2.2 - 2026-08-28

#### Verbessert
- Der Dienst-Benutzer im Container hat kein Home-Verzeichnis mehr und ist
  nicht mehr anmeldbar (Haerten des Abbilds).

### 0.2.1 - 2026-08-26

#### Verbessert
- Der Dienst braucht dauerhaft rund fuenf Prozent weniger Rechenzeit. Seine
  regelmaessige Zustandspruefung kostete mehr als der Dienst selbst.

### 0.2.0 - 2026-08-25

#### Behoben
- Eine LED, die auf eine gesperrte Karte gebunden ist, reagiert jetzt auch
  darauf - bisher passierte nichts.
- Wiederholungen zaehlen ueberall ganze Zyklen: ein Blinken ist einmal an und
  wieder aus.
- Der LED-Test blinkt die vollen fuenf Sekunden, und die Oberflaeche wartet
  nicht mehr darauf, sondern antwortet sofort.
- Ein Muster mit unbrauchbaren Werten laesst die LED nicht mehr stumm dunkel,
  sondern laeuft mit einem sinnvollen Standardwert weiter.
- Eine abgeschaltete LED gibt ihren GPIO-Pin wieder frei.
- Das Speichern der LED-Einstellungen hinterlaesst keine Fehlermeldungen mehr
  im Protokoll.
- Waehrend der Wiedergabe schreibt der Dienst nicht mehr im Sekundentakt
  dieselbe Zeile ins Protokoll.

#### Verbessert
- Die Systemuebersicht unterscheidet jetzt, wie viele LEDs eingerichtet und wie
  viele davon wirklich ansprechbar sind.
- Das Abbild des Dienstes ist rund ein Viertel kleiner, Updates laden schneller.

### 0.1.1 - 2026-08-23

### 0.1.0 - 2026-08-20

#### Neu
- Der Dienst meldet seine Version.

---

## display

### 0.3.0 - 2026-09-02

#### Verbessert
- Die Lautstaerke zeigt jetzt Knuffel, der singt - je lauter, desto mehr Noten
  steigen aus ihm auf.
- Beim Abspielen laeuft Knuffel die Fortschrittsleiste ab und winkt zum
  Schluss; die Restzeit macht dafuer Platz.
- Der Stumm-Bildschirm zeigt Knuffel mit geschlossenem Mund statt eines
  durchgestrichenen Lautsprechers.

### 0.2.3 - 2026-08-29

#### Neu
- Zeigt einen eigenen Bildschirm, wenn die Box nicht auf dem gewohnten Weg
  erreichbar ist - mit SSID, Passwort und Adresse des Setup-WLANs.

### 0.2.2 - 2026-08-28

#### Verbessert
- Der Dienst-Benutzer im Container hat kein Home-Verzeichnis mehr und ist
  nicht mehr anmeldbar (Haerten des Abbilds).

### 0.2.1 - 2026-08-26

#### Neu
- Beim Pausieren schlaeft das Wesen jetzt ein, mit Zs, die ueber ihm
  aufsteigen. Vorher stand da nur das Wort "Pause" - das hilft nur, wer schon
  lesen kann.

#### Verbessert
- Der Statusanschluss ist nur noch von der Box aus erreichbar, nicht mehr aus
  dem Netzwerk.

### 0.2.0 - 2026-08-26

#### Neu
- Das Display zeigt jetzt fuer jede Situation ein eigenes Bild statt einer Reihe
  kleiner Symbole: waehrend der Wiedergabe Titel, Fortschritt und Restzeit, im
  Leerlauf ein kleines Wesen, das umherwandert, blinzelt und winkt.
- Beim Drehen am Lautstaerkeknopf erscheint kurz eine grosse Anzeige mit einem
  Block je Raste.
- Eine unbekannte, eine gesperrte Figur und ein erreichtes Tageslimit haben je
  ein eigenes Bild - vorher blieb das Display stumm.
- Nachts wird das Display dunkler und kann sich ganz abschalten, solange nichts
  passiert.

#### Verbessert
- Die Lautstaerkeanzeige zeigt die Stellung im erlaubten Bereich. Auf einer Box
  mit Maximum 40 stand vorher "40 %", obwohl der Knopf am Anschlag war.
- Es wird nur noch der geaenderte Bildausschnitt an das Panel geschickt, statt
  jedes Mal das ganze Bild. Der Leser am selben Anschluss wird dadurch deutlich
  seltener blockiert.

#### Behoben
- Beim Abnehmen und beim Auflegen einer Figur sprang kurz die Lautstaerkeanzeige
  an, obwohl sich nichts geaendert hatte.

### 0.1.1 - 2026-08-23

### 0.1.0 - 2026-08-20

#### Neu
- Der Dienst meldet seine Version.
