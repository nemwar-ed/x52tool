"""Dauerhafte x52d-Konfiguration, die x52tool selbst verwaltet.

Hintergrund: `x52ctl config set` wirkt nur im laufenden Daemon.
`x52ctl config save` meldet zwar "OK", schreibt in der getesteten
libx52-Version aber nichts – nach einem Neustart von x52d (z.B. beim
Booten) waren Uhrformat, LED-Farben und Helligkeit wieder auf Standard.

Loesung: install.sh legt einmalig eine Kopie der x52d-Konfiguration unter
/var/lib/x52tool/x52d.conf an, die dem Benutzer gehoert, und startet x52d
per systemd-Drop-in mit `-c` auf genau diese Datei. x52tool setzt jeden
Wert live per x52ctl *und* schreibt ihn hier hinein. Beim naechsten Start
laedt x52d die Werte selbst – das x52tool muss dafuer nicht laufen.

Das Format ist INI: [Section] / Key=Value, Kommentare mit '#'. Schluessel
werden ohne Ruecksicht auf Gross-/Kleinschreibung gesucht; Kommentare und
Reihenfolge der Datei bleiben erhalten.
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

from .logger import get_logger

log = get_logger("x52d_conf")

DEFAULT_PATH = Path("/var/lib/x52tool/x52d.conf")

_SECTION_RE = re.compile(r"^\s*\[([^\]]+)\]\s*$")
_KEY_RE = re.compile(r"^\s*([^#;=\s][^=]*?)\s*=\s*(.*?)\s*$")

# Schreibweise der Schluessel wie in der x52d.conf von libx52.
_CANONICAL = {
    ("led", "fire"): "Fire",
    ("led", "throttle"): "Throttle",
    ("led", "clutch"): "Clutch",
    ("led", "pov"): "POV",
    ("brightness", "mfd"): "MFD",
    ("brightness", "led"): "LED",
}


def conf_path() -> Path:
    """Pfad der verwalteten Datei (fuer Tests per Umgebungsvariable aenderbar)."""
    override = os.environ.get("X52TOOL_X52D_CONF")
    return Path(override) if override else DEFAULT_PATH


def canonical_key(section: str, key: str) -> str:
    """'a' -> 'A', 'fire' -> 'Fire', 'mfd' -> 'MFD' usw."""
    found = _CANONICAL.get((section.lower(), key.lower()))
    if found:
        return found
    if section.lower() == "led":
        return key.upper()
    return key


def is_ready() -> bool:
    """True, wenn die Datei existiert und vom aktuellen Benutzer beschreibbar ist."""
    path = conf_path()
    return (
        path.is_file()
        and os.access(path, os.W_OK)
        and os.access(path.parent, os.W_OK)
    )


def read_all() -> dict[tuple[str, str], str]:
    """Alle Werte als {(section, key): value}, beides kleingeschrieben."""
    values: dict[tuple[str, str], str] = {}
    try:
        text = conf_path().read_text(encoding="utf-8")
    except OSError:
        return values
    section = ""
    for line in text.splitlines():
        m = _SECTION_RE.match(line)
        if m:
            section = m.group(1).strip().lower()
            continue
        m = _KEY_RE.match(line)
        if m and section:
            values[(section, m.group(1).lower())] = m.group(2)
    return values


def get(section: str, key: str, default: str | None = None) -> str | None:
    return read_all().get((section.lower(), key.lower()), default)


def _apply(lines: list[str], section: str, key: str, value: str) -> list[str]:
    """Setzt einen Wert in den Zeilen; legt Schluessel/Abschnitt bei Bedarf an."""
    sec_l, key_l = section.lower(), key.lower()
    current = ""
    sec_start = -1   # Index der [Section]-Zeile
    last_key = -1    # letzte Schluesselzeile im Abschnitt
    for i, line in enumerate(lines):
        m = _SECTION_RE.match(line)
        if m:
            current = m.group(1).strip().lower()
            if current == sec_l:
                sec_start = i
            continue
        if current != sec_l:
            continue
        m = _KEY_RE.match(line)
        if m:
            last_key = i
            if m.group(1).lower() == key_l:
                lines[i] = f"{m.group(1)}={value}"
                return lines

    new_line = f"{canonical_key(section, key)}={value}"
    if last_key >= 0:
        lines.insert(last_key + 1, new_line)
    elif sec_start >= 0:
        lines.insert(sec_start + 1, new_line)
    else:
        if lines and lines[-1].strip():
            lines.append("")
        lines.extend([f"[{section}]", new_line])
    return lines


def set_values(items: list[tuple[str, str, str]]) -> bool:
    """Schreibt mehrere (section, key, value) in einem Rutsch, atomar.

    Gibt False zurueck, wenn die Datei fehlt oder nicht beschreibbar ist –
    dann gelten die Werte nur bis zum naechsten Neustart von x52d.
    """
    if not items:
        return True
    path = conf_path()
    if not is_ready():
        log.warning(
            "%s fehlt oder ist nicht beschreibbar – Einstellungen werden nicht "
            "dauerhaft gespeichert. Bitte 'sudo bash install.sh' ausführen.", path
        )
        return False
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        for section, key, value in items:
            lines = _apply(lines, section, key, str(value))
        fd, tmp = tempfile.mkstemp(prefix=".x52d.conf.", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write("\n".join(lines) + "\n")
            os.chmod(tmp, 0o644)
            os.replace(tmp, path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
    except OSError as exc:
        log.error("Konnte %s nicht schreiben: %s", path, exc)
        return False
    return True


def set_value(section: str, key: str, value: str) -> bool:
    return set_values([(section, key, value)])
