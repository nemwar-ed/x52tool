# x52tool – systemd user services einrichten

## Voraussetzungen

- `libx52` installiert (enthält `x52d` und `x52ctl`)
- `x52tool` installiert (`pip install --user .` im Repo-Verzeichnis)

## Installation

```bash
# Units ins systemd-Verzeichnis kopieren
mkdir -p ~/.config/systemd/user/
cp systemd/x52d.service ~/.config/systemd/user/
cp systemd/x52tool-apply.service ~/.config/systemd/user/
cp systemd/x52tool-clock.service ~/.config/systemd/user/
cp systemd/x52tool-clock.timer ~/.config/systemd/user/

# systemd neu laden
systemctl --user daemon-reload

# Alle Units aktivieren und starten
systemctl --user enable x52d.service x52tool-apply.service x52tool-clock.timer
systemctl --user start x52d.service x52tool-apply.service x52tool-clock.timer

# Status prüfen
systemctl --user status x52d.service x52tool-clock.timer
```

## Was passiert beim Login

1. `x52d.service` startet – hält die USB-Verbindung zum X52 Pro offen
2. `x52tool-apply.service` läuft einmalig – setzt gespeicherte Kalibrierungswerte via evdev
3. `x52tool-clock.timer` läuft jede Minute – schreibt aktuelle Uhrzeit ins MFD

## Steuerung aus der GUI

Im x52tool unter **Einstellungen → x52d Dienst** können alle drei Units
gemeinsam gestartet und gestoppt werden.

## Deinstallation

```bash
systemctl --user disable --now x52d.service x52tool-apply.service x52tool-clock.timer
rm ~/.config/systemd/user/x52d.service
rm ~/.config/systemd/user/x52tool-apply.service
rm ~/.config/systemd/user/x52tool-clock.service
rm ~/.config/systemd/user/x52tool-clock.timer
systemctl --user daemon-reload
```
