"""Messung und Auswertung.

Zwei Messungen, die es so fertig noch nicht gibt:

Ruhemessung   Stick und Schubhebel loslassen, N Sekunden mitschreiben.
              Ergebnis: Mittenversatz und Rauschbreite pro Achse, daraus
              ein Deadzone-Vorschlag.

Bereichsmessung  Jede Achse einmal voll ausfahren. Ergebnis: erreichter
                 Bereich gegen den vom Kernel gemeldeten Bereich. Faellt
                 eine Achse deutlich zurueck, ist das Poti verschlissen.

Wichtig: der Kernel filtert Ereignisse anhand von `fuzz`. Steht fuzz hoch,
misst man das Filter und nicht die Hardware. Die Oberflaeche bietet darum
an, fuzz fuer die Dauer der Messung auf 0 zu setzen.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field

from .device import AbsInfo, Axis, X52Device

# Sicherheitsfaktor auf die gemessene Rauschbreite. 1.5 laesst Luft fuer
# Temperaturdrift und Alterung, ohne die Achse traege zu machen.
DEADZONE_MARGIN = 1.5

# Unterhalb dieses Anteils der Achsenspanne ist das Rauschen so klein, dass
# eine Deadzone mehr Gefuehl kostet als sie bringt. Relativ, weil die Achsen
# des X52 unterschiedlich aufgeloest sind (10 bit am Stick, 8 bit am Slider).
DEADZONE_FLOOR_FRACTION = 0.001  # 0.1 % der Spanne


@dataclass
class AxisMeasurement:
    """Rohdaten einer Achse ueber einen Messzeitraum."""

    code: int
    label: str
    info: AbsInfo
    samples: list[int] = field(default_factory=list)

    # -- abgeleitete Werte -------------------------------------------------

    @property
    def count(self) -> int:
        return len(self.samples)

    @property
    def lowest(self) -> int:
        return min(self.samples) if self.samples else 0

    @property
    def highest(self) -> int:
        return max(self.samples) if self.samples else 0

    @property
    def spread(self) -> int:
        """Spitze-Spitze-Rauschen in Rohwerten."""
        return self.highest - self.lowest

    @property
    def mean(self) -> float:
        return statistics.fmean(self.samples) if self.samples else 0.0

    @property
    def stddev(self) -> float:
        return statistics.pstdev(self.samples) if len(self.samples) > 1 else 0.0

    @property
    def centre_offset(self) -> float:
        """Abweichung der Ruhelage von der Achsenmitte, in Rohwerten."""
        return self.mean - self.info.centre

    @property
    def coverage(self) -> float:
        """Anteil des Kernel-Bereichs, den die Achse tatsaechlich erreicht."""
        if self.info.span == 0:
            return 0.0
        return 100.0 * self.spread / self.info.span

    @property
    def suggested_flat(self) -> int:
        """Deadzone-Vorschlag aus der Ruhemessung."""
        if self.info.span <= 8:  # digitale Hats
            return 0
        raw = math.ceil(self.spread / 2 * DEADZONE_MARGIN)
        floor = max(2, math.ceil(self.info.span * DEADZONE_FLOOR_FRACTION))
        return 0 if raw < floor else raw

    def percent(self, raw_units: float) -> float:
        return self.info.as_percent(raw_units)


class Recorder:
    """Sammelt Stichproben des aktuellen Zustands.

    Wird von einem Timer getaktet, nicht vom Event-Strom. Eine ruhig
    liegende Achse sendet keine Events, soll aber trotzdem in die Statistik.
    """

    def __init__(self, device: X52Device, codes: list[int] | None = None) -> None:
        self.device = device
        wanted = codes if codes is not None else [ax.code for ax in device.axes]
        self._axes: dict[int, Axis] = {ax.code: ax for ax in device.axes if ax.code in wanted}
        self.measurements: dict[int, AxisMeasurement] = {
            code: AxisMeasurement(code=code, label=ax.label, info=ax.info)
            for code, ax in self._axes.items()
        }

    def sample(self, state_axes: dict[int, int]) -> None:
        for code, measurement in self.measurements.items():
            if code in state_axes:
                measurement.samples.append(state_axes[code])

    def results(self, skip_digital: bool = True) -> list[AxisMeasurement]:
        out = []
        for code, measurement in self.measurements.items():
            axis = self._axes[code]
            if skip_digital and axis.is_digital:
                continue
            out.append(measurement)
        return sorted(out, key=lambda m: m.code)


# --------------------------------------------------------------------------
# Persistenz-Export
# --------------------------------------------------------------------------


def _hex4(value: int) -> str:
    return f"{value:04x}"


def udev_rule_evdev_joystick(
    device: X52Device,
    axes: list[Axis],
    binary: str = "/usr/bin/evdev-joystick",
) -> str:
    """udev-Regel, die beim Einstecken `evdev-joystick` aufruft.

    Braucht das Paket `joystick` (Debian/Mint) bzw. `linuxconsole` (Arch).
    Hinweis: die Bedeutung von --axis ist versionsabhaengig. Der erzeugte
    Kommentar nennt den ABS-Code, damit sich das pruefen laesst.
    """
    lines = [
        "# x52tool - Kalibrierung beim Einstecken anwenden",
        f"# Geraet: {device.name} ({device.usb_id})",
        "# Ablegen unter /etc/udev/rules.d/99-x52tool.rules, danach:",
        "#   sudo udevadm control --reload-rules && sudo udevadm trigger",
        "",
    ]
    for axis in axes:
        if axis.is_digital:
            continue
        parts = [
            f'ACTION=="add", SUBSYSTEM=="input", KERNEL=="event*"',
            f'ATTRS{{idVendor}}=="{_hex4(device.vendor)}"',
            f'ATTRS{{idProduct}}=="{_hex4(device.product)}"',
            f'RUN+="{binary} --evdev $devnode --axis {axis.code}'
            f" --deadzone {axis.info.flat} --fuzz {axis.info.fuzz}"
            f' --minimum {axis.info.minimum} --maximum {axis.info.maximum}"',
        ]
        lines.append(f"# {axis.label} (ABS 0x{axis.code:02x})")
        lines.append(", ".join(parts))
    return "\n".join(lines) + "\n"


def udev_rule_selfcall(device: X52Device, python: str = "/usr/bin/python3", project_dir: str = "/opt/x52tool") -> str:
    """udev-Regel, die x52tool selbst im Apply-Modus aufruft.

    Unabhaengig von evdev-joystick und damit von dessen --axis-Semantik.
    """
    return (
        "# x52tool - gespeichertes Profil beim Einstecken anwenden\n"
        f"# Geraet: {device.name} ({device.usb_id})\n"
        "# Ablegen unter /etc/udev/rules.d/99-x52tool.rules\n"
        "\n"
        'ACTION=="add", SUBSYSTEM=="input", KERNEL=="event*", '
        f'ATTRS{{idVendor}}=="{_hex4(device.vendor)}", '
        f'ATTRS{{idProduct}}=="{_hex4(device.product)}", '
        f'RUN+="{python} -m x52tool --apply --device $devnode", '
        f'ENV{{PYTHONPATH}}="{project_dir}"\n'
    )


def udev_rule_permissions(device: X52Device) -> str:
    """Gibt dem angemeldeten Benutzer Zugriff, ohne ihn in die input-Gruppe zu stecken."""
    return (
        "# x52tool - Schreibzugriff nur fuer dieses eine Geraet\n"
        "# Ablegen unter /etc/udev/rules.d/70-x52-uaccess.rules\n"
        "\n"
        f'SUBSYSTEM=="input", ATTRS{{idVendor}}=="{_hex4(device.vendor)}", '
        f'ATTRS{{idProduct}}=="{_hex4(device.product)}", MODE="0660", TAG+="uaccess"\n'
        f'SUBSYSTEM=="usb", ATTR{{idVendor}}=="{_hex4(device.vendor)}", '
        f'ATTR{{idProduct}}=="{_hex4(device.product)}", MODE="0660", TAG+="uaccess"\n'
    )
