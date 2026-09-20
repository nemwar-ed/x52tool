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

from ..device import HAT_AXIS_PAIRS, X52Device, axis_label
from .widgets import AxisBar, ButtonGrid, HatWidget


class LiveTab(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.device: X52Device | None = None
        self.bars: dict[int, AxisBar] = {}
        self.hats: dict[int, HatWidget] = {}  # X-Code -> Widget
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
        self.hats.clear()
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

        axes_box = QGroupBox("Achsen")
        axes_layout = QVBoxLayout(axes_box)
        axes_layout.setSpacing(2)
        for axis in device.axes:
            if axis.code in hat_y_codes:
                continue  # wird zusammen mit dem X-Code als Kompass gezeichnet
            if axis.code in hat_x_codes:
                y_code = HAT_AXIS_PAIRS[axis.code]
                # "Hat 1 X" -> "Hat 1"; robust auch wenn die Beschriftung mal
                # anders lautet.
                label = axis_label(axis.code).replace(" X", "").strip() or "Hat"
                widget = HatWidget(label, axis.code, y_code)
                self.hats[axis.code] = widget
                row = QHBoxLayout()
                row.addWidget(widget)
                row.addStretch(1)
                axes_layout.addLayout(row)
                continue
            bar = AxisBar(axis)
            axes_layout.addWidget(bar)
            self.bars[axis.code] = bar
        self.body_layout.addWidget(axes_box)

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
        for x_code, widget in self.hats.items():
            y_code = widget.y_code
            if x_code in axes and y_code in axes:
                widget.set_values(axes[x_code], axes[y_code])
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
