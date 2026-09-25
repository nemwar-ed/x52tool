"""Reiter 'Einstellungen / Settings'."""

from __future__ import annotations

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


class SettingsTab(QWidget):
    languageChanged = pyqtSignal(str)  # emittiert den neuen Sprachcode "de"/"en"

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build()

    def _build(self) -> None:
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

        layout = QVBoxLayout(self)
        layout.addWidget(self.group_lang)
        layout.addWidget(self.hint_restart)
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

    def retranslate(self) -> None:
        self.group_lang.setTitle(i18n.t("settings.group_language"))
        self.btn_de.setText(i18n.t("settings.btn_de"))
        self.btn_en.setText(i18n.t("settings.btn_en"))
        self.hint_restart.setText(i18n.t("settings.hint_restart"))
        self._update_buttons(i18n.active_language())
