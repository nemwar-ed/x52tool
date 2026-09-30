"""Einstiegspunkt.

    python3 -m x52tool                     Oberflaeche
    python3 -m x52tool --list              gefundene Geraete auflisten
    python3 -m x52tool --apply             gespeichertes Profil anwenden
    python3 -m x52tool --apply --device /dev/input/event7
    python3 -m x52tool --clock             Uhrzeit einmalig ins MFD schreiben
                                           (wird vom x52tool-clock.timer aufgerufen)

Der Apply- und Clock-Modus brauchen kein Qt und sind genau das, was
udev-Regeln oder systemd-User-Services aufrufen.
"""

from __future__ import annotations

import argparse
import sys

from .config import Settings
from .device import X52Device, scan
from .logger import get_logger, init as log_init


def _get_version() -> str:
    try:
        from importlib.metadata import version
        return version("x52tool")
    except Exception:
        return "?"


def _list_devices() -> int:
    result = scan()
    if not result.devices:
        print("Kein joystickartiges Eingabegeraet gefunden.")
    for dev in result.devices:
        marker = "*" if dev.known_name else " "
        print(f"{marker} {dev.path}  {dev.usb_id}  {dev.name}")
        for axis in dev.axes:
            info = axis.info
            print(
                f"      ABS 0x{axis.code:02x}  {axis.label:<24} "
                f"min={info.minimum} max={info.maximum} "
                f"fuzz={info.fuzz} flat={info.flat}"
            )
        dev.close()
    for path in result.denied:
        print(f"! {path}  kein Leserecht")
    for msg in result.errors:
        print(f"! {msg}")
    return 0


def _apply_profile(device_path: str | None) -> int:
    settings = Settings.load()
    result = scan()
    devices: list[X52Device] = result.devices
    if device_path:
        devices = [d for d in devices if d.path == device_path]

    if not devices:
        print("Kein passendes Geraet gefunden.", file=sys.stderr)
        return 1

    status = 0
    for dev in devices:
        stored = settings.profile(dev.usb_id)
        if not stored:
            dev.close()
            continue
        # Nur Achsen anwenden, die das Geraet wirklich hat.
        changes = {
            axis.code: stored[axis.code] for axis in dev.axes if axis.code in stored
        }
        try:
            dev.apply_absinfo(changes)
            print(f"{dev.path}: {len(changes)} Achsen gesetzt")
        except OSError as exc:
            print(f"{dev.path}: {exc}", file=sys.stderr)
            status = 1
        finally:
            dev.close()
    return status


def _clock_tick() -> int:
    """Schreibt die aktuelle Uhrzeit einmalig ins MFD via x52ctl.

    Liest die gespeicherten MFD-Einstellungen (12h/24h, Lokalzeit/GMT,
    Datum-Format, Offsets) und sendet die passenden clock/offset-Befehle.
    Wird vom x52tool-clock.timer jede Minute aufgerufen.
    """
    import subprocess
    import shutil

    settings = Settings.load()
    mfd = settings.mfd

    binary = shutil.which("x52ctl")
    if not binary:
        print("x52ctl nicht gefunden – x52d-Daemon laeuft?", file=sys.stderr)
        return 1

    local    = "local" if mfd.local_time else "gmt"
    hr1      = "12hr"  if mfd.clock1_12h else "24hr"
    hr2      = "12hr"  if mfd.clock2_12h else "24hr"
    hr3      = "12hr"  if mfd.clock3_12h else "24hr"
    fmt_map  = {"DD-MM-YY": "ddmmyy", "MM-DD-YY": "mmddyy", "YY-MM-DD": "yymmdd"}
    date_fmt = fmt_map.get(mfd.date_fmt, "ddmmyy")

    cmds = [
        [binary, "clock", local, hr1, date_fmt],
        [binary, "offset", "2", str(mfd.offset2), hr2],
        [binary, "offset", "3", str(mfd.offset3), hr3],
    ]

    status = 0
    for cmd in cmds:
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if result.returncode != 0:
                print(f"Fehler: {' '.join(cmd)}: {result.stderr.strip()}", file=sys.stderr)
                status = 1
        except (OSError, subprocess.TimeoutExpired) as exc:
            print(f"Fehler: {' '.join(cmd)}: {exc}", file=sys.stderr)
            status = 1

    return status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="x52tool", description=__doc__)
    parser.add_argument("--list",  action="store_true", help="Geraete auflisten")
    parser.add_argument("--apply", action="store_true", help="Gespeichertes Profil anwenden")
    parser.add_argument("--clock", action="store_true", help="Uhrzeit einmalig ins MFD schreiben")
    parser.add_argument("--device", help="Event-Device, sonst alle passenden")
    args = parser.parse_args(argv)

    log_init(_get_version())

    if args.list:
        return _list_devices()
    if args.apply:
        return _apply_profile(args.device)
    if args.clock:
        return _clock_tick()

    from . import i18n
    from .ui import run  # Qt erst importieren, wenn es gebraucht wird

    settings = Settings.load()
    i18n.init(settings.language or None)
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
