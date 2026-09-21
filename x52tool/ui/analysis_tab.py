"""Reiter 'Analyse': Ruhemessung und Bereichsmessung."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..analysis import AxisMeasurement, Recorder, guided_axis_queue
from ..device import AbsInfo, Axis, X52Device

SAMPLE_INTERVAL_MS = 10  # 100 Hz

REST_COLUMNS = [
    "Achse",
    "Mittenversatz",
    "Rauschen (Spitze-Spitze)",
    "Standardabw.",
    "Aktuell (Deadzone / Fuzz)",
    "Vorschlag",
]
RANGE_COLUMNS = [
    "Achse",
    "Erreicht min",
    "Erreicht max",
    "Kernel-Bereich",
    "Abdeckung",
    "Bewertung",
]

ALL_AXES_ITEM = "Alle Achsen (der Reihe nach)"


class AnalysisTab(QWidget):
    # {abs_code: {"flat": N}} oder {abs_code: {"fuzz": N}} - je nachdem, ob
    # die Achse eine verlaessliche Mitte hat (siehe AxisMeasurement.
    # has_reliable_center). Nie beides fuer dieselbe Achse.
    suggestionsReady = pyqtSignal(dict)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.device: X52Device | None = None
        self.recorder: Recorder | None = None
        self.mode = "rest"
        self._suggestions: dict[int, dict[str, int]] = {}
        self._fuzz_backup: dict[int, AbsInfo] = {}
        self._ticks_left = 0

        # -- Zustand der gefuehrten Messung ---------------------------------
        self._guided = False
        self._guided_axes: list[Axis] = []
        self._guided_pos = 0
        self._guided_phase = "rest"
        self._guided_rest: dict[int, AxisMeasurement] = {}
        self._guided_range: dict[int, AxisMeasurement] = {}
        self._last_guided_rest: list[AxisMeasurement] = []
        self._last_guided_range: list[AxisMeasurement] = []
        self._showing_guided_range = False

        self.timer = QTimer(self)
        self.timer.setInterval(SAMPLE_INTERVAL_MS)
        self.timer.timeout.connect(self._sample)

        self._build()

    # -- Aufbau ------------------------------------------------------------

    def _build(self) -> None:
        self.explain = QLabel(
            "Ruhemessung: Haende weg, nichts anfassen. Fuer Stick und Twist "
            "(echte Federrueckstellung) ein Deadzone-Vorschlag um die Mitte. "
            "Fuer Schubhebel, Schieberegler und Rotary 1/2 (keine "
            "Federrueckstellung, teils auch keine feste Mitte) stattdessen "
            "ein Fuzz-Vorschlag - der wirkt unabhaengig von der Position.\n"
            "Bereichsmessung: jede Achse einmal langsam von Anschlag zu Anschlag. "
            "Zeigt, ob die Potis den vollen Bereich noch erreichen.\n\n"
            "Deadzone (auch \"flat\" genannt): ein Fenster um die Achsenmitte, "
            "in dem kleine Bewegungen ignoriert werden. Nur sinnvoll bei "
            "Achsen, die von selbst zur Mitte zurueckfedern.\n"
            "Fuzz: der Kernel ignoriert jede Wertaenderung, die kleiner ist "
            "als dieser Betrag - ein reiner Rauschfilter, unabhaengig davon, "
            "wo die Achse gerade steht."
        )
        self.explain.setWordWrap(True)

        self.seconds = QSpinBox()
        self.seconds.setRange(3, 120)
        self.seconds.setValue(10)
        self.seconds.setSuffix(" s")

        self.zero_fuzz = QCheckBox("fuzz waehrend der Messung auf 0 setzen")
        self.zero_fuzz.setChecked(True)
        self.zero_fuzz.setToolTip(
            "Der Kernel unterdrueckt Aenderungen kleiner als fuzz. Ohne diesen "
            "Schritt misst man das Filter statt der Hardware. Wird danach "
            "wiederhergestellt."
        )

        self.btn_rest = QPushButton("Ruhemessung starten")
        self.btn_range = QPushButton("Bereichsmessung starten")
        self.btn_stop = QPushButton("Abbrechen")
        self.btn_stop.setEnabled(False)
        self.btn_apply = QPushButton("Vorschlaege in Kalibrierung uebernehmen")
        self.btn_apply.setEnabled(False)

        self.btn_rest.clicked.connect(lambda: self._start("rest"))
        self.btn_range.clicked.connect(lambda: self._start("range"))
        self.btn_stop.clicked.connect(self._stop)
        self.btn_apply.clicked.connect(self._emit_suggestions)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Dauer"))
        controls.addWidget(self.seconds)
        controls.addWidget(self.zero_fuzz)
        controls.addStretch(1)
        controls.addWidget(self.btn_rest)
        controls.addWidget(self.btn_range)
        controls.addWidget(self.btn_stop)

        guided_box = self._build_guided_box()

        self.progress = QProgressBar()
        self.progress.setTextVisible(True)
        self.progress.setValue(0)

        self.table = QTableWidget(0, len(REST_COLUMNS))
        self.table.setHorizontalHeaderLabels(REST_COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )

        bottom_row = QHBoxLayout()
        self.btn_toggle_view = QPushButton("Bereichsmessung anzeigen")
        self.btn_toggle_view.setVisible(False)
        self.btn_toggle_view.clicked.connect(self._toggle_guided_view)
        bottom_row.addWidget(self.btn_toggle_view)
        bottom_row.addStretch(1)
        bottom_row.addWidget(self.btn_apply)

        layout = QVBoxLayout(self)
        layout.addWidget(self.explain)
        layout.addWidget(guided_box)
        layout.addLayout(controls)
        layout.addWidget(self.progress)
        layout.addWidget(self.table, 1)
        layout.addLayout(bottom_row)

    def _build_guided_box(self) -> QGroupBox:
        box = QGroupBox("Gefuehrte Messung (eine Achse nach der anderen)")
        layout = QVBoxLayout(box)

        explain = QLabel(
            "Statt alle Achsen gleichzeitig durcheinanderzubewegen: eine "
            "Achse auswaehlen (oder alle der Reihe nach), das Tool fuehrt "
            "dich durch Ruhe- und Bereichsmessung fuer jede einzeln."
        )
        explain.setWordWrap(True)
        layout.addWidget(explain)

        row = QHBoxLayout()
        self.axis_picker = QComboBox()
        self.axis_picker.addItem(ALL_AXES_ITEM, None)
        self.btn_guided_start = QPushButton("Gefuehrt starten")
        self.btn_guided_start.clicked.connect(self._start_guided)
        row.addWidget(QLabel("Achse"))
        row.addWidget(self.axis_picker, 1)
        row.addWidget(self.btn_guided_start)
        layout.addLayout(row)

        self.guided_instruction = QLabel("")
        self.guided_instruction.setWordWrap(True)
        self.guided_instruction.setStyleSheet("font-weight: 600;")
        layout.addWidget(self.guided_instruction)

        return box

    # -- Geraet ------------------------------------------------------------

    def set_device(self, device: X52Device | None) -> None:
        self._stop()
        self.device = device
        self.table.setRowCount(0)
        self._suggestions = {}
        self.btn_apply.setEnabled(False)
        self.btn_toggle_view.setVisible(False)
        self.guided_instruction.setText("")
        for btn in (self.btn_rest, self.btn_range, self.btn_guided_start):
            btn.setEnabled(device is not None)

        self.axis_picker.clear()
        self.axis_picker.addItem(ALL_AXES_ITEM, None)
        if device is not None:
            for axis in guided_axis_queue(device.axes):
                self.axis_picker.addItem(axis.label, axis.code)

    # -- Manuelle Messung (alle Achsen gleichzeitig) ------------------------

    def _start(self, mode: str, codes: list[int] | None = None) -> None:
        if self.device is None:
            return
        self.mode = mode
        self.recorder = Recorder(self.device, codes=codes)
        self._ticks_left = int(self.seconds.value() * 1000 / SAMPLE_INTERVAL_MS)
        self.progress.setMaximum(self._ticks_left)
        self.progress.setValue(0)
        self.btn_stop.setEnabled(True)
        self.btn_rest.setEnabled(False)
        self.btn_range.setEnabled(False)
        self.btn_guided_start.setEnabled(False)
        self.axis_picker.setEnabled(False)
        self.btn_apply.setEnabled(False)

        if mode == "rest" and self.zero_fuzz.isChecked():
            self._suspend_fuzz()

        self.timer.start()

    def _suspend_fuzz(self) -> None:
        if self.device is None or not self.device.writable:
            return
        self._fuzz_backup = {ax.code: ax.info.copy() for ax in self.device.axes}
        changes = {}
        for ax in self.device.axes:
            relaxed = ax.info.copy()
            relaxed.fuzz = 0
            changes[ax.code] = relaxed
        try:
            self.device.apply_absinfo(changes)
        except OSError:
            self._fuzz_backup = {}

    def _restore_fuzz(self) -> None:
        if self.device is None or not self._fuzz_backup:
            return
        try:
            self.device.apply_absinfo(self._fuzz_backup)
        except OSError:
            pass
        finally:
            self._fuzz_backup = {}

    def _sample(self) -> None:
        window = self.window()
        state = getattr(window, "state", None)
        if self.recorder is None or state is None:
            return
        self.recorder.sample(state.axes)
        self._ticks_left -= 1
        self.progress.setValue(self.progress.maximum() - self._ticks_left)
        if self._ticks_left <= 0:
            self._finish()

    def _stop(self) -> None:
        self.timer.stop()
        self._restore_fuzz()
        self.btn_stop.setEnabled(False)
        self.btn_rest.setEnabled(self.device is not None)
        self.btn_range.setEnabled(self.device is not None)
        self.btn_guided_start.setEnabled(self.device is not None)
        self.axis_picker.setEnabled(True)
        if self._guided:
            self._guided = False
            self.guided_instruction.setText("Abgebrochen.")

    def _finish(self) -> None:
        self.timer.stop()
        self._restore_fuzz()
        if self.recorder is None:
            return
        results = self.recorder.results()

        if self._guided:
            self._finish_guided_step(results)
            return

        self.btn_stop.setEnabled(False)
        self.btn_rest.setEnabled(True)
        self.btn_range.setEnabled(True)
        self.btn_guided_start.setEnabled(True)
        self.axis_picker.setEnabled(True)
        if self.mode == "rest":
            self._show_rest(results)
        else:
            self._show_range(results)

    # -- Gefuehrte Messung ---------------------------------------------------

    def _start_guided(self) -> None:
        if self.device is None:
            return
        only_code = self.axis_picker.currentData()
        queue = guided_axis_queue(self.device.axes, only_code)
        if not queue:
            return

        self._guided = True
        self._guided_axes = queue
        self._guided_pos = 0
        self._guided_rest = {}
        self._guided_range = {}
        self.btn_toggle_view.setVisible(False)
        self._begin_guided_step()

    def _begin_guided_step(self) -> None:
        axis = self._guided_axes[self._guided_pos]
        total = len(self._guided_axes)
        self._guided_phase = "rest"
        self.guided_instruction.setText(
            f"Achse {self._guided_pos + 1} von {total}: {axis.label}\n"
            "Jetzt loslassen, nichts anfassen - Ruhemessung laeuft."
        )
        self._start("rest", codes=[axis.code])

    def _finish_guided_step(self, results: list[AxisMeasurement]) -> None:
        axis = self._guided_axes[self._guided_pos]
        total = len(self._guided_axes)

        if self.mode == "rest":
            if results:
                self._guided_rest[axis.code] = results[0]
            self.guided_instruction.setText(
                f"Achse {self._guided_pos + 1} von {total}: {axis.label}\n"
                "Jetzt einmal LANGSAM von Anschlag zu Anschlag bewegen."
            )
            self._start("range", codes=[axis.code])
            return

        # mode == "range": diese Achse ist fertig, weiter zur naechsten.
        if results:
            self._guided_range[axis.code] = results[0]
        self._guided_pos += 1
        if self._guided_pos < len(self._guided_axes):
            self._begin_guided_step()
        else:
            self._finish_guided()

    def _finish_guided(self) -> None:
        self._guided = False
        self.btn_stop.setEnabled(False)
        self.btn_rest.setEnabled(True)
        self.btn_range.setEnabled(True)
        self.btn_guided_start.setEnabled(True)
        self.axis_picker.setEnabled(True)
        self.guided_instruction.setText(
            f"Gefuehrte Messung abgeschlossen ({len(self._guided_axes)} Achse(n))."
        )

        rest_results = list(self._guided_rest.values())
        range_results = list(self._guided_range.values())
        self._last_guided_rest = rest_results
        self._last_guided_range = range_results
        self._showing_guided_range = False

        self._show_rest(rest_results)
        self.btn_toggle_view.setText("Bereichsmessung anzeigen")
        self.btn_toggle_view.setVisible(bool(range_results))

    def _toggle_guided_view(self) -> None:
        if self._showing_guided_range:
            self._show_rest(self._last_guided_rest)
            self.btn_toggle_view.setText("Bereichsmessung anzeigen")
        else:
            self._show_range(self._last_guided_range)
            self.btn_toggle_view.setText("Ruhemessung anzeigen")
        self._showing_guided_range = not self._showing_guided_range

    # -- Darstellung -------------------------------------------------------

    def _prepare_table(self, columns: list[str], rows: int) -> None:
        self.table.clear()
        self.table.setColumnCount(len(columns))
        self.table.setHorizontalHeaderLabels(columns)
        self.table.setRowCount(rows)

    @staticmethod
    def _cell(text: str, warn: bool = False) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        if warn:
            item.setForeground(Qt.GlobalColor.red)
        return item

    def _show_rest(self, results: list[AxisMeasurement]) -> None:
        self._prepare_table(REST_COLUMNS, len(results))
        header_deadzone_fuzz = self.table.horizontalHeaderItem(4)
        if header_deadzone_fuzz is not None:
            header_deadzone_fuzz.setToolTip(
                "Deadzone/flat: Fenster um die Mitte, in dem Bewegungen ignoriert "
                "werden - nur sinnvoll bei Achsen mit Federrueckstellung.\n"
                "Fuzz: ignoriert jede Wertaenderung unterhalb dieses Betrags, "
                "egal wo die Achse steht - ein reiner Rauschfilter."
            )
        header_suggestion = self.table.horizontalHeaderItem(5)
        if header_suggestion is not None:
            header_suggestion.setToolTip(
                "Bei Achsen mit fester Mitte: Deadzone-Vorschlag.\n"
                "Bei allen anderen: Fuzz-Vorschlag (siehe Spalte links)."
            )
        self._suggestions = {}
        for row, m in enumerate(results):
            noise_pct = m.percent(m.spread)
            self.table.setItem(row, 0, self._cell(m.label))

            if m.has_reliable_center:
                drift_pct = m.percent(m.centre_offset)
                self.table.setItem(
                    row, 1,
                    self._cell(f"{m.centre_offset:+.0f}  ({drift_pct:+.2f} %)", abs(drift_pct) > 2.0),
                )
            else:
                # Keine Feder, die zur Mitte zurueckfuehrt - der Wert steht
                # einfach da, wo die Achse zuletzt hingestellt wurde. Eine
                # "Abweichung" davon anzuzeigen wuerde einen Defekt
                # suggerieren, den es nicht gibt.
                self.table.setItem(row, 1, self._cell("–  (keine feste Mitte)"))

            self.table.setItem(
                row, 2, self._cell(f"{m.spread}  ({noise_pct:.2f} %)", noise_pct > 1.0)
            )
            self.table.setItem(row, 3, self._cell(f"{m.stddev:.1f}"))
            self.table.setItem(row, 4, self._cell(f"{m.info.flat} / {m.info.fuzz}"))

            if m.has_reliable_center:
                suggestion = m.suggested_flat
                self._suggestions[m.code] = {"flat": suggestion}
                self.table.setItem(row, 5, self._cell(f"{suggestion}  (Deadzone)"))
            else:
                suggestion = m.suggested_fuzz
                self._suggestions[m.code] = {"fuzz": suggestion}
                self.table.setItem(row, 5, self._cell(f"{suggestion}  (Fuzz)"))
        self.btn_apply.setEnabled(bool(self._suggestions))

    def _show_range(self, results: list[AxisMeasurement]) -> None:
        self._prepare_table(RANGE_COLUMNS, len(results))
        for row, m in enumerate(results):
            coverage = m.coverage
            if coverage >= 97:
                verdict, warn = "voller Ausschlag", False
            elif coverage >= 90:
                verdict, warn = "knapp, aber brauchbar", False
            elif coverage >= 60:
                verdict, warn = "erreicht die Anschlaege nicht", True
            else:
                verdict, warn = "kaum bewegt oder defekt", True
            self.table.setItem(row, 0, self._cell(m.label))
            self.table.setItem(row, 1, self._cell(str(m.lowest)))
            self.table.setItem(row, 2, self._cell(str(m.highest)))
            self.table.setItem(row, 3, self._cell(f"{m.info.minimum} .. {m.info.maximum}"))
            self.table.setItem(row, 4, self._cell(f"{coverage:.1f} %", warn))
            self.table.setItem(row, 5, self._cell(verdict, warn))
        self.btn_apply.setEnabled(False)

    def _emit_suggestions(self) -> None:
        if self._suggestions:
            self.suggestionsReady.emit(dict(self._suggestions))
