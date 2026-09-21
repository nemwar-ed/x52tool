"""Reiter 'Live-Test': sieht alles, veraendert nichts."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..device import HAT_AXIS_PAIRS, X52_PRO_POV_BUTTON_GROUPS, X52Device, axis_label
from .widgets import AxisBar, ButtonGrid, ButtonHatWidget, HatWidget


class LiveTab(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.device: X52Device | None = None
        self.bars: dict[int, AxisBar] = {}
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
            "Alles bewegen, jede Taste einmal druecken. Ein Balken, der sich "
            "nicht bewegt, oder eine Taste, die nicht aufleuchtet, ist der Befund."
        )

        codes_present = {ax.code for ax in device.axes}
        # Welche X-Codes eines Hat-Paars gehoeren zusammen und sind beide da.
        hat_x_codes = {
            x for x, y in HAT_AXIS_PAIRS.items() if x in codes_present and y in codes_present
        }
        hat_y_codes = {HAT_AXIS_PAIRS[x] for x in hat_x_codes}

        # -- Achsen (ohne die Hat-Achsen, die wandern in die Hats-Zeile) ----
        axes_box = QGroupBox("Achsen")
        axes_layout = QVBoxLayout(axes_box)
        axes_layout.setSpacing(2)
        for axis in device.axes:
            if axis.code in hat_x_codes or axis.code in hat_y_codes:
                continue
            bar = AxisBar(axis)
            axes_layout.addWidget(bar)
            self.bars[axis.code] = bar
        self.body_layout.addWidget(axes_box)

        # -- Hats: echte Achsen-Hats und (beim X52 Pro) tasten-basierte
        # POV2/POV3 nebeneinander in einer Reihe. Die vier Tasten je
        # POV2/POV3 bleiben zusaetzlich ganz normal im Tastenraster unten
        # sichtbar - der Kompass hier ist eine zweite, leichter lesbare
        # Ansicht derselben Events, keine Ersetzung.
        hat_widgets: list[QWidget] = []
        for axis in device.axes:
            if axis.code not in hat_x_codes:
                continue
            y_code = HAT_AXIS_PAIRS[axis.code]
            label = axis_label(axis.code).replace(" X", "").strip() or "Hat"
            widget = HatWidget(label, axis.code, y_code)
            self.axis_hats[axis.code] = widget
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

        # -- Tasten ----------------------------------------------------------
        buttons_box = QGroupBox(f"Tasten ({len(device.buttons)})")
        buttons_layout = QVBoxLayout(buttons_box)
        self.grid = ButtonGrid(device.buttons)
        buttons_layout.addWidget(self.grid)
        self.body_layout.addWidget(buttons_box)

        self.body_layout.addStretch(1)

    # -- Takt --------------------------------------------------------------

    def refresh(self, axes: dict[int, int], buttons: dict[int, bool]) -> None:
        for code, bar in self.bars.items():
            if code in axes:
                bar.set_value(axes[code])
        for x_code, widget in self.axis_hats.items():
            y_code = widget.y_code
            if x_code in axes and y_code in axes:
                widget.set_values(axes[x_code], axes[y_code])
        for widget in self.button_hats:
            widget.set_pressed(buttons)
        if self.grid is not None:
            self.grid.update_state(buttons)

    def refresh_calibration(self) -> None:
        """Nach dem Schreiben neuer Kalibrierdaten die Balken neu zeichnen."""
        if self.device is None:
            return
        for axis in self.device.axes:
            bar = self.bars.get(axis.code)
            if bar is not None:
                bar.set_info(axis.info)
