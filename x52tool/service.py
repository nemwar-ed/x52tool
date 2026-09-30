"""Steuerung des x52d systemd user service.

Alle Aufrufe gehen ueber `systemctl --user` und blockieren kurz (timeout
2 Sekunden). Das reicht fuer Status-Abfragen und Start/Stopp aus der GUI.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from enum import Enum, auto


SERVICE_NAME = "x52d.service"


class ServiceState(Enum):
    RUNNING  = auto()   # ActiveState=active, SubState=running
    STOPPED  = auto()   # inactive oder failed, aber erreichbar
    FAILED   = auto()   # ActiveState=failed
    UNKNOWN  = auto()   # systemctl nicht verfuegbar oder anderer Fehler


@dataclass
class ServiceStatus:
    state: ServiceState
    active_state: str = ""   # z.B. "active", "inactive", "failed"
    sub_state:    str = ""   # z.B. "running", "dead", "exited"
    description:  str = ""  # menschenlesbare Zusammenfassung

    @property
    def is_running(self) -> bool:
        return self.state is ServiceState.RUNNING


def _systemctl(*args: str, timeout: int = 2) -> tuple[int, str, str]:
    """Ruft systemctl --user auf und gibt (returncode, stdout, stderr) zurueck."""
    try:
        proc = subprocess.run(
            ["systemctl", "--user", *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except FileNotFoundError:
        return 127, "", "systemctl nicht gefunden"
    except subprocess.TimeoutExpired:
        return 124, "", "Zeitüberschreitung"
    except OSError as exc:
        return 1, "", str(exc)


def status() -> ServiceStatus:
    """Liest den aktuellen Zustand des x52d user service."""
    rc, out, err = _systemctl("show", SERVICE_NAME,
                               "--property=ActiveState,SubState")
    if rc == 127:
        return ServiceStatus(ServiceState.UNKNOWN, description="systemctl nicht gefunden")

    props: dict[str, str] = {}
    for line in out.splitlines():
        if "=" in line:
            k, _, v = line.partition("=")
            props[k.strip()] = v.strip()

    active  = props.get("ActiveState", "")
    sub     = props.get("SubState", "")

    if active == "active" and sub == "running":
        state = ServiceState.RUNNING
    elif active == "failed":
        state = ServiceState.FAILED
    else:
        state = ServiceState.STOPPED

    return ServiceStatus(state=state, active_state=active, sub_state=sub)


def start() -> tuple[bool, str]:
    """Startet den x52d user service. Gibt (erfolg, fehlermeldung) zurueck."""
    rc, _, err = _systemctl("start", SERVICE_NAME, timeout=5)
    return rc == 0, err.strip()


def stop() -> tuple[bool, str]:
    """Stoppt den x52d user service. Gibt (erfolg, fehlermeldung) zurueck."""
    rc, _, err = _systemctl("stop", SERVICE_NAME, timeout=5)
    return rc == 0, err.strip()


def enable() -> tuple[bool, str]:
    """Aktiviert den Service fuer den automatischen Start beim Login."""
    rc, _, err = _systemctl("enable", SERVICE_NAME)
    return rc == 0, err.strip()


def disable() -> tuple[bool, str]:
    """Deaktiviert den automatischen Start beim Login."""
    rc, _, err = _systemctl("disable", SERVICE_NAME)
    return rc == 0, err.strip()


def is_enabled() -> bool:
    """True wenn der Service fuer den automatischen Start aktiviert ist."""
    rc, out, _ = _systemctl("is-enabled", SERVICE_NAME)
    return out.strip() == "enabled"


# ---------------------------------------------------------------------------
# Timer (x52tool-clock.timer)
# ---------------------------------------------------------------------------

TIMER_NAME  = "x52tool-clock.timer"
APPLY_NAME  = "x52tool-apply.service"


def timer_status() -> ServiceState:
    """Zustand des Uhrzeit-Timers."""
    rc, out, _ = _systemctl("show", TIMER_NAME, "--property=ActiveState,SubState")
    if rc == 127:
        return ServiceState.UNKNOWN
    props = {}
    for line in out.splitlines():
        if "=" in line:
            k, _, v = line.partition("=")
            props[k.strip()] = v.strip()
    active = props.get("ActiveState", "")
    sub    = props.get("SubState", "")
    if active == "active" and sub == "waiting":
        return ServiceState.RUNNING
    if active == "failed":
        return ServiceState.FAILED
    return ServiceState.STOPPED


def start_all() -> tuple[bool, str]:
    """Startet x52d, den Apply-Service und den Clock-Timer."""
    errors: list[str] = []
    for unit in (SERVICE_NAME, APPLY_NAME, TIMER_NAME):
        rc, _, err = _systemctl("start", unit, timeout=5)
        if rc != 0:
            errors.append(f"{unit}: {err.strip()}")
    return not errors, "\n".join(errors)


def stop_all() -> tuple[bool, str]:
    """Stoppt Clock-Timer, Apply-Service und x52d."""
    errors: list[str] = []
    for unit in (TIMER_NAME, APPLY_NAME, SERVICE_NAME):
        rc, _, err = _systemctl("stop", unit, timeout=5)
        if rc != 0:
            errors.append(f"{unit}: {err.strip()}")
    return not errors, "\n".join(errors)


def enable_all() -> tuple[bool, str]:
    """Aktiviert alle drei Units fuer den automatischen Start."""
    errors: list[str] = []
    for unit in (SERVICE_NAME, APPLY_NAME, TIMER_NAME):
        rc, _, err = _systemctl("enable", unit)
        if rc != 0:
            errors.append(f"{unit}: {err.strip()}")
    return not errors, "\n".join(errors)


def disable_all() -> tuple[bool, str]:
    """Deaktiviert alle drei Units."""
    errors: list[str] = []
    for unit in (TIMER_NAME, APPLY_NAME, SERVICE_NAME):
        rc, _, err = _systemctl("disable", unit)
        if rc != 0:
            errors.append(f"{unit}: {err.strip()}")
    return not errors, "\n".join(errors)
