"""Rausch- und Peak-Tracking für eine einzelne Achse.

NoiseTracker wird pro Achse instanziiert und vom UI-Refresh-Takt
(~30 Hz) mit dem aktuellen Rohwert gefüttert.

Rauschfenster (Ringpuffer, läuft immer):
    Die letzten `capacity` Samples werden gehalten.
    noise_range = max(window) - min(window)
    → repräsentiert das aktuelle Grundrauschen der Achse.

Peak-Tracking (läuft parallel, reset_peaks() zum Neustart):
    peak_min / peak_max wachsen mit jedem neuen Extremwert.
    center = (peak_min + peak_max) // 2
    → wird nach der geführten Peak-Kalibrierung ausgelesen.
"""

from __future__ import annotations

from collections import deque

_DEFAULT_CAPACITY = 100  # ~3 Sekunden bei 30 Hz
_FLAT_MARGIN      = 2    # Sicherheitspuffer für suggested_flat
_FUZZ_MARGIN      = 1    # Sicherheitspuffer für suggested_fuzz


class NoiseTracker:
    """Ringpuffer + Peak-Tracker für eine einzelne Achse."""

    def __init__(self, initial: int, capacity: int = _DEFAULT_CAPACITY) -> None:
        self._buf: deque[int] = deque([initial], maxlen=capacity)
        self.peak_min: int = initial
        self.peak_max: int = initial

    def push(self, value: int) -> None:
        """Neuen Rohwert aufnehmen."""
        self._buf.append(value)
        if value < self.peak_min:
            self.peak_min = value
        if value > self.peak_max:
            self.peak_max = value

    @property
    def noise_min(self) -> int:
        return min(self._buf)

    @property
    def noise_max(self) -> int:
        return max(self._buf)

    @property
    def noise_range(self) -> int:
        """Breite des Rauschbands im aktuellen Fenster."""
        return self.noise_max - self.noise_min

    @property
    def center(self) -> int:
        """Errechneter Mittelpunkt aus Peak-Min und Peak-Max."""
        return (self.peak_min + self.peak_max) // 2

    @property
    def peak_range(self) -> int:
        return self.peak_max - self.peak_min

    def reset_peaks(self, current: int | None = None) -> None:
        """Peak-Min/Max zurücksetzen auf aktuellen Wert."""
        value = current if current is not None else self._buf[-1]
        self.peak_min = value
        self.peak_max = value

    def suggested_flat(self) -> int:
        """Vorschlag für flat (Deadzone um Mitte). Nur nach Peak-Messung sinnvoll."""
        return self.noise_range + _FLAT_MARGIN

    def suggested_fuzz(self) -> int:
        """Vorschlag für fuzz (Kernel-Rauschfilter). Für alle Achsen sinnvoll."""
        return self.noise_range + _FUZZ_MARGIN

    def __repr__(self) -> str:
        return (
            f"NoiseTracker("
            f"noise={self.noise_range}, "
            f"peaks=[{self.peak_min}..{self.peak_max}], "
            f"center={self.center})"
        )
