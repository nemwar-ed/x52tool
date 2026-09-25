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

from .. import __version__, i18n
from ..config import Settings
from ..device import DeviceState, X52Device, find_related_nodes, scan
from .calib2_tab import Calib2Tab
from .live_tab import LiveTab
from .output_tab import OutputTab
from .settings_tab import SettingsTab

UI_REFRESH_MS = 33  # ~30 Hz


class DeviceTab(QWidget):
    """Uebersicht und Auswahl."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.table = QTableWidget(0, 2)
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

        self.tree_label = QLabel()
        self.tree = QTreeWidget()
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

        self._device: X52Device | None = None
        self._denied: list[str] = []
        self._errors: list[str] = []
        self._retranslate_headers()

    def _retranslate_headers(self) -> None:
        self.table.setHorizontalHeaderLabels([
            i18n.t("device.col_property"),
            i18n.t("device.col_value"),
        ])
        self.tree_label.setText(i18n.t("device.tree_label"))
        self.tree.setHeaderLabels([
            i18n.t("device.tree_col_node"),
            i18n.t("device.tree_col_role"),
            i18n.t("device.tree_col_evtypes"),
        ])

    def show_device(self, device: X52Device | None, denied: list[str], errors: list[str] | None = None) -> None:
        self._device = device
        self._denied = denied
        self._errors = errors or []
        self._render()

    def _render(self) -> None:
        device = self._device
        denied = self._denied
        errors = self._errors

        rows = device.describe() if device else []
        self.table.setRowCount(len(rows))
        for row, (key, value) in enumerate(rows):
            self.table.setItem(row, 0, QTableWidgetItem(key))
            self.table.setItem(row, 1, QTableWidgetItem(value))

        self.tree.clear()
        notes: list[str] = []
        if device is None:
            notes.append(i18n.t("device.note_no_device"))
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
                [device.path, i18n.t("device.tree_used_label"), "EV_ABS, EV_KEY"]
            )
            root.addChild(used)

            try:
                related = find_related_nodes(device.vendor, device.product, device.path, device.name)
            except OSError:
                related = []
            for node in related:
                root.addChild(QTreeWidgetItem([node.path, node.role, node.ev_types]))
            self.tree.expandAll()

            notes.append(i18n.t("device.note_multi_node") if related else i18n.t("device.note_single_node"))
            if not device.known_name:
                notes.append(i18n.t("device.note_unknown_id"))
            if not device.writable:
                notes.append(i18n.t("device.note_readonly", path=device.path))

        if denied:
            notes.append(i18n.t("device.note_denied", paths=", ".join(denied)))
        if errors:
            notes.append(i18n.t("device.note_errors", errors="\n".join(errors)))
        self.notes.setText("\n\n".join(notes))

    def retranslate(self) -> None:
        self._retranslate_headers()
        self._render()


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
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
        self.btn_rescan = QPushButton()
        self.btn_rescan.clicked.connect(self.rescan)
        self.label_device = QLabel()

        top = QHBoxLayout()
        top.addWidget(self.label_device)
        top.addWidget(self.picker, 1)
        top.addWidget(self.btn_rescan)

        self.tab_device   = DeviceTab()
        self.tab_live     = LiveTab()
        self.tab_calib2   = Calib2Tab(self.settings)
        self.tab_output   = OutputTab(self.settings)
        self.tab_settings = SettingsTab()

        self.tabs = QTabWidget()
        self.tabs.addTab(self.tab_device,   "")
        self.tabs.addTab(self.tab_live,     "")
        self.tabs.addTab(self.tab_calib2,   "")
        self.tabs.addTab(self.tab_output,   "")
        self.tabs.addTab(self.tab_settings, "")

        self.tab_calib2.calibrationChanged.connect(self.tab_live.refresh_calibration)
        self.tab_settings.languageChanged.connect(self._on_language_changed)

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
        self._retranslate_own()
        self.rescan()

    # -- Sprache -----------------------------------------------------------

    def _on_language_changed(self, lang: str) -> None:
        i18n.init(lang)
        self.settings.language = lang
        try:
            self.settings.save()
        except OSError:
            pass
        self._retranslate_all()

    def _retranslate_own(self) -> None:
        """Eigene Widgets des MainWindow neu beschriften."""
        self.setWindowTitle(i18n.t("main.window_title", version=__version__))
        self.label_device.setText(i18n.t("main.label_device"))
        self.btn_rescan.setText(i18n.t("main.btn_rescan"))
        self.tabs.setTabText(0, i18n.t("main.tab_device"))
        self.tabs.setTabText(1, i18n.t("main.tab_live"))
        self.tabs.setTabText(2, i18n.t("main.tab_calib2"))
        self.tabs.setTabText(3, i18n.t("main.tab_output"))
        self.tabs.setTabText(4, i18n.t("settings.tab_label"))
        # Statusbar
        if self.device is None:
            self.statusBar().showMessage(i18n.t("main.status_no_device"))
        else:
            self.statusBar().showMessage(
                i18n.t("main.status_device",
                       name=self.device.name,
                       axes=len(self.device.axes),
                       buttons=len(self.device.buttons))
            )

    def _retranslate_all(self) -> None:
        self._retranslate_own()
        self.tab_device.retranslate()
        self.tab_live.retranslate()
        self.tab_calib2.retranslate()
        self.tab_output.retranslate()
        self.tab_settings.retranslate()

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
        self.tab_calib2.set_device(device)

        if device is None:
            self.statusBar().showMessage(i18n.t("main.status_no_device"))
        else:
            self.statusBar().showMessage(
                i18n.t("main.status_device",
                       name=device.name,
                       axes=len(device.axes),
                       buttons=len(device.buttons))
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
