"""Steuerung des Hintergrunddienstes 'x52tool-ed' (systemd-User-Dienst).

Der Dienst laeuft als normaler Benutzer (kein root noetig) und startet mit
der Anmeldung. Die Unit-Datei wird von hier aus angelegt, damit sie auf den
Python-Interpreter und den Ort zeigt, aus dem x52tool gerade laeuft – egal
ob per pip installiert oder direkt aus dem Repository (run.sh).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

UNIT_NAME = "x52tool-ed.service"


def unit_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or "~/.config"
    return Path(base).expanduser() / "systemd" / "user" / UNIT_NAME


def state_path() -> Path:
    """Statusdatei des Dienstes (fuer die Live-Anzeige in der GUI)."""
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    base = Path(runtime) if runtime else Path("~/.cache").expanduser()
    return base / "x52tool" / "ed_leds.json"


def unit_text() -> str:
    package_root = Path(__file__).resolve().parents[2]
    return (
        "# Angelegt von x52tool – LEDs folgen dem Schiffszustand in Elite Dangerous\n"
        "[Unit]\n"
        "Description=x52tool: X52 Pro LEDs für Elite Dangerous\n"
        "After=graphical-session.target\n"
        "\n"
        "[Service]\n"
        "Type=simple\n"
        f"Environment=PYTHONPATH={package_root}\n"
        f"ExecStart={sys.executable} -m x52tool.elite.daemon\n"
        "Restart=on-failure\n"
        "RestartSec=5\n"
        "\n"
        "[Install]\n"
        "WantedBy=default.target\n"
    )


def _systemctl(*args: str, timeout: int = 10) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            ["systemctl", "--user", *args],
            capture_output=True, text=True, timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, str(exc)
    return proc.returncode, (proc.stderr or proc.stdout).strip()


def enable() -> tuple[bool, str]:
    """Unit schreiben (bzw. aktualisieren), aktivieren und starten."""
    path = unit_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        text = unit_text()
        if not path.exists() or path.read_text(encoding="utf-8") != text:
            path.write_text(text, encoding="utf-8")
    except OSError as exc:
        return False, str(exc)
    _systemctl("daemon-reload")
    rc, msg = _systemctl("enable", "--now", UNIT_NAME)
    if rc == 0:
        _systemctl("restart", UNIT_NAME)
    return rc == 0, msg


def disable() -> tuple[bool, str]:
    rc, msg = _systemctl("disable", "--now", UNIT_NAME)
    return rc == 0, msg


def is_active() -> bool:
    rc, _ = _systemctl("is-active", "--quiet", UNIT_NAME, timeout=3)
    return rc == 0


@dataclass
class DaemonState:
    alive: bool = False        # Statusdatei aktuell -> Dienst laeuft
    game_running: bool = False
    mode: str = ""
    binds_file: str = ""
    levels: dict | None = None


def read_state(max_age: float = 10.0) -> DaemonState:
    try:
        data = json.loads(state_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return DaemonState()
    if not isinstance(data, dict):
        return DaemonState()
    alive = time.time() - float(data.get("updated", 0)) < max_age
    if alive and data.get("pid"):
        alive = Path(f"/proc/{data['pid']}").exists()
    return DaemonState(
        alive=alive,
        game_running=bool(data.get("running")) and alive,
        mode=str(data.get("mode", "")),
        binds_file=str(data.get("binds_file", "")),
        levels=data.get("levels") if alive else None,
    )
