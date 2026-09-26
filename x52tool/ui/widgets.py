"""Anzeigebausteine, die mehrere Reiter benutzen.

Alle Farben kommen aus der Qt-Palette, damit die Balken in hellen und in
dunklen Themes lesbar bleiben.
"""

from __future__ import annotations

from PyQt6.QtCore import QRect, Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPalette, QPen
from PyQt6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QSizePolicy, QWidget

from evdev import ecodes

from ..device import ABS_MISC_Y, AbsInfo, Axis, Button, display_value

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
    # Ministick: 0..15, aber Oliver hat bestaetigt, dass die Ruhelage in der
    # Mitte liegt (Rohwert 8), nicht am Anfang - technisch also bipolar,
    # auch wenn er als digitale Achse (siehe DIGITAL_AXES) keine Deadzone
    # braucht.
    ecodes.ABS_MISC,
    ABS_MISC_Y,
}

class AxisBar(QWidget):
    """Balken mit Rohwert - waagerecht oder senkrecht.

    Zeigt bei Achsen mit einer Mitte (bipolar) die vorzeichenbehaftete
    Abweichung von der Mitte (z.B. "+3"), bei Achsen ohne Mitte den
    nackten Rohwert (z.B. "200") - keine Prozente, kein Bereich. Die
    Deadzone/Fuzz-Bearbeitung passiert im Kalibrierungs-Reiter; hier geht
    es nur um den Live-Wert.
    """

    def __init__(
        self, axis: Axis, parent: QWidget | None = None, orientation: str = "horizontal"
    ) -> None:
        super().__init__(parent)
        self.axis = axis
        self.value = axis.info.value
        self.orientation = orientation
        if orientation == "vertical":
            self.setMinimumSize(72, 140)
            self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        else:
            self.setMinimumSize(260, 38)
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
        shown = display_value(self.axis.code, info, int(value))
        return min(1.0, max(0.0, (shown - info.minimum) / info.span))

    def _value_text(self) -> str:
        info = self.axis.info
        shown_value = display_value(self.axis.code, info, self.value)
        if self.bipolar:
            return f"{shown_value - info.centre:+d}"
        return str(shown_value)

    # -- Zeichnen ----------------------------------------------------------

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt-Namenskonvention
        if self.orientation == "vertical":
            self._paint_vertical()
        else:
            self._paint_horizontal()

    def _colours(self):
        pal = self.palette()
        text_colour = pal.color(QPalette.ColorRole.WindowText)
        muted = QColor(text_colour)
        muted.setAlpha(150)
        track = pal.color(QPalette.ColorRole.Base)
        edge = pal.color(QPalette.ColorRole.Mid)
        fill = pal.color(QPalette.ColorRole.Highlight)
        return text_colour, muted, track, edge, fill

    def _paint_horizontal(self) -> None:
        text_colour, muted, track, edge, fill = self._colours()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        small = QFont(self.font())
        small.setPointSizeF(max(8.0, small.pointSizeF() - 0.5))
        painter.setFont(small)

        text_h = 16
        bar_rect = QRect(0, text_h + 1, self.width(), 15)

        metrics = painter.fontMetrics()
        label_w = min(self.width() - 40, metrics.horizontalAdvance(self.axis.label) + 6)
        painter.setPen(QPen(text_colour))
        painter.drawText(
            QRect(0, 0, label_w, text_h),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self.axis.label,
        )
        painter.setPen(QPen(muted))
        painter.drawText(
            QRect(label_w, 0, self.width() - label_w, text_h),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            self._value_text(),
        )

        painter.setPen(QPen(edge, 1))
        painter.setBrush(track)
        painter.drawRoundedRect(bar_rect, 3, 3)

        inner = bar_rect.adjusted(1, 1, -1, -1)

        # Oranger Deadzone-Bereich – nur für Achsen mit Mitte (bipolar)
        info = self.axis.info
        dead_size = max(info.fuzz, info.flat)
        if dead_size > 0 and info.span > 0 and self.bipolar:
            dead_colour = QColor(255, 140, 0, 120)
            centre_frac = self._fraction(info.centre)
            fuzz_frac   = dead_size / info.span
            dead_left  = inner.left() + inner.width() * max(0.0, centre_frac - fuzz_frac)
            dead_right = inner.left() + inner.width() * min(1.0, centre_frac + fuzz_frac)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(dead_colour)
            painter.drawRect(QRect(
                int(dead_left), inner.top(),
                max(2, int(dead_right - dead_left)), inner.height()
            ))

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(fill)
        start = self._fraction(self.axis.info.centre) if self.bipolar else 0.0
        end = self._fraction(self.value)
        left = inner.left() + inner.width() * min(start, end)
        width = inner.width() * abs(end - start)
        painter.drawRect(
            QRect(int(left), inner.top() + 1, max(2, int(width)), inner.height() - 2)
        )
        painter.end()

    def _paint_vertical(self) -> None:
        text_colour, muted, track, edge, fill = self._colours()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        small = QFont(self.font())
        small.setPointSizeF(max(8.0, small.pointSizeF() - 0.5))
        painter.setFont(small)

        label_h = 16
        value_h = 16
        painter.setPen(QPen(text_colour))
        painter.drawText(
            QRect(0, 0, self.width(), label_h),
            Qt.AlignmentFlag.AlignCenter,
            self.axis.label,
        )
        painter.setPen(QPen(muted))
        painter.drawText(
            QRect(0, self.height() - value_h, self.width(), value_h),
            Qt.AlignmentFlag.AlignCenter,
            self._value_text(),
        )

        margin = 6
        bar_rect = QRect(
            margin, label_h + 2, self.width() - 2 * margin, self.height() - label_h - value_h - 4
        )
        painter.setPen(QPen(edge, 1))
        painter.setBrush(track)
        painter.drawRoundedRect(bar_rect, 3, 3)

        inner = bar_rect.adjusted(1, 1, -1, -1)

        # Oranger Deadzone-Bereich – nur für Achsen mit Mitte (bipolar)
        info = self.axis.info
        dead_size = max(info.fuzz, info.flat)
        if dead_size > 0 and info.span > 0 and self.bipolar:
            dead_colour = QColor(255, 140, 0, 120)
            centre_frac = self._fraction(info.centre)
            fuzz_frac   = dead_size / info.span
            # Vertikal: 0 = unten, 1 = oben
            dead_top    = inner.top() + inner.height() * max(0.0, 1.0 - centre_frac - fuzz_frac)
            dead_bottom = inner.top() + inner.height() * min(1.0, 1.0 - centre_frac + fuzz_frac)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(dead_colour)
            painter.drawRect(QRect(
                inner.left(), int(dead_top),
                inner.width(), max(2, int(dead_bottom - dead_top))
            ))

        start = self._fraction(self.axis.info.centre) if self.bipolar else 0.0
        end = self._fraction(self.value)
        # Fraktion 0 = unten, 1 = oben (Hebel-Metapher: nach oben = mehr).
        top_frac = 1.0 - max(start, end)
        bottom_frac = 1.0 - min(start, end)
        top = inner.top() + inner.height() * top_frac
        bottom = inner.top() + inner.height() * bottom_frac
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(fill)
        painter.drawRect(QRect(inner.left() + 1, int(top), inner.width() - 2, max(2, int(bottom - top))))
        painter.end()


class Position2DWidget(QWidget):
    """2D-Positionsfeld fuer ein Achsenpaar mit Mitte (Stick X/Y, Ministick).

    Zeigt die tatsaechliche Auslenkung als Punkt in einem Quadrat, dazu
    darunter die vorzeichenbehafteten Abweichungen beider Achsen von ihrer
    jeweiligen Mitte - kein Rohwert, keine Prozente, keine Deadzone.
    Angelehnt an die "X Axis / Y Axis"-Darstellung der originalen Saitek/
    Logitech-Windows-Software.
    """

    def __init__(self, label: str, x_axis: Axis, y_axis: Axis, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.label = label
        self.x_axis = x_axis
        self.y_axis = y_axis
        self.x_value = x_axis.info.value
        self.y_value = y_axis.info.value
        self.setMinimumSize(150, 175)
        self.setToolTip(f"evdev ABS 0x{x_axis.code:02x} / 0x{y_axis.code:02x}")

    def set_values(self, x: int, y: int) -> None:
        if (x, y) != (self.x_value, self.y_value):
            self.x_value, self.y_value = x, y
            self.update()

    @staticmethod
    def _fraction(axis: Axis, value: int) -> float:
        info = axis.info
        if info.span == 0:
            return 0.5
        shown       = display_value(axis.code, info, value)
        shown_center = display_value(axis.code, info, info.value)
        return min(1.0, max(0.0, 0.5 + (shown - shown_center) / info.span))

    def paintEvent(self, _event) -> None:  # noqa: N802
        pal = self.palette()
        text_colour = pal.color(QPalette.ColorRole.WindowText)
        muted = QColor(text_colour)
        muted.setAlpha(150)
        track = pal.color(QPalette.ColorRole.Base)
        edge = pal.color(QPalette.ColorRole.Mid)
        highlight = pal.color(QPalette.ColorRole.Highlight)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        small = QFont(self.font())
        small.setPointSizeF(max(8.0, small.pointSizeF() - 0.5))
        painter.setFont(small)

        label_h = 16
        value_h = 16
        painter.setPen(QPen(text_colour))
        painter.drawText(
            QRect(0, 0, self.width(), label_h),
            Qt.AlignmentFlag.AlignCenter,
            self.label,
        )

        side = min(self.width(), self.height() - label_h - value_h) - 4
        square = QRect(
            (self.width() - side) // 2, label_h + 2, side, side
        )
        painter.setPen(QPen(edge, 1))
        painter.setBrush(track)
        painter.drawRect(square)

        cx = square.left() + square.width() * self._fraction(self.x_axis, self.x_value)
        # Bildschirm-Y waechst nach unten; "oben" im Feld soll dem Maximum
        # der Y-Achse entsprechen, wie bei der Vorlage.
        cy = square.top() + square.height() * (1.0 - self._fraction(self.y_axis, self.y_value))

        # Fadenkreuz in der Mitte
        painter.setPen(QPen(muted, 1))
        mid_x, mid_y = square.center().x(), square.center().y()
        painter.drawLine(mid_x - 6, mid_y, mid_x + 6, mid_y)
        painter.drawLine(mid_x, mid_y - 6, mid_x, mid_y + 6)

        # Oranger Deadzone-Kreis (fuzz oder flat > 0)
        fuzz_x = max(self.x_axis.info.fuzz, self.x_axis.info.flat)
        fuzz_y = max(self.y_axis.info.fuzz, self.y_axis.info.flat)
        if (fuzz_x > 0 or fuzz_y > 0) and self.x_axis.info.span > 0 and self.y_axis.info.span > 0:
            dead_colour = QColor(255, 140, 0, 80)
            rx = int(square.width()  * fuzz_x / self.x_axis.info.span)
            ry = int(square.height() * fuzz_y / self.y_axis.info.span)
            r_dead = max(rx, ry, 3)
            painter.setPen(QPen(QColor(255, 140, 0, 180), 1))
            painter.setBrush(dead_colour)
            painter.drawEllipse(int(mid_x - r_dead), int(mid_y - r_dead), r_dead * 2, r_dead * 2)

        # Aktuelle Position
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(highlight)
        r = 5
        painter.drawEllipse(int(cx - r), int(cy - r), r * 2, r * 2)

        x_info, y_info = self.x_axis.info, self.y_axis.info
        x_shown  = display_value(self.x_axis.code, x_info, self.x_value)
        y_shown  = display_value(self.y_axis.code, y_info, self.y_value)
        x_center = display_value(self.x_axis.code, x_info, x_info.value)
        y_center = display_value(self.y_axis.code, y_info, y_info.value)
        # Offset als % relativ zum halben Achsenbereich – immer symmetrisch
        x_half = x_info.span / 2 or 1
        y_half = y_info.span / 2 or 1
        x_pct = max(-100, min(100, int(round((x_shown - x_center) / x_half * 100))))
        y_pct = max(-100, min(100, int(round((y_shown - y_center) / y_half * 100))))
        text = f"X: {x_pct:+d}%   Y: {y_pct:+d}%"
        painter.setPen(QPen(muted))
        painter.drawText(
            QRect(0, self.height() - value_h, self.width(), value_h),
            Qt.AlignmentFlag.AlignCenter,
            text,
        )
        painter.end()


class _CompassWidget(QWidget):
    """Gemeinsame Zeichnung fuer einen 8-Wege-Kompass.

    Ein Hat ist digital: X und Y liegen praktisch immer bei -1, 0 oder +1.
    Als zwei Balken dargestellt sieht man nur zwei zuckende Striche und muss
    im Kopf zusammensetzen, welche der 8 Richtungen das ergibt. Hier wird
    stattdessen direkt die aktuelle Richtung markiert. Diese Basisklasse
    kennt nur x_value/y_value; woher die kommen (eine Achse oder vier
    Einzeltasten), entscheiden die Unterklassen.
    """

    # Reihenfolge im Uhrzeigersinn ab oben, fuer die Marker-Positionen.
    DIRECTIONS = [
        (0, -1), (1, -1), (1, 0), (1, 1),
        (0, 1), (-1, 1), (-1, 0), (-1, -1),
    ]

    def __init__(self, label: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.label = label
        self.x_value = 0
        self.y_value = 0
        self.setMinimumSize(96, 96)

    def _set_direction(self, x: int, y: int) -> None:
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

        # Die 8 Positionen, aktuelle Richtung hervorgehoben. Diagonalen
        # (Ecken) werden bewusst kleiner gezeichnet als die vier
        # Haupt-Richtungen - eine leichte visuelle Andeutung, keine
        # Einschraenkung: alle drei Hats koennen tatsaechlich 8 Wege.
        for dx, dy in self.DIRECTIONS:
            is_diagonal = dx != 0 and dy != 0
            px = cx + dx * r_outer * 0.72
            py = cy + dy * r_outer * 0.72
            is_active = not centred and (dx, dy) == active
            painter.setBrush(highlight if is_active else edge)
            base_size = r_dot * (0.7 if is_diagonal else 1.0)
            size = base_size * (1.3 if is_active else 1.0)
            painter.drawEllipse(int(px - size / 2), int(py - size / 2), int(size), int(size))

        painter.end()


class HatWidget(_CompassWidget):
    """Kompass fuer ein echtes Hat-Achsenpaar (z.B. ABS_HAT0X/Y)."""

    def __init__(self, label: str, x_code: int, y_code: int, parent: QWidget | None = None) -> None:
        super().__init__(label, parent)
        self.x_code = x_code
        self.y_code = y_code
        self.setToolTip(f"evdev ABS 0x{x_code:02x} / 0x{y_code:02x}")

    def set_values(self, x: int, y: int) -> None:
        self._set_direction(x, y)


class ButtonHatWidget(_CompassWidget):
    """Kompass fuer einen Hat, der als vier Einzeltasten kommt (POV2/POV3
    beim X52 Pro). Die vier zugehoerigen Tasten leuchten in der ButtonGrid
    unabhaengig davon weiter mit - dieser Kompass ist eine zusaetzliche,
    leichter lesbare Ansicht derselben Events, keine Ersetzung.
    """

    def __init__(
        self, label: str, up: int, right: int, down: int, left: int, parent: QWidget | None = None
    ) -> None:
        super().__init__(label, parent)
        self.up, self.right, self.down, self.left = up, right, down, left
        self.setToolTip(
            f"evdev-Codes 0x{up:x} (hoch) / 0x{right:x} (rechts) / "
            f"0x{down:x} (runter) / 0x{left:x} (links)"
        )

    def set_pressed(self, pressed: dict[int, bool]) -> None:
        x = (1 if pressed.get(self.right) else 0) - (1 if pressed.get(self.left) else 0)
        y = (1 if pressed.get(self.down) else 0) - (1 if pressed.get(self.up) else 0)
        self._set_direction(x, y)



class ButtonTile(QLabel):
    """Einzelne Taste (oder ein Tastenpaar) als kleine, frei platzierbare Kachel.

    Ersetzt das alte Raster (ButtonGrid): auf der Silhouette sitzt jede
    Taste an ihrer ungefaehren physischen Position statt in einer
    durchnummerierten Liste - die Nummer entfaellt deshalb, der Name
    reicht zur Identifikation. Ein Tastenpaar (z.B. T1/T2, oder Trigger
    Stufe 1+2) leuchtet, sobald irgendeiner der Codes gedrueckt ist.
    """

    def __init__(
        self,
        label: str,
        codes: list[int],
        evdev_name: str = "",
        parent: QWidget | None = None,
        number: int | None = None,
    ) -> None:
        super().__init__(parent)
        self.codes = codes
        self._pressed = False
        pal = self.palette()
        self._highlight = pal.color(QPalette.ColorRole.Highlight)
        self._highlight_text = pal.color(QPalette.ColorRole.HighlightedText)
        self._base = pal.color(QPalette.ColorRole.Base)
        self._mid = pal.color(QPalette.ColorRole.Mid)
        muted = QColor(pal.color(QPalette.ColorRole.WindowText))
        muted.setAlpha(160)
        self._style_idle = (
            f"QLabel{{border:1px solid {self._mid.name()};border-radius:3px;padding:2px 4px;"
            f"color:rgba({muted.red()},{muted.green()},{muted.blue()},{muted.alphaF():.2f});"
            f"background:{self._base.name()};}}"
        )
        self._style_active = (
            f"QLabel{{border:1px solid {self._highlight.name()};border-radius:3px;padding:2px 4px;"
            f"color:{self._highlight_text.name()};background:{self._highlight.name()};font-weight:700;}}"
        )
        small = QFont(self.font())
        small.setPointSizeF(max(7.0, small.pointSizeF() - 1.5))
        self.setFont(small)
        if number is not None:
            self.setTextFormat(Qt.TextFormat.RichText)
            self.setText(
                f"<div style='font-size:{small.pointSizeF() - 1.5:.1f}pt;opacity:0.6;'>"
                f"{number}</div><div>{label}</div>"
            )
        else:
            self.setText(label)
        self.setWordWrap(True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet(self._style_idle)
        if evdev_name:
            self.setToolTip(f"{evdev_name}  (0x{codes[0]:x})")

    def set_pressed_state(self, pressed: dict[int, bool]) -> None:
        now = any(pressed.get(code, False) for code in self.codes)
        if now != self._pressed:
            self._pressed = now
            self.setStyleSheet(self._style_active if now else self._style_idle)


class RockerTriplet(QWidget):
    """Wippe/Rad mit drei Zustaenden: hoch, runter, gedrueckt/Klick.

    Fuer das Mausrad am Schubhebel und die beiden Rollraeder an der
    MFD-Basis - je drei kleine Segmente statt drei einzelner Kacheln,
    kompakter fuer die Position auf der Silhouette.
    """

    def __init__(
        self,
        label: str,
        up_code: int,
        down_code: int,
        press_code: int,
        parent: QWidget | None = None,
        orientation: str = "vertical",
        segment_info: dict[str, tuple[str, int | None]] | None = None,
    ) -> None:
        super().__init__(parent)
        self.label = label
        self.codes = {"up": up_code, "down": down_code, "press": press_code}
        self.orientation = orientation
        self._pressed = {"up": False, "down": False, "press": False}
        # (Kurzname, Tastennummer) je Segment - fuer Beschriftung/Nummer
        # direkt im Segment, wie bei ButtonTile.
        self.segment_info = segment_info or {}
        if orientation == "vertical":
            self.setMinimumSize(40, 90)
        else:
            self.setMinimumSize(80, 46)
        self.setToolTip(f"{label}: hoch 0x{up_code:x} / runter 0x{down_code:x} / Klick 0x{press_code:x}")

    def set_pressed(self, pressed: dict[int, bool]) -> None:
        changed = False
        for key, code in self.codes.items():
            now = pressed.get(code, False)
            if now != self._pressed[key]:
                self._pressed[key] = now
                changed = True
        if changed:
            self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        pal = self.palette()
        text_colour = pal.color(QPalette.ColorRole.WindowText)
        edge = pal.color(QPalette.ColorRole.Mid)
        base = pal.color(QPalette.ColorRole.Base)
        highlight = pal.color(QPalette.ColorRole.Highlight)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        label_h = 14
        small = QFont(self.font())
        small.setPointSizeF(max(7.0, small.pointSizeF() - 1.5))
        painter.setFont(small)
        painter.setPen(QPen(text_colour))
        painter.drawText(
            QRect(0, 0, self.width(), label_h),
            Qt.AlignmentFlag.AlignCenter,
            self.label,
        )

        painter.setPen(QPen(edge, 1))
        body = QRect(0, label_h, self.width(), self.height() - label_h)
        text_colour_active = pal.color(QPalette.ColorRole.HighlightedText)
        tiny = QFont(self.font())
        tiny.setPointSizeF(max(6.5, small.pointSizeF() - 1.0))
        segments = ("up", "press", "down")
        n = len(segments)
        for i, key in enumerate(segments):
            if self.orientation == "vertical":
                h = body.height() / n
                rect = QRect(body.left(), int(body.top() + i * h), body.width(), int(h) - 2)
            else:
                w = body.width() / n
                rect = QRect(int(body.left() + i * w), body.top(), int(w) - 2, body.height())
            active = self._pressed[key]
            painter.setPen(QPen(edge, 1))
            painter.setBrush(highlight if active else base)
            painter.drawRoundedRect(rect, 2, 2)

            seg_label, seg_number = self.segment_info.get(key, ("", None))
            if seg_label or seg_number is not None:
                painter.setPen(QPen(text_colour_active if active else text_colour))
                painter.setFont(tiny)
                text = f"{seg_number}  {seg_label}" if seg_number is not None else seg_label
                painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
        painter.end()


class ButtonGrid(QWidget):
    """Raster aller Tasten. Gedrueckte Tasten leuchten auf.

    Zeigt Nummer (klein) und physische Bezeichnung (gross) untereinander.
    Ist keine Taste in X52_PRO_BUTTON_LABELS bekannt (nicht-Pro-Geraet,
    unbekanntes Modell), steht dort stattdessen der Kernel-Name.
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
            cell = QLabel()
            cell.setTextFormat(Qt.TextFormat.RichText)
            cell.setText(
                f"<div style='font-size:{small.pointSizeF():.1f}pt;opacity:0.6;'>"
                f"{button.index + 1}</div>"
                f"<div style='font-size:{small.pointSizeF() + 2.0:.1f}pt;font-weight:600;'>"
                f"{button.label}</div>"
            )
            cell.setWordWrap(True)
            cell.setMinimumHeight(42)
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


class AxesPanel(QWidget):
    """Achsen-Anzeigeblock: Stick X/Y, Schubhebel, Rotaries, Twist, Schieber.

    Wird sowohl vom Live-Tab als auch vom Kalibrierungs-Tab verwendet.
    Nach set_device() wird der Block neu aufgebaut.
    refresh(axes) muss im UI-Takt aufgerufen werden.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.bars: dict[int, AxisBar] = {}
        self.position_widgets: list[tuple[int, int, Position2DWidget]] = []
        self._layout = QGridLayout(self)
    def set_device(self, by_code: dict[int, Axis], used_codes: set[int]) -> None:
        """Baut den Block für das übergebene Gerät auf."""
        while self._layout.count():
            item = self._layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self.bars.clear()
        self.position_widgets.clear()

        if ecodes.ABS_X in by_code and ecodes.ABS_Y in by_code:
            x_axis, y_axis = by_code[ecodes.ABS_X], by_code[ecodes.ABS_Y]
            pos = Position2DWidget("Stick", x_axis, y_axis)
            self.position_widgets.append((x_axis.code, y_axis.code, pos))
            used_codes.update((x_axis.code, y_axis.code))
            self._layout.addWidget(pos, 0, 0, 3, 1)

        if ecodes.ABS_Z in by_code:
            axis = by_code[ecodes.ABS_Z]
            bar = AxisBar(axis, orientation="vertical")
            self.bars[axis.code] = bar
            used_codes.add(axis.code)
            self._layout.addWidget(bar, 0, 1, 3, 1)

        for row, code in enumerate((ecodes.ABS_RY, ecodes.ABS_RX)):
            if code in by_code:
                axis = by_code[code]
                bar = AxisBar(axis)
                self.bars[axis.code] = bar
                used_codes.add(axis.code)
                self._layout.addWidget(bar, row, 2)

        bottom_row = QHBoxLayout()
        has_bottom = False
        for code in (ecodes.ABS_RZ, ecodes.ABS_THROTTLE):
            if code in by_code:
                axis = by_code[code]
                bar = AxisBar(axis)
                self.bars[axis.code] = bar
                used_codes.add(axis.code)
                bottom_row.addWidget(bar)
                has_bottom = True
        if has_bottom:
            bottom_widget = QWidget()
            bottom_widget.setLayout(bottom_row)
            self._layout.addWidget(bottom_widget, 3, 0, 1, 3)

        self._layout.setColumnStretch(2, 1)


    def refresh(self, axes: dict[int, int]) -> None:
        """Aktualisiert alle Balken und 2D-Felder mit neuen Rohwerten."""
        for code, bar in self.bars.items():
            if code in axes:
                bar.set_value(axes[code])
        for x_code, y_code, pos in self.position_widgets:
            if x_code in axes and y_code in axes:
                pos.set_values(axes[x_code], axes[y_code])

    def refresh_calibration(self, device: "X52Device") -> None:  # type: ignore[name-defined]
        """Nach dem Schreiben neuer Kalibrierdaten Balken neu zeichnen."""
        for axis in device.axes:
            bar = self.bars.get(axis.code)
            if bar is not None:
                bar.set_info(axis.info)
        for _, _, pos in self.position_widgets:
            pos.update()
