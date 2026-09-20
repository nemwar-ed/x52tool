"""Einstiegspunkt.

    python3 -m x52tool                     Oberflaeche
    python3 -m x52tool --list              gefundene Geraete auflisten
    python3 -m x52tool --apply             gespeichertes Profil anwenden
    python3 -m x52tool --apply --device /dev/input/event7

Der Apply-Modus braucht kein Qt und ist genau das, was eine udev-Regel
oder ein systemd-User-Service aufruft.
"""

from __future__ import annotations

import argparse
import sys

from .config import Settings
from .device import X52Device, scan


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="x52tool", description=__doc__)
    parser.add_argument("--list", action="store_true", help="Geraete auflisten")
    parser.add_argument("--apply", action="store_true", help="Gespeichertes Profil anwenden")
    parser.add_argument("--device", help="Event-Device, sonst alle passenden")
    args = parser.parse_args(argv)

    if args.list:
        return _list_devices()
    if args.apply:
        return _apply_profile(args.device)

    from .ui import run  # Qt erst importieren, wenn es gebraucht wird

    return run()


if __name__ == "__main__":
    raise SystemExit(main())
