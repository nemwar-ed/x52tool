"""Steuerung und Status des x52d system service.

x52d wird durch libx52 als system service installiert und laeuft als root.
Dieses Modul fragt seinen Status ab und kann ihn starten/stoppen –
ausschliesslich ueber 'systemctl' (kein --user, da system service).

Der Socket /run/x52d.cmd muss fuer den aktuellen User schreibbar sein.
Das erledigt /etc/tmpfiles.d/x52d-access.conf (einmalig per install.sh).
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from enum import Enum, auto

SERVICE_NAME = "x52d.service"


class ServiceState(Enum):
    RUNNING = auto()   # active + running
    STOPPED = auto()   # inactive oder dead
    FAILED  = auto()   # failed
    UNKNOWN = auto()   # systemctl nicht verfuegbar


@dataclass
class ServiceStatus:
    state: ServiceState
    active_state: str = ""
    sub_state:    str = ""

    @property
    def is_running(self) -> bool:
        return self.state is ServiceState.RUNNING


def _systemctl(*args: str, timeout: int = 3) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            ["systemctl", *args],
            capture_output=True, text=True, timeout=timeout,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except FileNotFoundError:
        return 127, "", "systemctl nicht gefunden"
    except subprocess.TimeoutExpired:
        return 124, "", "Zeitüberschreitung"
    except OSError as exc:
        return 1, "", str(exc)


def status() -> ServiceStatus:
    """Liest den aktuellen Zustand des x52d system service."""
    rc, out, _ = _systemctl(
        "show", SERVICE_NAME, "--property=ActiveState,SubState"
    )
    if rc == 127:
        return ServiceStatus(ServiceState.UNKNOWN)

    props: dict[str, str] = {}
    for line in out.splitlines():
        if "=" in line:
            k, _, v = line.partition("=")
            props[k.strip()] = v.strip()

    active = props.get("ActiveState", "")
    sub    = props.get("SubState", "")

    if active == "active" and sub == "running":
        state = ServiceState.RUNNING
    elif active == "failed":
        state = ServiceState.FAILED
    else:
        state = ServiceState.STOPPED

    return ServiceStatus(state=state, active_state=active, sub_state=sub)


def start() -> tuple[bool, str]:
    """Startet x52d (braucht sudo/polkit)."""
    rc, _, err = _systemctl("start", SERVICE_NAME, timeout=5)
    return rc == 0, err.strip()


def stop() -> tuple[bool, str]:
    """Stoppt x52d (braucht sudo/polkit)."""
    rc, _, err = _systemctl("stop", SERVICE_NAME, timeout=5)
    return rc == 0, err.strip()


def socket_writable() -> bool:
    """True wenn der Socket /run/x52d.cmd fuer den aktuellen User schreibbar ist."""
    import os
    return os.access("/run/x52d.cmd", os.W_OK)
