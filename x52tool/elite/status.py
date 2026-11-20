"""Schiffszustand aus Status.json und dem Journal.

Status.json schreibt Elite bei jeder Zustandsaenderung neu. Wichtig sind:

    Flags       Bitfeld (Schiff, SRV)
    Flags2      Bitfeld (Odyssey: zu Fuss, Temperatur, ...)
    GuiFocus    offenes Menue / Karte
    LegalState  z.B. "Speeding" (zu schnell in der Station)

Einige Zustaende stehen nur im Journal (Journal.*.log, eine JSON-Zeile pro
Ereignis), z.B. "Landeerlaubnis erteilt" oder "Unter Beschuss". Sie werden
hier als zusaetzliche Bedingungen gefuehrt.

Bedingungen werden als Text angesprochen (damit sie sich in config.json
speichern lassen):

    "LandingGearDown"       Flag aus Flags / Flags2
    "gui:GalaxyMap"         GuiFocus
    "legal:Speeding"        LegalState
    "event:DockingGranted"  aus dem Journal
    "!Supercruise"          Verneinung (vorangestelltes '!')
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# Bitnummern in "Flags"
FLAGS: dict[str, int] = {
    "Docked": 0,
    "Landed": 1,
    "LandingGearDown": 2,
    "ShieldsUp": 3,
    "Supercruise": 4,
    "FlightAssistOff": 5,
    "HardpointsDeployed": 6,
    "InWing": 7,
    "LightsOn": 8,
    "CargoScoopDeployed": 9,
    "SilentRunning": 10,
    "ScoopingFuel": 11,
    "SrvHandbrake": 12,
    "SrvTurretView": 13,
    "SrvTurretRetracted": 14,
    "SrvDriveAssist": 15,
    "FsdMassLocked": 16,
    "FsdCharging": 17,
    "FsdCooldown": 18,
    "LowFuel": 19,
    "OverHeating": 20,
    "HasLatLong": 21,
    "IsInDanger": 22,
    "BeingInterdicted": 23,
    "InMainShip": 24,
    "InFighter": 25,
    "InSRV": 26,
    "HudAnalysisMode": 27,
    "NightVision": 28,
    "AltitudeFromAverageRadius": 29,
    "FsdJump": 30,
    "SrvHighBeam": 31,
}

# Bitnummern in "Flags2" (Odyssey)
FLAGS2: dict[str, int] = {
    "OnFoot": 0,
    "InTaxi": 1,
    "InMulticrew": 2,
    "OnFootInStation": 3,
    "OnFootOnPlanet": 4,
    "AimDownSight": 5,
    "LowOxygen": 6,
    "LowHealth": 7,
    "Cold": 8,
    "Hot": 9,
    "VeryCold": 10,
    "VeryHot": 11,
    "GlideMode": 12,
    "OnFootInHangar": 13,
    "OnFootSocialSpace": 14,
    "OnFootExterior": 15,
    "BreathableAtmosphere": 16,
    "TelepresenceMulticrew": 17,
    "PhysicalMulticrew": 18,
    "FsdHyperdriveCharging": 19,
}

# Werte von "GuiFocus"
GUI_FOCUS: dict[str, int] = {
    "NoFocus": 0,
    "InternalPanel": 1,
    "ExternalPanel": 2,
    "CommsPanel": 3,
    "RolePanel": 4,
    "StationServices": 5,
    "GalaxyMap": 6,
    "SystemMap": 7,
    "Orrery": 8,
    "FSS": 9,
    "SAA": 10,
    "Codex": 11,
}

LEGAL_STATES = (
    "Clean", "IllegalCargo", "Speeding", "Wanted", "Hostile",
    "PassengerWanted", "Warrant",
)

# Journal-Ereignisse, die als Bedingung verfuegbar sind, und wann sie enden.
#   "until":  Ereignisse, die den Zustand beenden
#   "hold":   Sekunden, die der Zustand nach dem Ereignis gilt
JOURNAL_EVENTS: dict[str, dict] = {
    "DockingGranted": {
        "until": ("Docked", "DockingCancelled", "DockingTimeout", "Undocked", "Shutdown"),
    },
    "UnderAttack": {"hold": 10.0},
    "Interdicted": {"hold": 10.0},
    "HeatWarning": {"hold": 5.0},
    "HeatDamage": {"hold": 5.0},
    "HullDamage": {"hold": 5.0},
}
# "ShieldsDown" ist ein eigener Zustand aus ShieldState(ShieldsUp=false).
JOURNAL_CONDITIONS = (
    "DockingGranted", "UnderAttack", "Interdicted", "HeatWarning",
    "HeatDamage", "HullDamage", "ShieldsDown",
)


def all_conditions() -> list[str]:
    """Alle verfuegbaren Bedingungen (ohne Verneinung), fuer Auswahllisten."""
    return (
        list(FLAGS)
        + list(FLAGS2)
        + [f"gui:{name}" for name in GUI_FOCUS]
        + [f"legal:{name}" for name in LEGAL_STATES]
        + [f"event:{name}" for name in JOURNAL_CONDITIONS]
    )


def _parse_ts(text: str | None) -> float | None:
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        ).timestamp()
    except ValueError:
        return None


@dataclass
class GameState:
    """Aktueller Zustand: Status.json + Zustaende aus dem Journal."""

    flags: int = 0
    flags2: int = 0
    gui_focus: int = 0
    legal_state: str = "Clean"
    # Journal: Zustand -> Unix-Zeit, bis zu der er gilt (inf = bis Ende-Ereignis)
    journal_until: dict[str, float] = field(default_factory=dict)

    # -- Status.json -------------------------------------------------------

    def apply_status(self, data: dict) -> None:
        self.flags = int(data.get("Flags", 0) or 0)
        self.flags2 = int(data.get("Flags2", 0) or 0)
        self.gui_focus = int(data.get("GuiFocus", 0) or 0)
        self.legal_state = str(data.get("LegalState", "Clean") or "Clean")

    # -- Journal -----------------------------------------------------------

    def apply_event(self, event: dict, now: float | None = None) -> None:
        name = event.get("event")
        if not name:
            return
        ts = _parse_ts(event.get("timestamp"))
        now = time.time() if now is None else now
        ts = ts if ts is not None else now

        # Ereignisse, die einen Zustand beenden
        for cond, spec in JOURNAL_EVENTS.items():
            if name in spec.get("until", ()):
                self.journal_until.pop(cond, None)

        if name == "ShieldState":
            if event.get("ShieldsUp") is False:
                self.journal_until["ShieldsDown"] = float("inf")
            else:
                self.journal_until.pop("ShieldsDown", None)
            return

        spec = JOURNAL_EVENTS.get(name)
        if spec is None:
            return
        if "until" in spec:
            self.journal_until[name] = float("inf")
        else:
            self.journal_until[name] = ts + float(spec.get("hold", 0.0))

    def journal_active(self, cond: str, now: float | None = None) -> bool:
        until = self.journal_until.get(cond)
        if until is None:
            return False
        return (time.time() if now is None else now) < until

    def next_journal_expiry(self, now: float) -> float | None:
        """Naechster Zeitpunkt, zu dem ein zeitlich begrenzter Zustand endet."""
        times = [t for t in self.journal_until.values() if now < t < float("inf")]
        return min(times) if times else None

    # -- Bedingungen -------------------------------------------------------

    def check(self, condition: str, now: float | None = None) -> bool:
        """Prueft eine Bedingung; unbekannte Bedingungen sind immer falsch."""
        cond = condition.strip()
        if cond.startswith("!"):
            return not self.check(cond[1:], now)
        if cond.startswith("gui:"):
            wanted = GUI_FOCUS.get(cond[4:])
            return wanted is not None and self.gui_focus == wanted
        if cond.startswith("legal:"):
            return self.legal_state == cond[6:]
        if cond.startswith("event:"):
            return self.journal_active(cond[6:], now)
        if cond in FLAGS:
            return bool(self.flags >> FLAGS[cond] & 1)
        if cond in FLAGS2:
            return bool(self.flags2 >> FLAGS2[cond] & 1)
        return False

    def check_all(self, conditions: list[str], now: float | None = None) -> bool:
        return all(self.check(c, now) for c in conditions)


def read_status(path: Path) -> dict | None:
    """Status.json lesen; None, wenn sie fehlt oder gerade geschrieben wird."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    if not text.strip():
        return None
    try:
        data = json.loads(text)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


class JournalFollower:
    """Liest neue Zeilen aus der neuesten Journal-Datei (wie 'tail -f')."""

    def __init__(self, journal_dir: Path) -> None:
        self.journal_dir = journal_dir
        self.path: Path | None = None
        self._pos = 0
        self._partial = ""

    def _newest(self) -> Path | None:
        try:
            files = list(self.journal_dir.glob("Journal.*.log"))
        except OSError:
            return None
        if not files:
            return None
        # Dateiname enthaelt Datum/Uhrzeit -> lexikalisch sortierbar
        return max(files, key=lambda p: (p.name, p.stat().st_mtime))

    def poll(self) -> list[dict]:
        """Neue Ereignisse seit dem letzten Aufruf.

        Beim ersten Aufruf (und bei einer neuen Datei) wird die ganze Datei
        gelesen, damit z.B. eine bereits erteilte Landeerlaubnis bekannt ist.
        """
        newest = self._newest()
        if newest is None:
            return []
        if newest != self.path:
            self.path, self._pos, self._partial = newest, 0, ""
        try:
            size = self.path.stat().st_size
            if size < self._pos:  # Datei wurde ersetzt
                self._pos, self._partial = 0, ""
            if size == self._pos:
                return []
            with self.path.open("r", encoding="utf-8", errors="replace") as fh:
                fh.seek(self._pos)
                chunk = fh.read()
                self._pos = fh.tell()
        except OSError:
            return []
        text = self._partial + chunk
        lines = text.split("\n")
        self._partial = lines.pop()  # unvollstaendige letzte Zeile aufheben
        events: list[dict] = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if isinstance(event, dict):
                events.append(event)
        return events
