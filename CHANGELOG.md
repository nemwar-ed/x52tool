# Changelog

## v0.0.3.2-beta

### Neu
- Elite-Reiter: neue Zeile **Journal-Ordner** mit automatischer Suche, Ordnerwahl, Öffnen und Anzeige „Status.json zuletzt aktualisiert vor …“. Grundlage für die LED-Regeln je Schiffszustand.
- `elite/paths.py` sucht jetzt E:D-Installationen (Benutzerordner im Wine-Prefix) und leitet daraus Bindings- **und** Journal-Ordner ab. Bei mehreren Installationen steht die zuletzt gespielte vorne (neueste `Status.json` bzw. neuestes Journal) – das gilt jetzt auch für die Bindings.
- Journal-Ordner wird auch gefunden, wenn „Saved Games“ im Prefix anders heißt.
- Neue Einstellung `ed_journal_dir` in `config.json` (leer = automatisch suchen).
- Tests für die Ordnersuche.

## v0.0.3.1-beta

### Behoben
- LED-Farben, Uhrformat (12/24h), Datumsformat, Zeitzonen und Helligkeit gingen nach einem Neustart verloren. Ursache: `x52ctl config save` meldet „OK“, speichert in libx52 aber nichts.
- Lösung: `x52tool` schreibt jede Änderung zusätzlich in `/var/lib/x52tool/x52d.conf`, und `x52d` lädt diese Datei beim Start (`-c`). Das `x52tool` muss dafür nicht laufen.

### Geändert
- `install.sh` legt `/var/lib/x52tool/x52d.conf` an (Kopie von `/etc/x52d/x52d.conf`, gehört dem Benutzer) und erweitert das systemd-Drop-in um `ExecStart … -c`. Unbekannte Altlast-Schlüssel (`SocketGroup`, `SocketMode`) werden entfernt.
- LED/MFD-Reiter zeigt beim Start die tatsächlich gesetzten LED-Farben und Helligkeiten statt „off“.
- „Alle LEDs an/aus“ und „MFD an/aus“ ändern jetzt die Einstellungen (inkl. Anzeige), statt nur kurz zu schalten.
- Der Volltest wird nicht gespeichert und stellt danach den eingestellten Zustand wieder her.
- Einstellungen-Reiter zeigt, ob Einstellungen dauerhaft gespeichert werden.
- README (DE/EN) komplett überarbeitet.

**Nach dem Update einmal `sudo bash install.sh` ausführen.**

## v0.0.3-beta
- Neuer Reiter „Elite Dangerous“: Bindings-Ordner automatisch finden (Steam-Bibliotheken, Heroic, Faugus, Lutris), eigene Tastennamen (`.buttonMap`) für den X52 Pro installieren/entfernen, fremde Dateien werden gesichert.

## v0.0.2.1-beta
- MFD-Uhr läuft über `x52d` (Zeitzonen-Namen statt GMT-Versatz).
- Socket-Zugriff bleibt nach Neustart erhalten (systemd-Drop-in statt tmpfiles-Regel).
- Alte x52cli-Einstellungen werden automatisch migriert.

## v0.0.2-beta
- Umstellung von `x52cli` (direkter USB-Zugriff) auf den Dienst `x52d` mit `x52ctl`.
- Dienststatus mit Start/Stopp im Einstellungen-Reiter.
- `install.sh` für die einmalige Systemeinrichtung.

## v0.0.1-beta
- Erste öffentliche Version: Live-Test, Kalibrierung (Rauschen, Peak-Messung, flat/fuzz via `EVIOCSABS`), LED/MFD-Steuerung, Einstellungen, Deutsch/Englisch, Logs und Diagnosebericht.
