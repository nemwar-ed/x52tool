"""Reiter 'Einstellungen / Settings'."""

from __future__ import annotations

import subprocess

from PyQt6.QtCore import pyqtSignal, Qt, QTimer
from PyQt6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .. import i18n
from .. import service as svc
from ..service import ServiceState
from ..logger import log_path, diag_log_path, write_diag_log, get_logger

log = get_logger("settings")


class SettingsTab(QWidget):
    languageChanged = pyqtSignal(str)
    rescanRequested = pyqtSignal()

    def __init__(self, settings=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._build()

    def _build(self) -> None:
        # --- Sprache ---
        self.group_lang = QGroupBox(i18n.t("settings.group_language"))
        row_lang = QHBoxLayout(self.group_lang)
        self.btn_de = QPushButton(i18n.t("settings.btn_de"))
        self.btn_en = QPushButton(i18n.t("settings.btn_en"))
        self.btn_de.setCheckable(True)
        self.btn_en.setCheckable(True)
        self.btn_de.setMinimumWidth(100)
        self.btn_en.setMinimumWidth(100)
        self.btn_de.clicked.connect(lambda: self._switch("de"))
        self.btn_en.clicked.connect(lambda: self._switch("en"))
        self.hint_restart = QLabel(i18n.t("settings.hint_restart"))
        self.hint_restart.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hint_restart.setVisible(False)
        row_lang.addStretch(1)
        row_lang.addWidget(self.btn_de)
        row_lang.addWidget(self.btn_en)
        row_lang.addStretch(1)

        # --- Gerät ---
        self.group_device = QGroupBox(i18n.t("settings.group_device"))
        device_layout = QVBoxLayout(self.group_device)

        self.lbl_device_name     = QLabel()
        self.lbl_device_usbid    = QLabel()
        self.lbl_device_path     = QLabel()
        self.lbl_device_writable = QLabel()
        self.lbl_device_name.setWordWrap(True)
        self.lbl_device_path.setWordWrap(True)

        self.btn_rescan = QPushButton(i18n.t("main.btn_rescan"))
        self.btn_rescan.clicked.connect(self.rescanRequested.emit)

        device_layout.addWidget(self.lbl_device_name)
        device_layout.addWidget(self.lbl_device_usbid)
        device_layout.addWidget(self.lbl_device_path)
        device_layout.addWidget(self.lbl_device_writable)
        device_layout.addWidget(self.btn_rescan)

        # --- Log ---
        self.group_log = QGroupBox(i18n.t("settings.group_log"))
        row_log = QHBoxLayout(self.group_log)
        self.btn_open_log    = QPushButton(i18n.t("settings.btn_open_log"))
        self.btn_create_diag = QPushButton(i18n.t("settings.btn_create_diag"))
        self.btn_open_log.clicked.connect(self._open_log)
        self.btn_create_diag.clicked.connect(self._create_diag)
        row_log.addStretch(1)
        row_log.addWidget(self.btn_open_log)
        row_log.addWidget(self.btn_create_diag)
        row_log.addStretch(1)

        # --- x52d Service ---
        self.group_service = QGroupBox(i18n.t("settings.group_service"))
        svc_layout = QVBoxLayout(self.group_service)

        self.lbl_svc_status = QLabel()
        self.lbl_svc_socket = QLabel()
        svc_layout.addWidget(self.lbl_svc_status)
        svc_layout.addWidget(self.lbl_svc_socket)

        btn_row = QHBoxLayout()
        self.btn_svc_start = QPushButton(i18n.t("settings.btn_svc_start"))
        self.btn_svc_stop  = QPushButton(i18n.t("settings.btn_svc_stop"))
        self.btn_svc_start.clicked.connect(self._on_svc_start)
        self.btn_svc_stop.clicked.connect(self._on_svc_stop)
        btn_row.addStretch(1)
        btn_row.addWidget(self.btn_svc_start)
        btn_row.addWidget(self.btn_svc_stop)
        btn_row.addStretch(1)
        svc_layout.addLayout(btn_row)

        self._svc_timer = QTimer(self)
        self._svc_timer.setInterval(3000)
        self._svc_timer.timeout.connect(self._refresh_service)
        self._svc_timer.start()
        self._refresh_service()

        # --- Layout ---
        layout = QVBoxLayout(self)
        layout.addWidget(self.group_lang)
        layout.addWidget(self.hint_restart)
        layout.addWidget(self.group_service)
        layout.addWidget(self.group_device)
        layout.addWidget(self.group_log)
        layout.addStretch(1)

        self._update_buttons(i18n.active_language())
        self._clear_device()

    # -- Sprache -----------------------------------------------------------

    def _switch(self, lang: str) -> None:
        if lang == i18n.active_language():
            self._update_buttons(lang)
            return
        self.languageChanged.emit(lang)
        self.hint_restart.setText(i18n.t("settings.hint_restart"))
        self.hint_restart.setVisible(True)

    def _update_buttons(self, lang: str) -> None:
        self.btn_de.setChecked(lang == "de")
        self.btn_en.setChecked(lang == "en")

    # -- Service -----------------------------------------------------------

    def _refresh_service(self) -> None:
        s = svc.status()
        if s.state is ServiceState.RUNNING:
            color, text = "green",  i18n.t("settings.svc_running")
        elif s.state is ServiceState.FAILED:
            color, text = "red",    i18n.t("settings.svc_failed")
        elif s.state is ServiceState.UNKNOWN:
            color, text = "gray",   i18n.t("settings.svc_unknown")
        else:
            color, text = "orange", i18n.t("settings.svc_stopped")

        self.lbl_svc_status.setText(
            f"<span style='color:{color}'>●</span>  {text}"
        )

        writable = svc.socket_writable()
        sock_text = i18n.t("settings.svc_socket_ok") if writable \
               else i18n.t("settings.svc_socket_err")
        sock_color = "green" if writable else "red"
        self.lbl_svc_socket.setText(
            f"<span style='color:{sock_color}'>●</span>  {sock_text}"
        )

        self.btn_svc_start.setEnabled(s.state is not ServiceState.RUNNING)
        self.btn_svc_stop.setEnabled(s.state is ServiceState.RUNNING)

    def _on_svc_start(self) -> None:
        ok, err = svc.start()
        if not ok:
            log.error("x52d starten fehlgeschlagen: %s", err)
        self._refresh_service()

    def _on_svc_stop(self) -> None:
        ok, err = svc.stop()
        if not ok:
            log.error("x52d stoppen fehlgeschlagen: %s", err)
        self._refresh_service()

    # -- Gerät -------------------------------------------------------------

    def _clear_device(self) -> None:
        none = "–"
        self.lbl_device_name.setText(f"{i18n.t('device.describe_name')}: {none}")
        self.lbl_device_usbid.setText(f"{i18n.t('device.describe_usb_id')}: {none}")
        self.lbl_device_path.setText(f"{i18n.t('device.describe_path')}: {none}")
        self.lbl_device_writable.setText(f"{i18n.t('device.describe_writable')}: {none}")

    def update_device(self, device) -> None:
        """Wird vom MainWindow nach jedem scan() aufgerufen."""
        if device is None:
            self._clear_device()
            log.warning("Geräteerkennung: kein Gerät gefunden.")
            return

        writable = i18n.t("device.describe_yes") if device.writable else i18n.t("device.describe_no")
        known = device.known_name or i18n.t("device.describe_unknown")

        self.lbl_device_name.setText(
            f"{i18n.t('device.describe_name')}: {known}"
        )
        self.lbl_device_usbid.setText(
            f"{i18n.t('device.describe_usb_id')}: {device.usb_id}"
        )
        self.lbl_device_path.setText(
            f"{i18n.t('device.describe_path')}: {device.path}"
        )
        self.lbl_device_writable.setText(
            f"{i18n.t('device.describe_writable')}: {writable}"
        )

        if not device.known_name:
            log.warning("Gerät erkannt, aber USB-ID unbekannt: %s", device.usb_id)
        if not device.writable:
            log.warning("Gerät %s ist nicht schreibbar.", device.path)

    # -- Log ---------------------------------------------------------------

    def _open_log(self) -> None:
        path = log_path()
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("", encoding="utf-8")
        subprocess.Popen(["xdg-open", str(path)])

    def _create_diag(self) -> None:
        path = write_diag_log(self._settings)
        subprocess.Popen(["xdg-open", str(path)])

    # -- Allgemein ---------------------------------------------------------

    def set_settings(self, settings) -> None:
        self._settings = settings

    def retranslate(self) -> None:
        self.group_lang.setTitle(i18n.t("settings.group_language"))
        self.btn_de.setText(i18n.t("settings.btn_de"))
        self.btn_en.setText(i18n.t("settings.btn_en"))
        self.hint_restart.setText(i18n.t("settings.hint_restart"))
        self.group_service.setTitle(i18n.t("settings.group_service"))
        self.btn_svc_start.setText(i18n.t("settings.btn_svc_start"))
        self.btn_svc_stop.setText(i18n.t("settings.btn_svc_stop"))
        self.group_device.setTitle(i18n.t("settings.group_device"))
        self.btn_rescan.setText(i18n.t("main.btn_rescan"))
        self.group_log.setTitle(i18n.t("settings.group_log"))
        self.btn_open_log.setText(i18n.t("settings.btn_open_log"))
        self.btn_create_diag.setText(i18n.t("settings.btn_create_diag"))
        self._update_buttons(i18n.active_language())
        self._refresh_service()
