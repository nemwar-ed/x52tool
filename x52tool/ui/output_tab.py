"""Reiter 'LED / MFD': Ausgabe ueber das libx52-CLI.

Bewusst als duenne Huelle gebaut. Die Kommandovorlagen stehen unten in der
Oberflaeche und sind editierbar, weil die genaue Syntax von der
installierten libx52-Version abhaengt. Jeder Aufruf wird im Protokoll mit
Rueckgabewert angezeigt - einmal gegen `x52cli --help` abgleichen, Vorlage
korrigieren, speichern.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ..output import MFD_LINES, MFD_WIDTH, PRO_LEDS, Backend, CommandResult, detect_binary


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

    def _build(self) -> None:
        self.status = QLabel()
        self.status.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.addWidget(self.status)
        layout.addWidget(self._build_leds())
        layout.addWidget(self._build_mfd())
        layout.addWidget(self._build_backend())
        layout.addWidget(self._build_log(), 1)

    def _build_leds(self) -> QGroupBox:
        box = QGroupBox("LEDs")
        grid = QGridLayout(box)
        for i, (key, label, states) in enumerate(PRO_LEDS):
            combo = QComboBox()
            combo.addItems(states)
            combo.currentTextChanged.connect(
                lambda state, k=key: self._log_one(self.backend.set_led(k, state))
            )
            grid.addWidget(QLabel(label), i // 3, (i % 3) * 2)
            grid.addWidget(combo, i // 3, (i % 3) * 2 + 1)
            self._led_boxes[key] = combo

        row = QHBoxLayout()
        btn_sweep = QPushButton("Alle LEDs durchtesten")
        btn_on = QPushButton("Alle an")
        btn_off = QPushButton("Alle aus")
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
        row.addWidget(QLabel("Helligkeit"))
        row.addWidget(bright)

        wrapper = QVBoxLayout()
        wrapper.addLayout(row)
        holder = QWidget()
        holder.setLayout(wrapper)
        grid.addWidget(holder, (len(PRO_LEDS) + 2) // 3, 0, 1, 6)
        return box

    def _build_mfd(self) -> QGroupBox:
        box = QGroupBox(f"MFD ({MFD_LINES} Zeilen zu {MFD_WIDTH} Zeichen)")
        form = QFormLayout(box)
        for line in range(MFD_LINES):
            edit = QLineEdit()
            edit.setMaxLength(MFD_WIDTH)
            edit.editingFinished.connect(
                lambda l=line, e=edit: self._log_one(self.backend.set_mfd_line(l, e.text()))
            )
            form.addRow(f"Zeile {line}", edit)
            self._mfd_edits.append(edit)

        row = QHBoxLayout()
        btn_test = QPushButton("Testmuster senden")
        btn_clear = QPushButton("MFD leeren")
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
        row.addWidget(QLabel("Helligkeit"))
        row.addWidget(bright)
        form.addRow(row)
        return box

    def _build_backend(self) -> QGroupBox:
        box = QGroupBox("Aufruf des libx52-CLI")
        form = QFormLayout(box)

        cfg = self.settings.backend
        self.edit_binary = QLineEdit(cfg.binary)
        self.edit_led = QLineEdit(cfg.led)
        self.edit_mfd = QLineEdit(cfg.mfd)
        self.edit_bri = QLineEdit(cfg.brightness)

        form.addRow("Programm", self.edit_binary)
        form.addRow("LED", self.edit_led)
        form.addRow("MFD", self.edit_mfd)
        form.addRow("Helligkeit", self.edit_bri)

        hint = QLabel(
            "Platzhalter: {bin} {led} {state} {line} {text} {target} {value}. "
            "Die Vorlage wird erst in Tokens zerlegt, dann eingesetzt - "
            "MFD-Text mit Leerzeichen bleibt also ein Argument."
        )
        hint.setWordWrap(True)
        form.addRow(hint)

        row = QHBoxLayout()
        btn_detect = QPushButton("Programm suchen")
        btn_save = QPushButton("Uebernehmen und speichern")
        btn_detect.clicked.connect(self._detect)
        btn_save.clicked.connect(self._save_backend)
        row.addWidget(btn_detect)
        row.addWidget(btn_save)
        row.addStretch(1)
        form.addRow(row)
        return box

    def _build_log(self) -> QGroupBox:
        box = QGroupBox("Protokoll")
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        font = self.log.font()
        font.setFamily("monospace")
        self.log.setFont(font)
        layout = QVBoxLayout(box)
        layout.addWidget(self.log)
        return box

    # -- Aktionen ----------------------------------------------------------

    def _detect(self) -> None:
        found = detect_binary()
        if found:
            self.edit_binary.setText(found)
            self._save_backend()
        else:
            self.log.appendPlainText(
                "Kein x52ctl oder x52cli im PATH. libx52 installieren "
                "(PPA, AUR oder aus dem Quelltext)."
            )

    def _save_backend(self) -> None:
        cfg = self.settings.backend
        cfg.binary = self.edit_binary.text().strip()
        cfg.led = self.edit_led.text()
        cfg.mfd = self.edit_mfd.text()
        cfg.brightness = self.edit_bri.text()
        self.backend = Backend(cfg)
        path = self.settings.save()
        self.log.appendPlainText(f"Einstellungen gespeichert in {path}")
        self._refresh_availability()

    def _refresh_availability(self) -> None:
        if self.backend.available:
            self.status.setText(
                f"Ausgabe geht ueber {self.backend.config.binary}. "
                "Laeuft der Daemon x52d, sollte hier dessen Client stehen - "
                "zwei Prozesse gleichzeitig auf MFD und LEDs vertraegt das Geraet nicht."
            )
        else:
            self.status.setText(
                "Kein libx52-CLI gefunden. LEDs und MFD des X52 Pro laufen nicht "
                "ueber evdev, sondern ueber USB-Control-Transfers - dafuer wird "
                "libx52 gebraucht. Unten 'Programm suchen' oder den Pfad eintragen."
            )
        enabled = self.backend.available
        for combo in self._led_boxes.values():
            combo.setEnabled(enabled)
        for edit in self._mfd_edits:
            edit.setEnabled(enabled)

    # -- Protokoll ---------------------------------------------------------

    def _log_one(self, result: CommandResult) -> None:
        self.log.appendPlainText(result.summary())

    def _log_many(self, results: list[CommandResult]) -> None:
        failures = [r for r in results if not r.ok]
        for result in results:
            self.log.appendPlainText(result.summary())
        self.log.appendPlainText(
            f"-- {len(results)} Befehle, {len(failures)} fehlgeschlagen"
        )
