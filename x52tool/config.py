"""Einstellungen und Kalibrierprofile unter ~/.config/x52tool/config.json."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .device import AbsInfo


def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or "~/.config"
    return Path(base).expanduser() / "x52tool"


def config_path() -> Path:
    return config_dir() / "config.json"


@dataclass
class BackendConfig:
    """Wie x52ctl aufgerufen wird.

    x52ctl spricht mit dem x52d-Daemon ueber den Socket /run/x52d.cmd.
    Das Protokoll: x52ctl config set <Section> <Key> <Value>

    Die Vorlagen sind bewusst Text und in der Oberflaeche editierbar,
    falls sich die Syntax in einer kuenftigen libx52-Version aendert.
    """

    binary: str = ""
    # LED: Section "LED", Key = LED-Name, Value = Zustand
    led: str = "{bin} config set LED {led} {state}"
    # MFD-Text: Section "MFD", Key = "Line{line}", Value = Text
    mfd: str = "{bin} config set MFD Line{line} {text}"
    # Helligkeit: Section "Brightness", Key = MFD oder LED
    brightness: str = "{bin} config set Brightness {target} {value}"
    # Clutch: Section "Profiles", Key = ClutchEnabled
    clutch: str = "{bin} config set Profiles ClutchEnabled {value}"


@dataclass
class MfdConfig:
    """MFD-Uhr- und Datumseinstellungen sowie Clutch-Modi."""
    local_time:    bool = True
    clock1_12h:    bool = False
    date_fmt:      str  = "DD-MM-YY"
    tz2:           str  = "UTC"   # Zeitzonen-Name (Olson), wie x52d ihn erwartet
    clock2_12h:    bool = False
    tz3:           str  = "UTC"
    clock3_12h:    bool = False
    clutch_active: bool = False
    clutch_latched: bool = False


def offset_to_tz(minutes: int) -> str:
    """Alten GMT-Versatz (Minuten) in einen Zeitzonen-Namen umrechnen.

    Etc/GMT-Zonen haben ein umgekehrtes Vorzeichen: GMT+2 = 'Etc/GMT-2'.
    Halbe Stunden gibt es dort nicht -> Fallback UTC.
    """
    if minutes == 0 or minutes % 60:
        return "UTC"
    hours = minutes // 60
    return f"Etc/GMT{'-' if hours > 0 else '+'}{abs(hours)}"


def _is_legacy_backend(raw: dict) -> bool:
    """True wenn die gespeicherte Backend-Konfiguration noch von x52cli stammt."""
    if not raw:
        return False
    if Path(raw.get("binary", "") or "x52ctl").name != "x52ctl":
        return True
    templates = [raw.get(k, "") for k in ("led", "mfd", "brightness", "clutch")]
    return any(t and "config set" not in t for t in templates)


@dataclass
class Settings:
    backend: BackendConfig = field(default_factory=BackendConfig)
    mfd: MfdConfig = field(default_factory=MfdConfig)
    # Kalibrierprofile je USB-ID: {"06a3:0762": {"0": {"flat": 512, ...}}}
    profiles: dict[str, dict[str, dict[str, int]]] = field(default_factory=dict)
    last_device_path: str = ""
    rest_test_seconds: int = 10
    zero_fuzz_during_test: bool = True
    language: str = ""  # "" = aus LANG/LANGUAGE-Env, "de" oder "en" fuer manuell
    ed_bindings_dir: str = ""  # "" = automatisch suchen

    # -- Profile -----------------------------------------------------------

    def profile(self, usb_id: str) -> dict[int, AbsInfo]:
        raw = self.profiles.get(usb_id, {})
        return {int(code): AbsInfo(**values) for code, values in raw.items()}

    def set_profile(self, usb_id: str, calibration: dict[int, AbsInfo]) -> None:
        self.profiles[usb_id] = {
            str(code): asdict(info) for code, info in calibration.items()
        }

    # -- Laden / Speichern -------------------------------------------------

    @classmethod
    def load(cls) -> "Settings":
        path = config_path()
        if not path.exists():
            return cls()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        backend_raw = raw.pop("backend", {})
        mfd_raw = raw.pop("mfd", {})
        legacy = _is_legacy_backend(backend_raw)
        if legacy:
            # Alte x52cli-Vorlagen verwerfen -> x52ctl-Standardwerte
            backend = BackendConfig()
        else:
            backend = BackendConfig(**{
                k: v for k, v in backend_raw.items()
                if k in BackendConfig.__dataclass_fields__
            })
        # Migration: GMT-Versatz (Minuten) -> Zeitzonen-Name
        for n in ("2", "3"):
            if f"tz{n}" not in mfd_raw and f"offset{n}" in mfd_raw:
                mfd_raw[f"tz{n}"] = offset_to_tz(int(mfd_raw[f"offset{n}"] or 0))
        if legacy:
            # Unter x52cli stand der Default auf GMT – Lokalzeit ist gewollt
            mfd_raw["local_time"] = True
        mfd = MfdConfig(**{k: v for k, v in mfd_raw.items() if k in MfdConfig.__dataclass_fields__})
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        filtered = {k: v for k, v in raw.items() if k in known and k not in ("backend", "mfd")}
        return cls(backend=backend, mfd=mfd, **filtered)

    def save(self) -> Path:
        path = config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(self)
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return path
