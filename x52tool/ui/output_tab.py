"""Reiter 'LED / MFD': Ausgabe ueber das libx52-CLI."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ..output import PRO_LEDS, Backend, detect_binary
from .. import i18n


class OutputTab(QWidget):
    def __init__(self, settings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.backend  = Backend(settings.backend)
        self._led_boxes: dict[str, QComboBox] = {}
        self._build()
        self._refresh_availability()

    # -- Aufbau ------------------------------------------------------------

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.addWidget(self._build_leds())
        layout.addWidget(self._build_mfd())
        layout.addWidget(self._build_clutch())
        layout.addWidget(self._build_test())
        layout.addStretch(1)

    def _build_leds(self) -> QGroupBox:
        box  = QGroupBox(i18n.t("output.group_leds"))
        grid = QGridLayout(box)
        leds = PRO_LEDS()
        for i, (key, label, states) in enumerate(leds):
            combo = QComboBox()
            combo.addItems(states)
            combo.currentTextChanged.connect(
                lambda state, k=key: self.backend.set_led(k, state)
            )
            grid.addWidget(QLabel(label), i // 3, (i % 3) * 2)
            grid.addWidget(combo,         i // 3, (i % 3) * 2 + 1)
            self._led_boxes[key] = combo
        return box

    def _build_mfd(self) -> QGroupBox:
        box    = QGroupBox(i18n.t("output.group_mfd_clock"))
        layout = QVBoxLayout(box)

        # Datumsformat
        date_row = QHBoxLayout()
        self.combo_date_fmt = QComboBox()
        self.combo_date_fmt.addItems(["DD-MM-YY", "MM-DD-YY", "YY-MM-DD"])
        self.combo_date_fmt.currentIndexChanged.connect(self._apply_clock)
        date_row.addStretch(1)
        date_row.addWidget(QLabel(i18n.t("output.mfd_date_format")))
        date_row.addWidget(self.combo_date_fmt)
        date_row.addStretch(1)
        layout.addLayout(date_row)

        # Drei Uhren nebeneinander
        clocks_row = QHBoxLayout()

        # Uhr 1
        clock1_box = QGroupBox(i18n.t("output.mfd_clock1"))
        clock1_layout = QVBoxLayout(clock1_box)
        self.chk_local_time = QCheckBox(i18n.t("output.mfd_local_time"))
        self.chk_12h_clock1 = QCheckBox(i18n.t("output.mfd_12h"))
        self.chk_local_time.toggled.connect(self._apply_clock)
        self.chk_12h_clock1.toggled.connect(self._apply_clock)
        clock1_layout.addWidget(self.chk_local_time)
        clock1_layout.addWidget(self.chk_12h_clock1)

        # Uhr 2
        clock2_box = QGroupBox(i18n.t("output.mfd_clock2"))
        clock2_layout = QVBoxLayout(clock2_box)
        self.combo_offset2 = QComboBox()
        self._fill_offset_combo(self.combo_offset2)
        self.chk_12h_clock2 = QCheckBox(i18n.t("output.mfd_12h"))
        self.combo_offset2.currentIndexChanged.connect(self._apply_clock)
        self.chk_12h_clock2.toggled.connect(self._apply_clock)
        clock2_layout.addWidget(QLabel(i18n.t("output.mfd_gmt_offset")))
        clock2_layout.addWidget(self.combo_offset2)
        clock2_layout.addWidget(self.chk_12h_clock2)

        # Uhr 3
        clock3_box = QGroupBox(i18n.t("output.mfd_clock3"))
        clock3_layout = QVBoxLayout(clock3_box)
        self.combo_offset3 = QComboBox()
        self._fill_offset_combo(self.combo_offset3)
        self.chk_12h_clock3 = QCheckBox(i18n.t("output.mfd_12h"))
        self.combo_offset3.currentIndexChanged.connect(self._apply_clock)
        self.chk_12h_clock3.toggled.connect(self._apply_clock)
        clock3_layout.addWidget(QLabel(i18n.t("output.mfd_gmt_offset")))
        clock3_layout.addWidget(self.combo_offset3)
        clock3_layout.addWidget(self.chk_12h_clock3)

        clocks_row.addWidget(clock1_box, 1)
        clocks_row.addWidget(clock2_box, 1)
        clocks_row.addWidget(clock3_box, 1)
        layout.addLayout(clocks_row)
        return box

    def _fill_offset_combo(self, combo: QComboBox) -> None:
        """GMT -12 bis +14 in 30-Minuten-Schritten."""
        for h in range(-12, 15):
            for m in (0, 30):
                if h == 14 and m == 30:
                    break
                sign  = "+" if h >= 0 else ""
                label = f"GMT {sign}{h}:{m:02d}"
                combo.addItem(label, h * 60 + m)
        # Default: GMT 0:00
        idx = combo.findData(0)
        if idx >= 0:
            combo.setCurrentIndex(idx)

    def _apply_clock(self) -> None:
        """Sendet clock- und date-Befehle ans Gerät."""
        local = "local" if self.chk_local_time.isChecked() else "gmt"
        hr1   = "12hr" if self.chk_12h_clock1.isChecked() else "24hr"
        hr2   = "12hr" if self.chk_12h_clock2.isChecked() else "24hr"
        hr3   = "12hr" if self.chk_12h_clock3.isChecked() else "24hr"

        fmt_map = {"DD-MM-YY": "ddmmyy", "MM-DD-YY": "mmddyy", "YY-MM-DD": "yymmdd"}
        date_fmt = fmt_map.get(self.combo_date_fmt.currentText(), "ddmmyy")

        off2 = self.combo_offset2.currentData() or 0
        off3 = self.combo_offset3.currentData() or 0

        self.backend.run_raw(["clock", local, hr1, date_fmt])
        self.backend.run_raw(["offset", "2", str(off2), hr2])
        self.backend.run_raw(["offset", "3", str(off3), hr3])

    def _build_clutch(self) -> QGroupBox:
        box    = QGroupBox(i18n.t("output.group_clutch"))
        layout = QHBoxLayout(box)
        self.clutch_checkbox = QCheckBox(i18n.t("output.clutch_checkbox"))
        self.clutch_checkbox.toggled.connect(
            lambda checked: self.backend.set_clutch(checked)
        )
        self.clutch_latched = QCheckBox(i18n.t("output.clutch_latched"))
        layout.addStretch(1)
        layout.addWidget(self.clutch_checkbox)
        layout.addWidget(self.clutch_latched)
        layout.addStretch(1)
        return box

    def _build_test(self) -> QGroupBox:
        box   = QGroupBox(i18n.t("output.group_test"))
        outer = QVBoxLayout(box)

        # Buttons oben zentriert
        btn_row = QHBoxLayout()
        btn_on  = QPushButton(i18n.t("output.btn_all_on"))
        btn_off = QPushButton(i18n.t("output.btn_all_off"))
        btn_on.clicked.connect(lambda: self.backend.all_leds("green"))
        btn_off.clicked.connect(lambda: self.backend.all_leds("off"))
        btn_row.addStretch(1)
        btn_row.addWidget(btn_on)
        btn_row.addWidget(btn_off)
        btn_row.addStretch(1)
        outer.addLayout(btn_row)

        # Helligkeit-Label zentriert
        bri_label_row = QHBoxLayout()
        bri_label_row.addStretch(1)
        bri_label_row.addWidget(QLabel(i18n.t("output.group_brightness")))
        bri_label_row.addStretch(1)
        outer.addLayout(bri_label_row)

        # LED-Slider
        led_row = QHBoxLayout()
        self.bright_led = QSlider(Qt.Orientation.Horizontal)
        self.bright_led.setRange(0, 128)
        self.bright_led.setValue(128)
        self.bright_led.sliderReleased.connect(
            lambda: self.backend.set_brightness("led", self.bright_led.value())
        )
        led_row.addWidget(QLabel(i18n.t("output.label_brightness_led")))
        led_row.addWidget(self.bright_led, 1)
        outer.addLayout(led_row)

        # MFD-Slider
        mfd_row = QHBoxLayout()
        self.bright_mfd = QSlider(Qt.Orientation.Horizontal)
        self.bright_mfd.setRange(0, 128)
        self.bright_mfd.setValue(128)
        self.bright_mfd.sliderReleased.connect(
            lambda: self.backend.set_brightness("mfd", self.bright_mfd.value())
        )
        mfd_row.addWidget(QLabel(i18n.t("output.label_brightness_mfd")))
        mfd_row.addWidget(self.bright_mfd, 1)
        outer.addLayout(mfd_row)

        return box

    # -- Verfügbarkeit -----------------------------------------------------

    def _refresh_availability(self) -> None:
        avail = self.backend.available
        for combo in self._led_boxes.values():
            combo.setEnabled(avail)
        self.clutch_checkbox.setEnabled(avail)

    # -- i18n --------------------------------------------------------------

    def retranslate(self) -> None:
        layout = self.layout()
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.hide()
                w.setParent(None)
        self._led_boxes.clear()
        clutch_checked = self.clutch_checkbox.isChecked()
        led_states = {k: combo.currentText() for k, combo in self._led_boxes.items()}

        layout.addWidget(self._build_leds())
        layout.addWidget(self._build_mfd())
        layout.addWidget(self._build_clutch())
        layout.addWidget(self._build_test())
        layout.addStretch(1)

        self.clutch_checkbox.blockSignals(True)
        self.clutch_checkbox.setChecked(clutch_checked)
        self.clutch_checkbox.blockSignals(False)
        for k, state in led_states.items():
            combo = self._led_boxes.get(k)
            if combo:
                combo.blockSignals(True)
                idx = combo.findText(state)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
                combo.blockSignals(False)
        self._refresh_availability()
