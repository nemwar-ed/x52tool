"""LED-Regeln je Schiffszustand (Logik nach dem Vorbild von EDXLC).

Jede LED ist in einem von vier Zustaenden:

    inactive  Aktion kann ausgeloest werden, ist es aber nicht   (gruen)
    active    Aktion ist gerade aktiv                            (gelb)
    blocked   Aktion geht gerade nicht                           (rot)
    alert     Aktion sollte dringend ausgeloest werden           (gelb blinkend)

Regeln setzen Zustaende: "wenn alle Bedingungen erfuellt, dann bekommt die
LED der Taste, auf der Aktion X liegt, Zustand Y". Teilen sich mehrere
Tasten eine LED (T1/T2, POV 2) oder treffen mehrere Regeln, gewinnt der
hoechste Zustand (alert > blocked > active > inactive).

Welche Farbe ein Zustand hat, bestimmt das Farbschema des aktuellen Modus.
Der Modus wechselt bei Silent Running, Nachtsicht oder ausgefahrenen
Hardpoints (feste Rangfolge in dieser Reihenfolge), sonst "default".

LEDs, deren Tasten keine Aktion aus den Regeln tragen, bleiben unberuehrt
und zeigen weiter die in x52tool eingestellte Grundfarbe.

Regeln und Farbschemata werden als einfache Daten in config.json
gespeichert (Settings.ed_leds); fehlt etwas, gelten die Standardwerte unten.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field

from .binds import Bindings, LED_ORDER
from .status import GameState

LEVELS = ("inactive", "active", "blocked", "alert")
LEVEL_RANK = {name: i for i, name in enumerate(LEVELS)}

MODES = ("default", "hardpoints", "nightvision", "silent")

# Einfarbige LEDs (an/aus)
MONO_LEDS = frozenset({"fire", "throttle"})

# Moegliche Darstellungen
MONO_LOOKS = ("off", "on", "flash")
COLOR_LOOKS = (
    "off", "red", "amber", "green",
    "red-flash", "amber-flash", "green-flash",
    "red-amber-flash", "red-green-flash",
    "amber-red-flash", "amber-green-flash",
    "green-red-flash", "green-amber-flash",
)

FLASH_SECONDS = 0.5

# Aktionen, die die FSD ausloesen
FSD_ACTIONS = ["HyperSuperCombination", "Supercruise", "Hyperspace"]

# Standard-Farbschemata (wie EDXLC): je Modus und Zustand
# [Darstellung einfarbiger LED, Darstellung dreifarbiger LED]
DEFAULT_SCHEMES: dict[str, dict[str, list[str]]] = {
    "default": {
        "inactive": ["off", "green"],
        "active": ["on", "amber"],
        "blocked": ["off", "red"],
        "alert": ["flash", "amber-flash"],
    },
    "hardpoints": {
        "inactive": ["off", "red"],
        "active": ["on", "amber"],
        "blocked": ["off", "off"],
        "alert": ["flash", "amber-flash"],
    },
    "nightvision": {
        "inactive": ["off", "off"],
        "active": ["on", "green"],
        "blocked": ["off", "off"],
        "alert": ["flash", "green-flash"],
    },
    "silent": {
        "inactive": ["off", "off"],
        "active": ["on", "green"],
        "blocked": ["off", "red"],
        "alert": ["flash", "green-flash"],
    },
}


@dataclass
class Rule:
    """Wenn alle `when`-Bedingungen gelten, bekommt das Ziel den Zustand `level`.

    Ziel ist entweder eine Liste von Aktionen (die LED folgt der Belegung),
    eine Liste fester LEDs, oder `all_leds` (alle LEDs).
    """

    id: str
    when: list[str]
    level: str
    actions: list[str] = field(default_factory=list)
    leds: list[str] = field(default_factory=list)
    all_leds: bool = False
    enabled: bool = True

    def to_dict(self) -> dict:
        d: dict = {"id": self.id, "when": list(self.when), "level": self.level}
        if self.actions:
            d["actions"] = list(self.actions)
        if self.leds:
            d["leds"] = list(self.leds)
        if self.all_leds:
            d["all_leds"] = True
        if not self.enabled:
            d["enabled"] = False
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Rule":
        return cls(
            id=str(d.get("id", "")),
            when=[str(c) for c in d.get("when", [])],
            level=str(d.get("level", "active")),
            actions=[str(a) for a in d.get("actions", [])],
            leds=[str(x) for x in d.get("leds", [])],
            all_leds=bool(d.get("all_leds", False)),
            enabled=bool(d.get("enabled", True)),
        )


def _r(id_: str, when: list[str], level: str, actions=None, leds=None,
       all_leds=False, enabled=True) -> Rule:
    return Rule(id_, when, level, list(actions or []), list(leds or []),
                all_leds, enabled)


# Standardregeln nach EDXLC, ergaenzt um ein paar abschaltbare Extras.
DEFAULT_RULES: list[Rule] = [
    _r("cargo_scoop",      ["CargoScoopDeployed"], "active", ["ToggleCargoScoop"]),
    _r("lights",           ["LightsOn"], "active", ["ShipSpotLightToggle"]),
    _r("hardpoints",       ["HardpointsDeployed"], "active", ["DeployHardpointToggle"]),
    _r("night_vision",     ["NightVision"], "active", ["NightVisionToggle"]),
    _r("silent_running",   ["SilentRunning"], "active", ["ToggleButtonUpInput"]),
    _r("silent_heat",      ["SilentRunning", "OverHeating"], "alert", ["ToggleButtonUpInput"]),
    _r("landing_gear",     ["LandingGearDown"], "active", ["LandingGearToggle"]),
    _r("docking_granted",  ["event:DockingGranted"], "alert", ["LandingGearToggle"]),
    _r("heat_sink",        ["OverHeating"], "alert", ["DeployHeatSink"]),
    _r("boost_gear",       ["LandingGearDown"], "blocked", ["UseBoostJuice"]),
    _r("fsd_charging",     ["FsdCharging"], "active", FSD_ACTIONS),
    _r("fsd_heat",         ["FsdCharging", "OverHeating"], "alert", FSD_ACTIONS),
    _r("fsd_masslock",     ["FsdMassLocked"], "blocked", FSD_ACTIONS),
    _r("fsd_cooldown",     ["FsdCooldown"], "blocked", FSD_ACTIONS),
    _r("fsd_scoop",        ["CargoScoopDeployed"], "blocked", FSD_ACTIONS),
    _r("fsd_gear",         ["LandingGearDown"], "blocked", FSD_ACTIONS),
    _r("fsd_hardpoints",   ["HardpointsDeployed", "!Supercruise"], "blocked", FSD_ACTIONS),
    _r("speeding",         ["legal:Speeding"], "alert", ["ThrottleAxis"]),
    # Extras (nicht in EDXLC), zunaechst abgeschaltet
    _r("under_attack",     ["event:UnderAttack"], "alert", leds=["fire"], enabled=False),
    _r("interdiction",     ["BeingInterdicted"], "alert", all_leds=True, enabled=False),
]


@dataclass
class LedConfig:
    rules: list[Rule]
    schemes: dict[str, dict[str, list[str]]]


def load_config(raw: dict | None) -> LedConfig:
    """Regeln/Farbschemata aus Settings.ed_leds; fehlende Teile = Standard."""
    raw = raw or {}
    if raw.get("rules"):
        rules = [Rule.from_dict(d) for d in raw["rules"] if isinstance(d, dict)]
    else:
        rules = copy.deepcopy(DEFAULT_RULES)
    schemes = copy.deepcopy(DEFAULT_SCHEMES)
    for mode, levels in (raw.get("schemes") or {}).items():
        if mode in schemes and isinstance(levels, dict):
            for level, look in levels.items():
                if level in LEVEL_RANK and isinstance(look, list) and len(look) == 2:
                    schemes[mode][level] = [str(look[0]), str(look[1])]
    return LedConfig(rules=rules, schemes=schemes)


def dump_config(cfg: LedConfig) -> dict:
    return {
        "rules": [r.to_dict() for r in cfg.rules],
        "schemes": copy.deepcopy(cfg.schemes),
    }


def current_mode(state: GameState) -> str:
    if state.check("SilentRunning"):
        return "silent"
    if state.check("NightVision"):
        return "nightvision"
    if state.check("HardpointsDeployed"):
        return "hardpoints"
    return "default"


def managed_leds(rules: list[Rule], bindings: Bindings) -> set[str]:
    """LEDs, die von Regeln gesteuert werden (Grundzustand 'inactive')."""
    leds: set[str] = set()
    for rule in rules:
        if not rule.enabled:
            continue
        for action in rule.actions:
            leds |= bindings.leds_for_action(action)
        leds |= {x for x in rule.leds if x in LED_ORDER}
    return leds


def evaluate(
    rules: list[Rule], bindings: Bindings, state: GameState, now: float | None = None
) -> dict[str, str]:
    """Zustand je LED. LEDs ohne Eintrag bleiben bei ihrer Grundfarbe."""
    levels: dict[str, str] = {led: "inactive" for led in managed_leds(rules, bindings)}
    for rule in rules:
        if not rule.enabled or rule.level not in LEVEL_RANK:
            continue
        if not state.check_all(rule.when, now):
            continue
        if rule.all_leds:
            targets = set(LED_ORDER)
        else:
            targets = {x for x in rule.leds if x in LED_ORDER}
            for action in rule.actions:
                targets |= bindings.leds_for_action(action)
        for led in targets:
            old = levels.get(led)
            if old is None or LEVEL_RANK[rule.level] > LEVEL_RANK[old]:
                levels[led] = rule.level
    return levels


def look_for(led: str, level: str, mode: str, schemes: dict) -> str:
    """Darstellung (z.B. 'amber-flash' oder 'on') fuer LED, Zustand, Modus."""
    pair = schemes.get(mode, {}).get(level) or DEFAULT_SCHEMES["default"][level]
    return pair[0] if led in MONO_LEDS else pair[1]


def render(look: str, led: str, now: float) -> str:
    """Darstellung -> konkreter LED-Wert zum Zeitpunkt `now` (fuer Blinken).

    Ergebnis ist ein Wert fuer x52ctl: off/on bzw. off/red/amber/green.
    """
    phase = int(now / FLASH_SECONDS) % 2
    if led in MONO_LEDS:
        if look == "flash":
            return "on" if phase == 0 else "off"
        return "on" if look == "on" else "off"
    if look.endswith("-flash"):
        colors = look[: -len("-flash")].split("-")
        if len(colors) == 1:
            colors.append("off")
        return colors[phase]
    return look if look in ("off", "red", "amber", "green") else "off"
