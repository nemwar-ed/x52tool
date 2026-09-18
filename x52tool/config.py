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
    """Wie das externe libx52-CLI aufgerufen wird.

    Die Vorlagen sind bewusst Text und in der Oberflaeche editierbar: die
    genaue Syntax haengt davon ab, ob x52cli oder der Daemon-Client x52ctl
    installiert ist und in welcher Version. Einmal gegen `--help` pruefen,
    anpassen, fertig.
    """

    binary: str = ""
    led: str = "{bin} led {led} {state}"
    mfd: str = "{bin} mfd {line} {text}"
    brightness: str = "{bin} bri {target} {value}"


@dataclass
class Settings:
    backend: BackendConfig = field(default_factory=BackendConfig)
    # Kalibrierprofile je USB-ID: {"06a3:0762": {"0": {"flat": 512, ...}}}
    profiles: dict[str, dict[str, dict[str, int]]] = field(default_factory=dict)
    last_device_path: str = ""
    rest_test_seconds: int = 10
    zero_fuzz_during_test: bool = True

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
        backend = BackendConfig(**raw.pop("backend", {}))
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        filtered = {k: v for k, v in raw.items() if k in known and k != "backend"}
        return cls(backend=backend, **filtered)

    def save(self) -> Path:
        path = config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(self)
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return path
