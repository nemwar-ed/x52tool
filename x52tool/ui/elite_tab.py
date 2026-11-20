"""Reiter 'Elite Dangerous': Bindings-Ordner, Journal-Ordner und eigene Tastennamen."""

from __future__ import annotations

import subprocess
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .. import i18n
from ..elite import buttonmap, paths
from ..elite.buttonmap import MapState
from ..logger import get_logger

log = get_logger("elite")


class EliteTab(QWidget):
    def __init__(self, settings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.settings = settings
        self._bindings: Path | None = None
        self._journal: Path | None = None
        self._message = ""
        self._journal_message = ""
        self._build()
        self._init_bindings()
        self._init_journal()
        self.retranslate()
        # Alter der Status.json laufend aktualisieren
        self._journal_timer = QTimer(self)
        self._journal_timer.setInterval(2000)
        self._journal_timer.timeout.connect(self._refresh_journal)
        self._journal_timer.start()

    # -- Aufbau ------------------------------------------------------------

    def _build(self) -> None:
        layout = QVBoxLayout(self)

        # Bindings-Ordner
        self.group_dir = QGroupBox()
        dir_layout = QVBoxLayout(self.group_dir)
        self.lbl_dir = QLabel()
        self.lbl_dir.setWordWrap(True)
        self.lbl_dir.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        row = QHBoxLayout()
        self.btn_search = QPushButton()
        self.btn_choose = QPushButton()
        self.btn_open   = QPushButton()
        self.btn_search.clicked.connect(self._search)
        self.btn_choose.clicked.connect(self._choose)
        self.btn_open.clicked.connect(self._open_dir)
        row.addWidget(self.btn_search)
        row.addWidget(self.btn_choose)
        row.addWidget(self.btn_open)
        row.addStretch(1)
        dir_layout.addWidget(self.lbl_dir)
        dir_layout.addLayout(row)
        layout.addWidget(self.group_dir)

        # Journal-Ordner (Status.json, Journal-Dateien)
        self.group_journal = QGroupBox()
        journal_layout = QVBoxLayout(self.group_journal)
        self.lbl_journal = QLabel()
        self.lbl_journal.setWordWrap(True)
        self.lbl_journal.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.lbl_journal_state = QLabel()
        self.lbl_journal_state.setWordWrap(True)
        row_j = QHBoxLayout()
        self.btn_j_search = QPushButton()
        self.btn_j_choose = QPushButton()
        self.btn_j_open   = QPushButton()
        self.btn_j_search.clicked.connect(self._search_journal)
        self.btn_j_choose.clicked.connect(self._choose_journal)
        self.btn_j_open.clicked.connect(self._open_journal)
        row_j.addWidget(self.btn_j_search)
        row_j.addWidget(self.btn_j_choose)
        row_j.addWidget(self.btn_j_open)
        row_j.addStretch(1)
        journal_layout.addWidget(self.lbl_journal)
        journal_layout.addWidget(self.lbl_journal_state)
        journal_layout.addLayout(row_j)
        layout.addWidget(self.group_journal)

        # Tastennamen
        self.group_names = QGroupBox()
        names_layout = QVBoxLayout(self.group_names)
        self.lbl_names_info = QLabel()
        self.lbl_names_info.setWordWrap(True)
        self.lbl_names_state = QLabel()
        self.lbl_names_state.setWordWrap(True)
        row2 = QHBoxLayout()
        self.btn_install   = QPushButton()
        self.btn_uninstall = QPushButton()
        self.btn_install.clicked.connect(self._install)
        self.btn_uninstall.clicked.connect(self._uninstall)
        row2.addWidget(self.btn_install)
        row2.addWidget(self.btn_uninstall)
        row2.addStretch(1)
        names_layout.addWidget(self.lbl_names_info)
        names_layout.addWidget(self.lbl_names_state)
        names_layout.addLayout(row2)
        layout.addWidget(self.group_names)

        layout.addStretch(1)

    # -- Bindings-Ordner ---------------------------------------------------

    def _init_bindings(self) -> None:
        saved = self.settings.ed_bindings_dir
        if saved and Path(saved).is_dir():
            self._bindings = Path(saved)
        else:
            self._search(save=bool(saved))

    def _set_bindings(self, path: Path | None, save: bool = True) -> None:
        self._bindings = path
        if save:
            self.settings.ed_bindings_dir = str(path) if path else ""
            try:
                self.settings.save()
            except OSError:
                pass
        self._refresh()

    def _search(self, save: bool = True) -> None:
        found = paths.find_bindings_dirs()
        if found:
            log.info("E:D-Bindings gefunden: %s", ", ".join(map(str, found)))
            self._message = ""
            self._set_bindings(found[0], save=save)
        else:
            log.info("Kein E:D-Bindings-Ordner gefunden")
            self._message = i18n.t("elite.msg_not_found")
            self._set_bindings(None, save=False)

    def _choose(self) -> None:
        start = str(self._bindings or Path.home())
        chosen = QFileDialog.getExistingDirectory(
            self, i18n.t("elite.dlg_choose"), start
        )
        if not chosen:
            return
        path = Path(chosen)
        if paths.is_bindings_dir(path):
            self._message = ""
            self._set_bindings(path)
        else:
            self._message = i18n.t("elite.msg_invalid_dir", path=chosen)
            self._refresh()

    def _open_dir(self) -> None:
        if self._bindings:
            subprocess.Popen(["xdg-open", str(self._bindings)])

    # -- Journal-Ordner ----------------------------------------------------

    def _init_journal(self) -> None:
        saved = self.settings.ed_journal_dir
        if saved and paths.is_journal_dir(Path(saved)):
            self._journal = Path(saved)
        else:
            self._search_journal(save=bool(saved))

    def _set_journal(self, path: Path | None, save: bool = True) -> None:
        self._journal = path
        if save:
            self.settings.ed_journal_dir = str(path) if path else ""
            try:
                self.settings.save()
            except OSError:
                pass
        self._refresh_journal()

    def _search_journal(self, save: bool = True) -> None:
        found = paths.find_journal_dirs()
        if found:
            log.info("E:D-Journal-Ordner gefunden: %s", ", ".join(map(str, found)))
            self._journal_message = ""
            self._set_journal(found[0], save=save)
        else:
            log.info("Kein E:D-Journal-Ordner gefunden")
            self._journal_message = i18n.t("elite.msg_journal_not_found")
            self._set_journal(None, save=False)

    def _choose_journal(self) -> None:
        start = str(self._journal or self._bindings or Path.home())
        chosen = QFileDialog.getExistingDirectory(
            self, i18n.t("elite.dlg_choose_journal"), start
        )
        if not chosen:
            return
        path = Path(chosen)
        if paths.is_journal_dir(path):
            self._journal_message = ""
            self._set_journal(path)
        else:
            self._journal_message = i18n.t("elite.msg_invalid_journal_dir", path=chosen)
            self._refresh_journal()

    def _open_journal(self) -> None:
        if self._journal:
            subprocess.Popen(["xdg-open", str(self._journal)])

    @staticmethod
    def _format_age(seconds: float) -> str:
        s = int(seconds)
        if s < 60:
            return i18n.t("elite.age_seconds", n=s)
        if s < 3600:
            return i18n.t("elite.age_minutes", n=s // 60)
        if s < 86400:
            return i18n.t("elite.age_hours", n=s // 3600)
        return i18n.t("elite.age_days", n=s // 86400)

    def _refresh_journal(self) -> None:
        has_dir = self._journal is not None
        self.lbl_journal.setText(str(self._journal) if has_dir else i18n.t("elite.journal_none"))
        self.btn_j_open.setEnabled(has_dir)
        state = ""
        if has_dir:
            age = paths.status_age(self._journal)
            if age is None:
                state = i18n.t("elite.journal_status_missing")
            else:
                state = i18n.t("elite.journal_status_age", age=self._format_age(age))
        if self._journal_message:
            state = f"{state}\n\n{self._journal_message}" if state else self._journal_message
        self.lbl_journal_state.setText(state)

    # -- Tastennamen -------------------------------------------------------

    def _install(self) -> None:
        if not self._bindings:
            return
        try:
            result = buttonmap.install(self._bindings)
        except OSError as exc:
            log.error("buttonMap schreiben fehlgeschlagen: %s", exc)
            self._message = i18n.t("elite.msg_error", error=exc)
        else:
            log.info("buttonMap geschrieben: %s", ", ".join(map(str, result.written)))
            msg = i18n.t("elite.msg_installed")
            if result.backups:
                msg += "\n" + i18n.t(
                    "elite.msg_backup", files=", ".join(p.name for p in result.backups)
                )
            self._message = msg
        self._refresh()

    def _uninstall(self) -> None:
        if not self._bindings:
            return
        try:
            removed = buttonmap.uninstall(self._bindings)
        except OSError as exc:
            log.error("buttonMap entfernen fehlgeschlagen: %s", exc)
            self._message = i18n.t("elite.msg_error", error=exc)
        else:
            log.info("buttonMap entfernt: %s", ", ".join(map(str, removed)))
            self._message = i18n.t("elite.msg_removed")
        self._refresh()

    # -- Anzeige -----------------------------------------------------------

    def _refresh(self) -> None:
        has_dir = self._bindings is not None
        if has_dir:
            self.lbl_dir.setText(str(self._bindings))
        else:
            self.lbl_dir.setText(i18n.t("elite.dir_none"))
        self.btn_open.setEnabled(has_dir)

        if has_dir:
            st = buttonmap.state(self._bindings)
            state_text = i18n.t({
                MapState.MISSING:  "elite.state_missing",
                MapState.OURS:     "elite.state_ours",
                MapState.OUTDATED: "elite.state_outdated",
                MapState.FOREIGN:  "elite.state_foreign",
            }[st])
            self.btn_install.setEnabled(st is not MapState.OURS)
            self.btn_uninstall.setEnabled(st in (MapState.OURS, MapState.OUTDATED))
        else:
            state_text = ""
            self.btn_install.setEnabled(False)
            self.btn_uninstall.setEnabled(False)

        text = state_text
        if self._message:
            text = f"{text}\n\n{self._message}" if text else self._message
        self.lbl_names_state.setText(text)

    # -- i18n --------------------------------------------------------------

    def retranslate(self) -> None:
        self.group_dir.setTitle(i18n.t("elite.group_dir"))
        self.btn_search.setText(i18n.t("elite.btn_search"))
        self.btn_choose.setText(i18n.t("elite.btn_choose"))
        self.btn_open.setText(i18n.t("elite.btn_open"))
        self.group_journal.setTitle(i18n.t("elite.group_journal"))
        self.btn_j_search.setText(i18n.t("elite.btn_search"))
        self.btn_j_choose.setText(i18n.t("elite.btn_choose"))
        self.btn_j_open.setText(i18n.t("elite.btn_open"))
        self.group_names.setTitle(i18n.t("elite.group_names"))
        self.lbl_names_info.setText(i18n.t("elite.names_info"))
        self.btn_install.setText(i18n.t("elite.btn_install"))
        self.btn_uninstall.setText(i18n.t("elite.btn_uninstall"))
        self._message = ""
        self._journal_message = ""
        self._refresh()
        self._refresh_journal()
