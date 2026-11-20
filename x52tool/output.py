"""LED- und MFD-Ausgabe ueber x52ctl (Client des x52d-Daemons).

x52d laeuft als system service (installiert durch libx52) und haelt die
USB-Verbindung zum X52 Pro dauerhaft offen. x52ctl ist sein Client und
spricht mit ihm ueber den Socket /run/x52d.cmd.

Das Protokoll: x52ctl config set <Section> <Key> <Value>
Beispiel:       x52ctl config set Clock FormatPrimary 24hr

x52cli (Direktzugriff auf USB) wird nicht mehr verwendet – zwei Prozesse
gleichzeitig auf dem Geraet wuerden es durcheinanderbringen.

Wenn du spaeter auf die C-Bibliothek umsteigen willst, ist `Backend` die
einzige Klasse, die du ersetzen musst.
"""

from __future__ import annotations

import shlex
import shutil
import subprocess
from dataclasses import dataclass

from .config import BackendConfig
from . import i18n
from . import x52d_conf

# Reihenfolge wie auf dem Geraet, oben nach unten.
# Zweifarbige LEDs koennen rot/gelb/gruen, einfarbige nur an/aus.
TRICOLOR = ("off", "red", "amber", "green")
MONO = ("off", "on")

# (key, i18n-key, states) – Label wird zur Laufzeit per i18n.t() geholt.
_PRO_LEDS_DEF: list[tuple[str, str, tuple[str, ...]]] = [
    ("fire",     "output.led_fire",     MONO),
    ("a",        "output.led_a",        TRICOLOR),
    ("b",        "output.led_b",        TRICOLOR),
    ("d",        "output.led_d",        TRICOLOR),
    ("e",        "output.led_e",        TRICOLOR),
    ("t1",       "output.led_t1",       TRICOLOR),
    ("t2",       "output.led_t2",       TRICOLOR),
    ("t3",       "output.led_t3",       TRICOLOR),
    ("pov",      "output.led_pov",      TRICOLOR),
    ("clutch",   "output.led_clutch",   TRICOLOR),
    ("throttle", "output.led_throttle", MONO),
]


def PRO_LEDS() -> list[tuple[str, str, tuple[str, ...]]]:
    """Gibt die LED-Definitionen mit uebersetzten Labels zurueck."""
    return [(key, i18n.t(label_key), states) for key, label_key, states in _PRO_LEDS_DEF]

MFD_LINES = 3
MFD_WIDTH = 16

# Einziger unterstuetzter Client: x52ctl spricht mit dem laufenden x52d-Daemon.
# x52cli (Direktzugriff) wird nicht mehr verwendet.
BINARY_CANDIDATES = ("x52ctl",)


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

    def _persist(self, result: CommandResult, *items: tuple[str, str, str]) -> None:
        """Erfolgreich gesetzte Werte in die von x52d geladene Datei schreiben."""
        if result.ok:
            x52d_conf.set_values(list(items))

    def set_led(self, led: str, state: str, persist: bool = True) -> CommandResult:
        result = self._run(self._build(self.config.led, led=led, state=state))
        if persist:
            self._persist(result, ("LED", x52d_conf.canonical_key("LED", led), state))
        return result

    def set_mfd_line(self, line: int, text: str) -> CommandResult:
        """MFD-Text wird bewusst nicht gespeichert (nur Anzeige zur Laufzeit)."""
        return self._run(
            self._build(self.config.mfd, line=line, text=truncate_mfd(text))
        )

    def set_brightness(self, target: str, value: int, persist: bool = True) -> CommandResult:
        """target ist 'mfd' oder 'led'."""
        result = self._run(
            self._build(self.config.brightness, target=target, value=value)
        )
        if persist:
            self._persist(
                result,
                ("Brightness", x52d_conf.canonical_key("Brightness", target), str(value)),
            )
        return result

    def set_clutch(self, enabled: bool, persist: bool = True) -> CommandResult:
        """Kupplungsmodus (Clutch Mode) an- oder abschalten.

        Ist dieser Modus am Geraet aktiv, liest der Kernel-Treiber (usbhid)
        Taste 31 (Clutch, aufgedrucktes Symbol ein "i" im Kreis) nicht mehr
        als normalen Joystick-Button ein - sie bleibt dann unsichtbar,
        obwohl sie physisch gedrueckt wird.
        """
        value = "1" if enabled else "0"
        result = self._run(self._build(self.config.clutch, value=value))
        if persist:
            self._persist(result, ("Profiles", "ClutchEnabled", value))
        return result

    def set_config(
        self, section: str, key: str, value: str, persist: bool = True
    ) -> CommandResult:
        """Setzt einen x52d-Konfigurationswert live und (standardmaessig) dauerhaft."""
        result = self._run([self.config.binary, "config", "set", section, key, value])
        if persist:
            self._persist(result, (section, key, value))
        return result

    def set_clock(
        self,
        primary_local: bool,
        formats: tuple[bool, bool, bool],
        date_fmt: str,
        tz2: str,
        tz3: str,
    ) -> list[CommandResult]:
        """Alle Uhr-Einstellungen an x52d senden und dauerhaft speichern.

        formats: je Uhr True = 12hr, False = 24hr.
        tz2/tz3: Zeitzonen-Namen (z.B. 'UTC', 'Europe/Berlin').

        Hinweis: `x52ctl config save` wird nicht verwendet – es speichert in
        libx52 nichts. Persistiert wird ueber x52d_conf (siehe dort).
        """
        hr = ["12hr" if f else "24hr" for f in formats]
        wanted = [
            ("Clock", "PrimaryIsLocal", "yes" if primary_local else "no"),
            ("Clock", "FormatPrimary",   hr[0]),
            ("Clock", "FormatSecondary", hr[1]),
            ("Clock", "FormatTertiary",  hr[2]),
            ("Clock", "DateFormat", date_fmt),
            ("Clock", "Secondary", tz2),
            ("Clock", "Tertiary",  tz3),
        ]
        results = [self.set_config(*item, persist=False) for item in wanted]
        x52d_conf.set_values(
            [item for item, res in zip(wanted, results) if res.ok]
        )
        return results

    # -- Testabläufe -------------------------------------------------------

    def led_sweep(self) -> list[CommandResult]:
        """Jede LED einmal durch alle Zustaende. Findet tote LEDs (nicht gespeichert)."""
        results: list[CommandResult] = []
        for key, _label, states in PRO_LEDS():
            for state in states[1:]:
                results.append(self.set_led(key, state, persist=False))
            results.append(self.set_led(key, "off", persist=False))
        return results

    def all_leds(self, state: str, persist: bool = True) -> list[CommandResult]:
        results = []
        for key, _label, states in PRO_LEDS():
            results.append(
                self.set_led(key, state if state in states else states[-1], persist=persist)
            )
        return results

    def mfd_test(self) -> list[CommandResult]:
        pattern = ["0123456789ABCDEF", "x52tool MFD-Test", "################"]
        return [self.set_mfd_line(i, text) for i, text in enumerate(pattern)]
