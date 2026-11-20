"""Reiter 'LED / MFD': Ausgabe ueber x52ctl an den x52d-Daemon."""

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
from ..logger import get_logger
from .. import i18n
from .. import x52d_conf

log = get_logger("output")

# Oben in der Zeitzonen-Auswahl, danach alle uebrigen alphabetisch.
COMMON_TIMEZONES = (
    "UTC",
    "Europe/London",
    "Europe/Berlin",
    "Europe/Moscow",
    "America/New_York",
    "America/Chicago",
    "America/Denver",
    "America/Los_Angeles",
    "Asia/Tokyo",
    "Australia/Sydney",
)


def all_timezones() -> list[str]:
    try:
        from zoneinfo import available_timezones
        return sorted(tz for tz in available_timezones() if "/" in tz or tz == "UTC")
    except Exception:  # tzdata fehlt -> nur die festen Zonen
        return list(COMMON_TIMEZONES)


class OutputTab(QWidget):
    def __init__(self, settings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.backend  = Backend(settings.backend)
        self._led_boxes: dict[str, QComboBox] = {}
        self._build()
        self._refresh_availability()
        self._load_mfd_settings()
        self._load_hw_state()
        self._apply_clock()

    def _load_hw_state(self) -> None:
        """LED-Farben und Helligkeit aus der von x52d geladenen Datei anzeigen.

        Damit zeigt die Oberflaeche den Zustand, den das Geraet tatsaechlich
        hat, statt beim Start alles auf 'off' zu stellen.
        """
        values = x52d_conf.read_all()
        for key, combo in self._led_boxes.items():
            state = values.get(("led", key.lower()))
            idx = combo.findText(state) if state else -1
            if idx >= 0:
                combo.blockSignals(True)
                combo.setCurrentIndex(idx)
                combo.blockSignals(False)
        for target, slider in (("led", self.bright_led), ("mfd", self.bright_mfd)):
            raw = values.get(("brightness", target))
            try:
                value = int(raw) if raw is not None else None
            except ValueError:
                value = None
            if value is not None:
                slider.blockSignals(True)
                slider.setValue(max(0, min(128, value)))
                slider.blockSignals(False)

    def _set_all_leds(self, wanted: str) -> None:
        """Alle LEDs ueber die Auswahlfelder setzen – so bleiben Anzeige,
        Geraet und gespeicherte Konfiguration einheitlich."""
        for combo in self._led_boxes.values():
            states = [combo.itemText(i) for i in range(combo.count())]
            target = wanted if wanted in states else ("on" if wanted != "off" else "off")
            if target in states:
                combo.setCurrentText(target)

    def _restore_hw_state(self) -> None:
        """Nach dem Volltest den eingestellten Zustand wiederherstellen."""
        for key, combo in self._led_boxes.items():
            self.backend.set_led(key, combo.currentText(), persist=False)
        self.backend.set_brightness("led", self.bright_led.value(), persist=False)
        self.backend.set_brightness("mfd", self.bright_mfd.value(), persist=False)

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
        self.combo_tz2 = QComboBox()
        self._fill_tz_combo(self.combo_tz2)
        self.chk_12h_clock2 = QCheckBox(i18n.t("output.mfd_12h"))
        self.combo_tz2.currentIndexChanged.connect(self._apply_clock)
        self.chk_12h_clock2.toggled.connect(self._apply_clock)
        clock2_layout.addWidget(QLabel(i18n.t("output.mfd_timezone")))
        clock2_layout.addWidget(self.combo_tz2)
        clock2_layout.addWidget(self.chk_12h_clock2)

        # Uhr 3
        clock3_box = QGroupBox(i18n.t("output.mfd_clock3"))
        clock3_layout = QVBoxLayout(clock3_box)
        self.combo_tz3 = QComboBox()
        self._fill_tz_combo(self.combo_tz3)
        self.chk_12h_clock3 = QCheckBox(i18n.t("output.mfd_12h"))
        self.combo_tz3.currentIndexChanged.connect(self._apply_clock)
        self.chk_12h_clock3.toggled.connect(self._apply_clock)
        clock3_layout.addWidget(QLabel(i18n.t("output.mfd_timezone")))
        clock3_layout.addWidget(self.combo_tz3)
        clock3_layout.addWidget(self.chk_12h_clock3)

        clocks_row.addWidget(clock1_box, 1)
        clocks_row.addWidget(clock2_box, 1)
        clocks_row.addWidget(clock3_box, 1)
        layout.addLayout(clocks_row)
        return box

    def _fill_tz_combo(self, combo: QComboBox) -> None:
        """Zeitzonen: haeufige oben, darunter alle aus der tz-Datenbank."""
        for tz in COMMON_TIMEZONES:
            combo.addItem(tz, tz)
        combo.insertSeparator(combo.count())
        for tz in all_timezones():
            if tz not in COMMON_TIMEZONES:
                combo.addItem(tz, tz)
        combo.setCurrentIndex(0)  # UTC

    @staticmethod
    def _select_tz(combo: QComboBox, tz: str) -> None:
        idx = combo.findData(tz)
        if idx < 0:
            combo.addItem(tz, tz)
            idx = combo.findData(tz)
        combo.setCurrentIndex(idx)

    def _apply_clock(self) -> None:
        """Sendet die Uhr-Einstellungen an x52d, speichert sie dauerhaft in der
        von x52d geladenen Datei (siehe x52d_conf) und in der config.json."""
        fmt_map = {"DD-MM-YY": "ddmmyy", "MM-DD-YY": "mmddyy", "YY-MM-DD": "yymmdd"}
        date_fmt = fmt_map.get(self.combo_date_fmt.currentText(), "ddmmyy")

        tz2 = self.combo_tz2.currentData() or "UTC"
        tz3 = self.combo_tz3.currentData() or "UTC"

        if self.backend.available:
            results = self.backend.set_clock(
                primary_local=self.chk_local_time.isChecked(),
                formats=(
                    self.chk_12h_clock1.isChecked(),
                    self.chk_12h_clock2.isChecked(),
                    self.chk_12h_clock3.isChecked(),
                ),
                date_fmt=date_fmt,
                tz2=tz2,
                tz3=tz3,
            )
            for res in results:
                if not res.ok:
                    log.warning("Uhr-Einstellung fehlgeschlagen: %s", res.summary())

        # Einstellungen speichern
        mfd = self.settings.mfd
        mfd.local_time = self.chk_local_time.isChecked()
        mfd.clock1_12h = self.chk_12h_clock1.isChecked()
        mfd.date_fmt   = self.combo_date_fmt.currentText()
        mfd.tz2        = tz2
        mfd.clock2_12h = self.chk_12h_clock2.isChecked()
        mfd.tz3        = tz3
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
        self.combo_tz2.blockSignals(True)
        self.chk_12h_clock2.blockSignals(True)
        self.combo_tz3.blockSignals(True)
        self.chk_12h_clock3.blockSignals(True)
        self.clutch_checkbox.blockSignals(True)
        self.clutch_latched.blockSignals(True)

        self.chk_local_time.setChecked(mfd.local_time)
        self.chk_12h_clock1.setChecked(mfd.clock1_12h)
        idx = self.combo_date_fmt.findText(mfd.date_fmt)
        if idx >= 0:
            self.combo_date_fmt.setCurrentIndex(idx)
        self._select_tz(self.combo_tz2, mfd.tz2)
        self.chk_12h_clock2.setChecked(mfd.clock2_12h)
        self._select_tz(self.combo_tz3, mfd.tz3)
        self.chk_12h_clock3.setChecked(mfd.clock3_12h)
        self.clutch_checkbox.setChecked(mfd.clutch_active)
        self.clutch_latched.setChecked(mfd.clutch_latched)

        self.chk_local_time.blockSignals(False)
        self.chk_12h_clock1.blockSignals(False)
        self.combo_date_fmt.blockSignals(False)
        self.combo_tz2.blockSignals(False)
        self.chk_12h_clock2.blockSignals(False)
        self.combo_tz3.blockSignals(False)
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
        btn_on.clicked.connect(lambda: self._set_all_leds("green"))
        btn_off.clicked.connect(lambda: self._set_all_leds("off"))
        btn_row.addStretch(1)
        btn_row.addWidget(btn_on)
        btn_row.addWidget(btn_off)
        btn_row.addStretch(1)
        outer.addLayout(btn_row)

        # Buttons – Zeile 2: MFD
        mfd_row = QHBoxLayout()
        btn_mfd_on  = QPushButton(i18n.t("output.btn_mfd_on"))
        btn_mfd_off = QPushButton(i18n.t("output.btn_mfd_off"))
        btn_mfd_on.clicked.connect(lambda: self.bright_mfd.setValue(128))
        btn_mfd_off.clicked.connect(lambda: self.bright_mfd.setValue(0))
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
            self._restore_hw_state()
            self._apply_clock()
            return
        step = self._test_steps[self._test_idx]
        kind = step[0]
        if kind == "brightness":
            self.backend.set_brightness(step[1], step[2], persist=False)
            self._test_timer.setInterval(500)
        elif kind == "led":
            self.backend.set_led(step[1], step[2], persist=False)
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
        led_states = {k: combo.currentText() for k, combo in self._led_boxes.items()}
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.hide()
                w.setParent(None)
        self._led_boxes.clear()

        layout.addWidget(self._build_leds())
        layout.addWidget(self._build_mfd())
        layout.addWidget(self._build_clutch())
        layout.addWidget(self._build_test())
        layout.addStretch(1)

        self._load_mfd_settings()
        self._load_hw_state()
        for k, state in led_states.items():
            combo = self._led_boxes.get(k)
            if combo:
                combo.blockSignals(True)
                idx = combo.findText(state)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
                combo.blockSignals(False)
        self._refresh_availability()
