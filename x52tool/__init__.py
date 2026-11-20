"""x52tool - Test-, Analyse- und Kalibrierwerkzeug fuer den Saitek/Logitech X52 (Pro).

Aufbau:
    device.py    Geraeteerkennung, evdev-Zugriff, ABS-Ioctls (Lesen/Schreiben)
    analysis.py  Ruhe- und Bereichsmessung, Deadzone-Vorschlag, udev-Regeln
    output.py    LED- und MFD-Ausgabe ueber x52ctl (x52d)
    x52d_conf.py dauerhafte x52d-Konfiguration
    config.py    Profile und Einstellungen unter ~/.config/x52tool/
    ui/          PyQt6-Oberflaeche, ein Modul pro Reiter
"""

__version__ = "0.0.3.2-beta"
__all__ = ["__version__"]
