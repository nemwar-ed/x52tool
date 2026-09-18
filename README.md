# x52tool

**Test-, Analyse- und Kalibrierwerkzeug für Saitek / Logitech X52 und X52 Pro unter Linux.**

`x52tool` ist eine native Linux-GUI zur Untersuchung eines X52/X52 Pro. Das Programm zeigt, was Linux vom Gerät sieht, hilft beim Testen von Achsen und Tasten, misst Achsen im Ruhezustand und über ihren Bewegungsbereich und bietet experimentelle Kalibrierfunktionen.

Das Projekt entstand ursprünglich durch **AI-assisted development („Vibe Coding“) mit Anthropic Claude**. Die weitere Entwicklung, Überprüfung, Fehlersuche und Aufräumarbeit erfolgt mit Unterstützung von **OpenAI ChatGPT**.

Der Code wird nicht ungeprüft als korrekt vorausgesetzt: Funktionen sollen auf echter Linux-/X52-Pro-Hardware praktisch getestet werden. Nicht getestete Funktionen werden entsprechend gekennzeichnet.

## Aktueller Stand – v0.1.0

### Enthalten

- Erkennung von X52/X52 Pro über Linux `evdev`
- Anzeige der erkannten Achsen und Tasten
- Live-Test mit Achsbalken und Tastenraster
- Ruhemessung von Achsen
- Bereichsmessung von Achsen
- Vorschlag einer Deadzone auf Basis der gemessenen Ruhelage und des Rauschens
- experimentelle Kalibrierung über `EVIOCSABS`
- Speichern und Laden von Kalibrierprofilen
- LED-Steuerung über `x52cli` / `libx52`
- MFD-Ausgabe über `x52cli` / `libx52`
- Helligkeitssteuerung für unterstützte LED-/MFD-Funktionen
- native PyQt6-Oberfläche
- kein Flatpak erforderlich

### Noch nicht vollständig validiert

- praktische Kalibrierung mit `EVIOCSABS` auf verschiedenen X52-Pro-Systemen
- dauerhafte Anwendung von Kalibrierprofilen über udev
- Übernahme von `flat`/Deadzone durch alle Anwendungen und Spiele
- vollständiger MFD-Test auf unterschiedlicher X52-Hardware
- Grenzwerte und Heuristiken der Analyse als allgemeingültige Hardwarediagnose

### Nicht Bestandteil von v0.1.0

- Elite-Dangerous-Integration
- andere Game-Plugins
- virtuelle Joysticks / eigene Antwortkurven über `uinput`
- Hintergrund-Daemon für mehrere Anwendungen

Diese Funktionen können später separat entwickelt werden.

## Architektur

Das Programm verwendet bewusst vorhandene Linux-Schnittstellen und baut das USB-Protokoll des X52 nicht selbst nach:

    x52tool
       │
       ├───────────────┐
       │               │
    Eingabe          Ausgabe
       │               │
     evdev           x52cli
       │               │
    /dev/input/      libx52
    eventN             │
       │               │
       └───────┬───────┘
               │
             X52 Pro

- **PyQt6** – grafische Oberfläche
- **python-evdev** – Achsen, Tasten und Event-Geräte
- **EVIOCGABS / EVIOCSABS** – Lesen und Schreiben der evdev-Achsenparameter
- **x52cli / libx52** – LEDs und MFD

`x52d` und `x52ctl` gehören ebenfalls zum libx52-Projekt. Sie sind für den aktuellen v0.1.0-Ausgabeweg jedoch nicht erforderlich. `x52tool` verwendet für LEDs und MFD bewusst das direkte `x52cli`.

## Voraussetzungen

- Linux
- Python 3
- PyQt6
- python-evdev
- ein Saitek / Logitech X52 oder X52 Pro
- optional: `libx52` für LEDs und MFD

Die Entwicklung und die Hardwaretests dieses Projekts erfolgen auf **CachyOS**.

## Installation unter CachyOS / Arch

Python-Abhängigkeiten können aus den vorhandenen Systempaketen oder in einer virtuellen Umgebung installiert werden.

Beispiel mit einer virtuellen Umgebung:

    python3 -m venv .venv
    .venv/bin/pip install -r requirements.txt

Danach kann das Programm gestartet werden:

    ./run.sh

Wenn die Abhängigkeiten über die virtuelle Umgebung installiert wurden und `run.sh` das System-Python verwendet, kann alternativ direkt die Python-Umgebung gestartet werden:

    .venv/bin/python -m x52tool

### libx52 / x52cli

Für die LED- und MFD-Funktionen wird `libx52` benötigt.

`libx52` ist auf Arch-basierten Systemen derzeit nicht Bestandteil der offiziellen Arch-/CachyOS-Repositories, sondern über das **AUR** verfügbar.

Mit einem AUR-Helper beispielsweise:

    yay -S libx52

Anschließend sollte das Programm gefunden werden:

    which x52cli

`x52tool` benötigt für diesen Ausgabeweg nicht `x52d`.

## USB-Rechte für LEDs und MFD

`x52cli` greift für die X52-spezifischen Ausgabefunktionen direkt auf das USB-Gerät zu. Auf einer Standardinstallation kann der Zugriff für einen normalen Benutzer fehlen.

Für einen X52 Pro mit USB-ID `06a3:0762` kann eine udev-Regel verwendet werden:

    SUBSYSTEMS=="usb", ATTRS{idVendor}=="06a3", ATTRS{idProduct}=="0762", MODE="0666"

Zum Beispiel als:

    /etc/udev/rules.d/60-x52tool.rules

Danach die Regeln neu laden:

    sudo udevadm control --reload-rules

Anschließend den X52 Pro einmal abziehen und wieder einstecken.

**Hinweis:** Diese Regel gibt Zugriff auf genau dieses USB-Gerät für alle lokalen Benutzer. Sie wurde für den Entwicklungsstand von `x52tool` auf CachyOS praktisch getestet.

Die USB-ID anderer X52-Varianten kann abweichen.

## Live-Test

Der Live-Test zeigt alle vom gewählten evdev-Gerät erkannten Achsen und Tasten.

Achsen werden mit Rohwert, Bereich und sichtbarer Deadzone dargestellt. Tasten leuchten in der Oberfläche auf, sobald Linux den entsprechenden Button-Event meldet.

Der Tab ist bewusst rein diagnostisch: Er verändert keine Geräteeinstellungen.

## Analyse

### Ruhemessung

Stick und Schubhebel werden für eine einstellbare Zeit nicht berührt. `x52tool` sammelt den aktuellen Achszustand und berechnet unter anderem:

- Mittelwert / Mittenversatz
- Spitze-Spitze-Rauschbreite
- Standardabweichung
- aktuellen `flat`-Wert
- einen daraus abgeleiteten Deadzone-Vorschlag

Wenn gewünscht, wird `fuzz` während der Messung vorübergehend auf 0 gesetzt und anschließend wiederhergestellt. Dadurch soll vermieden werden, dass die Kernel-Filterung selbst als Hardware-Rauschen gemessen wird.

Der Deadzone-Vorschlag ist eine **Heuristik**, keine garantierte optimale Einstellung.

### Bereichsmessung

Jede Achse wird einmal von Anschlag zu Anschlag bewegt. Das Programm vergleicht den gemessenen Bereich mit dem vom Kernel gemeldeten Bereich.

Ein geringer gemessener Bereich bedeutet zunächst nur:

> Die Achse hat während der Messung den erwarteten Bereich nicht erreicht.

Das ist **kein automatischer Beweis für einen defekten oder verschlissenen Sensor**. Die Bewegung während der Messung, die Mechanik und weitere Faktoren können das Ergebnis beeinflussen.

## Kalibrierung

Der Kalibrierungs-Tab kann für analoge Achsen folgende evdev-Werte verändern:

- `minimum`
- `maximum`
- `fuzz`
- `flat`

Die Werte werden über `EVIOCSABS` direkt an das Event-Gerät geschrieben.

Die Änderungen gelten zunächst nur für den aktuellen Gerätezustand und können beim erneuten Einstecken verloren gehen. Das Projekt enthält deshalb Funktionen zum Speichern von Profilen und zum Erzeugen von udev-Regeln.

### Wichtige Einschränkung

Nicht jede Anwendung verwendet die evdev-Achsenparameter auf dieselbe Weise. Insbesondere bei Proton kann der tatsächlich verwendete Eingabeweg unterschiedlich sein.

Deshalb sollte eine Kalibrierung **nicht als automatisch spielwirksame Deadzone betrachtet werden**, bevor sie mit der konkreten Anwendung getestet wurde.

Die Kalibrierungsfunktion ist in v0.1.0 ausdrücklich **experimentell**.

## Kommandozeile

Auch ohne Qt kann das Programm Geräte auflisten:

    python3 -m x52tool --list

Gespeicherte Profile können über den Apply-Modus auf ein Gerät geschrieben werden:

    python3 -m x52tool --apply

Oder gezielt auf einen Event-Knoten:

    python3 -m x52tool --apply --device /dev/input/event7

Dieser Teil ist für die spätere dauerhafte Profilanwendung vorgesehen und in v0.1.0 noch nicht als vollständig getesteter udev-Workflow anzusehen.

## Projektstruktur

    x52tool/
    ├── README.md
    ├── LICENSE
    ├── requirements.txt
    ├── run.sh
    └── x52tool/
        ├── __init__.py
        ├── __main__.py
        ├── analysis.py
        ├── config.py
        ├── device.py
        ├── output.py
        └── ui/
            ├── __init__.py
            ├── analysis_tab.py
            ├── calib_tab.py
            ├── live_tab.py
            ├── main_window.py
            ├── output_tab.py
            └── widgets.py

Lokale Einstellungen und Kalibrierprofile werden unter

    ~/.config/x52tool/config.json

gespeichert.

## AI-assisted development

`x52tool` entstand ursprünglich durch AI-assisted development („Vibe Coding“) mit **Anthropic Claude**.

Die weitere Entwicklung umfasst Review, Fehlersuche, Tests, technische Recherche und strukturelle Überarbeitung mit Unterstützung von **OpenAI ChatGPT**.

KI-generierter Code kann Fehler enthalten. Deshalb gilt für dieses Projekt ausdrücklich: Eine Funktion gilt nicht allein deshalb als zuverlässig, weil der Code plausibel aussieht.

Hardwarefunktionen werden auf realer Linux-/X52-Pro-Hardware getestet und ungetestete Funktionen werden als solche dokumentiert.

## Mitmachen

Fehlerberichte, Tests mit anderen X52-/X52-Pro-Geräten und Verbesserungen sind willkommen.

Besonders hilfreich sind bei Fehlerberichten:

- Distribution und Version
- Kernel-Version
- X52 oder X52 Pro
- Ausgabe von `lsusb`
- Ausgabe von `python3 -m x52tool --list`
- relevante Fehlermeldungen aus dem Terminal

## Lizenz

`x52tool` wird unter der **GNU General Public License v3.0** veröffentlicht. Siehe `LICENSE`.

Die verwendeten externen Projekte und Bibliotheken besitzen eigene Lizenzen. Insbesondere `libx52` ist ein separates Projekt und wird von `x52tool` nicht als Bestandteil des Python-Quellcodes eingebettet.

## Bekannte Einschränkungen

- Die Kalibrierungsfunktionen sind noch nicht umfassend auf verschiedenen X52-Pro-Geräten getestet.
- Die Wirkung von `flat` und `fuzz` hängt vom verwendeten Eingabeweg der jeweiligen Anwendung ab.
- Die Analyse liefert Messwerte und Heuristiken, keine automatische Aussage über einen Hardwaredefekt.
- Für LEDs und MFD wird ein installiertes `x52cli` benötigt.
- Für den direkten USB-Zugriff kann eine passende udev-Regel erforderlich sein.
- Game-Integration und Plugin-Unterstützung sind noch nicht Bestandteil von v0.1.0.

## Danksagung

Danke an die Entwickler von **libx52** und **python-evdev** für die vorhandenen Linux-Schnittstellen und Werkzeuge, auf denen `x52tool` aufbaut.

### Weitere Projekte

- libx52: https://github.com/nirenjan/libx52
- python-evdev: https://python-evdev.readthedocs.io/
- libx52 im Arch User Repository: https://aur.archlinux.org/packages/libx52
