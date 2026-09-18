"""Reiter 'Live-Test': sieht alles, veraendert nichts."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QGroupBox,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..device import X52Device
from .widgets import AxisBar, ButtonGrid


class LiveTab(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.device: X52Device | None = None
        self.bars: dict[int, AxisBar] = {}
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

        axes_box = QGroupBox("Achsen")
        axes_layout = QVBoxLayout(axes_box)
        axes_layout.setSpacing(2)
        for axis in device.axes:
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
