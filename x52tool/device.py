"""Geraeteerkennung und Low-Level-Zugriff auf die evdev-Schnittstelle.

Diese Datei kennt kein Qt. Sie laesst sich unabhaengig von der Oberflaeche
testen und ist die Stelle, an der spaeter ein uinput-Pfad andocken wuerde.
"""

from __future__ import annotations

import fcntl
import os
import re
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
    ecodes.ABS_RX: "Rotary 1",
    ecodes.ABS_RY: "Rotary 2",
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
    """Kernel-Name der Taste, etwa BTN_TRIGGER."""
    raw = ecodes.BTN.get(code) or ecodes.KEY.get(code) or f"CODE {code}"
    if isinstance(raw, (list, tuple)):
        raw = raw[0]
    return str(raw)


# --------------------------------------------------------------------------
# Physische Tastenbeschriftung fuer den X52 Pro
#
# Von Oliver an seinem eigenen X52 Pro Taste fuer Taste im Live-Test
# durchgezaehlt und bestaetigt (nicht mehr nur aus Community-Quellen
# rekonstruiert). Zwei Stellen wichen von der ersten, aus Foren
# zusammengetragenen Fassung ab: Position 16-19 sind Maustasten/Mausrad
# (nicht ein Daumenrad am Ministick), und Position 39 ist "Rad rechts
# gedrueckt" statt einer eigenen MFD-Auswahltaste.
#
# 28/29/30 (Mode Red/Purple/Blue) sind ein 3-Stufen-Drehschalter, kein
# Momentkontakt: genau einer der drei Codes ist immer aktiv, das ist kein
# Fehler. Die Farbe entspricht dem am Geraet eingestellten MFD-Modus 1/2/3.
#
# Wie sich 32-39 (die beiden Raeder samt Start/Stop/Reset an der MFD-Basis)
# im Zusammenspiel mit mehrseitigen MFD-Anzeigen verhalten, ist noch offen -
# unter Windows waren sie fest mit Uhr/Stoppuhr verdrahtet und nicht frei
# nutzbar.
#
# Die Zuordnung haengt an den evdev-Codes (deterministisch), nicht an der
# Listenposition: die ersten 12 Tasten fallen auf die eigens fuer Joysticks
# vorgesehenen Kernel-Konstanten BTN_TRIGGER..BTN_BASE6. Fuer die
# restlichen 27 Tasten kennt der Kernel keine joystick-spezifischen Namen
# mehr, sie laufen ueber BTN_DEAD und die generischen BTN_TRIGGER_HAPPYn.
X52_PRO_BUTTON_LABELS: dict[int, str] = {
    ecodes.BTN_TRIGGER: "Trigger",
    ecodes.BTN_THUMB: "Fire",
    ecodes.BTN_THUMB2: "A",
    ecodes.BTN_TOP: "B",
    ecodes.BTN_TOP2: "C",
    ecodes.BTN_PINKIE: "Pinkie Trigger",
    ecodes.BTN_BASE: "D",
    ecodes.BTN_BASE2: "E",
    ecodes.BTN_BASE3: "T1",
    ecodes.BTN_BASE4: "T2",
    ecodes.BTN_BASE5: "T3",
    ecodes.BTN_BASE6: "T4",
    ecodes.BTN_DEAD: "T5",
    ecodes.BTN_TRIGGER_HAPPY1: "T6",
    ecodes.BTN_TRIGGER_HAPPY2: "Second Trigger",
    ecodes.BTN_TRIGGER_HAPPY3: "Mouse Button 1 (links)",
    ecodes.BTN_TRIGGER_HAPPY4: "Mouse Wheel hoch",
    ecodes.BTN_TRIGGER_HAPPY5: "Mouse Wheel runter",
    ecodes.BTN_TRIGGER_HAPPY6: "Mouse Button 2 (rechts)",
    ecodes.BTN_TRIGGER_HAPPY7: "POV2 hoch",
    ecodes.BTN_TRIGGER_HAPPY8: "POV2 rechts",
    ecodes.BTN_TRIGGER_HAPPY9: "POV2 runter",
    ecodes.BTN_TRIGGER_HAPPY10: "POV2 links",
    ecodes.BTN_TRIGGER_HAPPY11: "POV3 hoch",
    ecodes.BTN_TRIGGER_HAPPY12: "POV3 rechts",
    ecodes.BTN_TRIGGER_HAPPY13: "POV3 runter",
    ecodes.BTN_TRIGGER_HAPPY14: "POV3 links",
    ecodes.BTN_TRIGGER_HAPPY15: "Mode Red (MFD Mode 1)",
    ecodes.BTN_TRIGGER_HAPPY16: "Mode Purple (MFD Mode 2)",
    ecodes.BTN_TRIGGER_HAPPY17: "Mode Blue (MFD Mode 3)",
    ecodes.BTN_TRIGGER_HAPPY18: "i",
    ecodes.BTN_TRIGGER_HAPPY19: "Rad links gedrueckt",
    ecodes.BTN_TRIGGER_HAPPY20: "Start/Stop",
    ecodes.BTN_TRIGGER_HAPPY21: "Reset",
    ecodes.BTN_TRIGGER_HAPPY22: "Rad links hoch (PG Up)",
    ecodes.BTN_TRIGGER_HAPPY23: "Rad links runter (PG Down)",
    ecodes.BTN_TRIGGER_HAPPY24: "Rad rechts hoch",
    ecodes.BTN_TRIGGER_HAPPY25: "Rad rechts runter",
    ecodes.BTN_TRIGGER_HAPPY26: "Rad rechts gedrueckt",
}


def button_label(index: int, evdev_name: str, code: int = -1, is_pro: bool = False) -> str:
    """Anzeigetext fuer eine Taste.

    Ist das Geraet als X52 Pro erkannt und der Code in der rekonstruierten
    Tabelle bekannt, steht die physische Bezeichnung vorne (z.B. "Fire"),
    der Kernel-Name dahinter in Klammern - so bleibt die Gegenprobe im
    Live-Test jederzeit moeglich, ohne der Tabelle blind vertrauen zu
    muessen. Sonst wie bisher: Nummer und Kernel-Name.
    """
    physical = X52_PRO_BUTTON_LABELS.get(code) if is_pro else None
    if physical:
        return f"{index + 1}  {physical}"
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
                Button(
                    code=code,
                    label=button_label(index, name, code, self.is_pro),
                    index=index,
                    evdev_name=name,
                )
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
    errors: list[str] = field(default_factory=list)  # Pfad + Fehlertext, alles andere als Permission


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


# Woerter, die in praktisch jedem Geraetenamen vorkommen und daher beim
# Abgleich per Namen ignoriert werden - sonst wuerde z.B. "Flight Control
# System" zwei komplett verschiedene Sticks als "verwandt" ausgeben.
_NAME_STOPWORDS = {
    "flight", "control", "system", "professional", "hotas", "virtual",
    "mouse", "joystick", "controller", "pro", "device", "input",
}
_NAME_BRANDS = {"logitech", "saitek", "madcatz", "mad", "catz", "microsoft"}


def _name_tokens(name: str) -> set[str]:
    tokens = {t.lower() for t in re.findall(r"[A-Za-z0-9]+", name)}
    return {t for t in tokens if len(t) >= 2 and t not in _NAME_STOPWORDS and t not in _NAME_BRANDS}


def find_related_nodes(vendor: int, product: int, exclude_path: str, name: str = "") -> list[RelatedNode]:
    """Alle Event-Knoten desselben Sticks - auch virtuelle ohne USB-ID.

    Der X52 Pro legt fuer den Ministick zusaetzlich ein rein virtuelles
    Geraet an ("X52 virtual mouse", vom Kernel erzeugt), das Vendor=0000
    und Product=0000 meldet - ein Abgleich ueber die USB-ID findet es nie.
    Es gibt auch keinen gemeinsamen physischen Pfad (Phys ist bei virtuellen
    Geraeten leer). Einziger Anhaltspunkt ist der Name: geteilte, nicht
    generische Woerter wie "X52". Das ist eine Heuristik, kein Beweis -
    deshalb wird die Rolle entsprechend gekennzeichnet.
    """
    related: list[RelatedNode] = []
    own_tokens = _name_tokens(name) if name else set()
    for path in sorted(evdev.list_devices()):
        if path == exclude_path:
            continue
        try:
            dev = evdev.InputDevice(path)
        except OSError:
            continue
        try:
            same_usb_id = dev.info.vendor == vendor and dev.info.product == product
            shared_tokens = own_tokens & _name_tokens(dev.name) if own_tokens else set()
            is_virtual_match = (
                not same_usb_id
                and dev.info.vendor == 0
                and dev.info.product == 0
                and shared_tokens
            )
            if not (same_usb_id or is_virtual_match):
                continue
            caps = dev.capabilities(absinfo=False)
            role, ev_types = _classify_node(caps)
            if is_virtual_match:
                role += " - virtuell, per Name erkannt (keine USB-ID vorhanden)"
            related.append(
                RelatedNode(path=dev.path, name=dev.name, phys=dev.phys or "-", role=role, ev_types=ev_types)
            )
        finally:
            dev.close()
    return related



def _is_joystick(dev: evdev.InputDevice) -> bool:
    caps = dev.capabilities(absinfo=False)
    abs_codes = set(caps.get(ecodes.EV_ABS, []))
    key_codes = set(caps.get(ecodes.EV_KEY, []))
    has_stick = bool(abs_codes & {ecodes.ABS_X, ecodes.ABS_Y})
    has_buttons = any(ecodes.BTN_JOYSTICK <= c <= ecodes.BTN_GEAR_UP for c in key_codes)
    return has_stick and has_buttons


def scan(known_first: bool = True) -> ScanResult:
    """Sucht alle joystickartigen Eingabegeraete.

    Geraete ohne Leserecht landen in `denied`. Jeder andere Fehler beim
    Oeffnen (z.B. "Device or resource busy", was bei USB-Aussetzern oder
    einem zweiten Prozess auf demselben Knoten vorkommt) landet in `errors`
    statt lautlos zu verschwinden - das war vorher der Fall und hat einen
    echten Fehler wie ein leeres Ergebnis aussehen lassen.
    """
    result = ScanResult()
    for path in sorted(evdev.list_devices()):
        try:
            dev = evdev.InputDevice(path)
        except PermissionError:
            result.denied.append(path)
            continue
        except OSError as exc:
            result.errors.append(f"{path}: {exc}")
            continue
        try:
            if _is_joystick(dev):
                result.devices.append(X52Device(dev))
            else:
                dev.close()
        except OSError as exc:
            result.errors.append(f"{path}: {exc}")
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
