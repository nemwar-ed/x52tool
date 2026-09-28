"""Reiter 'LED / MFD': Ausgabe ueber das libx52-CLI."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
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
        self._load_mfd_settings()
        self._apply_clock()

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
        """Sendet clock- und date-Befehle ans Gerät und speichert die Einstellungen."""
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

        # Einstellungen speichern
        mfd = self.settings.mfd
        mfd.local_time = self.chk_local_time.isChecked()
        mfd.clock1_12h = self.chk_12h_clock1.isChecked()
        mfd.date_fmt   = self.combo_date_fmt.currentText()
        mfd.offset2    = off2
        mfd.clock2_12h = self.chk_12h_clock2.isChecked()
        mfd.offset3    = off3
        mfd.clock3_12h = self.chk_12h_clock3.isChecked()
        try:
            self.settings.save()
        except OSError:
            pass

    def _load_mfd_settings(self) -> None:
        """Lädt gespeicherte MFD-Einstellungen in die UI."""
        mfd = self.settings.mfd

        self.chk_local_time.blockSignals(True)
        self.chk_12h_clock1.blockSignals(True)
        self.combo_date_fmt.blockSignals(True)
        self.combo_offset2.blockSignals(True)
        self.chk_12h_clock2.blockSignals(True)
        self.combo_offset3.blockSignals(True)
        self.chk_12h_clock3.blockSignals(True)
        self.clutch_checkbox.blockSignals(True)
        self.clutch_latched.blockSignals(True)

        self.chk_local_time.setChecked(mfd.local_time)
        self.chk_12h_clock1.setChecked(mfd.clock1_12h)
        idx = self.combo_date_fmt.findText(mfd.date_fmt)
        if idx >= 0:
            self.combo_date_fmt.setCurrentIndex(idx)
        idx2 = self.combo_offset2.findData(mfd.offset2)
        if idx2 >= 0:
            self.combo_offset2.setCurrentIndex(idx2)
        self.chk_12h_clock2.setChecked(mfd.clock2_12h)
        idx3 = self.combo_offset3.findData(mfd.offset3)
        if idx3 >= 0:
            self.combo_offset3.setCurrentIndex(idx3)
        self.chk_12h_clock3.setChecked(mfd.clock3_12h)
        self.clutch_checkbox.setChecked(mfd.clutch_active)
        self.clutch_latched.setChecked(mfd.clutch_latched)

        self.chk_local_time.blockSignals(False)
        self.chk_12h_clock1.blockSignals(False)
        self.combo_date_fmt.blockSignals(False)
        self.combo_offset2.blockSignals(False)
        self.chk_12h_clock2.blockSignals(False)
        self.combo_offset3.blockSignals(False)
        self.chk_12h_clock3.blockSignals(False)
        self.clutch_checkbox.blockSignals(False)
        self.clutch_latched.blockSignals(False)

    def _build_clutch(self) -> QGroupBox:
        box    = QGroupBox(i18n.t("output.group_clutch"))
        layout = QHBoxLayout(box)
        self.clutch_checkbox = QCheckBox(i18n.t("output.clutch_checkbox"))
        self.clutch_checkbox.toggled.connect(self._on_clutch_changed)
        self.clutch_latched = QCheckBox(i18n.t("output.clutch_latched"))
        self.clutch_latched.toggled.connect(self._on_clutch_changed)
        layout.addStretch(1)
        layout.addWidget(self.clutch_checkbox)
        layout.addWidget(self.clutch_latched)
        layout.addStretch(1)
        return box

    def _on_clutch_changed(self) -> None:
        self.backend.set_clutch(self.clutch_checkbox.isChecked())
        self.settings.mfd.clutch_active  = self.clutch_checkbox.isChecked()
        self.settings.mfd.clutch_latched = self.clutch_latched.isChecked()
        try:
            self.settings.save()
        except OSError:
            pass

    def _build_test(self) -> QGroupBox:
        box   = QGroupBox(i18n.t("output.group_test"))
        outer = QVBoxLayout(box)

        # Buttons – Zeile 1: LEDs
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

        # Buttons – Zeile 2: MFD
        mfd_row = QHBoxLayout()
        btn_mfd_on  = QPushButton(i18n.t("output.btn_mfd_on"))
        btn_mfd_off = QPushButton(i18n.t("output.btn_mfd_off"))
        btn_mfd_on.clicked.connect(lambda: self.backend.set_brightness("mfd", 128))
        btn_mfd_off.clicked.connect(lambda: self.backend.set_brightness("mfd", 0))
        mfd_row.addStretch(1)
        mfd_row.addWidget(btn_mfd_on)
        mfd_row.addWidget(btn_mfd_off)
        mfd_row.addStretch(1)
        outer.addLayout(mfd_row)

        # Buttons – Zeile 3: Volltest
        full_row = QHBoxLayout()
        self.btn_test_all = QPushButton(i18n.t("output.btn_test_all"))
        self.btn_test_all.clicked.connect(self._start_full_test)
        full_row.addStretch(1)
        full_row.addWidget(self.btn_test_all)
        full_row.addStretch(1)
        outer.addLayout(full_row)

        outer.addSpacing(12)

        # Helligkeit-Label zentriert
        bri_label_row = QHBoxLayout()
        bri_label_row.addStretch(1)
        bri_label_row.addWidget(QLabel(i18n.t("output.group_brightness")))
        bri_label_row.addStretch(1)
        outer.addLayout(bri_label_row)

        # Beide Slider nebeneinander
        sliders_row = QHBoxLayout()
        self.bright_led = QSlider(Qt.Orientation.Horizontal)
        self.bright_led.setRange(0, 128)
        self.bright_led.setValue(128)
        self.bright_led.valueChanged.connect(
            lambda v: self.backend.set_brightness("led", v)
        )
        self.bright_mfd = QSlider(Qt.Orientation.Horizontal)
        self.bright_mfd.setRange(0, 128)
        self.bright_mfd.setValue(128)
        self.bright_mfd.valueChanged.connect(
            lambda v: self.backend.set_brightness("mfd", v)
        )
        sliders_row.addWidget(QLabel(i18n.t("output.label_brightness_led")))
        sliders_row.addWidget(self.bright_led, 1)
        sliders_row.addSpacing(16)
        sliders_row.addWidget(QLabel(i18n.t("output.label_brightness_mfd")))
        sliders_row.addWidget(self.bright_mfd, 1)
        outer.addLayout(sliders_row)

        return box

    # -- Volltest ----------------------------------------------------------

    def _build_test_steps(self) -> list:
        from ..output import PRO_LEDS, MFD_LINES
        steps = []
        STICK_KEYS    = ["fire", "a", "b", "pov", "t1", "t2", "t3"]
        THROTTLE_KEYS = ["e", "d", "clutch", "throttle"]
        led_map = {key: states for key, _label, states in PRO_LEDS()}

        # Blink
        for target in ("mfd", "led"):
            steps.append(("brightness", target, 0))
        for target in ("mfd", "led"):
            steps.append(("brightness", target, 128))

        # Alle aus
        for key in STICK_KEYS + THROTTLE_KEYS:
            if key in led_map:
                steps.append(("led", key, "off"))

        # Stick-LEDs
        for key in STICK_KEYS:
            for state in led_map.get(key, ())[1:]:
                steps.append(("led", key, state))
            steps.append(("led", key, "off"))

        # Throttle-LEDs
        for key in THROTTLE_KEYS:
            for state in led_map.get(key, ())[1:]:
                steps.append(("led", key, state))
            steps.append(("led", key, "off"))

        # MFD leeren
        for line in range(MFD_LINES):
            steps.append(("mfd", line, ""))

        # MFD ASCII-Test
        for line, text in enumerate([
            "ABCDEFGHIJKLMNOP",
            "abcdefghijklmnop",
            "0123456789!?+-.,",
        ]):
            steps.append(("mfd", line, text))

        # MFD Abschlusstext
        for line, text in enumerate([
            "X52 Professional",
            "  Space/Flight  ",
            "   H.O.T.A.S.  ",
        ]):
            steps.append(("mfd", line, text))

        # Alle LEDs grün/an
        for key in STICK_KEYS + THROTTLE_KEYS:
            states = led_map.get(key, ())
            final  = "green" if "green" in states else ("on" if "on" in states else states[-1])
            steps.append(("led", key, final))

        return steps

    def _start_full_test(self) -> None:
        if not self.backend.available:
            return
        self._test_steps = self._build_test_steps()
        self._test_idx   = 0
        self._test_total = len(self._test_steps)
        self.btn_test_all.setEnabled(False)
        self._test_timer = QTimer(self)
        self._test_timer.timeout.connect(self._run_test_step)
        self._test_timer.start(80)

    def _run_test_step(self) -> None:
        if self._test_idx >= self._test_total:
            self._test_timer.stop()
            self.btn_test_all.setEnabled(True)
            self._apply_clock()
            return
        step = self._test_steps[self._test_idx]
        kind = step[0]
        if kind == "brightness":
            self.backend.set_brightness(step[1], step[2])
            self._test_timer.setInterval(500)
        elif kind == "led":
            self.backend.set_led(step[1], step[2])
            self._test_timer.setInterval(180)
        elif kind == "mfd":
            self.backend.set_mfd_line(step[1], step[2])
            self._test_timer.setInterval(800)
        self._test_idx += 1

    # -- Verfügbarkeit -----------------------------------------------------

    def _refresh_availability(self) -> None:
        avail = self.backend.available
        for combo in self._led_boxes.values():
            combo.setEnabled(avail)
        self.clutch_checkbox.setEnabled(avail)
        self.btn_test_all.setEnabled(avail)

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
