"""Bindings-Ordner von Elite Dangerous unter Linux finden.

E:D laeuft unter Proton/Wine – der Ordner liegt also immer in einem
Wine-Prefix unter
    drive_c/users/<user>/AppData/Local/Frontier Developments/
        Elite Dangerous/Options/Bindings

Gesucht wird in:
  - allen Steam-Bibliotheken (libraryfolders.vdf), App-ID 359320
  - Heroic (Epic), Faugus und weiteren ueblichen Prefix-Orten
"""

from __future__ import annotations

import re
from pathlib import Path

STEAM_APP_ID = "359320"

_BINDINGS_SUFFIX = Path(
    "AppData/Local/Frontier Developments/Elite Dangerous/Options/Bindings"
)

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


def _bindings_in_prefix(prefix: Path) -> list[Path]:
    # Manche Launcher legen den Prefix eine Ebene tiefer in "pfx" ab
    found: list[Path] = []
    for base in (prefix, prefix / "pfx"):
        users = base / "drive_c" / "users"
        if not users.is_dir():
            continue
        for user_dir in users.iterdir():
            candidate = user_dir / _BINDINGS_SUFFIX
            if candidate.is_dir():
                found.append(candidate)
    return found


def find_bindings_dirs() -> list[Path]:
    """Alle gefundenen Bindings-Ordner, zuerst Steam."""
    result: list[Path] = []
    seen: set[Path] = set()
    for prefix in _prefixes():
        try:
            if not prefix.is_dir():
                continue
        except OSError:
            continue
        for path in _bindings_in_prefix(prefix):
            key = path.resolve()
            if key not in seen:
                seen.add(key)
                result.append(path)
    return result


def is_bindings_dir(path: Path) -> bool:
    """Plausibilitaetspruefung fuer einen manuell gewaehlten Ordner."""
    return path.is_dir() and (
        path.name == "Bindings"
        or any(path.glob("*.binds"))
        or (path / "DeviceButtonMaps").is_dir()
    )
