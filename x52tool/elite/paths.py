"""Ordner von Elite Dangerous unter Linux finden.

E:D laeuft unter Proton/Wine – die Ordner liegen also immer in einem
Wine-Prefix unter drive_c/users/<user>/:

    AppData/Local/Frontier Developments/Elite Dangerous/Options/Bindings
        -> .binds-Dateien, DeviceButtonMaps
    Saved Games/Frontier Developments/Elite Dangerous
        -> Status.json (Schiffszustand), Journal.*.log, NavRoute.json, ...

Beide liegen im selben Prefix. Gesucht wird deshalb einmal nach
"Installationen" (Benutzerordner im Prefix), daraus werden beide Pfade
abgeleitet. Bei mehreren Treffern steht die zuletzt gespielte Installation
(neueste Status.json bzw. neuestes Journal) vorne.

Gesucht wird in:
  - allen Steam-Bibliotheken (libraryfolders.vdf), App-ID 359320
  - Heroic (Epic), Faugus und weiteren ueblichen Prefix-Orten
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

STEAM_APP_ID = "359320"

_BINDINGS_SUFFIX = Path(
    "AppData/Local/Frontier Developments/Elite Dangerous/Options/Bindings"
)

_JOURNAL_SUFFIX = Path("Saved Games/Frontier Developments/Elite Dangerous")
_ED_SUBPATH = Path("Frontier Developments/Elite Dangerous")

STATUS_FILE = "Status.json"

_STEAM_ROOTS = (
    "~/.steam/steam",
    "~/.local/share/Steam",
    "~/.var/app/com.valvesoftware.Steam/.local/share/Steam",  # Flatpak
)

# Orte, unter denen Wine-Prefixe anderer Launcher liegen koennen.
# Jeder Eintrag ist ein Glob-Muster fuer das Prefix-Verzeichnis selbst.
_PREFIX_GLOBS = (
    "~/Games/Heroic/Prefixes/*",
    "~/Games/Heroic/Prefixes/*/*",
    "~/.config/heroic/Prefixes/*",
    "~/Games/*",
    "~/Faugus/*",
    "~/.local/share/faugus-launcher/prefixes/*",
    "~/.config/faugus-launcher/prefixes/*",
    "~/.local/share/lutris/prefixes/*",
    "~/.wine",
)


def _steam_libraries() -> list[Path]:
    libs: list[Path] = []
    for root in _STEAM_ROOTS:
        root_path = Path(root).expanduser()
        vdf = root_path / "steamapps" / "libraryfolders.vdf"
        if root_path.is_dir():
            libs.append(root_path)
        try:
            text = vdf.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for match in re.finditer(r'"path"\s+"([^"]+)"', text):
            libs.append(Path(match.group(1).replace("\\\\", "\\")))
    # Duplikate (Symlinks) entfernen, Reihenfolge erhalten
    seen: set[Path] = set()
    unique: list[Path] = []
    for lib in libs:
        try:
            key = lib.resolve()
        except OSError:
            key = lib
        if key not in seen:
            seen.add(key)
            unique.append(lib)
    return unique


def _prefixes() -> list[Path]:
    prefixes = [
        lib / "steamapps" / "compatdata" / STEAM_APP_ID / "pfx"
        for lib in _steam_libraries()
    ]
    home = Path.home()
    for pattern in _PREFIX_GLOBS:
        expanded = Path(pattern).expanduser()
        try:
            rel = expanded.relative_to(home)
        except ValueError:
            continue
        prefixes.extend(home.glob(str(rel)) if "*" in pattern else [expanded])
    return prefixes


@dataclass
class EdInstall:
    """Eine gefundene E:D-Installation (ein Benutzerordner in einem Prefix)."""

    user_dir: Path
    bindings: Path | None
    journal: Path | None
    last_activity: float  # Unix-Zeit der letzten Aktivitaet, 0 = nie gespielt


def is_journal_dir(path: Path) -> bool:
    """True, wenn der Ordner Status.json oder Journal-Dateien enthaelt."""
    try:
        if not path.is_dir():
            return False
        if (path / STATUS_FILE).is_file():
            return True
        return any(path.glob("Journal.*.log"))
    except OSError:
        return False


def last_activity(journal_dir: Path) -> float:
    """Neueste Aenderungszeit von Status.json und den Journal-Dateien."""
    newest = 0.0
    try:
        with os.scandir(journal_dir) as entries:
            for entry in entries:
                name = entry.name
                if name == STATUS_FILE or (
                    name.startswith("Journal.") and name.endswith(".log")
                ):
                    try:
                        newest = max(newest, entry.stat().st_mtime)
                    except OSError:
                        pass
    except OSError:
        pass
    return newest


def status_age(journal_dir: Path, now: float | None = None) -> float | None:
    """Sekunden seit der letzten Aenderung von Status.json, None wenn sie fehlt."""
    try:
        mtime = (journal_dir / STATUS_FILE).stat().st_mtime
    except OSError:
        return None
    return max(0.0, (now if now is not None else time.time()) - mtime)


def _journal_in_user_dir(user_dir: Path) -> Path | None:
    """Journal-Ordner im Benutzerordner suchen.

    Normalerweise 'Saved Games/...'; falls ein Prefix den Ordner anders
    benennt (z.B. lokalisiert), werden auch alle anderen Unterordner geprueft.
    """
    default = user_dir / _JOURNAL_SUFFIX
    if is_journal_dir(default):
        return default
    try:
        children = [c for c in user_dir.iterdir() if c.is_dir()]
    except OSError:
        return None
    for child in children:
        candidate = child / _ED_SUBPATH
        if is_journal_dir(candidate):
            return candidate
    return None


def find_installs() -> list[EdInstall]:
    """Alle E:D-Installationen, die zuletzt gespielte zuerst."""
    result: list[EdInstall] = []
    seen: set[Path] = set()
    for prefix in _prefixes():
        # Manche Launcher legen den Prefix eine Ebene tiefer in "pfx" ab
        for base in (prefix, prefix / "pfx"):
            users = base / "drive_c" / "users"
            try:
                if not users.is_dir():
                    continue
                user_dirs = [u for u in users.iterdir() if u.is_dir()]
            except OSError:
                continue
            for user_dir in user_dirs:
                try:
                    key = user_dir.resolve()
                    if key in seen:
                        continue
                    bindings = user_dir / _BINDINGS_SUFFIX
                    bindings_ok = bindings.is_dir()
                    journal = _journal_in_user_dir(user_dir)
                except OSError:
                    continue
                if not bindings_ok and journal is None:
                    continue
                seen.add(key)
                result.append(EdInstall(
                    user_dir=user_dir,
                    bindings=bindings if bindings_ok else None,
                    journal=journal,
                    last_activity=last_activity(journal) if journal else 0.0,
                ))
    # stabil sortieren: zuletzt gespielt zuerst, sonst Suchreihenfolge (Steam vorn)
    result.sort(key=lambda inst: -inst.last_activity)
    return result


def find_bindings_dirs() -> list[Path]:
    """Alle gefundenen Bindings-Ordner, zuletzt gespielte Installation zuerst."""
    return [inst.bindings for inst in find_installs() if inst.bindings]


def find_journal_dirs() -> list[Path]:
    """Alle gefundenen Journal-Ordner, zuletzt gespielte Installation zuerst."""
    return [inst.journal for inst in find_installs() if inst.journal]


def is_bindings_dir(path: Path) -> bool:
    """Plausibilitaetspruefung fuer einen manuell gewaehlten Ordner."""
    return path.is_dir() and (
        path.name == "Bindings"
        or any(path.glob("*.binds"))
        or (path / "DeviceButtonMaps").is_dir()
    )
