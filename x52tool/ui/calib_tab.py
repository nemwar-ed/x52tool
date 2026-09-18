"""Reiter 'Kalibrierung': Deadzone, Bereich und Fuzz schreiben.

Schreibt ueber EVIOCSABS direkt in den Kernel. Das gilt nur bis zum
naechsten Abziehen des Sticks - deshalb der Export als udev-Regel.

Ob eine hier gesetzte Deadzone im Spiel ankommt, haengt am Konsumenten:
ueber /dev/input/jsX wird `flat` angewendet, ueber /dev/input/eventN ist
es fuer viele Clients nur eine Angabe. Wer unter Proton spielt, prueft
das einmal mit einem absurd grossen Wert, bevor er sich darauf verlaesst.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..analysis import (
    udev_rule_evdev_joystick,
    udev_rule_permissions,
    udev_rule_selfcall,
)
from ..device import AbsInfo, X52Device

COLUMNS = ["Achse", "Minimum", "Maximum", "Fuzz", "Deadzone (flat)", "Deadzone %"]


class TextDialog(QDialog):
    def __init__(self, title: str, text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(760, 420)
        edit = QPlainTextEdit(text)
        edit.setReadOnly(False)
        font = edit.font()
        font.setFamily("monospace")
        edit.setFont(font)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout = QVBoxLayout(self)
        layout.addWidget(edit)
        layout.addWidget(buttons)


class CalibrationTab(QWidget):
    calibrationChanged = pyqtSignal()

    def __init__(self, settings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.device: X52Device | None = None
        self._spins: dict[int, dict[str, QSpinBox]] = {}
        self._build()

    # -- Aufbau ------------------------------------------------------------

    def _build(self) -> None:
        self.status = QLabel()
        self.status.setWordWrap(True)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)

        self.btn_reload = QPushButton("Vom Geraet lesen")
        self.btn_apply = QPushButton("Auf Geraet schreiben")
        self.btn_reset = QPushButton("Auf Kernel-Standard zurueck")
        self.btn_save = QPushButton("Als Profil speichern")
        self.btn_load = QPushButton("Profil laden")
        self.btn_udev = QPushButton("udev-Regel erzeugen")
        self.btn_rights = QPushButton("Rechte-Regel erzeugen")

        self.btn_reload.clicked.connect(self.reload_from_device)
        self.btn_apply.clicked.connect(self.apply_to_device)
        self.btn_reset.clicked.connect(self.reset_to_baseline)
        self.btn_save.clicked.connect(self.save_profile)
        self.btn_load.clicked.connect(self.load_profile)
        self.btn_udev.clicked.connect(self.show_udev_rule)
        self.btn_rights.clicked.connect(self.show_permission_rule)

        row1 = QHBoxLayout()
        for btn in (self.btn_reload, self.btn_apply, self.btn_reset):
            row1.addWidget(btn)
        row1.addStretch(1)

        row2 = QHBoxLayout()
        for btn in (self.btn_save, self.btn_load, self.btn_udev, self.btn_rights):
            row2.addWidget(btn)
        row2.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addWidget(self.status)
        layout.addWidget(self.table, 1)
        layout.addLayout(row1)
        layout.addLayout(row2)

    # -- Geraet ------------------------------------------------------------

    def set_device(self, device: X52Device | None) -> None:
        self.device = device
        self._spins.clear()
        self.table.setRowCount(0)
        enabled = device is not None
        for btn in (
            self.btn_reload,
            self.btn_apply,
            self.btn_reset,
            self.btn_save,
            self.btn_load,
            self.btn_udev,
            self.btn_rights,
        ):
            btn.setEnabled(enabled)
        if device is None:
            self.status.setText("Kein Geraet gewaehlt.")
            return

        if device.writable:
            self.status.setText(
                "Aenderungen wirken sofort und gelten bis zum Abziehen des Sticks. "
                "Fuer dauerhaft: unten eine udev-Regel erzeugen."
            )
        else:
            self.status.setText(
                f"Nur Lesezugriff auf {device.path}. Schreiben schlaegt fehl. "
                "Mit 'Rechte-Regel erzeugen' bekommst du eine udev-Regel, die "
                "genau diesem Geraet Schreibrecht gibt."
            )
            self.btn_apply.setEnabled(False)
            self.btn_reset.setEnabled(False)

        self._populate(device)

    def _populate(self, device: X52Device) -> None:
        rows = [ax for ax in device.axes]
        self.table.setRowCount(len(rows))
        for row, axis in enumerate(rows):
            name = QTableWidgetItem(f"{axis.label}   (ABS 0x{axis.code:02x})")
            name.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.table.setItem(row, 0, name)

            spins: dict[str, QSpinBox] = {}
            for col, field in enumerate(("minimum", "maximum", "fuzz", "flat"), start=1):
                spin = QSpinBox()
                spin.setRange(-2_147_483, 2_147_483)
                spin.setValue(getattr(axis.info, field))
                spin.setEnabled(device.writable and not axis.is_digital)
                spin.valueChanged.connect(self._update_percent_column)
                self.table.setCellWidget(row, col, spin)
                spins[field] = spin
            self._spins[axis.code] = spins

            pct = QTableWidgetItem("")
            pct.setFlags(Qt.ItemFlag.ItemIsEnabled)
            pct.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 5, pct)
        self._update_percent_column()

    def _update_percent_column(self) -> None:
        if self.device is None:
            return
        for row, axis in enumerate(self.device.axes):
            spins = self._spins.get(axis.code)
            if not spins:
                continue
            span = spins["maximum"].value() - spins["minimum"].value()
            flat = spins["flat"].value()
            text = "-" if span <= 0 else f"{200.0 * flat / span:.2f} %"
            item = self.table.item(row, 5)
            if item is not None:
                item.setText(text)

    # -- Aktionen ----------------------------------------------------------

    def current_values(self) -> dict[int, AbsInfo]:
        result: dict[int, AbsInfo] = {}
        if self.device is None:
            return result
        for axis in self.device.axes:
            spins = self._spins.get(axis.code)
            if not spins:
                continue
            info = axis.info.copy()
            info.minimum = spins["minimum"].value()
            info.maximum = spins["maximum"].value()
            info.fuzz = spins["fuzz"].value()
            info.flat = spins["flat"].value()
            result[axis.code] = info
        return result

    def reload_from_device(self) -> None:
        if self.device is None:
            return
        self.device.refresh_absinfo()
        self._populate(self.device)
        self.calibrationChanged.emit()

    def apply_to_device(self) -> None:
        if self.device is None:
            return
        try:
            self.device.apply_absinfo(self.current_values())
        except PermissionError:
            QMessageBox.warning(
                self,
                "Schreiben fehlgeschlagen",
                f"Kein Schreibrecht auf {self.device.path}.\n\n"
                "Erzeuge unten eine Rechte-Regel oder starte das Programm einmal "
                "mit erhoehten Rechten, um den Effekt zu testen.",
            )
            return
        except OSError as exc:
            QMessageBox.warning(self, "Schreiben fehlgeschlagen", str(exc))
            return
        self._populate(self.device)
        self.calibrationChanged.emit()

    def reset_to_baseline(self) -> None:
        if self.device is None:
            return
        try:
            self.device.restore_baseline()
        except OSError as exc:
            QMessageBox.warning(self, "Zuruecksetzen fehlgeschlagen", str(exc))
            return
        self._populate(self.device)
        self.calibrationChanged.emit()

    def apply_suggestions(self, suggestions: dict[int, int]) -> None:
        """Wird vom Analyse-Reiter aufgerufen."""
        for code, flat in suggestions.items():
            spins = self._spins.get(code)
            if spins:
                spins["flat"].setValue(flat)
        self._update_percent_column()

    # -- Profile und Export ------------------------------------------------

    def save_profile(self) -> None:
        if self.device is None:
            return
        self.settings.set_profile(self.device.usb_id, self.current_values())
        path = self.settings.save()
        QMessageBox.information(self, "Profil gespeichert", f"Abgelegt in {path}")

    def load_profile(self) -> None:
        if self.device is None:
            return
        stored = self.settings.profile(self.device.usb_id)
        if not stored:
            QMessageBox.information(
                self, "Kein Profil", f"Fuer {self.device.usb_id} ist nichts gespeichert."
            )
            return
        for code, info in stored.items():
            spins = self._spins.get(code)
            if spins:
                for field in ("minimum", "maximum", "fuzz", "flat"):
                    spins[field].setValue(getattr(info, field))
        self._update_percent_column()

    def show_udev_rule(self) -> None:
        if self.device is None:
            return
        # Vorher die Tabellenwerte in die Achsen uebernehmen, damit die Regel
        # das zeigt, was gerade eingestellt ist.
        values = self.current_values()
        for axis in self.device.axes:
            if axis.code in values:
                axis.info = values[axis.code]
        text = (
            udev_rule_evdev_joystick(self.device, self.device.axes)
            + "\n\n# --- Alternative ohne evdev-joystick ---\n\n"
            + udev_rule_selfcall(self.device)
        )
        TextDialog("udev-Regel", text, self).exec()

    def show_permission_rule(self) -> None:
        if self.device is None:
            return
        TextDialog("Rechte-Regel", udev_rule_permissions(self.device), self).exec()
