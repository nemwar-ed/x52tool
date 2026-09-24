"""Reiter 'Live-Test': sieht alles, veraendert nichts.

Anordnung angelehnt an die originale Saitek/Logitech-Windows-Software
(Test-Reiter): Stick X/Y als 2D-Feld, Schubhebel als senkrechter Balken
daneben, Rotary 1/2 uebereinander, Twist und Schieberegler darunter,
Ministick als eigenes 2D-Feld daneben, POV-Hats zentriert darunter.
"""

from __future__ import annotations

from evdev import ecodes

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..device import (
    ABS_MISC_Y,
    HAT_AXIS_PAIRS,
    X52_PRO_POV_BUTTON_GROUPS,
    Axis,
    X52Device,
)
from .widgets import AxisBar, ButtonGrid, ButtonHatWidget, HatWidget, Position2DWidget


class LiveTab(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.device: X52Device | None = None
        self.bars: dict[int, AxisBar] = {}
        self.position_widgets: list[tuple[int, int, Position2DWidget]] = []
        self.axis_hats: dict[int, HatWidget] = {}  # X-Code -> Widget
        self.button_hats: list[ButtonHatWidget] = []
        self.grid: ButtonGrid | None = None

        self.hint = QLabel("Kein Geraet gewaehlt.")
        self.hint.setWordWrap(True)

        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(8, 8, 8, 8)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.body)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.hint)
        layout.addWidget(scroll, 1)

    # -- Aufbau ------------------------------------------------------------

    def set_device(self, device: X52Device | None) -> None:
        self.device = device
        self.bars.clear()
        self.position_widgets.clear()
        self.axis_hats.clear()
        self.button_hats.clear()
        self.grid = None
        while self.body_layout.count():
            item = self.body_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        if device is None:
            self.hint.setText("Kein Geraet gewaehlt.")
            return

        self.hint.setText(
            "Alles bewegen, jede Taste einmal druecken. Ein Feld/Balken, das "
            "sich nicht bewegt, oder eine Taste, die nicht aufleuchtet, ist "
            "der Befund."
        )

        by_code: dict[int, Axis] = {ax.code: ax for ax in device.axes}
        used_codes: set[int] = set()

        top_row = QHBoxLayout()
        top_row.addWidget(self._build_stick_and_throttle_box(by_code, used_codes), 3)
        ministick_box = self._build_ministick_box(by_code, used_codes)
        if ministick_box is not None:
            top_row.addWidget(ministick_box, 1)
        self.body_layout.addLayout(top_row)

        # Hat-Achsencodes schon hier reservieren (nicht erst in
        # _build_hats_row), sonst landen sie faelschlich im Fallback unten.
        for x_code, y_code in HAT_AXIS_PAIRS.items():
            if x_code in by_code and y_code in by_code:
                used_codes.add(x_code)
                used_codes.add(y_code)

        # Alle Achsen, die keinen Spezialplatz oben bekommen haben (z.B. auf
        # einem anderen Geraet als dem X52 Pro), landen sicherheitshalber
        # als ganz normaler waagerechter Balken hier - nichts geht verloren.
        leftover = [ax for ax in device.axes if ax.code not in used_codes]
        if leftover:
            fallback_box = QGroupBox("Weitere Achsen")
            fallback_layout = QVBoxLayout(fallback_box)
            fallback_layout.setSpacing(2)
            for axis in leftover:
                bar = AxisBar(axis)
                fallback_layout.addWidget(bar)
                self.bars[axis.code] = bar
            self.body_layout.addWidget(fallback_box)

        self._build_hats_row(device, by_code, used_codes)

        # -- Tasten ----------------------------------------------------------
        buttons_box = QGroupBox(f"Tasten ({len(device.buttons)})")
        buttons_layout = QVBoxLayout(buttons_box)
        self.grid = ButtonGrid(device.buttons)
        buttons_layout.addWidget(self.grid)
        self.body_layout.addWidget(buttons_box)

        self.body_layout.addStretch(1)

    def _build_stick_and_throttle_box(
        self, by_code: dict[int, Axis], used_codes: set[int]
    ) -> QGroupBox:
        box = QGroupBox("Achsen")
        grid = QGridLayout(box)

        # Stick X/Y als 2D-Feld
        if ecodes.ABS_X in by_code and ecodes.ABS_Y in by_code:
            x_axis, y_axis = by_code[ecodes.ABS_X], by_code[ecodes.ABS_Y]
            pos = Position2DWidget("Stick", x_axis, y_axis)
            self.position_widgets.append((x_axis.code, y_axis.code, pos))
            used_codes.update((x_axis.code, y_axis.code))
            grid.addWidget(pos, 0, 0, 3, 1)

        # Schubhebel als senkrechter Balken direkt daneben
        if ecodes.ABS_Z in by_code:
            axis = by_code[ecodes.ABS_Z]
            bar = AxisBar(axis, orientation="vertical")
            self.bars[axis.code] = bar
            used_codes.add(axis.code)
            grid.addWidget(bar, 0, 1, 3, 1)

        # Rotary 2 (X-Achse) oben, Rotary 1 (Y-Achse) darunter - rechts
        # vom Schubhebel. Reihenfolge von Oliver an echter Hardware
        # bestaetigt.
        for row, code in enumerate((ecodes.ABS_RY, ecodes.ABS_RX)):
            if code in by_code:
                axis = by_code[code]
                bar = AxisBar(axis)
                self.bars[axis.code] = bar
                used_codes.add(axis.code)
                grid.addWidget(bar, row, 2)

        # Twist und Schieberegler nebeneinander, volle Breite der Box -
        # als eigene Zeile statt ueber Grid-Spaltenspannen (die reichen bei
        # nur 3 definierten Spalten sonst über den Rand hinaus).
        bottom_row = QHBoxLayout()
        has_bottom = False
        for code in (ecodes.ABS_RZ, ecodes.ABS_THROTTLE):
            if code in by_code:
                axis = by_code[code]
                bar = AxisBar(axis)
                self.bars[axis.code] = bar
                used_codes.add(axis.code)
                bottom_row.addWidget(bar)
                has_bottom = True
        if has_bottom:
            bottom_widget = QWidget()
            bottom_widget.setLayout(bottom_row)
            grid.addWidget(bottom_widget, 3, 0, 1, 3)

        grid.setColumnStretch(2, 1)
        return box

    def _build_ministick_box(
        self, by_code: dict[int, Axis], used_codes: set[int]
    ) -> QGroupBox | None:
        if ecodes.ABS_MISC not in by_code or ABS_MISC_Y not in by_code:
            return None
        x_axis, y_axis = by_code[ecodes.ABS_MISC], by_code[ABS_MISC_Y]
        box = QGroupBox("Ministick")
        layout = QVBoxLayout(box)
        pos = Position2DWidget("Maus-Stick", x_axis, y_axis)
        self.position_widgets.append((x_axis.code, y_axis.code, pos))
        used_codes.update((x_axis.code, y_axis.code))
        # In beide Richtungen zentrieren, egal wie gross die Box durch das
        # Streckungsverhaeltnis in der oberen Reihe am Ende wird.
        layout.addStretch(1)
        layout.addWidget(pos, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch(1)
        return box

    def _build_hats_row(
        self, device: X52Device, by_code: dict[int, Axis], used_codes: set[int]
    ) -> None:
        # Welche X-Codes eines Hat-Achsenpaars gehoeren zusammen und sind da.
        hat_x_codes = {
            x for x, y in HAT_AXIS_PAIRS.items() if x in by_code and y in by_code
        }

        hat_widgets: list[QWidget] = []
        for x_code in hat_x_codes:
            y_code = HAT_AXIS_PAIRS[x_code]
            widget = HatWidget("POV 1", x_code, y_code)
            self.axis_hats[x_code] = widget
            used_codes.update((x_code, y_code))
            hat_widgets.append(widget)

        if device.is_pro:
            button_codes_present = {btn.code for btn in device.buttons}
            for label, (up, right, down, left) in X52_PRO_POV_BUTTON_GROUPS.items():
                if {up, right, down, left} <= button_codes_present:
                    widget = ButtonHatWidget(label, up, right, down, left)
                    self.button_hats.append(widget)
                    hat_widgets.append(widget)

        if hat_widgets:
            hats_box = QGroupBox("Hats")
            hats_layout = QHBoxLayout(hats_box)
            hats_layout.addStretch(1)
            for widget in hat_widgets:
                hats_layout.addWidget(widget)
            hats_layout.addStretch(1)
            self.body_layout.addWidget(hats_box)

    # -- Takt --------------------------------------------------------------

    def refresh(self, axes: dict[int, int], buttons: dict[int, bool]) -> None:
        for code, bar in self.bars.items():
            if code in axes:
                bar.set_value(axes[code])
        for x_code, y_code, pos in self.position_widgets:
            if x_code in axes and y_code in axes:
                pos.set_values(axes[x_code], axes[y_code])
        for x_code, widget in self.axis_hats.items():
            y_code = widget.y_code
            if x_code in axes and y_code in axes:
                widget.set_values(axes[x_code], axes[y_code])
        for widget in self.button_hats:
            widget.set_pressed(buttons)
        if self.grid is not None:
            self.grid.update_state(buttons)

    def refresh_calibration(self) -> None:
        """Nach dem Schreiben neuer Kalibrierdaten die Balken/Felder neu zeichnen."""
        if self.device is None:
            return
        for axis in self.device.axes:
            bar = self.bars.get(axis.code)
            if bar is not None:
                bar.set_info(axis.info)
        for x_code, y_code, pos in self.position_widgets:
            pos.update()
