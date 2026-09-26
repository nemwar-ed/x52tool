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
    Button,
    X52Device,
)
from .widgets import (
    AxesPanel,
    AxisBar,
    ButtonHatWidget,
    ButtonTile,
    HatWidget,
    Position2DWidget,
    RockerTriplet,
)
from .. import i18n

# Die drei vom Kernel unbenannten Codes zwischen BTN_BASE6 und BTN_DEAD
# (siehe device.py) - T5, T6, Second Trigger.
_GAP1 = ecodes.BTN_BASE6 + 1
_GAP2 = ecodes.BTN_BASE6 + 2
_GAP3 = ecodes.BTN_BASE6 + 3


class LiveTab(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.device: X52Device | None = None
        self.axes_panel: AxesPanel | None = None
        self.bars: dict[int, AxisBar] = {}
        self.position_widgets: list[tuple[int, int, Position2DWidget]] = []
        self.axis_hats: dict[int, HatWidget] = {}
        self.button_hats: list[ButtonHatWidget] = []
        self.button_tiles: list[ButtonTile] = []
        self.rockers: list[RockerTriplet] = []

        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(8, 8, 8, 8)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.body)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll, 1)

    # -- Aufbau ------------------------------------------------------------

    def set_device(self, device: X52Device | None) -> None:
        self.device = device
        self.bars.clear()
        self.position_widgets.clear()
        self.axis_hats.clear()
        self.button_hats.clear()
        self.button_tiles.clear()
        self.rockers.clear()
        while self.body_layout.count():
            item = self.body_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        if device is None:
            return


        by_code: dict[int, Axis] = {ax.code: ax for ax in device.axes}
        used_codes: set[int] = set()

        self.axes_panel = AxesPanel()
        self.axes_panel.set_device(by_code, used_codes)
        self.bars = self.axes_panel.bars
        self.position_widgets = self.axes_panel.position_widgets

        axes_box = QGroupBox(i18n.t("live.group_axes"))
        axes_box_layout = QVBoxLayout(axes_box)
        axes_box_layout.addWidget(self.axes_panel)

        top_row = QHBoxLayout()
        top_row.addWidget(axes_box, 3)
        ministick_box = self._build_ministick_box(by_code, used_codes)
        if ministick_box is not None:
            top_row.addWidget(ministick_box, 1)
        self.body_layout.addLayout(top_row)

        for x_code, y_code in HAT_AXIS_PAIRS.items():
            if x_code in by_code and y_code in by_code:
                used_codes.add(x_code)
                used_codes.add(y_code)

        leftover = [ax for ax in device.axes if ax.code not in used_codes]
        if leftover:
            fallback_box = QGroupBox(i18n.t("live.group_extra_axes"))
            fallback_layout = QVBoxLayout(fallback_box)
            fallback_layout.setSpacing(2)
            for axis in leftover:
                bar = AxisBar(axis)
                fallback_layout.addWidget(bar)
                self.bars[axis.code] = bar
            self.body_layout.addWidget(fallback_box)

        self._build_hats_row(device, by_code, used_codes)

        by_btn_code = {b.code: b for b in device.buttons}

        top_buttons_row = QHBoxLayout()
        top_buttons_row.addWidget(self._build_buttons_box(by_btn_code), 3)
        mode_box = self._build_mode_box(by_btn_code)
        if mode_box is not None:
            top_buttons_row.addWidget(mode_box, 1)
        self.body_layout.addLayout(top_buttons_row)

        cross_row = QHBoxLayout()
        for box in (
            self._build_cross_box(
                "POV2", by_btn_code,
                up=(i18n.t("live.dir_up"),    ecodes.BTN_TRIGGER_HAPPY4),
                right=(i18n.t("live.dir_right"), ecodes.BTN_TRIGGER_HAPPY5),
                down=(i18n.t("live.dir_down"),  ecodes.BTN_TRIGGER_HAPPY6),
                left=(i18n.t("live.dir_left"),  ecodes.BTN_TRIGGER_HAPPY7),
            ),
            self._build_cross_box(
                "Throttle Hat", by_btn_code,
                up=(i18n.t("live.dir_up"),    ecodes.BTN_TRIGGER_HAPPY8),
                right=(i18n.t("live.dir_right"), ecodes.BTN_TRIGGER_HAPPY9),
                down=(i18n.t("live.dir_down"),  ecodes.BTN_TRIGGER_HAPPY10),
                left=(i18n.t("live.dir_left"),  ecodes.BTN_TRIGGER_HAPPY11),
            ),
            self._build_cross_box(
                "Mouse", by_btn_code,
                up=("Wheel " + i18n.t("live.dir_up"),    ecodes.BTN_TRIGGER_HAPPY1),
                right=(i18n.t("live.dir_right"),           ecodes.BTN_TRIGGER_HAPPY3),
                down=("Wheel " + i18n.t("live.dir_down"), ecodes.BTN_TRIGGER_HAPPY2),
                left=(i18n.t("live.dir_left"),             ecodes.BTN_DEAD),
            ),
        ):
            if box is not None:
                cross_row.addWidget(box, 1)
        self.body_layout.addLayout(cross_row)

        bottom_row = QHBoxLayout()
        mfd_box = self._build_mfd_box(by_btn_code)
        if mfd_box is not None:
            bottom_row.addWidget(mfd_box, 3)
        toggles_box = self._build_toggles_box(by_btn_code)
        if toggles_box is not None:
            bottom_row.addWidget(toggles_box, 2)
        self.body_layout.addLayout(bottom_row)

        self.body_layout.addStretch(1)

    def _build_cross_box(
        self,
        title: str,
        by_btn_code: dict[int, Button],
        up: tuple[str, int],
        right: tuple[str, int],
        down: tuple[str, int],
        left: tuple[str, int],
    ) -> QGroupBox | None:
        entries = {"up": up, "right": right, "down": down, "left": left}
        if not any(code in by_btn_code for _, code in entries.values()):
            return None
        box = QGroupBox(title)
        grid = QGridLayout(box)
        positions = {"up": (0, 1), "left": (1, 0), "right": (1, 2), "down": (2, 1)}
        for key, (label, code) in entries.items():
            tile = self._tile(by_btn_code, label, [code])
            if tile:
                row, col = positions[key]
                grid.addWidget(tile, row, col)
        return box

    def _tile(self, by_btn_code: dict[int, Button], label: str, codes: list[int]) -> ButtonTile | None:
        if not any(c in by_btn_code for c in codes):
            return None
        evdev_name = by_btn_code[codes[0]].evdev_name if codes[0] in by_btn_code else ""
        number = by_btn_code[codes[0]].index + 1 if codes[0] in by_btn_code else None
        tile = ButtonTile(label, codes, evdev_name, number=number)
        tile.setMinimumSize(88, 40)
        self.button_tiles.append(tile)
        return tile

    def _centered_row(self, widgets: list[QWidget]) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addStretch(1)
        for w in widgets:
            row.addWidget(w)
        row.addStretch(1)
        return row

    def _build_buttons_box(self, by_btn_code: dict[int, Button]) -> QGroupBox:
        box = QGroupBox(i18n.t("live.group_buttons"))
        layout = QVBoxLayout(box)

        rows: list[list[tuple[str, list[int]]]] = [
            [("Trigger", [ecodes.BTN_TRIGGER]), ("Sec. Trigger", [_GAP3])],
            [
                ("Fire",   [ecodes.BTN_THUMB]),  ("Fire A", [ecodes.BTN_THUMB2]),
                ("Fire B", [ecodes.BTN_TOP]),    ("Fire C", [ecodes.BTN_TOP2]),
                ("Fire D", [ecodes.BTN_BASE]),   ("Fire E", [ecodes.BTN_BASE2]),
            ],
            [("Pinkie", [ecodes.BTN_PINKIE]), ("Clutch (i)", [ecodes.BTN_TRIGGER_HAPPY15])],
        ]
        for row_spec in rows:
            tiles = [t for label, codes in row_spec if (t := self._tile(by_btn_code, label, codes))]
            if tiles:
                layout.addLayout(self._centered_row(tiles))
        return box

    def _build_toggles_box(self, by_btn_code: dict[int, Button]) -> QGroupBox | None:
        top_codes    = [ecodes.BTN_BASE3, ecodes.BTN_BASE5, _GAP1]
        bottom_codes = [ecodes.BTN_BASE4, ecodes.BTN_BASE6, _GAP2]
        if not any(c in by_btn_code for c in top_codes + bottom_codes):
            return None
        box = QGroupBox(i18n.t("live.group_toggles"))
        grid = QGridLayout(box)
        for col, (label, code) in enumerate(zip(["T1", "T3", "T5"], top_codes)):
            tile = self._tile(by_btn_code, label, [code])
            if tile:
                grid.addWidget(tile, 0, col)
        for col, (label, code) in enumerate(zip(["T2", "T4", "T6"], bottom_codes)):
            tile = self._tile(by_btn_code, label, [code])
            if tile:
                grid.addWidget(tile, 1, col)
        return box

    def _build_mode_box(self, by_btn_code: dict[int, Button]) -> QGroupBox | None:
        entries = [
            (i18n.t("buttons.mode_blue"),   [ecodes.BTN_TRIGGER_HAPPY14]),
            (i18n.t("buttons.mode_purple"), [ecodes.BTN_TRIGGER_HAPPY13]),
            (i18n.t("buttons.mode_red"),    [ecodes.BTN_TRIGGER_HAPPY12]),
        ]
        if not any(c in by_btn_code for _, codes in entries for c in codes):
            return None
        box = QGroupBox(i18n.t("live.group_mode"))
        layout = QVBoxLayout(box)
        for label, codes in entries:
            tile = self._tile(by_btn_code, label, codes)
            if tile:
                layout.addWidget(tile)
        return box

    def _rocker_segment_info(
        self, by_btn_code: dict[int, Button], up: int, down: int, press: int
    ) -> dict[str, tuple[str, int | None]]:
        def num(code: int) -> int | None:
            btn = by_btn_code.get(code)
            return btn.index + 1 if btn else None

        return {
            "up":    (i18n.t("live.rocker_up"),    num(up)),
            "down":  (i18n.t("live.rocker_down"),  num(down)),
            "press": (i18n.t("live.rocker_click"),  num(press)),
        }

    def _build_mfd_box(self, by_btn_code: dict[int, Button]) -> QGroupBox | None:
        left_codes  = (ecodes.BTN_TRIGGER_HAPPY19, ecodes.BTN_TRIGGER_HAPPY20, ecodes.BTN_TRIGGER_HAPPY16)
        right_codes = (ecodes.BTN_TRIGGER_HAPPY21, ecodes.BTN_TRIGGER_HAPPY22, ecodes.BTN_TRIGGER_HAPPY23)
        mid_codes   = (ecodes.BTN_TRIGGER_HAPPY17, ecodes.BTN_TRIGGER_HAPPY18)
        if not any(c in by_btn_code for c in left_codes + right_codes + mid_codes):
            return None

        box = QGroupBox(i18n.t("live.group_mfd"))
        row = QHBoxLayout(box)
        row.addStretch(1)

        if all(c in by_btn_code for c in left_codes):
            up, down, press = left_codes
            rocker = RockerTriplet(
                i18n.t("live.mfd_left"), up, down, press,
                segment_info=self._rocker_segment_info(by_btn_code, up, down, press),
            )
            rocker.setMinimumSize(85, 100)
            self.rockers.append(rocker)
            row.addWidget(rocker)

        mid_tiles = [t for t in (
            self._tile(by_btn_code, "Start/Stop", [ecodes.BTN_TRIGGER_HAPPY17]),
            self._tile(by_btn_code, "Reset",      [ecodes.BTN_TRIGGER_HAPPY18]),
        ) if t]
        if mid_tiles:
            mid_col = QVBoxLayout()
            mid_col.addStretch(1)
            for t in mid_tiles:
                mid_col.addWidget(t)
            mid_col.addStretch(1)
            row.addLayout(mid_col)

        if all(c in by_btn_code for c in right_codes):
            up, down, press = right_codes
            rocker = RockerTriplet(
                i18n.t("live.mfd_right"), up, down, press,
                segment_info=self._rocker_segment_info(by_btn_code, up, down, press),
            )
            rocker.setMinimumSize(85, 100)
            self.rockers.append(rocker)
            row.addWidget(rocker)

        row.addStretch(1)
        return box

    def _build_stick_and_throttle_box(
        self, by_code: dict[int, Axis], used_codes: set[int]
    ) -> QGroupBox:
        box = QGroupBox(i18n.t("live.group_axes"))
        grid = QGridLayout(box)

        if ecodes.ABS_X in by_code and ecodes.ABS_Y in by_code:
            x_axis, y_axis = by_code[ecodes.ABS_X], by_code[ecodes.ABS_Y]
            pos = Position2DWidget("Stick", x_axis, y_axis)
            self.position_widgets.append((x_axis.code, y_axis.code, pos))
            used_codes.update((x_axis.code, y_axis.code))
            grid.addWidget(pos, 0, 0, 3, 1)

        if ecodes.ABS_Z in by_code:
            axis = by_code[ecodes.ABS_Z]
            bar = AxisBar(axis, orientation="vertical")
            self.bars[axis.code] = bar
            used_codes.add(axis.code)
            grid.addWidget(bar, 0, 1, 3, 1)

        for row, code in enumerate((ecodes.ABS_RY, ecodes.ABS_RX)):
            if code in by_code:
                axis = by_code[code]
                bar = AxisBar(axis)
                self.bars[axis.code] = bar
                used_codes.add(axis.code)
                grid.addWidget(bar, row, 2)

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
        box = QGroupBox(i18n.t("live.group_ministick"))
        layout = QVBoxLayout(box)
        pos = Position2DWidget(i18n.t("live.ministick_label"), x_axis, y_axis)
        self.position_widgets.append((x_axis.code, y_axis.code, pos))
        used_codes.update((x_axis.code, y_axis.code))
        layout.addStretch(1)
        layout.addWidget(pos, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch(1)
        return box

    def _build_hats_row(
        self, device: X52Device, by_code: dict[int, Axis], used_codes: set[int]
    ) -> None:
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
            hats_box = QGroupBox(i18n.t("live.group_hats"))
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
        for tile in self.button_tiles:
            tile.set_pressed_state(buttons)
        for rocker in self.rockers:
            rocker.set_pressed(buttons)

    def refresh_calibration(self) -> None:
        """Nach dem Schreiben neuer Kalibrierdaten die Balken/Felder neu zeichnen."""
        if self.device is None or self.axes_panel is None:
            return
        self.axes_panel.refresh_calibration(self.device)

    def retranslate(self) -> None:
        """Beschriftungen nach Sprachwechsel aktualisieren.
        Baut den Tab mit dem aktuellen Geraet neu auf - alle Labels kommen
        dann frisch aus i18n, inkl. Achsennamen und Gruppentitel.
        """
        self.set_device(self.device)
