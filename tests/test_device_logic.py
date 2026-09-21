"""Direkte Tests fuer device.py, ohne Qt und ohne echte Hardware.

Diese Tests waren der fehlende Teil, der die drei Regressionen mit
verstuemmelten Funktionskoerpern (_is_joystick, ButtonGrid) nicht
aufgefangen hat: ein 'startet ohne Absturz'-Test sieht identisch aus,
egal ob eine Funktion korrekt oder leer ist, wenn in der Testumgebung
ohnehin kein echter Stick angeschlossen ist. Diese Tests rufen die
Funktionen stattdessen direkt mit synthetischen Werten auf und pruefen
das tatsaechliche Ergebnis.

Aufruf: python3 -m pytest tests/ -v
oder ohne pytest: python3 tests/test_device_logic.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evdev import ecodes

from x52tool.device import X52_PRO_BUTTON_LABELS, _is_joystick, _name_tokens, button_label, evdev_button_name


class FakeCapsDevice:
    """Attrappe mit fester capabilities()-Rueckgabe, wie evdev.InputDevice sie liefert."""

    def __init__(self, caps: dict) -> None:
        self._caps = caps

    def capabilities(self, absinfo: bool = False) -> dict:
        return self._caps


def test_is_joystick_erkennt_x52():
    """Ein Geraet mit Stick-Achsen und Joystick-Tasten muss True liefern."""
    caps = {
        ecodes.EV_ABS: [ecodes.ABS_X, ecodes.ABS_Y, ecodes.ABS_Z],
        ecodes.EV_KEY: [ecodes.BTN_TRIGGER, ecodes.BTN_THUMB],
    }
    assert _is_joystick(FakeCapsDevice(caps)) is True


def test_is_joystick_lehnt_tastatur_ab():
    """Eine normale Tastatur (keine ABS-Achsen) darf nicht als Joystick durchgehen."""
    caps = {ecodes.EV_KEY: [ecodes.KEY_A, ecodes.KEY_B, ecodes.KEY_ENTER]}
    assert _is_joystick(FakeCapsDevice(caps)) is False


def test_is_joystick_lehnt_maus_ab():
    """Eine Maus hat REL-Achsen, keine ABS_X/Y und keine Joystick-Tasten-Range."""
    caps = {
        ecodes.EV_REL: [ecodes.REL_X, ecodes.REL_Y],
        ecodes.EV_KEY: [ecodes.BTN_LEFT, ecodes.BTN_RIGHT],
    }
    assert _is_joystick(FakeCapsDevice(caps)) is False


def test_is_joystick_ohne_buttons():
    """Nur ABS_X/Y ohne jede Taste im Joystick-Bereich reicht nicht."""
    caps = {ecodes.EV_ABS: [ecodes.ABS_X, ecodes.ABS_Y]}
    assert _is_joystick(FakeCapsDevice(caps)) is False


def test_name_tokens_findet_gemeinsames_x52():
    """Realer Fall: Haupt-Stick und virtuelle Ministick-Maus teilen sich 'x52'."""
    main = _name_tokens("Logitech X52 Professional H.O.T.A.S.")
    virtual = _name_tokens("X52 virtual mouse")
    assert main & virtual == {"x52"}


def test_name_tokens_ignoriert_fremdgeraet():
    """Eine Tastatur mit anderem Namen darf keine Ueberschneidung ergeben."""
    main = _name_tokens("Logitech X52 Professional H.O.T.A.S.")
    keyboard = _name_tokens("AT Translated Set 2 keyboard")
    assert not (main & keyboard)


def test_x52_pro_button_mapping_hat_39_eintraege():
    """Der echte X52 Pro hat 39 Tasten - die Tabelle darf nicht schrumpfen."""
    assert len(X52_PRO_BUTTON_LABELS) == 39


def test_x52_pro_button_mapping_reihenfolge_stimmt_mit_geraet_ueberein():
    """Die ersten 12 sortierten Codes muessen exakt Trigger..T4 ergeben -
    von Oliver an echter Hardware bestaetigt."""
    codes = sorted(X52_PRO_BUTTON_LABELS.keys())
    erwartet = [
        "Trigger", "Fire", "Fire A", "Fire B", "Fire C", "Pinkie Trigger", "Fire D", "Fire E",
        "T1", "T2", "T3", "T4",
    ]
    tatsaechlich = [X52_PRO_BUTTON_LABELS[c] for c in codes[:12]]
    assert tatsaechlich == erwartet


def test_x52_pro_button_mapping_maus_und_mfd_stellen_korrigiert():
    """Zwei Stellen, an denen die erste (Community-)Fassung falsch lag und
    Oliver an echter Hardware korrigiert hat: 16-19 sind Maustasten/-rad,
    nicht ein Daumenrad am Ministick; 39 ist 'Rad rechts gedrueckt', keine
    eigene MFD-Auswahltaste."""
    codes = sorted(X52_PRO_BUTTON_LABELS.keys())
    assert X52_PRO_BUTTON_LABELS[codes[15]] == "Mouse Button 1 (links)"  # Nr. 16
    assert X52_PRO_BUTTON_LABELS[codes[18]] == "Mouse Button 2 (rechts)"  # Nr. 19
    assert X52_PRO_BUTTON_LABELS[codes[38]] == "Rad rechts gedrueckt"  # Nr. 39


def test_x52_pro_button_mapping_unbenannte_luecken_codes_beruecksichtigt():
    """Regression: zwischen BTN_BASE6 und BTN_DEAD liegen drei vom Kernel
    unbenannte Codes (0x12c-0x12e), die der X52 Pro tatsaechlich benutzt.
    Werden sie beim Aufbau der Tabelle uebersehen, verschiebt sich alles ab
    Taste 13 um drei Stellen, ohne dass die Gesamtzahl (39) es verraet."""
    from evdev import ecodes
    codes = sorted(X52_PRO_BUTTON_LABELS.keys())
    assert codes[12:15] == [ecodes.BTN_BASE6 + 1, ecodes.BTN_BASE6 + 2, ecodes.BTN_BASE6 + 3]
    assert [X52_PRO_BUTTON_LABELS[c] for c in codes[12:16]] == [
        "T5", "T6", "Second Trigger", "Mouse Button 1 (links)",
    ]


def test_button_label_nutzt_physischen_namen_nur_wenn_pro():
    """Ohne is_pro=True (unbekanntes/nicht-Pro-Geraet) nie die Pro-Tabelle
    anwenden - der normale X52 (ohne Pro) hat eine andere Tastenbelegung."""
    from evdev import ecodes
    name = evdev_button_name(ecodes.BTN_TRIGGER)
    mit_pro = button_label(name, ecodes.BTN_TRIGGER, is_pro=True)
    ohne_pro = button_label(name, ecodes.BTN_TRIGGER, is_pro=False)
    assert mit_pro == "Trigger"
    assert ohne_pro == name


def test_axis_label_rotary_achsen():
    """ABS_RX/ABS_RY sind die beiden Rotary-Dreher am Schubhebel, von Oliver
    bestaetigt - vorher fielen sie faelschlich unter 'Ministick'."""
    from evdev import ecodes
    from x52tool.device import axis_label
    assert axis_label(ecodes.ABS_RX) == "Rotary 1"
    assert axis_label(ecodes.ABS_RY) == "Rotary 2"


def test_pov_button_gruppen_zeigen_auf_bekannte_tasten():
    """POV2/POV3 sind beim X52 Pro Tasten, keine Achsen - jede der acht
    Tasten in X52_PRO_POV_BUTTON_GROUPS muss auch in der Haupttabelle mit
    dem erwarteten POV-Namen stehen, sonst zeigt der Kompass ins Leere."""
    from x52tool.device import X52_PRO_POV_BUTTON_GROUPS

    assert set(X52_PRO_POV_BUTTON_GROUPS) == {"Hat 2", "Hat 3"}
    for hat_name, (up, right, down, left) in X52_PRO_POV_BUTTON_GROUPS.items():
        prefix = "POV2" if hat_name == "Hat 2" else "POV3"
        assert X52_PRO_BUTTON_LABELS[up] == f"{prefix} hoch"
        assert X52_PRO_BUTTON_LABELS[right] == f"{prefix} rechts"
        assert X52_PRO_BUTTON_LABELS[down] == f"{prefix} runter"
        assert X52_PRO_BUTTON_LABELS[left] == f"{prefix} links"



def test_x52_pro_button_31_heisst_clutch():
    """Taste 31 (Symbol: ein 'i' im Kreis) heisst tatsaechlich Clutch,
    nicht nur 'i' - von Oliver korrigiert."""
    codes = sorted(X52_PRO_BUTTON_LABELS.keys())
    assert X52_PRO_BUTTON_LABELS[codes[30]] == "Clutch"  # Nr. 31


def test_backend_set_clutch_baut_erwarteten_befehl():
    """set_clutch() muss die konfigurierte Vorlage mit 0/1 fuellen."""
    from x52tool.config import BackendConfig
    from x52tool.output import Backend

    backend = Backend(BackendConfig(binary="/usr/bin/x52cli"))
    an = backend.preview(backend.config.clutch, value="1")
    aus = backend.preview(backend.config.clutch, value="0")
    assert an == "/usr/bin/x52cli -c 1"
    assert aus == "/usr/bin/x52cli -c 0"



if __name__ == "__main__":
    # Laeuft auch ohne pytest - fuer eine schnelle Kontrolle per
    # 'python3 tests/test_device_logic.py'.
    tests = [obj for name, obj in list(globals().items()) if name.startswith("test_")]
    failures = 0
    for test in tests:
        try:
            test()
            print(f"OK    {test.__name__}")
        except AssertionError as exc:
            failures += 1
            print(f"FEHLER {test.__name__}: {exc}")
    print(f"\n{len(tests) - failures}/{len(tests)} bestanden")
    raise SystemExit(1 if failures else 0)
