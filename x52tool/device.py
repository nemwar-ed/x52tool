"""Geraeteerkennung und Low-Level-Zugriff auf die evdev-Schnittstelle.

Diese Datei kennt kein Qt. Sie laesst sich unabhaengig von der Oberflaeche
testen und ist die Stelle, an der spaeter ein uinput-Pfad andocken wuerde.
"""

from __future__ import annotations

import fcntl
import os
import struct
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Iterator

import evdev
from evdev import ecodes

# --------------------------------------------------------------------------
# Bekannte USB-IDs. Saitek, MadCatz und Logitech haben alle unter 0x06a3
# ausgeliefert; die PID entscheidet ueber Pro / Nicht-Pro.
# --------------------------------------------------------------------------

KNOWN_DEVICES: dict[tuple[int, int], tuple[str, bool]] = {
    # (vendor, product): (Anzeigename, ist_pro)
    (0x06A3, 0x0255): ("Saitek X52 Flight Controller", False),
    (0x06A3, 0x075C): ("Saitek X52 Flight Control System", False),
    (0x06A3, 0x0762): ("Saitek X52 Pro Flight Control System", True),
}


# --------------------------------------------------------------------------
# struct input_absinfo { __s32 value, minimum, maximum, fuzz, flat, resolution; }
# --------------------------------------------------------------------------

_ABSINFO = struct.Struct("6i")

_IOC_WRITE = 1
_IOC_READ = 2
_IOC_TYPE_EVENT = ord("E")


def _ioc(direction: int, nr: int, size: int) -> int:
    """Baut eine ioctl-Nummer nach dem Linux-Schema (dir, size, type, nr)."""
    return (direction << 30) | (size << 16) | (_IOC_TYPE_EVENT << 8) | nr


def _eviocgabs(code: int) -> int:
    return _ioc(_IOC_READ, 0x40 + code, _ABSINFO.size)


def _eviocsabs(code: int) -> int:
    return _ioc(_IOC_WRITE, 0xC0 + code, _ABSINFO.size)


@dataclass
class AbsInfo:
    """Kalibrierdaten einer Achse, so wie der Kernel sie fuehrt."""

    value: int = 0
    minimum: int = 0
    maximum: int = 0
    fuzz: int = 0
    flat: int = 0
    resolution: int = 0

    @classmethod
    def unpack(cls, raw: bytes) -> "AbsInfo":
        return cls(*_ABSINFO.unpack(raw))

    def pack(self) -> bytes:
        return _ABSINFO.pack(
            self.value,
            self.minimum,
            self.maximum,
            self.fuzz,
            self.flat,
            self.resolution,
        )

    @property
    def span(self) -> int:
        return self.maximum - self.minimum

    @property
    def centre(self) -> int:
        return (self.maximum + self.minimum) // 2

    def as_percent(self, raw_units: int) -> float:
        """Rechnet Rohwerte in Prozent der Achsenspanne um."""
        return 0.0 if self.span == 0 else 100.0 * raw_units / self.span

    def copy(self) -> "AbsInfo":
        return AbsInfo(
            self.value, self.minimum, self.maximum, self.fuzz, self.flat, self.resolution
        )


def read_absinfo(fd: int, code: int) -> AbsInfo:
    raw = fcntl.ioctl(fd, _eviocgabs(code), bytes(_ABSINFO.size))
    return AbsInfo.unpack(raw)


def write_absinfo(fd: int, code: int, info: AbsInfo) -> None:
    fcntl.ioctl(fd, _eviocsabs(code), info.pack())


@contextmanager
def open_writable(path: str) -> Iterator[int]:
    """Oeffnet das Event-Device schreibbar. EVIOCSABS braucht O_RDWR.

    Faellt der Aufruf mit PermissionError durch, fehlt dem Benutzer der
    Schreibzugriff auf /dev/input/eventN. Siehe README, Abschnitt Rechte.
    """
    fd = os.open(path, os.O_RDWR)
    try:
        yield fd
    finally:
        os.close(fd)


# --------------------------------------------------------------------------
# Achsen und Tasten
# --------------------------------------------------------------------------

# Namen, die ein Pilot erkennt, statt der evdev-Konstanten.
#
# Ministick: Oliver hat das korrigiert - der kleine Maus-Stick am Schubhebel
# meldet sich nicht auf ABS_RX/ABS_RY, sondern auf ABS_MISC (0x28) und dem im
# Kernel unbenannten Code 0x29. Er ist rein digital (0 oder Vollausschlag in
# jede Richtung), keine echte Analogachse - deshalb auch in DIGITAL_AXES.
# Was ABS_RX/ABS_RY beim X52 Pro tatsaechlich sind, ist unklar; sie bleiben
# bewusst unbeschriftet und fallen auf den Kernel-Namen zurueck, statt etwas
# Falsches zu behaupten. Im Live-Test laesst sich das durch Bewegen klaeren.
ABS_MISC_Y = 0x29  # im Kernel kein eigener Name vergeben

AXIS_LABELS: dict[int, str] = {
    ecodes.ABS_X: "Stick X (Rollen)",
    ecodes.ABS_Y: "Stick Y (Nicken)",
    ecodes.ABS_RZ: "Stick Z (Gieren / Twist)",
    ecodes.ABS_Z: "Schubhebel",
    ecodes.ABS_MISC: "Ministick X (Maus-Stick, digital)",
    ABS_MISC_Y: "Ministick Y (Maus-Stick, digital)",
    ecodes.ABS_THROTTLE: "Schieberegler",
    ecodes.ABS_RUDDER: "Rudder",
    ecodes.ABS_HAT0X: "Hat 1 X",
    ecodes.ABS_HAT0Y: "Hat 1 Y",
}

# Achsen, bei denen eine Deadzone unsinnig ist: digitale Hats und der
# Ministick, der ohnehin nur zwischen 0 und Vollausschlag springt.
DIGITAL_AXES = {
    ecodes.ABS_HAT0X,
    ecodes.ABS_HAT0Y,
    ecodes.ABS_HAT1X,
    ecodes.ABS_HAT1Y,
    ecodes.ABS_HAT2X,
    ecodes.ABS_HAT2Y,
    ecodes.ABS_HAT3X,
    ecodes.ABS_HAT3Y,
    ecodes.ABS_MISC,
    ABS_MISC_Y,
}

# Hat-Achsenpaare (X-Code -> Y-Code), fuer die Kompass-Darstellung im
# Live-Test statt zweier Balken. Bislang nur Hat 1 - Oliver hat bestaetigt,
# dass POV-Hat 2 und 3 beim X52 Pro als Tasten kommen, nicht als Achsen.
HAT_AXIS_PAIRS: dict[int, int] = {
    ecodes.ABS_HAT0X: ecodes.ABS_HAT0Y,
    ecodes.ABS_HAT1X: ecodes.ABS_HAT1Y,
    ecodes.ABS_HAT2X: ecodes.ABS_HAT2Y,
    ecodes.ABS_HAT3X: ecodes.ABS_HAT3Y,
}


def axis_label(code: int) -> str:
    if code in AXIS_LABELS:
        return AXIS_LABELS[code]
    raw = ecodes.ABS.get(code, f"ABS {code}")
    if isinstance(raw, (list, tuple)):
        raw = raw[0]
    return str(raw)


def evdev_button_name(code: int) -> str:
    """Kernel-Name der Taste, etwa BTN_TRIGGER.

    Es gibt keine verlaessliche, offizielle Saitek-Nummerierung zum
    Nachschlagen - jede Quelle dazu sagt sinngemaess "zaehl selbst durch".
    Der Kernel-Name ist das einzige, was sich nicht erfindet, deshalb steht
    er direkt in der Kachel statt nur im Tooltip.
    """
    raw = ecodes.BTN.get(code) or ecodes.KEY.get(code) or f"CODE {code}"
    if isinstance(raw, (list, tuple)):
        raw = raw[0]
    return str(raw)


def button_label(index: int, evdev_name: str) -> str:
    """Anzeigetext: fortlaufende Nummer und Kernel-Name zusammen.

    Die Nummer ist nur die Reihenfolge, in der der Kernel die Codes meldet -
    keine Saitek-Tastennummer. Der Kernel-Name daneben ist das, was auch in
    evtest, jstest-gtk oder einer .binds-Datei auftaucht und sich damit
    tatsaechlich nachschlagen laesst.
    """
    return f"{index + 1}  {evdev_name}"


@dataclass
class Axis:
    code: int
    label: str
    info: AbsInfo
    baseline: AbsInfo  # Zustand beim Oeffnen, fuer "zuruecksetzen"

    @property
    def is_digital(self) -> bool:
        return self.code in DIGITAL_AXES or self.info.span <= 8


@dataclass
class Button:
    code: int
    label: str
    index: int
    evdev_name: str = ""


# --------------------------------------------------------------------------
# Geraet
# --------------------------------------------------------------------------


class X52Device:
    """Duenner Wrapper um evdev.InputDevice mit Kalibrierzugriff."""

    def __init__(self, dev: evdev.InputDevice) -> None:
        self.dev = dev
        self.axes: list[Axis] = []
        self.buttons: list[Button] = []
        self._set_nonblocking()
        self._load_capabilities()

    def _set_nonblocking(self) -> None:
        """QSocketNotifier braucht einen nicht blockierenden Deskriptor."""
        flags = fcntl.fcntl(self.dev.fd, fcntl.F_GETFL)
        fcntl.fcntl(self.dev.fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

    # -- Metadaten ---------------------------------------------------------

    @property
    def path(self) -> str:
        return self.dev.path

    @property
    def name(self) -> str:
        return self.dev.name

    @property
    def vendor(self) -> int:
        return self.dev.info.vendor

    @property
    def product(self) -> int:
        return self.dev.info.product

    @property
    def usb_id(self) -> str:
        return f"{self.vendor:04x}:{self.product:04x}"

    @property
    def known_name(self) -> str | None:
        entry = KNOWN_DEVICES.get((self.vendor, self.product))
        return entry[0] if entry else None

    @property
    def is_pro(self) -> bool:
        entry = KNOWN_DEVICES.get((self.vendor, self.product))
        return bool(entry and entry[1])

    def describe(self) -> list[tuple[str, str]]:
        return [
            ("Name", self.dev.name),
            ("Pfad", self.dev.path),
            ("USB-ID", self.usb_id),
            ("Erkannt als", self.known_name or "unbekanntes Eingabegeraet"),
            ("MFD / LEDs", "ja (Pro)" if self.is_pro else "nein"),
            ("Physischer Pfad", self.dev.phys or "-"),
            ("Seriennummer", self.dev.uniq or "-"),
            ("Version", f"0x{self.dev.info.version:04x}"),
            ("Achsen", str(len(self.axes))),
            ("Tasten", str(len(self.buttons))),
            ("Schreibrecht", "ja" if self.writable else "nein"),
        ]

    @property
    def writable(self) -> bool:
        return os.access(self.dev.path, os.W_OK)

    # -- Faehigkeiten ------------------------------------------------------

    def _load_capabilities(self) -> None:
        caps = self.dev.capabilities(absinfo=False)
        for code in sorted(caps.get(ecodes.EV_ABS, [])):
            info = read_absinfo(self.dev.fd, code)
            self.axes.append(
                Axis(code=code, label=axis_label(code), info=info, baseline=info.copy())
            )
        for index, code in enumerate(sorted(caps.get(ecodes.EV_KEY, []))):
            name = evdev_button_name(code)
            self.buttons.append(
                Button(code=code, label=button_label(index, name), index=index, evdev_name=name)
            )

    def axis(self, code: int) -> Axis | None:
        return next((a for a in self.axes if a.code == code), None)

    # -- Kalibrierung ------------------------------------------------------

    def refresh_absinfo(self) -> None:
        for ax in self.axes:
            ax.info = read_absinfo(self.dev.fd, ax.code)

    def apply_absinfo(self, changes: dict[int, AbsInfo]) -> None:
        """Schreibt Kalibrierdaten fuer mehrere Achsen in einem Rutsch."""
        with open_writable(self.dev.path) as fd:
            for code, info in changes.items():
                write_absinfo(fd, code, info)
        self.refresh_absinfo()

    def restore_baseline(self) -> None:
        self.apply_absinfo({ax.code: ax.baseline.copy() for ax in self.axes})

    # -- Lebenszyklus ------------------------------------------------------

    @property
    def fd(self) -> int:
        return self.dev.fd

    def read_pending(self) -> list[evdev.InputEvent]:
        """Liest alles, was gerade anliegt. Blockiert nicht."""
        try:
            return list(self.dev.read())
        except BlockingIOError:
            return []
        except OSError:
            return []

    def close(self) -> None:
        try:
            self.dev.close()
        except Exception:
            pass


# --------------------------------------------------------------------------
# Suche
# --------------------------------------------------------------------------


@dataclass
class ScanResult:
    devices: list[X52Device] = field(default_factory=list)
    denied: list[str] = field(default_factory=list)


@dataclass
class RelatedNode:
    """Ein weiterer Event-Knoten, den derselbe USB-Stick anmeldet.

    Der X52 Pro erzeugt beim Einstecken mehrere /dev/input/eventN. Einer
    traegt die Joystick-Achsen (der wird als X52Device geoeffnet), ein
    anderer meldet den Ministick als Maus-Emulation (EV_REL statt EV_ABS).
    Diese Klasse beschreibt einen Knoten, ohne ihn als Joystick zu behandeln.
    """

    path: str
    name: str
    phys: str
    role: str  # kurze Einordnung, z.B. "Maus-Emulation (Ministick)"
    ev_types: str  # z.B. "EV_REL, EV_KEY"


_EV_TYPE_NAMES = {
    ecodes.EV_KEY: "EV_KEY",
    ecodes.EV_ABS: "EV_ABS",
    ecodes.EV_REL: "EV_REL",
    ecodes.EV_MSC: "EV_MSC",
    ecodes.EV_SYN: "EV_SYN",
}


def _classify_node(caps: dict) -> tuple[str, str]:
    """Grobe Einordnung anhand der Capabilities, fuer Menschen lesbar."""
    types_present = [t for t in (ecodes.EV_ABS, ecodes.EV_REL, ecodes.EV_KEY) if t in caps]
    ev_types = ", ".join(_EV_TYPE_NAMES.get(t, str(t)) for t in sorted(caps.keys()))

    if ecodes.EV_REL in caps and ecodes.EV_ABS not in caps:
        return "Maus-Emulation (vermutlich Ministick)", ev_types
    if ecodes.EV_ABS in caps:
        abs_codes = set(caps.get(ecodes.EV_ABS, []))
        if abs_codes & {ecodes.ABS_X, ecodes.ABS_Y}:
            return "Joystick-Achsen (dieser Knoten wird verwendet)", ev_types
        return "Zusatzachsen ohne Haupt-Stick", ev_types
    if ecodes.EV_KEY in caps:
        return "Nur Tasten, keine Achsen", ev_types
    return "Unklare Rolle", ev_types


def find_related_nodes(vendor: int, product: int, exclude_path: str) -> list[RelatedNode]:
    """Alle Event-Knoten mit derselben USB-ID, ausser dem schon gewaehlten.

    Damit wird sichtbar, was scan() sonst stillschweigend wegfiltert - zum
    Beispiel der Maus-Emulations-Knoten des Ministicks.
    """
    related: list[RelatedNode] = []
    for path in sorted(evdev.list_devices()):
        if path == exclude_path:
            continue
        try:
            dev = evdev.InputDevice(path)
        except OSError:
            continue
        try:
            if dev.info.vendor == vendor and dev.info.product == product:
                caps = dev.capabilities(absinfo=False)
                role, ev_types = _classify_node(caps)
                related.append(
                    RelatedNode(path=dev.path, name=dev.name, phys=dev.phys or "-", role=role, ev_types=ev_types)
                )
        finally:
            dev.close()
    return related



    caps = dev.capabilities(absinfo=False)
    abs_codes = set(caps.get(ecodes.EV_ABS, []))
    key_codes = set(caps.get(ecodes.EV_KEY, []))
    has_stick = bool(abs_codes & {ecodes.ABS_X, ecodes.ABS_Y})
    has_buttons = any(ecodes.BTN_JOYSTICK <= c <= ecodes.BTN_GEAR_UP for c in key_codes)
    return has_stick and has_buttons


def scan(known_first: bool = True) -> ScanResult:
    """Sucht alle joystickartigen Eingabegeraete.

    Geraete ohne Leserecht landen in `denied`, damit die Oberflaeche eine
    brauchbare Meldung statt einer leeren Liste zeigen kann.
    """
    result = ScanResult()
    for path in sorted(evdev.list_devices()):
        try:
            dev = evdev.InputDevice(path)
        except PermissionError:
            result.denied.append(path)
            continue
        except OSError:
            continue
        try:
            if _is_joystick(dev):
                result.devices.append(X52Device(dev))
            else:
                dev.close()
        except OSError:
            dev.close()

    if known_first:
        result.devices.sort(key=lambda d: (d.known_name is None, d.name))
    return result


def find_first_x52() -> X52Device | None:
    for dev in scan().devices:
        if dev.known_name:
            return dev
    return None


# --------------------------------------------------------------------------
# Live-Zustand
# --------------------------------------------------------------------------


class DeviceState:
    """Haelt den aktuellen Achsen- und Tastenzustand.

    Bewusst vom Event-Strom getrennt: evdev sendet nur bei Aenderung, die
    Oberflaeche und die Messung wollen aber jederzeit den Ist-Wert.
    """

    def __init__(self, device: X52Device) -> None:
        self.axes: dict[int, int] = {ax.code: ax.info.value for ax in device.axes}
        self.buttons: dict[int, bool] = {btn.code: False for btn in device.buttons}
        self.events_seen = 0

    def apply(self, event: evdev.InputEvent) -> None:
        if event.type == ecodes.EV_ABS:
            if event.code in self.axes:
                self.axes[event.code] = event.value
                self.events_seen += 1
        elif event.type == ecodes.EV_KEY:
            if event.code in self.buttons:
                self.buttons[event.code] = event.value != 0
                self.events_seen += 1

    def apply_all(self, events) -> None:
        for event in events:
            self.apply(event)
