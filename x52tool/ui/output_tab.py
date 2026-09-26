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
    QProgressBar,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ..output import MFD_LINES, MFD_WIDTH, PRO_LEDS, Backend, CommandResult, detect_binary
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
        self.status = QLabel()
        self.status.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.addWidget(self.status)
        layout.addWidget(self._build_leds())
        layout.addWidget(self._build_clutch())
        layout.addWidget(self._build_brightness())
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

        btn_row = QHBoxLayout()
        btn_sweep = QPushButton(i18n.t("output.btn_sweep"))
        btn_on    = QPushButton(i18n.t("output.btn_all_on"))
        btn_off   = QPushButton(i18n.t("output.btn_all_off"))
        btn_sweep.clicked.connect(lambda: self.backend.led_sweep())
        btn_on.clicked.connect(lambda: self.backend.all_leds("green"))
        btn_off.clicked.connect(lambda: self.backend.all_leds("off"))
        btn_row.addWidget(btn_sweep)
        btn_row.addWidget(btn_on)
        btn_row.addWidget(btn_off)
        btn_row.addStretch(1)

        holder = QWidget()
        holder.setLayout(btn_row)
        grid.addWidget(holder, (len(leds) + 2) // 3, 0, 1, 6)
        return box

    def _build_clutch(self) -> QGroupBox:
        box    = QGroupBox(i18n.t("output.group_clutch"))
        layout = QVBoxLayout(box)
        explain = QLabel(i18n.t("output.clutch_explain"))
        explain.setWordWrap(True)
        layout.addWidget(explain)
        self.clutch_checkbox = QCheckBox(i18n.t("output.clutch_checkbox"))
        self.clutch_checkbox.toggled.connect(
            lambda checked: self.backend.set_clutch(checked)
        )
        layout.addWidget(self.clutch_checkbox)
        return box

    def _build_brightness(self) -> QGroupBox:
        box = QGroupBox(i18n.t("output.group_brightness"))
        row = QHBoxLayout(box)

        self.bright_led = QSlider(Qt.Orientation.Horizontal)
        self.bright_led.setRange(0, 128)
        self.bright_led.setValue(128)
        self.bright_led.sliderReleased.connect(
            lambda: self.backend.set_brightness("led", self.bright_led.value())
        )

        self.bright_mfd = QSlider(Qt.Orientation.Horizontal)
        self.bright_mfd.setRange(0, 128)
        self.bright_mfd.setValue(128)
        self.bright_mfd.sliderReleased.connect(
            lambda: self.backend.set_brightness("mfd", self.bright_mfd.value())
        )

        row.addWidget(QLabel(i18n.t("output.label_brightness_led")))
        row.addWidget(self.bright_led, 1)
        row.addWidget(QLabel(i18n.t("output.label_brightness_mfd")))
        row.addWidget(self.bright_mfd, 1)
        return box

    def _build_test(self) -> QGroupBox:
        box   = QGroupBox(i18n.t("output.group_test"))
        outer = QVBoxLayout(box)

        row = QHBoxLayout()
        row.addStretch(1)

        self.btn_test_all = QPushButton(i18n.t("output.btn_test_all"))
        self.btn_test_all.clicked.connect(self._start_full_test)
        row.addWidget(self.btn_test_all)

        self.test_progress = QProgressBar()
        self.test_progress.setRange(0, 100)
        self.test_progress.setValue(0)
        self.test_progress.setTextVisible(True)
        self.test_progress.setFixedWidth(300)
        row.addWidget(self.test_progress)

        row.addStretch(1)
        outer.addLayout(row)
        return box

    # -- Volltest ----------------------------------------------------------

    def _build_test_steps(self) -> list:
        steps = []
        STICK_KEYS    = ["fire", "a", "b", "pov", "t1", "t2", "t3"]
        THROTTLE_KEYS = ["e", "d", "clutch", "throttle"]
        led_map = {key: states for key, _label, states in PRO_LEDS()}

        # Flackern
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

        # MFD leeren
        for line in range(MFD_LINES):
            steps.append(("mfd", line, ""))

        # Ende: alles grün/an
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
        self.test_progress.setValue(0)
        self._test_timer = QTimer(self)
        self._test_timer.timeout.connect(self._run_test_step)
        self._test_timer.start(80)

    def _run_test_step(self) -> None:
        if self._test_idx >= self._test_total:
            self._test_timer.stop()
            self.test_progress.setValue(100)
            self.btn_test_all.setEnabled(True)
            return

        step = self._test_steps[self._test_idx]
        kind = step[0]

        if kind == "brightness":
            self.backend.set_brightness(step[1], step[2])
            self._test_timer.setInterval(80)
        elif kind == "led":
            self.backend.set_led(step[1], step[2])
            self._test_timer.setInterval(180)
        elif kind == "mfd":
            self.backend.set_mfd_line(step[1], step[2])
            self._test_timer.setInterval(800)

        self._test_idx += 1
        self.test_progress.setValue(int(self._test_idx / self._test_total * 100))

    # -- Verfügbarkeit -----------------------------------------------------

    def _refresh_availability(self) -> None:
        avail = self.backend.available
        if avail:
            self.status.setText(
                i18n.t("output.status_available", binary=self.backend.config.binary)
            )
        else:
            self.status.setText(i18n.t("output.status_unavailable"))
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

        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        layout.addWidget(self._build_leds())
        layout.addWidget(self._build_clutch())
        layout.addWidget(self._build_brightness())
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
