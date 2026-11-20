"""Aktive Tastenbelegung von Elite Dangerous lesen (.binds).

Elite merkt sich in ``StartPreset[.N].start`` je Bereich (eine Zeile pro
Bereich) den Namen des aktiven Presets, z.B. "Custom". Eigene Presets liegen
als ``<Name>.<Version>.binds`` im Bindings-Ordner (z.B. Custom.4.2.binds).
Vordefinierte Presets (z.B. "SaitekX52Pro") liegen im Spielverzeichnis und
werden hier (noch) nicht gelesen.

Aufbau einer .binds (XML)::

    <Root PresetName="Custom" ...>
      <LandingGearToggle>
        <Primary Device="SaitekX52Pro" Key="Joy_9" />
        <Secondary Device="Keyboard" Key="Key_L" />
      </LandingGearToggle>
      <ThrottleAxis>
        <Binding Device="SaitekX52Pro" Key="Joy_ZAxis" />
      </ThrottleAxis>
    </Root>

Die Zuordnung Joy-Nummer -> LED entspricht dem aufgedruckten Layout
(identisch mit EDXLC).
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

# So nennt Elite den X52 Pro in den .binds; ohne Eintrag in seiner
# Geraeteliste wuerde es VID+PID verwenden.
X52_DEVICES = frozenset({"SaitekX52Pro", "06A30762"})

# Joy-Taste -> LED-Schluessel (wie in output.PRO_LEDS / x52ctl)
JOY_TO_LED: dict[str, str] = {
    "Joy_2": "fire",
    "Joy_3": "a",
    "Joy_4": "b",
    "Joy_7": "d",
    "Joy_8": "e",
    "Joy_9": "t1", "Joy_10": "t1",
    "Joy_11": "t2", "Joy_12": "t2",
    "Joy_13": "t3", "Joy_14": "t3",
    "Joy_20": "pov", "Joy_21": "pov", "Joy_22": "pov", "Joy_23": "pov",
    "Joy_31": "clutch",
    "Joy_ZAxis": "throttle",
}

# Reihenfolge wie auf dem Geraet, fuer Anzeigen
LED_ORDER = ("fire", "a", "b", "d", "e", "t1", "t2", "t3", "pov", "clutch", "throttle")

# Tasten je LED, fuer Anzeigen (Beschriftung wie aufgedruckt)
LED_BUTTONS: dict[str, str] = {
    "fire": "Fire",
    "a": "Fire A",
    "b": "Fire B",
    "d": "Fire D",
    "e": "Fire E",
    "t1": "T1, T2",
    "t2": "T3, T4",
    "t3": "T5, T6",
    "pov": "POV 2",
    "clutch": "Clutch (i)",
    "throttle": "Schubhebel / Throttle",
}

_VERSION_RE = re.compile(r"\.(\d+(?:\.\d+)*)\.binds$")


@dataclass
class Bindings:
    """Ergebnis des Einlesens: welche Aktion liegt auf welcher X52-Taste."""

    path: Path | None = None
    # Aktion -> Joy-Tasten am X52 (z.B. {"LandingGearToggle": ["Joy_9"]})
    actions: dict[str, list[str]] = field(default_factory=dict)

    def leds_for_action(self, action: str) -> set[str]:
        return {JOY_TO_LED[k] for k in self.actions.get(action, ()) if k in JOY_TO_LED}

    def actions_for_led(self, led: str) -> list[str]:
        return sorted(
            action for action, keys in self.actions.items()
            if any(JOY_TO_LED.get(k) == led for k in keys)
        )


def _version_key(path: Path) -> tuple[int, ...]:
    m = _VERSION_RE.search(path.name)
    if not m:
        return ()
    return tuple(int(part) for part in m.group(1).split("."))


def _start_files(bindings_dir: Path) -> list[Path]:
    """StartPreset*.start, neueste Version zuerst."""
    files = list(bindings_dir.glob("StartPreset*.start"))

    def key(p: Path) -> tuple[int, ...]:
        nums = re.findall(r"\d+", p.stem)
        return tuple(int(n) for n in nums)

    return sorted(files, key=key, reverse=True)


def preset_names(bindings_dir: Path) -> list[str]:
    """Namen der aktiven Presets (eine Zeile je Bereich), ohne Duplikate."""
    for start in _start_files(bindings_dir):
        try:
            lines = start.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        names: list[str] = []
        for line in lines:
            name = line.strip()
            if name and name not in names:
                names.append(name)
        if names:
            return names
    return []


def preset_file(bindings_dir: Path, preset: str) -> Path | None:
    """Neueste <preset>.<version>.binds im Bindings-Ordner (keine Backups)."""
    candidates = [
        p for p in bindings_dir.glob(f"{glob_escape(preset)}.*.binds")
        if p.is_file() and _VERSION_RE.search(p.name)
    ]
    if not candidates:
        plain = bindings_dir / f"{preset}.binds"
        return plain if plain.is_file() else None
    return max(candidates, key=lambda p: (_version_key(p), p.stat().st_mtime))


def glob_escape(text: str) -> str:
    return re.sub(r"([*?\[])", r"[\1]", text)


def active_binds_file(bindings_dir: Path) -> Path | None:
    """Die aktive .binds-Datei: erstes Preset aus StartPreset, das als Datei
    im Bindings-Ordner liegt. Ohne StartPreset: neueste .binds."""
    for name in preset_names(bindings_dir):
        found = preset_file(bindings_dir, name)
        if found:
            return found
    candidates = [p for p in bindings_dir.glob("*.binds") if p.is_file()]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def parse(path: Path) -> Bindings:
    """Liest eine .binds-Datei und sammelt alle Belegungen auf dem X52 Pro."""
    result = Bindings(path=path)
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError):
        return result
    for action in root:
        keys: list[str] = []
        for slot in action:
            if slot.tag not in ("Primary", "Secondary", "Binding"):
                continue
            if slot.get("Device") in X52_DEVICES:
                key = slot.get("Key") or ""
                if key and key not in keys:
                    keys.append(key)
        if keys:
            result.actions[action.tag] = keys
    return result


def load(bindings_dir: Path | None) -> Bindings:
    """Aktive Belegung aus einem Bindings-Ordner; leer, wenn nichts gefunden."""
    if bindings_dir is None or not bindings_dir.is_dir():
        return Bindings()
    path = active_binds_file(bindings_dir)
    return parse(path) if path else Bindings()
