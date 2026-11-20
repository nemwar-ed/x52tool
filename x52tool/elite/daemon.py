"""Hintergrunddienst: X52-Pro-LEDs folgen dem Schiffszustand in Elite Dangerous.

Start (normalerweise als systemd-User-Dienst 'x52tool-ed', siehe ctl.py):

    python3 -m x52tool.elite.daemon

Ablauf:
  - alle 2 s: laeuft Elite (Prozess EliteDangerous64.exe)? Einstellungen,
    Ordner und .binds bei Aenderung neu laden
  - solange Elite laeuft: Status.json und Journal verfolgen, Regeln
    auswerten, LEDs setzen (nur Aenderungen, blinkende LEDs im Takt)
  - endet Elite (oder der Dienst): Grundfarben aus der gespeicherten
    x52d-Konfiguration wiederherstellen

LEDs werden mit persist=False gesetzt – die gespeicherten Grundeinstellungen
werden nie veraendert. Der aktuelle Stand wird fuer die Oberflaeche in eine
kleine JSON-Datei geschrieben (state_path()).
"""

from __future__ import annotations

import json
import logging
import os
import signal
import sys
import time
from pathlib import Path

from ..config import Settings, config_path
from ..output import PRO_LEDS, Backend
from .. import x52d_conf
from . import binds as binds_mod
from . import paths, rules as rules_mod
from .status import GameState, JournalFollower, read_status
from .ctl import state_path

log = logging.getLogger("x52tool.ed")

GAME_EXE = b"elitedangerous64.exe"
TICK = 0.1             # Hauptschleife
SLOW_EVERY = 2.0       # Prozess-, Einstellungs- und Binds-Pruefung
STATUS_EVERY = 0.2     # Status.json
JOURNAL_EVERY = 0.5    # Journal
RESYNC_EVERY = 15.0    # alle LEDs erneut senden (falls jemand dazwischenfunkt)


def elite_running() -> bool:
    """True, wenn ein Prozess mit EliteDangerous64.exe in der Kommandozeile laeuft."""
    try:
        entries = os.listdir("/proc")
    except OSError:
        return False
    for pid in entries:
        if not pid.isdigit():
            continue
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as fh:
                if GAME_EXE in fh.read().lower():
                    return True
        except OSError:
            continue
    return False


def _led_keys() -> list[str]:
    return [key for key, _label, _states in PRO_LEDS()]


class LedDriver:
    """Sendet LED-Werte an x52d – nur Aenderungen, nie dauerhaft."""

    def __init__(self, backend: Backend) -> None:
        self.backend = backend
        self.sent: dict[str, str] = {}

    def show(self, values: dict[str, str]) -> None:
        for led, value in values.items():
            if self.sent.get(led) == value:
                continue
            res = self.backend.set_led(led, value, persist=False)
            if res.ok:
                self.sent[led] = value
            else:
                log.warning("LED %s=%s fehlgeschlagen: %s", led, value, res.summary())

    def base_values(self) -> dict[str, str]:
        """Grundfarben aus der gespeicherten x52d-Konfiguration."""
        saved = x52d_conf.read_all()
        result: dict[str, str] = {}
        for key, _label, states in PRO_LEDS():
            value = saved.get(("led", key))
            if value in states:
                result[key] = value
        return result

    def restore(self, leds: list[str] | None = None) -> None:
        base = self.base_values()
        for led in leds if leds is not None else list(self.sent):
            value = base.get(led)
            if value is not None:
                self.backend.set_led(led, value, persist=False)
            self.sent.pop(led, None)

    def forget(self) -> None:
        self.sent.clear()


class EdLedService:
    def __init__(self) -> None:
        self.settings = Settings.load()
        self.backend = Backend(self.settings.backend)
        self.driver = LedDriver(self.backend)
        self.cfg = rules_mod.load_config(self.settings.ed_leds)
        self.state = GameState()
        self.bindings = binds_mod.Bindings()
        self.bindings_dir: Path | None = None
        self.journal_dir: Path | None = None
        self.follower: JournalFollower | None = None
        self._binds_mtime = 0.0
        self._status_mtime = 0.0
        self._config_mtime = self._mtime(config_path())
        self.running = False
        self.stop = False
        self.levels: dict[str, str] = {}
        self.mode = "default"
        self._dirty = True
        self._next_expiry: float | None = None
        self._last_state_json = ""

    # -- Hilfen ------------------------------------------------------------

    @staticmethod
    def _mtime(path: Path | None) -> float:
        if path is None:
            return 0.0
        try:
            return path.stat().st_mtime
        except OSError:
            return 0.0

    def _resolve_dirs(self) -> None:
        s = self.settings
        bdir = Path(s.ed_bindings_dir) if s.ed_bindings_dir else None
        jdir = Path(s.ed_journal_dir) if s.ed_journal_dir else None
        if bdir is None or not bdir.is_dir() or jdir is None or not paths.is_journal_dir(jdir):
            installs = paths.find_installs()
            if bdir is None or not bdir.is_dir():
                bdir = next((i.bindings for i in installs if i.bindings), None)
            if jdir is None or not paths.is_journal_dir(jdir):
                jdir = next((i.journal for i in installs if i.journal), None)
        if bdir != self.bindings_dir:
            log.info("Bindings-Ordner: %s", bdir)
            self.bindings_dir, self._binds_mtime = bdir, 0.0
        if jdir != self.journal_dir:
            log.info("Journal-Ordner: %s", jdir)
            self.journal_dir = jdir
            self.follower = JournalFollower(jdir) if jdir else None
            self._status_mtime = 0.0

    def _reload_binds(self) -> None:
        if self.bindings_dir is None:
            if self.bindings.path is not None:
                self.bindings = binds_mod.Bindings()
                self._dirty = True
            return
        path = binds_mod.active_binds_file(self.bindings_dir)
        mtime = self._mtime(path)
        if path != self.bindings.path or mtime != self._binds_mtime:
            self.bindings = binds_mod.parse(path) if path else binds_mod.Bindings()
            self._binds_mtime = mtime
            log.info("Belegung geladen: %s (%d Aktionen auf dem X52)",
                     path, len(self.bindings.actions))
            self._dirty = True

    def _reload_settings(self) -> None:
        mtime = self._mtime(config_path())
        if mtime == self._config_mtime:
            return
        self._config_mtime = mtime
        self.settings = Settings.load()
        self.backend.config = self.settings.backend
        self.cfg = rules_mod.load_config(self.settings.ed_leds)
        log.info("Einstellungen neu geladen")
        self._dirty = True

    # -- Zyklus ------------------------------------------------------------

    def _slow_tick(self) -> None:
        self._reload_settings()
        self._resolve_dirs()
        self._reload_binds()
        running = elite_running()
        if running != self.running:
            self.running = running
            if running:
                log.info("Elite Dangerous läuft – LED-Steuerung aktiv")
                self.state = GameState()
                if self.journal_dir:
                    self.follower = JournalFollower(self.journal_dir)
                self._status_mtime = 0.0
            else:
                log.info("Elite Dangerous beendet – Grundfarben wiederhergestellt")
                self.driver.restore()
                self.levels = {}
            self._dirty = True

    def _poll_status(self) -> None:
        if self.journal_dir is None:
            return
        path = self.journal_dir / paths.STATUS_FILE
        mtime = self._mtime(path)
        if mtime == self._status_mtime:
            return
        data = read_status(path)
        if data is None:
            return  # gerade im Schreiben – naechster Versuch
        self._status_mtime = mtime
        self.state.apply_status(data)
        self._dirty = True

    def _poll_journal(self) -> None:
        if self.follower is None:
            return
        events = self.follower.poll()
        for event in events:
            self.state.apply_event(event)
        if events:
            self._dirty = True

    def _update_leds(self, now: float) -> None:
        if self._dirty:
            old = set(self.levels)
            self.levels = rules_mod.evaluate(self.cfg.rules, self.bindings, self.state, now)
            self.mode = rules_mod.current_mode(self.state)
            self._next_expiry = self.state.next_journal_expiry(now)
            released = sorted(old - set(self.levels))
            if released:
                self.driver.restore(released)
            self._dirty = False
        values = {
            led: rules_mod.render(
                rules_mod.look_for(led, level, self.mode, self.cfg.schemes), led, now
            )
            for led, level in self.levels.items()
        }
        self.driver.show(values)

    def _write_state(self) -> None:
        payload = {
            "pid": os.getpid(),
            "running": self.running,
            "mode": self.mode if self.running else "",
            "binds_file": str(self.bindings.path or ""),
            "journal_dir": str(self.journal_dir or ""),
            "levels": self.levels if self.running else {},
        }
        text = json.dumps(payload, sort_keys=True)
        path = state_path()
        # Inhalt nur bei Aenderung schreiben, Zeitstempel aber regelmaessig,
        # damit die GUI erkennt, dass der Dienst lebt.
        if text == self._last_state_json and time.time() - self._mtime(path) < 5:
            return
        self._last_state_json = text
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps({**payload, "updated": time.time()}), encoding="utf-8")
            os.replace(tmp, path)
        except OSError as exc:
            log.debug("Statusdatei nicht schreibbar: %s", exc)

    def run(self) -> int:
        if not self.backend.available:
            log.error("x52ctl nicht gefunden – libx52 installieren")
        signal.signal(signal.SIGTERM, self._on_signal)
        signal.signal(signal.SIGINT, self._on_signal)
        log.info("x52tool-ed gestartet")
        next_slow = next_status = next_journal = 0.0
        next_resync = time.monotonic() + RESYNC_EVERY
        try:
            while not self.stop:
                mono = time.monotonic()
                if mono >= next_slow:
                    self._slow_tick()
                    self._write_state()
                    next_slow = mono + SLOW_EVERY
                if self.running:
                    if mono >= next_status:
                        self._poll_status()
                        next_status = mono + STATUS_EVERY
                    if mono >= next_journal:
                        self._poll_journal()
                        next_journal = mono + JOURNAL_EVERY
                    # Zeitlich begrenzte Journal-Zustaende (z.B. UnderAttack) laufen ab
                    if self._next_expiry is not None and time.time() >= self._next_expiry:
                        self._dirty = True
                    if mono >= next_resync:
                        self.driver.forget()
                        next_resync = mono + RESYNC_EVERY
                    was_dirty = self._dirty
                    self._update_leds(time.time())
                    if was_dirty:
                        self._write_state()
                time.sleep(TICK)
        finally:
            self.driver.restore()
            self.running = False
            self.levels = {}
            self._last_state_json = ""
            self._write_state()
            log.info("x52tool-ed beendet")
        return 0

    def _on_signal(self, *_args) -> None:
        self.stop = True


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(message)s",
        stream=sys.stderr,
    )
    return EdLedService().run()


if __name__ == "__main__":
    sys.exit(main())
