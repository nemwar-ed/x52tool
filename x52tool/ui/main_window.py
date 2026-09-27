"""Hauptfenster: Geraetewahl, Event-Pumpe, Reiter."""

from __future__ import annotations

import sys

from PyQt6.QtCore import QSocketNotifier, Qt, QTimer
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .. import __version__, i18n
from ..config import Settings
from ..device import DeviceState, X52Device, scan
from ..logger import get_logger
from .calib2_tab import Calib2Tab
from .live_tab import LiveTab
from .output_tab import OutputTab
from .settings_tab import SettingsTab

log = get_logger("main_window")

UI_REFRESH_MS = 33  # ~30 Hz


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__(None)
        self.resize(1000, 720)

        self.settings = Settings.load()
        self.device: X52Device | None = None
        self.state: DeviceState | None = None
        self.notifier: QSocketNotifier | None = None
        self._denied: list[str] = []
        self._errors: list[str] = []

        # Geraetewahl (Picker bleibt oben – kompakte Zeile ohne Rescan-Button)
        self.picker = QComboBox()
        self.picker.setMinimumWidth(420)
        self.picker.currentIndexChanged.connect(self._on_pick)
        self.label_device = QLabel()

        top = QHBoxLayout()
        top.addWidget(self.label_device)
        top.addWidget(self.picker, 1)

        self.tab_live     = LiveTab()
        self.tab_calib2   = Calib2Tab(self.settings)
        self.tab_output   = OutputTab(self.settings)
        self.tab_settings = SettingsTab(settings=self.settings)

        self.tabs = QTabWidget()
        self.tabs.addTab(self.tab_live,     "")
        self.tabs.addTab(self.tab_calib2,   "")
        self.tabs.addTab(self.tab_output,   "")
        self.tabs.addTab(self.tab_settings, "")

        self.tab_calib2.calibrationChanged.connect(self.tab_live.refresh_calibration)
        self.tab_settings.languageChanged.connect(self._on_language_changed)
        self.tab_settings.rescanRequested.connect(self.rescan)

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
        self.setWindowTitle(i18n.t("main.window_title", version=__version__))
        self.label_device.setText(i18n.t("main.label_device"))
        self.tabs.setTabText(0, i18n.t("main.tab_live"))
        self.tabs.setTabText(1, i18n.t("main.tab_calib2"))
        self.tabs.setTabText(2, i18n.t("main.tab_output"))
        self.tabs.setTabText(3, i18n.t("settings.tab_label"))
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

        # Hinweise ins Log
        for path in self._denied:
            log.warning("Kein Leserecht auf %s", path)
        for msg in self._errors:
            log.error("Gerätefehler: %s", msg)

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
            log.info(
                "Gerät ausgewählt: %s  USB-ID: %s  Pfad: %s  Schreibrecht: %s",
                device.known_name or device.name,
                device.usb_id,
                device.path,
                device.writable,
            )

        self.tab_settings.update_device(device)
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
