"""Hauptfenster: Geraetewahl, Event-Pumpe, Reiter."""

from __future__ import annotations

import sys

from PyQt6.QtCore import QSocketNotifier, Qt, QTimer
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import __version__
from ..config import Settings
from ..device import DeviceState, X52Device, find_related_nodes, scan
from .analysis_tab import AnalysisTab
from .calib_tab import CalibrationTab
from .live_tab import LiveTab
from .output_tab import OutputTab

UI_REFRESH_MS = 33  # ~30 Hz reicht fuer das Auge und spart Strom


class DeviceTab(QWidget):
    """Uebersicht und Auswahl."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Eigenschaft", "Wert"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self.table.verticalHeader().setDefaultSectionSize(24)
        self.table.setMinimumHeight(360)

        self.tree_label = QLabel("Event-Knoten desselben USB-Geraets")
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Knoten", "Rolle", "Event-Typen"])
        self.tree.setRootIsDecorated(True)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tree.setMaximumHeight(180)

        self.notes = QLabel()
        self.notes.setWordWrap(True)
        self.notes.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)

        layout = QVBoxLayout(self)
        layout.addWidget(self.table)
        layout.addWidget(self.tree_label)
        layout.addWidget(self.tree, 1)
        layout.addWidget(self.notes)

    def show_device(self, device: X52Device | None, denied: list[str], errors: list[str] | None = None) -> None:
        rows = device.describe() if device else []
        self.table.setRowCount(len(rows))
        for row, (key, value) in enumerate(rows):
            self.table.setItem(row, 0, QTableWidgetItem(key))
            self.table.setItem(row, 1, QTableWidgetItem(value))

        self.tree.clear()
        notes: list[str] = []
        if device is None:
            notes.append(
                "Kein joystickartiges Eingabegeraet gefunden. Steckt der Stick, "
                "und zeigt `lsusb` ihn an?"
            )
            self.tree_label.setVisible(False)
            self.tree.setVisible(False)
        else:
            self.tree_label.setVisible(True)
            self.tree.setVisible(True)

            root = QTreeWidgetItem([device.known_name or device.name, "", ""])
            root_font = root.font(0)
            root_font.setBold(True)
            root.setFont(0, root_font)
            self.tree.addTopLevelItem(root)

            used = QTreeWidgetItem(
                [device.path, "Joystick-Achsen (verwendet)", "EV_ABS, EV_KEY"]
            )
            root.addChild(used)

            try:
                related = find_related_nodes(device.vendor, device.product, device.path, device.name)
            except OSError:
                related = []
            for node in related:
                root.addChild(QTreeWidgetItem([node.path, node.role, node.ev_types]))

            self.tree.expandAll()

            if related:
                notes.append(
                    "Derselbe Stick meldet mehrere Event-Knoten - oben aufgeklappt. "
                    "Nur der als 'verwendet' markierte liefert die Achsen und Tasten "
                    "in diesem Programm; die anderen (z.B. eine Maus-Emulation fuer "
                    "den Ministick) werden hier nicht ausgewertet."
                )
            else:
                notes.append(
                    "Kein weiterer Event-Knoten mit derselben USB-ID gefunden - "
                    "entweder meldet der Stick nur einen, oder ein zusaetzlicher "
                    "Knoten liegt ohne Leserecht vor (siehe unten)."
                )

            if not device.known_name:
                notes.append(
                    "Die USB-ID steht nicht in der bekannten Liste. Das Werkzeug "
                    "funktioniert trotzdem, nur LED und MFD bleiben aus."
                )
            if not device.writable:
                notes.append(
                    f"Auf {device.path} besteht nur Leserecht. Kalibrieren braucht "
                    "Schreibrecht - im Reiter Kalibrierung gibt es dafuer eine "
                    "fertige udev-Regel."
                )
        if denied:
            notes.append(
                "Ohne Leserecht uebersprungen: " + ", ".join(denied)
            )
        if errors:
            notes.append(
                "Fehler beim Oeffnen (weder Rechte- noch Formatproblem, siehe Text):\n"
                + "\n".join(errors)
            )
        self.notes.setText("\n\n".join(notes))


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"x52tool {__version__}")
        self.resize(1000, 720)

        self.settings = Settings.load()
        self.device: X52Device | None = None
        self.state: DeviceState | None = None
        self.notifier: QSocketNotifier | None = None
        self._denied: list[str] = []
        self._errors: list[str] = []

        self.picker = QComboBox()
        self.picker.setMinimumWidth(420)
        self.picker.currentIndexChanged.connect(self._on_pick)
        self.btn_rescan = QPushButton("Neu suchen")
        self.btn_rescan.clicked.connect(self.rescan)

        top = QHBoxLayout()
        top.addWidget(QLabel("Geraet"))
        top.addWidget(self.picker, 1)
        top.addWidget(self.btn_rescan)

        self.tab_device = DeviceTab()
        self.tab_live = LiveTab()
        self.tab_analysis = AnalysisTab()
        self.tab_calib = CalibrationTab(self.settings)
        self.tab_output = OutputTab(self.settings)

        self.tabs = QTabWidget()
        self.tabs.addTab(self.tab_device, "Geraet")
        self.tabs.addTab(self.tab_live, "Live-Test")
        self.tabs.addTab(self.tab_analysis, "Analyse")
        self.tabs.addTab(self.tab_calib, "Kalibrierung")
        self.tabs.addTab(self.tab_output, "LED / MFD")

        self.tab_analysis.suggestionsReady.connect(self._on_suggestions)
        self.tab_calib.calibrationChanged.connect(self.tab_live.refresh_calibration)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addLayout(top)
        layout.addWidget(self.tabs, 1)
        self.setCentralWidget(central)

        self.timer = QTimer(self)
        self.timer.setInterval(UI_REFRESH_MS)
        self.timer.timeout.connect(self._refresh_ui)
        self.timer.start()

        self._candidates: list[X52Device] = []
        self.rescan()

    # -- Geraeteverwaltung -------------------------------------------------

    def rescan(self) -> None:
        self._detach()
        for dev in self._candidates:
            dev.close()
        result = scan()
        self._candidates = result.devices
        self._denied = result.denied
        self._errors = result.errors

        self.picker.blockSignals(True)
        self.picker.clear()
        for dev in self._candidates:
            tag = dev.known_name or dev.name
            self.picker.addItem(f"{tag}  -  {dev.path}  ({dev.usb_id})")
        self.picker.blockSignals(False)

        if not self._candidates:
            self._select(None)
            return

        wanted = self.settings.last_device_path
        index = next(
            (i for i, d in enumerate(self._candidates) if d.path == wanted), 0
        )
        self.picker.setCurrentIndex(index)
        self._on_pick(index)

    def _on_pick(self, index: int) -> None:
        if 0 <= index < len(self._candidates):
            self._select(self._candidates[index])

    def _select(self, device: X52Device | None) -> None:
        self._detach()
        self.device = device
        self.state = DeviceState(device) if device else None

        if device is not None:
            self.notifier = QSocketNotifier(
                device.fd, QSocketNotifier.Type.Read, self
            )
            self.notifier.activated.connect(self._drain)
            self.settings.last_device_path = device.path

        self.tab_device.show_device(device, self._denied, self._errors)
        self.tab_live.set_device(device)
        self.tab_analysis.set_device(device)
        self.tab_calib.set_device(device)

        if device is None:
            self.statusBar().showMessage("Kein Geraet")
        else:
            self.statusBar().showMessage(
                f"{device.name} - {len(device.axes)} Achsen, {len(device.buttons)} Tasten"
            )

    def _detach(self) -> None:
        if self.notifier is not None:
            self.notifier.setEnabled(False)
            self.notifier.deleteLater()
            self.notifier = None

    # -- Ereignisse --------------------------------------------------------

    def _drain(self) -> None:
        if self.device is None or self.state is None:
            return
        self.state.apply_all(self.device.read_pending())

    def _refresh_ui(self) -> None:
        if self.state is None:
            return
        if self.tabs.currentWidget() is self.tab_live:
            self.tab_live.refresh(self.state.axes, self.state.buttons)

    def _on_suggestions(self, suggestions: dict) -> None:
        cleaned = {int(code): dict(values) for code, values in suggestions.items()}
        self.tab_calib.apply_suggestions(cleaned)
        self.tabs.setCurrentWidget(self.tab_calib)

    # -- Ende --------------------------------------------------------------

    def closeEvent(self, event) -> None:  # noqa: N802
        self._detach()
        for dev in self._candidates:
            dev.close()
        try:
            self.settings.save()
        except OSError:
            pass
        super().closeEvent(event)


def run(argv: list[str] | None = None) -> int:
    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName("x52tool")
    window = MainWindow()
    window.show()
    return app.exec()
