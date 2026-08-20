# Minabox installieren

Diese Anleitung richtet sich an Endnutzer. Wer den Stack von Hand aufsetzen
oder daran entwickeln will, findet den manuellen Weg in
[DEPLOYMENT.md](DEPLOYMENT.md).

## Was du brauchst

| | |
|---|---|
| Raspberry Pi | 4 oder 5 (3B+ funktioniert, ist aber spuerbar langsamer) |
| Speicherkarte | 16 GB oder mehr |
| Netzteil | 5V/3A (Pi 4) bzw. 5V/5A (Pi 5) |
| Betriebssystem | Raspberry Pi OS **64-bit** |
| Netzwerk | LAN oder WLAN mit Internetzugang |

Ein zu schwaches Netzteil ist die haeufigste Ursache fuer sporadische Abstuerze
und Tonaussetzer. Wenn etwas unerklaerlich klemmt: zuerst das Netzteil pruefen.

## 1. Betriebssystem aufspielen

Mit dem [Raspberry Pi Imager](https://www.raspberrypi.com/software/):

1. **Raspberry Pi OS (64-bit)** waehlen — die 32-Bit-Variante funktioniert nicht.
2. Vor dem Schreiben ueber das Zahnrad die Voreinstellungen oeffnen und setzen:
   - Hostname, z. B. `minabox`
   - Benutzername und Passwort
   - WLAN-Zugangsdaten
   - SSH aktivieren
3. Karte schreiben, in den Pi stecken, einschalten.

## 2. Verbinden

Vom Rechner aus:

```bash
ssh <benutzername>@minabox.local
```

## 3. Installationsassistent starten

```bash
curl -fsSL https://raw.githubusercontent.com/Opnek90/Minabox/main/install.sh -o minabox-install.sh
```

```bash
bash minabox-install.sh
```

Der zweite Schritt ist Absicht: `curl ... | bash` wuerde die Dialoge nicht
bedienbar machen, weil sie ein echtes Terminal brauchen.

## 4. Durch den Assistenten

Der Assistent fuehrt durch diese Schritte:

**Sprache** — Deutsch oder Englisch. Gilt fuer den Assistenten und wird als
Vorgabe fuer die Bedienoberflaeche gespeichert.

**Komponenten** — Mit der Leertaste an- und abwaehlen, mit TAB auf *OK*.

| Komponente | Wofuer | Hardware |
|---|---|---|
| RFID-Leser | Karten und Figuren erkennen | PN532 am I2C |
| LEDs | Statusanzeige | GPIO |
| Taster / Drehregler | Bedienung am Geraet | GPIO |
| OLED-Display | Titel, Uhrzeit, Lautstaerke | SSD1306 am I2C |
| Medienimport | Medien von einer URL in die Bibliothek holen | keine |

MQTT, Backend, Host-Helper, Audio und WebUI laufen immer und stehen nicht zur
Wahl. Waehle nur an, was du wirklich angeschlossen hast — eine ausgewaehlte
Komponente ohne Hardware startet dauerhaft neu.

Nichts davon ist endgueltig: der Assistent laesst sich jederzeit erneut starten
und Komponenten nachtraeglich zu- oder abschalten.

**Basisangaben** — Geraetename, Port der Bedienoberflaeche (Standard 80),
Zeitzone, Protokollumfang.

**Audio** — Erkannte Soundkarten sind mit `(*)` markiert. Zur Wahl stehen die
Kopfhoererbuchse, HDMI, USB-Soundkarten sowie HiFiBerry-, IQaudio- und
WM8960-HATs. Bei einem HAT traegt der Assistent das passende `dtoverlay` ein;
das wird erst nach einem Neustart wirksam.

Die bestehende `config.txt` wird vorher als `config.txt.minabox-backup`
gesichert, und der Assistent aendert nur seinen eigenen, markierten Abschnitt.

**Autostart** — Optional. Die Container starten ohnehin von allein neu; der
Systemdienst hilft zusaetzlich, wenn Minabox vorher von Hand gestoppt wurde.

Danach laedt der Assistent die Container und startet sie.

## 5. Einrichten

Zum Schluss nennt der Assistent die Adresse, etwa:

```
http://192.168.1.42
```

Diese im Browser oeffnen — dort werden Karten angelegt, Musik hochgeladen und
alles Weitere eingestellt.

Wurde bei Audio ein HAT gewaehlt, jetzt neu starten und den Assistenten noch
einmal aufrufen, um unter *Audio neu einrichten* den Ausgang festzulegen.

## Erneuter Aufruf: das Wartungsmenue

```bash
bash minabox-install.sh
```

Auf einer bestehenden Installation oeffnet sich statt der Neuinstallation:

| Punkt | Wirkung |
|---|---|
| Komponenten aendern | LED, Display etc. nachruesten oder entfernen |
| Update einspielen | Neueste Version laden und neu starten |
| Audio neu einrichten | Ausgang wechseln oder nach einem Neustart festlegen |
| Status und Diagnose | Zustand aller Container |
| Sprache aendern | Deutsch / Englisch |
| Minabox entfernen | Container und Dienst entfernen; Daten nur auf Nachfrage |

## Wenn etwas nicht klappt

Der Assistent schreibt alles nach `~/minabox-install.log`. Das ist bei
Rueckfragen die erste Anlaufstelle.

**Kein Ton.** Meist ist der falsche Ausgang eingestellt. Assistent starten →
*Audio neu einrichten*. Nach einem HAT-Wechsel ist ein Neustart noetig.

**Ton nur nach dem Anmelden per SSH.** Der Audio-Dienst braucht die
Benutzersitzung. Der Assistent aktiviert das dauerhaft mit
`loginctl enable-linger`; pruefen mit `loginctl show-user $USER | grep Linger`.

**Ein Container startet dauernd neu.** Meist ist eine Komponente ausgewaehlt,
deren Hardware nicht angeschlossen ist. Im Wartungsmenue abwaehlen.

**Bedienoberflaeche nicht erreichbar.** Beim ersten Start dauert es einen
Moment. Zustand pruefen mit:

```bash
cd ~/minabox && docker compose ps
```

**Weitere Hilfe.** [Troubleshooting.md](Troubleshooting.md), und fuer eine
Supportanfrage das Diagnose-Paket aus der Oberflaeche
(*Einstellungen → Diagnose*) mitschicken — siehe [DebugExport.md](DebugExport.md).
