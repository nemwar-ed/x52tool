"""Anzeigebausteine, die mehrere Reiter benutzen.

Alle Farben kommen aus der Qt-Palette, damit die Balken in hellen und in
dunklen Themes lesbar bleiben.
"""

from __future__ import annotations

from PyQt6.QtCore import QRect, Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPalette, QPen
from PyQt6.QtWidgets import QGridLayout, QLabel, QSizePolicy, QWidget

from evdev import ecodes

from ..device import AbsInfo, Axis, Button

# Achsen, die um eine Mittelstellung herum arbeiten. Der Rest wird von
# links nach rechts gefuellt, wie ein Schubhebel.
BIPOLAR_AXES = {
    ecodes.ABS_X,
    ecodes.ABS_Y,
    ecodes.ABS_RX,
    ecodes.ABS_RY,
    ecodes.ABS_RZ,
    ecodes.ABS_HAT0X,
    ecodes.ABS_HAT0Y,
}

# Einzige feste Farbe: die Deadzone soll in beiden Themes als Warnband lesbar
# sein und darf sich nicht mit der Auswahlfarbe des Systems beissen.
DEADZONE_COLOUR = QColor(196, 121, 48)


class AxisBar(QWidget):
    """Balken mit Mittenmarke, Deadzone-Band und Rohwert.

    Die Deadzone wird mitgezeichnet, weil sonst niemand sieht, was das
    Setzen von `flat` eigentlich bewirkt.
    """

    def __init__(self, axis: Axis, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.axis = axis
        self.value = axis.info.value
        self.setMinimumHeight(38)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setToolTip(f"evdev ABS 0x{axis.code:02x}")

    # -- Zustand -----------------------------------------------------------

    def set_value(self, value: int) -> None:
        if value != self.value:
            self.value = value
            self.update()

    def set_info(self, info: AbsInfo) -> None:
        self.axis.info = info
        self.update()

    @property
    def bipolar(self) -> bool:
        return self.axis.code in BIPOLAR_AXES

    def _fraction(self, value: float) -> float:
        info = self.axis.info
        if info.span == 0:
            return 0.5
        return min(1.0, max(0.0, (value - info.minimum) / info.span))

    # -- Zeichnen ----------------------------------------------------------

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt-Namenskonvention
        info = self.axis.info
        pal = self.palette()
        text_colour = pal.color(QPalette.ColorRole.WindowText)
        muted = QColor(text_colour)
        muted.setAlpha(150)
        track = pal.color(QPalette.ColorRole.Base)
        edge = pal.color(QPalette.ColorRole.Mid)
        fill = pal.color(QPalette.ColorRole.Highlight)
        fill_idle = QColor(fill)
        fill_idle.setAlpha(110)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        small = QFont(self.font())
        small.setPointSizeF(max(8.0, small.pointSizeF() - 0.5))
        painter.setFont(small)

        text_h = 16
        bar_rect = QRect(0, text_h + 1, self.width(), 15)

        # Beschriftung links, Messwerte rechts
        painter.setPen(QPen(text_colour))
        painter.drawText(
            QRect(0, 0, self.width() // 2, text_h),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self.axis.label,
        )
        def clamp(pct: float) -> float:
            return max(-100.0, min(100.0, pct))

        if self.bipolar:
            pct_text = f"{clamp(info.as_percent(self.value - info.centre) * 2):+.1f} %"
        else:
            pct_text = f"{clamp(info.as_percent(self.value - info.minimum)):.1f} %"
        painter.setPen(QPen(muted))
        painter.drawText(
            QRect(self.width() // 2, 0, self.width() // 2, text_h),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            f"{self.value}   {pct_text}   [{info.minimum} .. {info.maximum}]",
        )

        # Schiene
        painter.setPen(QPen(edge, 1))
        painter.setBrush(track)
        painter.drawRoundedRect(bar_rect, 3, 3)

        inner = bar_rect.adjusted(1, 1, -1, -1)

        # Deadzone-Band um die Mitte
        if info.flat > 0 and info.span > 0:
            half = inner.width() * (info.flat / info.span)
            centre_x = inner.left() + inner.width() * self._fraction(info.centre)
            zone = QRect(int(centre_x - half), inner.top(), max(1, int(half * 2)), inner.height())
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(DEADZONE_COLOUR)
            painter.drawRect(zone.intersected(inner))

        # Fuellung
        in_deadzone = info.flat > 0 and abs(self.value - info.centre) <= info.flat
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(fill_idle if in_deadzone else fill)
        start = self._fraction(info.centre) if self.bipolar else 0.0
        end = self._fraction(self.value)
        left = inner.left() + inner.width() * min(start, end)
        width = inner.width() * abs(end - start)
        painter.drawRect(
            QRect(int(left), inner.top() + 1, max(2, int(width)), inner.height() - 2)
        )

        # Mittenmarke
        if self.bipolar:
            centre_x = int(inner.left() + inner.width() * self._fraction(info.centre))
            painter.setPen(QPen(muted, 1))
            painter.drawLine(centre_x, bar_rect.top(), centre_x, bar_rect.bottom())

        painter.end()


class HatWidget(QWidget):
    """8-Wege-Kompass fuer ein Hat-Achsenpaar (z.B. ABS_HAT0X/Y).

    Ein Hat ist digital: X und Y liegen praktisch immer bei -1, 0 oder +1.
    Als zwei Balken dargestellt sieht man nur zwei zuckende Striche und muss
    im Kopf zusammensetzen, welche der 8 Richtungen das ergibt. Hier wird
    stattdessen direkt die aktuelle Richtung markiert.
    """

    # Reihenfolge im Uhrzeigersinn ab oben, fuer die Marker-Positionen.
    DIRECTIONS = [
        (0, -1), (1, -1), (1, 0), (1, 1),
        (0, 1), (-1, 1), (-1, 0), (-1, -1),
    ]

    def __init__(self, label: str, x_code: int, y_code: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.label = label
        self.x_code = x_code
        self.y_code = y_code
        self.x_value = 0
        self.y_value = 0
        self.setMinimumSize(96, 96)
        self.setToolTip(f"evdev ABS 0x{x_code:02x} / 0x{y_code:02x}")

    def set_values(self, x: int, y: int) -> None:
        x = 0 if x == 0 else (1 if x > 0 else -1)
        y = 0 if y == 0 else (1 if y > 0 else -1)
        if (x, y) != (self.x_value, self.y_value):
            self.x_value, self.y_value = x, y
            self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        pal = self.palette()
        text_colour = pal.color(QPalette.ColorRole.WindowText)
        edge = pal.color(QPalette.ColorRole.Mid)
        base = pal.color(QPalette.ColorRole.Base)
        highlight = pal.color(QPalette.ColorRole.Highlight)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        label_h = 16
        side = min(self.width(), self.height() - label_h)
        cx = self.width() / 2
        cy = label_h + (self.height() - label_h) / 2
        r_outer = side * 0.46
        r_dot = side * 0.11

        small = QFont(self.font())
        small.setPointSizeF(max(8.0, small.pointSizeF() - 0.5))
        painter.setFont(small)
        painter.setPen(QPen(text_colour))
        painter.drawText(
            QRect(0, 0, self.width(), label_h),
            Qt.AlignmentFlag.AlignCenter,
            self.label,
        )

        # Aussenring
        painter.setPen(QPen(edge, 2))
        painter.setBrush(base)
        painter.drawEllipse(int(cx - r_outer), int(cy - r_outer), int(r_outer * 2), int(r_outer * 2))

        active = (self.x_value, self.y_value)
        centred = active == (0, 0)

        # Mittelpunkt: leuchtet, wenn der Hat losgelassen ist
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(highlight if centred else edge)
        painter.drawEllipse(int(cx - r_dot * 0.6), int(cy - r_dot * 0.6), int(r_dot * 1.2), int(r_dot * 1.2))

        # Die 8 Positionen, aktuelle Richtung hervorgehoben
        for dx, dy in self.DIRECTIONS:
            px = cx + dx * r_outer * 0.72
            py = cy + dy * r_outer * 0.72
            is_active = not centred and (dx, dy) == active
            painter.setBrush(highlight if is_active else edge)
            size = r_dot * (1.3 if is_active else 1.0)
            painter.drawEllipse(int(px - size / 2), int(py - size / 2), int(size), int(size))

        painter.end()



class ButtonGrid(QWidget):
    """Raster aller Tasten. Gedrueckte Tasten leuchten auf.

    Zeigt Nummer und Kernel-Name zusammen (z.B. "12  BTN_TOP"), weil es
    keine verlaessliche Saitek-Nummerierung zum Nachschlagen gibt - der
    Kernel-Name ist das, was auch in evtest oder einer .binds-Datei steht.
    """

    COLUMNS = 4

    def __init__(self, buttons: list[Button], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.cells: dict[int, QLabel] = {}
        self._state: dict[int, bool] = {}

        pal = self.palette()
        highlight = pal.color(QPalette.ColorRole.Highlight)
        highlight_text = pal.color(QPalette.ColorRole.HighlightedText)
        base = pal.color(QPalette.ColorRole.Base)
        mid = pal.color(QPalette.ColorRole.Mid)
        muted = QColor(pal.color(QPalette.ColorRole.WindowText))
        muted.setAlpha(160)

        self.style_idle = (
            f"QLabel{{border:1px solid {mid.name()};border-radius:3px;padding:4px 2px;"
            f"color:rgba({muted.red()},{muted.green()},{muted.blue()},{muted.alphaF():.2f});"
            f"background:{base.name()};}}"
        )
        self.style_active = (
            f"QLabel{{border:1px solid {highlight.name()};border-radius:3px;padding:4px 2px;"
            f"color:{highlight_text.name()};background:{highlight.name()};font-weight:700;}}"
        )

        small = QFont(self.font())
        small.setPointSizeF(max(7.5, small.pointSizeF() - 1.0))

        grid = QGridLayout(self)
        grid.setSpacing(3)
        grid.setContentsMargins(0, 0, 0, 0)
        for i, button in enumerate(buttons):
            cell = QLabel(button.label)
            cell.setFont(small)
            cell.setWordWrap(True)
            cell.setMinimumHeight(36)
            cell.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cell.setStyleSheet(self.style_idle)
            cell.setToolTip(
                f"{button.evdev_name}  (0x{button.code:x})\n"
                "Physische Bezeichnung an echter Hardware bestaetigt."
            )
            grid.addWidget(cell, i // self.COLUMNS, i % self.COLUMNS)
            self.cells[button.code] = cell
            self._state[button.code] = False
        for column in range(self.COLUMNS):
            grid.setColumnStretch(column, 1)

    def update_state(self, pressed: dict[int, bool]) -> None:
        for code, cell in self.cells.items():
            now = pressed.get(code, False)
            if now != self._state[code]:
                self._state[code] = now
                cell.setStyleSheet(self.style_active if now else self.style_idle)
