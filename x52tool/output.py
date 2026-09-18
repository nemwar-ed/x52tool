"""LED- und MFD-Ausgabe.

Die USB-Seite des X52 Pro ist durch libx52 bereits geloest. Dieses Modul
baut das Protokoll nicht nach, sondern ruft das vorhandene CLI auf. Ein
zweiter Prozess, der gleichzeitig auf MFD und LEDs schreibt, bringt das
Geraet durcheinander - laeuft der Daemon x52d, sollte der Aufruf ueber
dessen Client gehen statt direkt auf USB.

Wenn du spaeter auf die C-Bibliothek umsteigen willst, ist `Backend` die
einzige Klasse, die du ersetzen musst.
"""

from __future__ import annotations

import shlex
import shutil
import subprocess
from dataclasses import dataclass

from .config import BackendConfig

# Reihenfolge wie auf dem Geraet, oben nach unten.
# Zweifarbige LEDs koennen rot/gelb/gruen, einfarbige nur an/aus.
TRICOLOR = ("off", "red", "amber", "green")
MONO = ("off", "on")

PRO_LEDS: list[tuple[str, str, tuple[str, ...]]] = [
    ("fire", "Fire (Abdeckung)", MONO),
    ("a", "Taste A", TRICOLOR),
    ("b", "Taste B", TRICOLOR),
    ("d", "Taste D", TRICOLOR),
    ("e", "Taste E", TRICOLOR),
    ("t1", "Kippschalter T1/T2", TRICOLOR),
    ("t2", "Kippschalter T3/T4", TRICOLOR),
    ("t3", "Kippschalter T5/T6", TRICOLOR),
    ("pov", "POV-Hat 2", TRICOLOR),
    ("clutch", "Clutch (i-Taste)", TRICOLOR),
    ("throttle", "Schubhebel", MONO),
]

MFD_LINES = 3
MFD_WIDTH = 16

# Kandidaten in der Reihenfolge, in der gesucht wird. x52ctl spricht mit dem
# Daemon, x52cli geht direkt auf das Geraet.
BINARY_CANDIDATES = ("x52ctl", "x52cli")


@dataclass
class CommandResult:
    command: str
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    def summary(self) -> str:
        head = "ok " if self.ok else f"rc={self.returncode} "
        tail = (self.stderr or self.stdout).strip().splitlines()
        return head + self.command + (f"   {tail[0]}" if tail else "")


def detect_binary() -> str | None:
    for candidate in BINARY_CANDIDATES:
        found = shutil.which(candidate)
        if found:
            return found
    return None


def truncate_mfd(text: str) -> str:
    return text[:MFD_WIDTH]


class Backend:
    """Fuehrt die konfigurierten Kommandovorlagen aus."""

    def __init__(self, config: BackendConfig) -> None:
        self.config = config
        if not self.config.binary:
            self.config.binary = detect_binary() or ""

    @property
    def available(self) -> bool:
        return bool(self.config.binary)

    # -- intern ------------------------------------------------------------

    def _build(self, template: str, **values: object) -> list[str]:
        """Erst zerlegen, dann einsetzen.

        So bleibt MFD-Text mit Leerzeichen ein einzelnes Argument, statt in
        mehrere Tokens zu zerfallen.
        """
        values = {"bin": self.config.binary, **values}
        return [token.format(**values) for token in shlex.split(template)]

    def _run(self, argv: list[str]) -> CommandResult:
        printable = shlex.join(argv)
        try:
            proc = subprocess.run(argv, capture_output=True, text=True, timeout=5)
        except FileNotFoundError:
            return CommandResult(printable, 127, "", "Programm nicht gefunden")
        except subprocess.TimeoutExpired:
            return CommandResult(printable, 124, "", "Zeitueberschreitung")
        except OSError as exc:
            return CommandResult(printable, 1, "", str(exc))
        return CommandResult(printable, proc.returncode, proc.stdout, proc.stderr)

    def preview(self, template: str, **values: object) -> str:
        try:
            return shlex.join(self._build(template, **values))
        except (KeyError, ValueError) as exc:
            return f"Vorlage fehlerhaft: {exc}"

    # -- oeffentliche Befehle ---------------------------------------------

    def set_led(self, led: str, state: str) -> CommandResult:
        return self._run(self._build(self.config.led, led=led, state=state))

    def set_mfd_line(self, line: int, text: str) -> CommandResult:
        return self._run(
            self._build(self.config.mfd, line=line, text=truncate_mfd(text))
        )

    def set_brightness(self, target: str, value: int) -> CommandResult:
        """target ist 'mfd' oder 'led'."""
        return self._run(
            self._build(self.config.brightness, target=target, value=value)
        )

    # -- Testabläufe -------------------------------------------------------

    def led_sweep(self) -> list[CommandResult]:
        """Jede LED einmal durch alle Zustaende. Findet tote LEDs."""
        results: list[CommandResult] = []
        for key, _label, states in PRO_LEDS:
            for state in states[1:]:
                results.append(self.set_led(key, state))
            results.append(self.set_led(key, "off"))
        return results

    def all_leds(self, state: str) -> list[CommandResult]:
        results = []
        for key, _label, states in PRO_LEDS:
            results.append(self.set_led(key, state if state in states else states[-1]))
        return results

    def mfd_test(self) -> list[CommandResult]:
        pattern = ["0123456789ABCDEF", "x52tool MFD-Test", "################"]
        return [self.set_mfd_line(i, text) for i, text in enumerate(pattern)]
