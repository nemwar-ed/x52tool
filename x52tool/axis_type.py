"""Klassifikation der X52-Pro-Achsen nach mechanischem Verhalten.

SPRING_CENTER     Feder zentriert automatisch (Stick X/Y, Stick Z/Twist).
                  → flat (Deadzone) um gemessenen Mittelpunkt sinnvoll.

MECHANICAL_CENTER Mechanisch spürbare Rastmitte, keine Feder (Rotary 1+2).
                  → flat nur nach Peak-Kalibrierung sinnvoll.
                  → fuzz hilft gegen Grundrauschen unabhängig von Position.

FREE_SLIDER       Kein Mittenkonzept (Schubhebel, Schieberegler).
                  → kein flat sinnvoll; Peak-Messung prüft Bereichsabdeckung.
"""

from __future__ import annotations

from enum import Enum, auto

from evdev import ecodes


class AxisKind(Enum):
    SPRING_CENTER     = auto()
    MECHANICAL_CENTER = auto()
    FREE_SLIDER       = auto()


_KIND: dict[int, AxisKind] = {
    ecodes.ABS_X:        AxisKind.SPRING_CENTER,      # Stick links/rechts
    ecodes.ABS_Y:        AxisKind.SPRING_CENTER,      # Stick vor/zurück
    ecodes.ABS_RZ:       AxisKind.SPRING_CENTER,      # Stick Z (Gieren / Twist)
    ecodes.ABS_RX:       AxisKind.MECHANICAL_CENTER,  # Rotary 1
    ecodes.ABS_RY:       AxisKind.MECHANICAL_CENTER,  # Rotary 2
    ecodes.ABS_Z:        AxisKind.FREE_SLIDER,        # Schubhebel
    ecodes.ABS_THROTTLE: AxisKind.FREE_SLIDER,        # Schieberegler
    # ABS_RUDDER nicht eingetragen – vom Gerät nicht gemeldet (Bitmaske bestätigt)
}


def axis_kind(code: int) -> AxisKind:
    """AxisKind für einen evdev-ABS-Code. Fallback: FREE_SLIDER."""
    return _KIND.get(code, AxisKind.FREE_SLIDER)


def has_center(code: int) -> bool:
    """True wenn die Achse einen definierten Mittelpunkt hat (flat sinnvoll)."""
    return axis_kind(code) in (AxisKind.SPRING_CENTER, AxisKind.MECHANICAL_CENTER)


def has_spring(code: int) -> bool:
    """True wenn die Achse federzentriert ist."""
    return axis_kind(code) is AxisKind.SPRING_CENTER


# ---------------------------------------------------------------------------
# Hardware-Defaults des X52 Pro (ermittelt per Bitmasken-Analyse)
# Reihenfolge: (value, minimum, maximum, fuzz, flat, resolution)
# ---------------------------------------------------------------------------

_HW_DEFAULTS: dict[int, tuple[int, int, int, int, int, int]] = {
    ecodes.ABS_X:        (0,   0, 1023, 0, 0, 0),  # Stick X
    ecodes.ABS_Y:        (0,   0, 1023, 0, 0, 0),  # Stick Y
    ecodes.ABS_RZ:       (0,   0, 1023, 0, 0, 0),  # Twist / Stick Z
    ecodes.ABS_RX:       (0,   0,  255, 0, 0, 0),  # Rotary 1
    ecodes.ABS_RY:       (0,   0,  255, 0, 0, 0),  # Rotary 2
    ecodes.ABS_Z:        (0,   0, 1023, 0, 0, 0),  # Schubhebel
    ecodes.ABS_THROTTLE: (0,   0,  255, 0, 0, 0),  # Schieberegler
}


def hardware_default(code: int) -> tuple[int, int, int, int, int, int] | None:
    """Gibt den bekannten Hardware-Default für einen ABS-Code zurück.

    Rückgabe: (value, minimum, maximum, fuzz, flat, resolution)
    None wenn der Code unbekannt ist.
    """
    return _HW_DEFAULTS.get(code)
