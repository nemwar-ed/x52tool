# x52tool

**Test-, Kalibrierungs- und LED/MFD-Werkzeug für den Saitek / Logitech X52 und X52 Pro unter Linux.**

| | | | |
|---|---|---|---|
| ![Live-Test](tab_live-test.jpg) | ![Kalibrierung](tab_kalibrierung.jpg) | ![LED/MFD](tab_led-mfd.png) | ![Einstellungen](tab_einstellungen.jpg) |

`x52tool` ist eine native Linux-GUI für den X52 und X52 Pro HOTAS. Das Programm zeigt, was Linux vom Gerät sieht, ermöglicht den Echtzeit-Test von Achsen und Tasten, die Kalibrierung der Achsen sowie die Steuerung von LEDs und dem MFD-Display – ohne Daemon und ohne Windows-Treiber.

Getestet auf: **Logitech X52 Professional** (USB-ID `06a3:0762`) unter **CachyOS** (Arch-basiert).

---

## Funktionen

### Live-Test
- Echtzeit-Anzeige aller Achsen und Tasten aus Linux `evdev`
- Achsbalken mit Deadzone-Anzeige
- Tastenraster mit Live-Hervorhebung
- Ministick separat dargestellt

### Kalibrierung
- Geführte Achsenmessung (Min/Max-Erkennung, eine Achse nach der anderen)
- Anzeige von Rauschen und Mittenpunktversatz
- Deadzone- und Fuzz-Vorschläge auf Basis der Messwerte
- Direkte Übernahme der Kalibrierung in den Kernel via `EVIOCSABS`
- Speichern und Laden von Kalibrierprofilen je USB-ID

### LED / MFD
- Einzelne LED-Farben einstellen (Fire, A, B, D, E, T1/T2, T3/T4, T5/T6, POV2, Clutch, Schubhebel)
- MFD-Uhr: Lokalzeit, 12/24h-Format, Datumsformat, Zeitzonen-Versatz für Uhr 2 und Uhr 3
- MFD-Helligkeit und LED-Helligkeit per Live-Schieberegler
- Alle LEDs an / Alle LEDs aus / MFD an / MFD aus
- Vollständiger LED/MFD-Test mit Abschlussanzeige im Display
- Kupplungsmodus (Clutch) umschalten

### Einstellungen
- Geräteinformationen mit Neu-Suchen-Button
- Sprachwahl (Deutsch / Englisch)
- Log-Datei öffnen und Diagnosebericht erstellen

---

## Voraussetzungen

- Linux
- Python 3.10 oder neuer
- PyQt6
- python-evdev
- Saitek / Logitech X52 oder X52 Pro
- `libx52` (`x52cli`) für LED- und MFD-Steuerung

---

## Installation

### CachyOS / Arch

Python-Abhängigkeiten installieren:

```bash
pip install pyqt6 evdev --break-system-packages
```

Oder in einer virtuellen Umgebung:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

`libx52` aus dem AUR installieren:

```bash
yay -S libx52
```

Programm starten:

```bash
python3 -m x52tool
```

Oder mit der virtuellen Umgebung:

```bash
.venv/bin/python -m x52tool
```

### USB-Rechte für LEDs und MFD

`x52cli` greift direkt auf das USB-Gerät zu. Für den Zugriff ohne Root-Rechte wird eine udev-Regel benötigt.

Für den X52 Pro (`06a3:0762`) folgende Datei anlegen: `/etc/udev/rules.d/60-x52tool.rules`

```
SUBSYSTEMS=="usb", ATTRS{idVendor}=="06a3", ATTRS{idProduct}=="0762", MODE="0666"
```

Danach Regeln neu laden und Gerät neu einstecken:

```bash
sudo udevadm control --reload-rules
```

Den X52 Pro einmal abziehen und wieder einstecken.

---

## Kommandozeile

Erkannte Geräte ohne GUI auflisten:

```bash
python3 -m x52tool --list
```

Gespeichertes Kalibrierprofil anwenden:

```bash
python3 -m x52tool --apply
python3 -m x52tool --apply --device /dev/input/event7
```

---

## Projektstruktur

```
x52tool/
├── README.md
├── README.de.md
├── LICENSE
├── requirements.txt
├── run.sh
└── x52tool/
    ├── __init__.py
    ├── __main__.py
    ├── analysis.py
    ├── config.py
    ├── device.py
    ├── logger.py
    ├── output.py
    └── ui/
        ├── calib2_tab.py
        ├── live_tab.py
        ├── main_window.py
        ├── output_tab.py
        ├── settings_tab.py
        └── widgets.py
```

Einstellungen und Kalibrierprofile werden gespeichert unter:

```
~/.config/x52tool/config.json
```

Log-Dateien werden gespeichert unter:

```
~/.local/share/x52tool/x52tool.log
~/.local/share/x52tool/x52tool-diag.log
```

---

## KI-gestützte Entwicklung

`x52tool` wurde mit Unterstützung von **Anthropic Claude** entwickelt. Aller Code wird vor dem Commit auf echter Linux- / X52-Pro-Hardware überprüft und getestet.

---

## Mitmachen

Fehlerberichte, Tests auf anderer X52- / X52-Pro-Hardware und Verbesserungsvorschläge sind willkommen.

Für Fehlerberichte bitte folgendes mitschicken:

- Distribution und Version
- Kernel-Version
- X52 oder X52 Pro
- Ausgabe von `lsusb`
- Ausgabe von `python3 -m x52tool --list`
- Fehlermeldungen aus dem Terminal
- Den Diagnosebericht aus Einstellungen → Diagnose erstellen

---

## Lizenz

`x52tool` wird unter der **GNU General Public License v3.0** veröffentlicht. Siehe `LICENSE`.

`libx52` ist ein eigenständiges Projekt mit eigener Lizenz: https://github.com/nirenjan/libx52

---

## Links

- libx52: https://github.com/nirenjan/libx52
- python-evdev: https://python-evdev.readthedocs.io/
- libx52 im AUR: https://aur.archlinux.org/packages/libx52
