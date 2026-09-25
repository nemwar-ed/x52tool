"""Reiter 'Achsen & Kalibrierung' (v0.3).

Drei Bereiche:
  1. Achsen-Block  – AxesPanel (Live-Anzeige aller Achsen)
  2. Tabelle       – Rohwert, Peak-Min/Max, Rauschen, Deadzone-Vorschlag
  3. Aktionsleiste – [Peaks zurücksetzen] [Messung starten] [Speichern]

Geführte Messung (Peak-to-Peak):
  Dialog führt achsenweise durch: ans Minimum, dann ans Maximum.
  Jede Achse wird abgehakt sobald beide Extremwerte sicher erreicht wurden.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..axis_type import AxisKind, axis_kind, has_center
from ..device import Axis, X52Device
from ..noise import NoiseTracker
from .. import i18n
from .widgets import AxesPanel

_PEAK_MARGIN_PCT = 0.03   # 3 % vom Achsbereich gilt als "Anschlag erreicht"
_PEAK_CONFIRM    = 5       # Samples in Folge nötig zur Bestätigung
SAMPLE_INTERVAL_MS = 33    # ~30 Hz


# ---------------------------------------------------------------------------
# Geführter Peak-Dialog
# ---------------------------------------------------------------------------

class _PeakDialog(QDialog):
    """Führt den Nutzer durch die Achsen-Extremwert-Messung."""

    finished = pyqtSignal(dict)

    def __init__(
        self,
        axes: list[Axis],
        trackers: dict[int, NoiseTracker],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(i18n.t("calib2.peak_dlg_title"))
        self.setMinimumWidth(480)
        self.axes = [ax for ax in axes if not ax.is_digital]
        self.trackers = trackers
        self._results: dict[int, tuple[int, int]] = {}
        self._idx = 0
        self._phase = "min"
        self._confirm_count = 0

        self._build()
        self._timer = QTimer(self)
        self._timer.setInterval(SAMPLE_INTERVAL_MS)
        self._timer.timeout.connect(self._poll)
        self._timer.start()
        self._update_instruction()

    def _build(self) -> None:
        self.instruction = QLabel()
        self.instruction.setWordWrap(True)
        self.instruction.setStyleSheet("font-weight: 600; font-size: 13px;")

        self.sub = QLabel()
        self.sub.setWordWrap(True)

        self.rows: list[tuple[QLabel, QLabel]] = []
        checklist_box = QGroupBox(i18n.t("calib2.peak_dlg_checklist"))
        cl_layout = QVBoxLayout(checklist_box)
        for axis in self.axes:
            row = QHBoxLayout()
            name = QLabel(axis.label)
            status = QLabel(i18n.t("calib2.peak_status_pending"))
            status.setAlignment(Qt.AlignmentFlag.AlignRight)
            row.addWidget(name)
            row.addStretch(1)
            row.addWidget(status)
            cl_layout.addLayout(row)
            self.rows.append((name, status))

        buttons = QDialogButtonBox()
        self.btn_skip = buttons.addButton(
            i18n.t("calib2.peak_btn_skip"), QDialogButtonBox.ButtonRole.ActionRole
        )
        self.btn_abort = buttons.addButton(
            i18n.t("calib2.peak_btn_abort"), QDialogButtonBox.ButtonRole.RejectRole
        )
        self.btn_skip.clicked.connect(self._skip_axis)
        self.btn_abort.clicked.connect(self._abort)

        layout = QVBoxLayout(self)
        layout.addWidget(self.instruction)
        layout.addWidget(self.sub)
        layout.addWidget(checklist_box)
        layout.addWidget(buttons)

    def _current_axis(self) -> Axis | None:
        if self._idx < len(self.axes):
            return self.axes[self._idx]
        return None

    def _update_instruction(self) -> None:
        axis = self._current_axis()
        if axis is None:
            return
        total = len(self.axes)
        pos   = self._idx + 1
        if self._phase == "min":
            self.instruction.setText(
                i18n.t("calib2.peak_instr_min", pos=pos, total=total, label=axis.label)
            )
        else:
            self.instruction.setText(
                i18n.t("calib2.peak_instr_max", pos=pos, total=total, label=axis.label)
            )
        self.sub.setText(i18n.t("calib2.peak_instr_sub"))

    def _poll(self) -> None:
        axis = self._current_axis()
        if axis is None:
            return
        tracker = self.trackers.get(axis.code)
        if tracker is None:
            return

        span   = axis.info.span
        margin = max(1, int(span * _PEAK_MARGIN_PCT))

        if self._phase == "min":
            reached = tracker.peak_min <= axis.info.minimum + margin
        else:
            reached = tracker.peak_max >= axis.info.maximum - margin

        if reached:
            self._confirm_count += 1
        else:
            self._confirm_count = 0

        if self._confirm_count >= _PEAK_CONFIRM:
            self._confirm_count = 0
            self._advance()

    def _advance(self) -> None:
        axis = self._current_axis()
        if axis is None:
            return
        _, status = self.rows[self._idx]

        if self._phase == "min":
            self._phase = "max"
            status.setText(i18n.t("calib2.peak_status_min_ok"))
            status.setStyleSheet("color: orange;")
            self._update_instruction()
        else:
            tracker = self.trackers[axis.code]
            self._results[axis.code] = (tracker.peak_min, tracker.peak_max)
            status.setText(i18n.t("calib2.peak_status_done"))
            status.setStyleSheet("color: green;")
            self._next_axis()

    def _next_axis(self) -> None:
        self._idx += 1
        self._phase = "min"
        self._confirm_count = 0
        if self._idx >= len(self.axes):
            self._finish()
        else:
            axis = self.axes[self._idx]
            tracker = self.trackers.get(axis.code)
            if tracker is not None:
                tracker.reset_peaks()
            self._update_instruction()

    def _skip_axis(self) -> None:
        axis = self._current_axis()
        if axis is None:
            return
        _, status = self.rows[self._idx]
        status.setText(i18n.t("calib2.peak_status_skipped"))
        status.setStyleSheet("color: gray;")
        self._next_axis()

    def _abort(self) -> None:
        self._timer.stop()
        self.reject()

    def _finish(self) -> None:
        self._timer.stop()
        self.finished.emit(dict(self._results))
        self.accept()


# ---------------------------------------------------------------------------
# Hauptklasse
# ---------------------------------------------------------------------------

class Calib2Tab(QWidget):
    """Kombinierter Achsen- & Kalibrierungs-Tab."""

    calibrationChanged = pyqtSignal()

    def __init__(self, settings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.device: X52Device | None = None
        self._trackers: dict[int, NoiseTracker] = {}
        self._peak_results: dict[int, tuple[int, int]] = {}
        self._pending: dict[int, dict[str, int]] = {}

        self._timer = QTimer(self)
        self._timer.setInterval(SAMPLE_INTERVAL_MS)
        self._timer.timeout.connect(self._sample)

        self._build()

    def _build(self) -> None:
        self.axes_panel = AxesPanel()
        axes_group = QGroupBox(i18n.t("calib2.group_axes"))
        axes_group_layout = QVBoxLayout(axes_group)
        axes_group_layout.addWidget(self.axes_panel)

        self.table = QTableWidget(0, 6)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self._retranslate_table_headers()

        self.status = QLabel()
        self.status.setWordWrap(True)

        self.btn_reset_peaks = QPushButton(i18n.t("calib2.btn_reset_peaks"))
        self.btn_measure     = QPushButton(i18n.t("calib2.btn_measure"))
        self.btn_save        = QPushButton(i18n.t("calib2.btn_save"))

        self.btn_reset_peaks.clicked.connect(self._reset_peaks)
        self.btn_measure.clicked.connect(self._start_measurement)
        self.btn_save.clicked.connect(self._save)

        action_row = QHBoxLayout()
        action_row.addWidget(self.btn_reset_peaks)
        action_row.addWidget(self.btn_measure)
        action_row.addStretch(1)
        action_row.addWidget(self.btn_save)

        layout = QVBoxLayout(self)
        layout.addWidget(axes_group)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.status)
        layout.addLayout(action_row)

    def _retranslate_table_headers(self) -> None:
        self.table.setHorizontalHeaderLabels([
            i18n.t("calib2.col_axis"),
            i18n.t("calib2.col_current"),
            i18n.t("calib2.col_peak_min"),
            i18n.t("calib2.col_peak_max"),
            i18n.t("calib2.col_noise"),
            i18n.t("calib2.col_suggestion"),
        ])

    def set_device(self, device: X52Device | None) -> None:
        self._timer.stop()
        self.device = device
        self._trackers.clear()
        self._peak_results.clear()
        self._pending.clear()
        self.table.setRowCount(0)

        for btn in (self.btn_reset_peaks, self.btn_measure, self.btn_save):
            btn.setEnabled(device is not None)
        self.btn_save.setEnabled(False)

        if device is None:
            self.status.setText(i18n.t("calib2.status_no_device"))
            used: set[int] = set()
            self.axes_panel.set_device({}, used)
            return

        if device.writable:
            self.status.setText(i18n.t("calib2.status_rw"))
        else:
            self.status.setText(i18n.t("calib2.status_ro", path=device.path))

        by_code = {ax.code: ax for ax in device.axes}
        used_codes: set[int] = set()
        self.axes_panel.set_device(by_code, used_codes)

        analog_axes = [ax for ax in device.axes if not ax.is_digital]
        self.table.setRowCount(len(analog_axes))
        for row, axis in enumerate(analog_axes):
            self._trackers[axis.code] = NoiseTracker(initial=axis.info.value)
            name = QTableWidgetItem(axis.label)
            name.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.table.setItem(row, 0, name)
            for col in range(1, 6):
                item = QTableWidgetItem("—")
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                self.table.setItem(row, col, item)

        self._timer.start()

    def _sample(self) -> None:
        window = self.window()
        state  = getattr(window, "state", None)
        if state is None or self.device is None:
            return

        self.axes_panel.refresh(state.axes)

        analog_axes = [ax for ax in self.device.axes if not ax.is_digital]
        for row, axis in enumerate(analog_axes):
            tracker = self._trackers.get(axis.code)
            if tracker is None:
                continue
            raw = state.axes.get(axis.code)
            if raw is None:
                continue
            tracker.push(raw)
            self._update_row(row, axis, tracker, raw)

    def _update_row(
        self, row: int, axis: Axis, tracker: NoiseTracker, raw: int
    ) -> None:
        kind = axis_kind(axis.code)

        self.table.item(row, 1).setText(str(raw))
        self.table.item(row, 2).setText(str(tracker.peak_min))
        self.table.item(row, 3).setText(str(tracker.peak_max))

        noise = tracker.noise_range
        noise_pct = (noise / axis.info.span * 100) if axis.info.span > 0 else 0
        self.table.item(row, 4).setText(f"{noise}  ({noise_pct:.1f} %)")

        if kind == AxisKind.FREE_SLIDER:
            over_min = tracker.peak_min < axis.info.minimum
            over_max = tracker.peak_max > axis.info.maximum
            if over_min or over_max:
                self.table.item(row, 5).setText(
                    i18n.t("calib2.suggest_range_extend",
                           lo=tracker.peak_min, hi=tracker.peak_max)
                )
                self._pending[axis.code] = {
                    "minimum": tracker.peak_min,
                    "maximum": tracker.peak_max,
                }
            else:
                self.table.item(row, 5).setText(i18n.t("calib2.suggest_range_ok"))
                self._pending.pop(axis.code, None)
        else:
            flat = tracker.suggested_flat()
            fuzz = tracker.suggested_fuzz()
            self.table.item(row, 5).setText(
                i18n.t("calib2.suggest_flat", flat=flat, fuzz=fuzz)
            )
            self._pending[axis.code] = {"flat": flat, "fuzz": fuzz}

        if self.device and self.device.writable:
            self.btn_save.setEnabled(bool(self._pending))

    def _reset_peaks(self) -> None:
        window = self.window()
        state  = getattr(window, "state", None)
        for code, tracker in self._trackers.items():
            current = state.axes.get(code) if state else None
            tracker.reset_peaks(current)

    def _start_measurement(self) -> None:
        if self.device is None:
            return
        self._reset_peaks()
        dlg = _PeakDialog(
            axes=list(self.device.axes),
            trackers=self._trackers,
            parent=self,
        )
        dlg.finished.connect(self._on_peak_done)
        dlg.exec()

    def _on_peak_done(self, results: dict[int, tuple[int, int]]) -> None:
        self._peak_results = results
        if not results:
            return

        analog_axes = [ax for ax in self.device.axes if not ax.is_digital]
        for row, axis in enumerate(analog_axes):
            if axis.code not in results:
                continue
            tracker = self._trackers[axis.code]
            kind = axis_kind(axis.code)

            if kind == AxisKind.FREE_SLIDER:
                new_min = min(tracker.peak_min, axis.info.minimum)
                new_max = max(tracker.peak_max, axis.info.maximum)
                self._pending[axis.code] = {"minimum": new_min, "maximum": new_max}
                self.table.item(row, 5).setText(
                    i18n.t("calib2.suggest_range_extend", lo=new_min, hi=new_max)
                )
            else:
                flat = tracker.suggested_flat()
                fuzz = tracker.suggested_fuzz()
                self._pending[axis.code] = {"flat": flat, "fuzz": fuzz}
                self.table.item(row, 5).setText(
                    i18n.t("calib2.suggest_flat", flat=flat, fuzz=fuzz)
                )

        if self.device and self.device.writable:
            self.btn_save.setEnabled(bool(self._pending))

    def _save(self) -> None:
        if self.device is None or not self._pending:
            return

        changes = {}
        for axis in self.device.axes:
            vals = self._pending.get(axis.code)
            if not vals:
                continue
            info = axis.info.copy()
            if "flat" in vals:
                info.flat = vals["flat"]
            if "fuzz" in vals:
                info.fuzz = vals["fuzz"]
            if "minimum" in vals:
                info.minimum = vals["minimum"]
            if "maximum" in vals:
                info.maximum = vals["maximum"]
            # Mittelpunkt als neuen Kernel-Ruhewert setzen –
            # nur für Achsen mit Mitte (SPRING_CENTER / MECHANICAL_CENTER).
            # FREE_SLIDER haben keinen definierten Mittelpunkt.
            if has_center(axis.code):
                tracker = self._trackers.get(axis.code)
                if tracker is not None:
                    # Nach Peak-Messung: center aus peak_min/peak_max.
                    # Ohne Peak-Messung: Mitte aus aktuellem Rauschfenster.
                    if axis.code in self._peak_results:
                        info.value = tracker.center
                    else:
                        info.value = tracker.noise_min + tracker.noise_range // 2
            changes[axis.code] = info

        try:
            self.device.apply_absinfo(changes)
        except PermissionError:
            QMessageBox.warning(
                self,
                i18n.t("calib2.dlg_save_fail_title"),
                i18n.t("calib2.dlg_save_fail_msg", path=self.device.path),
            )
            return
        except OSError as exc:
            QMessageBox.warning(self, i18n.t("calib2.dlg_save_fail_title"), str(exc))
            return

        self._pending.clear()
        self.btn_save.setEnabled(False)
        self.status.setText(i18n.t("calib2.status_saved"))
        self.calibrationChanged.emit()

    def retranslate(self) -> None:
        self._retranslate_table_headers()
        self.btn_reset_peaks.setText(i18n.t("calib2.btn_reset_peaks"))
        self.btn_measure.setText(i18n.t("calib2.btn_measure"))
        self.btn_save.setText(i18n.t("calib2.btn_save"))
        if self.device is None:
            self.status.setText(i18n.t("calib2.status_no_device"))
        elif self.device.writable:
            self.status.setText(i18n.t("calib2.status_rw"))
        else:
            self.status.setText(i18n.t("calib2.status_ro", path=self.device.path))
