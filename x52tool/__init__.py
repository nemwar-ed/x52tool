"""x52tool - Test-, Analyse- und Kalibrierwerkzeug fuer den Saitek/Logitech X52 (Pro).

Aufbau:
    device.py    Geraeteerkennung, evdev-Zugriff, ABS-Ioctls (Lesen/Schreiben)
    analysis.py  Ruhe- und Bereichsmessung, Deadzone-Vorschlag, udev-Regeln
    output.py    LED- und MFD-Ausgabe ueber ein externes libx52-CLI
    config.py    Profile und Einstellungen unter ~/.config/x52tool/
    ui/          PyQt6-Oberflaeche, ein Modul pro Reiter
"""

__version__ = "0.3.1"
__all__ = ["__version__"]
