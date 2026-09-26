"""Reiter 'LED / MFD': Ausgabe ueber das libx52-CLI.

Bewusst als duenne Huelle gebaut. Die Kommandovorlagen stehen unten in der
Oberflaeche und sind editierbar, weil die genaue Syntax von der
installierten libx52-Version abhaengt. Jeder Aufruf wird im Protokoll mit
Rueckgabewert angezeigt - einmal gegen `x52cli --help` abgleichen, Vorlage
korrigieren, speichern.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
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
        self.backend = Backend(settings.backend)
        self._led_boxes: dict[str, QComboBox] = {}
        self._mfd_edits: list[QLineEdit] = []
        self._build()
        self._refresh_availability()

    # -- Aufbau ------------------------------------------------------------

    def _build_status(self) -> QLabel:
        lbl = QLabel()
        lbl.setWordWrap(True)
        return lbl

    def _build(self) -> None:
        self.status = self._build_status()

        layout = QVBoxLayout(self)
        layout.addWidget(self.status)
        layout.addWidget(self._build_leds())
        layout.addWidget(self._build_mfd())
        layout.addWidget(self._build_clutch())
        layout.addWidget(self._build_backend())
        layout.addWidget(self._build_test())

    def _build_leds(self) -> QGroupBox:
        box = QGroupBox(i18n.t("output.group_leds"))
        grid = QGridLayout(box)
        leds = PRO_LEDS()
        for i, (key, label, states) in enumerate(leds):
            combo = QComboBox()
            combo.addItems(states)
            combo.currentTextChanged.connect(
                lambda state, k=key: self._log_one(self.backend.set_led(k, state))
            )
            grid.addWidget(QLabel(label), i // 3, (i % 3) * 2)
            grid.addWidget(combo, i // 3, (i % 3) * 2 + 1)
            self._led_boxes[key] = combo

        row = QHBoxLayout()
        btn_sweep = QPushButton(i18n.t("output.btn_sweep"))
        btn_on    = QPushButton(i18n.t("output.btn_all_on"))
        btn_off   = QPushButton(i18n.t("output.btn_all_off"))
        btn_sweep.clicked.connect(lambda: self._log_many(self.backend.led_sweep()))
        btn_on.clicked.connect(lambda: self._log_many(self.backend.all_leds("green")))
        btn_off.clicked.connect(lambda: self._log_many(self.backend.all_leds("off")))
        row.addWidget(btn_sweep)
        row.addWidget(btn_on)
        row.addWidget(btn_off)
        row.addStretch(1)

        bright = QSlider(Qt.Orientation.Horizontal)
        bright.setRange(0, 128)
        bright.setValue(128)
        bright.sliderReleased.connect(
            lambda: self._log_one(self.backend.set_brightness("led", bright.value()))
        )
        row.addWidget(QLabel(i18n.t("output.label_brightness")))
        row.addWidget(bright)

        wrapper = QVBoxLayout()
        wrapper.addLayout(row)
        holder = QWidget()
        holder.setLayout(wrapper)
        grid.addWidget(holder, (len(leds) + 2) // 3, 0, 1, 6)
        return box

    def _build_mfd(self) -> QGroupBox:
        box = QGroupBox(i18n.t("output.group_mfd", lines=MFD_LINES, width=MFD_WIDTH))
        form = QFormLayout(box)
        for line in range(MFD_LINES):
            edit = QLineEdit()
            edit.setMaxLength(MFD_WIDTH)
            edit.editingFinished.connect(
                lambda l=line, e=edit: self._log_one(self.backend.set_mfd_line(l, e.text()))
            )
            form.addRow(i18n.t("output.mfd_row_label", line=line), edit)
            self._mfd_edits.append(edit)

        row = QHBoxLayout()
        btn_test  = QPushButton(i18n.t("output.btn_mfd_test"))
        btn_clear = QPushButton(i18n.t("output.btn_mfd_clear"))
        btn_test.clicked.connect(lambda: self._log_many(self.backend.mfd_test()))
        btn_clear.clicked.connect(
            lambda: self._log_many(
                [self.backend.set_mfd_line(i, "") for i in range(MFD_LINES)]
            )
        )
        bright = QSlider(Qt.Orientation.Horizontal)
        bright.setRange(0, 128)
        bright.setValue(128)
        bright.sliderReleased.connect(
            lambda: self._log_one(self.backend.set_brightness("mfd", bright.value()))
        )
        row.addWidget(btn_test)
        row.addWidget(btn_clear)
        row.addWidget(QLabel(i18n.t("output.label_brightness")))
        row.addWidget(bright)
        form.addRow(row)
        return box

    def _build_clutch(self) -> QGroupBox:
        box = QGroupBox(i18n.t("output.group_clutch"))
        layout = QVBoxLayout(box)

        explain = QLabel(i18n.t("output.clutch_explain"))
        explain.setWordWrap(True)
        layout.addWidget(explain)

        self.clutch_checkbox = QCheckBox(i18n.t("output.clutch_checkbox"))
        self.clutch_checkbox.toggled.connect(
            lambda checked: self._log_one(self.backend.set_clutch(checked))
        )
        layout.addWidget(self.clutch_checkbox)
        return box

    def _build_backend(self) -> QGroupBox:
        box = QGroupBox(i18n.t("output.group_backend"))
        form = QFormLayout(box)

        cfg = self.settings.backend
        self.edit_binary = QLineEdit(cfg.binary)
        self.edit_led    = QLineEdit(cfg.led)
        self.edit_mfd    = QLineEdit(cfg.mfd)
        self.edit_bri    = QLineEdit(cfg.brightness)
        self.edit_clutch = QLineEdit(cfg.clutch)

        form.addRow(i18n.t("output.backend_label_binary"), self.edit_binary)
        form.addRow(i18n.t("output.backend_label_led"),    self.edit_led)
        form.addRow(i18n.t("output.backend_label_mfd"),    self.edit_mfd)
        form.addRow(i18n.t("output.backend_label_bri"),    self.edit_bri)
        form.addRow(i18n.t("output.backend_label_clutch"), self.edit_clutch)

        hint = QLabel(i18n.t("output.backend_hint"))
        hint.setWordWrap(True)
        form.addRow(hint)

        row = QHBoxLayout()
        btn_detect = QPushButton(i18n.t("output.btn_detect"))
        btn_save   = QPushButton(i18n.t("output.btn_save_backend"))
        btn_detect.clicked.connect(self._detect)
        btn_save.clicked.connect(self._save_backend)
        row.addWidget(btn_detect)
        row.addWidget(btn_save)
        row.addStretch(1)
        form.addRow(row)
        return box

    def _build_test(self) -> QGroupBox:
        box = QGroupBox(i18n.t("output.group_test"))
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
        """Baut die Liste aller Testschritte auf.

        Reihenfolge: Flackern → Stick-LEDs → Throttle-LEDs → MFD → alles grün
        """
        steps = []

        # LEDs nach Gerät geordnet
        STICK_KEYS    = ["fire", "a", "b", "pov", "t1", "t2", "t3"]
        THROTTLE_KEYS = ["e", "d", "clutch", "throttle"]

        # Lookup: key → states
        led_map = {key: states for key, _label, states in PRO_LEDS()}

        # --- Flackern: Helligkeit 0 → 100 (schnell) ---
        for target in ("mfd", "led"):
            steps.append(("brightness", target, 0))
        for target in ("mfd", "led"):
            steps.append(("brightness", target, 128))

        # --- Alle LEDs aus ---
        for key in STICK_KEYS + THROTTLE_KEYS:
            if key in led_map:
                steps.append(("led", key, "off"))

        # --- Stick-LEDs einzeln durchtesten ---
        for key in STICK_KEYS:
            states = led_map.get(key, ())
            for state in states[1:]:          # off überspringen
                steps.append(("led", key, state))
            steps.append(("led", key, "off"))

        # --- Throttle-LEDs einzeln durchtesten ---
        for key in THROTTLE_KEYS:
            states = led_map.get(key, ())
            for state in states[1:]:
                steps.append(("led", key, state))
            steps.append(("led", key, "off"))

        # --- MFD leeren ---
        for line in range(MFD_LINES):
            steps.append(("mfd", line, ""))

        # --- MFD Zeichentest: Zeile für Zeile, Zeichen für Zeichen ---
        for line in range(MFD_LINES):
            current = [" "] * MFD_WIDTH
            for col in range(MFD_WIDTH):
                current[col] = "\xff" if col % 2 == 0 else "\x00"
                steps.append(("mfd", line, "".join(current)))

        # --- MFD leeren ---
        for line in range(MFD_LINES):
            steps.append(("mfd", line, ""))

        # --- Ende: alle LEDs grün / an ---
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
        self._test_timer.start(80)  # 80ms pro Schritt für LED-Sweep; Flackern schneller

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
            # Flackern: erste 4 Schritte schneller
            if self._test_idx < 4:
                self._test_timer.setInterval(80)
            else:
                self._test_timer.setInterval(80)
        elif kind == "led":
            self.backend.set_led(step[1], step[2])
            self._test_timer.setInterval(180)   # langsamer als bisheriger Sweep
        elif kind == "mfd":
            self.backend.set_mfd_line(step[1], step[2])
            self._test_timer.setInterval(80)

        self._test_idx += 1
        pct = int(self._test_idx / self._test_total * 100)
        self.test_progress.setValue(pct)

    # -- Protokoll (vereinfacht, kein UI mehr) -----------------------------

    def _log_one(self, result: CommandResult) -> None:
        pass  # Log-UI entfernt; Fehler werden ignoriert

    def _log_many(self, results: list[CommandResult]) -> None:
        pass  # Log-UI entfernt

    # -- Aktionen ----------------------------------------------------------

    def _detect(self) -> None:
        found = detect_binary()
        if found:
            self.edit_binary.setText(found)
            self._save_backend()
        else:
            self.log.appendPlainText(i18n.t("output.log_no_binary"))

    def _save_backend(self) -> None:
        cfg = self.settings.backend
        cfg.binary     = self.edit_binary.text().strip()
        cfg.led        = self.edit_led.text()
        cfg.mfd        = self.edit_mfd.text()
        cfg.brightness = self.edit_bri.text()
        cfg.clutch     = self.edit_clutch.text()
        self.backend = Backend(cfg)
        path = self.settings.save()
        self.log.appendPlainText(i18n.t("output.log_settings_saved", path=path))
        self._refresh_availability()

    def _refresh_availability(self) -> None:
        if self.backend.available:
            self.status.setText(
                i18n.t("output.status_available", binary=self.backend.config.binary)
            )
        else:
            self.status.setText(i18n.t("output.status_unavailable"))
        enabled = self.backend.available
        for combo in self._led_boxes.values():
            combo.setEnabled(enabled)
        for edit in self._mfd_edits:
            edit.setEnabled(enabled)
        self.clutch_checkbox.setEnabled(enabled)

    # -- Protokoll ---------------------------------------------------------

    def _log_one(self, result: CommandResult) -> None:
        self.log.appendPlainText(result.summary())

    def _log_many(self, results: list[CommandResult]) -> None:
        failures = [r for r in results if not r.ok]
        for result in results:
            self.log.appendPlainText(result.summary())
        self.log.appendPlainText(
            i18n.t("output.log_summary", count=len(results), failures=len(failures))
        )

    def retranslate(self) -> None:
        """Beschriftungen nach Sprachwechsel aktualisieren."""
        # Den ganzen Tab neu aufbauen ist hier am saubersten, da Gruppen-
        # boxen und FormLayout-Labels keine einfachen setter haben.
        # Zustand (Log, Backend-Felder) sichern und wiederherstellen.
        binary = self.edit_binary.text()
        led_t   = self.edit_led.text()
        mfd_t   = self.edit_mfd.text()
        bri_t   = self.edit_bri.text()
        clutch_t = self.edit_clutch.text()
        clutch_checked = self.clutch_checkbox.isChecked()
        led_states = {k: combo.currentText() for k, combo in self._led_boxes.items()}

        # Widgets aus dem bestehenden Layout entfernen
        layout = self.layout()
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.hide()
                w.setParent(None)
        self._led_boxes.clear()
        self._mfd_edits.clear()

        # Neu aufbauen (ohne neues Top-Level-Layout)
        self.status = self._build_status()
        layout.addWidget(self.status)
        layout.addWidget(self._build_leds())
        layout.addWidget(self._build_mfd())
        layout.addWidget(self._build_clutch())
        layout.addWidget(self._build_backend())
        layout.addWidget(self._build_test())

        # Zustand wiederherstellen
        self.edit_binary.setText(binary)
        self.edit_led.setText(led_t)
        self.edit_mfd.setText(mfd_t)
        self.edit_bri.setText(bri_t)
        self.edit_clutch.setText(clutch_t)
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
