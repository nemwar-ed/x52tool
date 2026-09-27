"""Zentrales Logging für x52tool.

Zwei Dateien:
  x52tool.log     – läuft immer, RotatingFileHandler (2 × 512 KB)
  x52tool-diag.log – wird nur auf Anforderung erzeugt (einmalig überschrieben)

Verwendung:
    from .logger import get_logger
    log = get_logger()
    log.info("...")
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import platform
import subprocess
import sys
from pathlib import Path


def _log_dir() -> Path:
    base = os.environ.get("XDG_DATA_HOME") or "~/.local/share"
    return Path(base).expanduser() / "x52tool"


def log_path() -> Path:
    return _log_dir() / "x52tool.log"


def diag_log_path() -> Path:
    return _log_dir() / "x52tool-diag.log"


def _setup() -> None:
    """Logging einmalig initialisieren (wird von init() aufgerufen)."""
    log_dir = _log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger("x52tool")
    if root.handlers:
        return  # bereits initialisiert

    root.setLevel(logging.DEBUG)

    handler = logging.handlers.RotatingFileHandler(
        log_path(),
        maxBytes=512 * 1024,
        backupCount=1,
        encoding="utf-8",
    )
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    root.addHandler(handler)


def init(version: str = "?") -> None:
    """Logging initialisieren und Programmstart loggen."""
    _setup()
    log = get_logger("startup")
    log.info(
        "x52tool %s gestartet – Python %s – %s %s",
        version,
        platform.python_version(),
        platform.system(),
        platform.release(),
    )


def get_logger(name: str = "x52tool") -> logging.Logger:
    """Gibt einen Logger zurück (Namespace: x52tool.<name>)."""
    if name == "x52tool":
        return logging.getLogger("x52tool")
    return logging.getLogger(f"x52tool.{name}")


# ---------------------------------------------------------------------------
# Diagnose-Log
# ---------------------------------------------------------------------------

def write_diag_log(settings=None) -> Path:
    """Erzeugt x52tool-diag.log und gibt den Pfad zurück."""
    import datetime

    from .device import scan

    lines: list[str] = []

    lines.append("=" * 60)
    lines.append(f"x52tool Diagnose-Log")
    lines.append(f"Erstellt: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("=" * 60)
    lines.append("")

    # Systeminfo
    lines.append("## System")
    lines.append(f"Python:   {platform.python_version()}")
    lines.append(f"OS:       {platform.system()} {platform.release()}")
    lines.append(f"Machine:  {platform.machine()}")
    try:
        uname = subprocess.check_output(["uname", "-a"], text=True).strip()
        lines.append(f"uname:    {uname}")
    except Exception:
        pass

    # x52cli / x52ctl Version
    lines.append("")
    lines.append("## libx52")
    for binary in ("x52cli", "x52ctl"):
        try:
            out = subprocess.check_output(
                [binary, "--version"], text=True, stderr=subprocess.STDOUT
            ).strip()
            lines.append(f"{binary}: {out}")
        except FileNotFoundError:
            lines.append(f"{binary}: nicht gefunden")
        except subprocess.CalledProcessError as exc:
            lines.append(f"{binary}: {exc.output.strip()}")

    # Geräteerkennung
    lines.append("")
    lines.append("## Geräte")
    try:
        result = scan()
        if result.devices:
            for dev in result.devices:
                lines.append(f"  {dev.path}  USB-ID: {dev.usb_id}  Name: {dev.name}")
                for axis in dev.axes:
                    info = axis.info
                    lines.append(
                        f"    ABS 0x{axis.code:02x}  {axis.label:<24} "
                        f"min={info.minimum} max={info.maximum} "
                        f"fuzz={info.fuzz} flat={info.flat}"
                    )
                dev.close()
        else:
            lines.append("  Kein Gerät gefunden.")
        for path in result.denied:
            lines.append(f"  ! {path}  kein Leserecht")
        for msg in result.errors:
            lines.append(f"  ! {msg}")
    except Exception as exc:
        lines.append(f"  Fehler bei Geräteerkennung: {exc}")

    # Kalibrierungsprofile aus Settings
    lines.append("")
    lines.append("## Gespeicherte Kalibrierungsprofile")
    if settings is not None:
        profiles = getattr(settings, "profiles", {})
        if profiles:
            for usb_id, axes in profiles.items():
                lines.append(f"  USB-ID {usb_id}:")
                for code, vals in axes.items():
                    lines.append(f"    ABS 0x{int(code):02x}: {vals}")
        else:
            lines.append("  Keine Profile gespeichert.")
    else:
        lines.append("  (Settings nicht übergeben)")

    lines.append("")
    lines.append("=" * 60)

    path = diag_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
