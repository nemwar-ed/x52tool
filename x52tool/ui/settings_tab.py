"""Reiter 'Einstellungen / Settings'."""

from __future__ import annotations

import subprocess

from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .. import i18n
from ..logger import log_path, diag_log_path, write_diag_log


class SettingsTab(QWidget):
    languageChanged = pyqtSignal(str)  # emittiert den neuen Sprachcode "de"/"en"

    def __init__(self, settings=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._build()

    def _build(self) -> None:
        # --- Sprache ---
        self.group_lang = QGroupBox(i18n.t("settings.group_language"))
        row = QHBoxLayout(self.group_lang)

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

        row.addStretch(1)
        row.addWidget(self.btn_de)
        row.addWidget(self.btn_en)
        row.addStretch(1)

        # --- Log ---
        self.group_log = QGroupBox(i18n.t("settings.group_log"))
        log_row = QHBoxLayout(self.group_log)

        self.btn_open_log = QPushButton(i18n.t("settings.btn_open_log"))
        self.btn_open_log.clicked.connect(self._open_log)

        self.btn_create_diag = QPushButton(i18n.t("settings.btn_create_diag"))
        self.btn_create_diag.clicked.connect(self._create_diag)

        log_row.addStretch(1)
        log_row.addWidget(self.btn_open_log)
        log_row.addWidget(self.btn_create_diag)
        log_row.addStretch(1)

        # --- Layout ---
        layout = QVBoxLayout(self)
        layout.addWidget(self.group_lang)
        layout.addWidget(self.hint_restart)
        layout.addWidget(self.group_log)
        layout.addStretch(1)

        self._update_buttons(i18n.active_language())

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

    def _open_log(self) -> None:
        path = log_path()
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("", encoding="utf-8")
        subprocess.Popen(["xdg-open", str(path)])

    def _create_diag(self) -> None:
        path = write_diag_log(self._settings)
        subprocess.Popen(["xdg-open", str(path)])

    def set_settings(self, settings) -> None:
        """Settings-Objekt nachträglich setzen (nach dem Laden)."""
        self._settings = settings

    def retranslate(self) -> None:
        self.group_lang.setTitle(i18n.t("settings.group_language"))
        self.btn_de.setText(i18n.t("settings.btn_de"))
        self.btn_en.setText(i18n.t("settings.btn_en"))
        self.hint_restart.setText(i18n.t("settings.hint_restart"))
        self.group_log.setTitle(i18n.t("settings.group_log"))
        self.btn_open_log.setText(i18n.t("settings.btn_open_log"))
        self.btn_create_diag.setText(i18n.t("settings.btn_create_diag"))
        self._update_buttons(i18n.active_language())
