"""Tests fuer Bindings, Schiffszustand und LED-Regeln (Elite Dangerous)."""

from __future__ import annotations

import json

from x52tool.elite import binds, rules
from x52tool.elite.status import FLAGS, GameState, JournalFollower

BINDS_XML = """<?xml version="1.0" encoding="UTF-8" ?>
<Root PresetName="Custom" MajorVersion="4" MinorVersion="2">
  <LandingGearToggle>
    <Primary Device="SaitekX52Pro" Key="Joy_9" />
    <Secondary Device="Keyboard" Key="Key_L" />
  </LandingGearToggle>
  <ShipSpotLightToggle>
    <Primary Device="SaitekX52Pro" Key="Joy_10" />
    <Secondary Device="{NoDevice}" Key="" />
  </ShipSpotLightToggle>
  <DeployHardpointToggle>
    <Primary Device="Keyboard" Key="Key_U" />
    <Secondary Device="SaitekX52Pro" Key="Joy_4" />
  </DeployHardpointToggle>
  <HyperSuperCombination>
    <Primary Device="SaitekX52Pro" Key="Joy_3">
      <Modifier Device="SaitekX52Pro" Key="Joy_6" />
    </Primary>
  </HyperSuperCombination>
  <ThrottleAxis>
    <Binding Device="SaitekX52Pro" Key="Joy_ZAxis" />
  </ThrottleAxis>
  <PrimaryFire>
    <Primary Device="SaitekX52Pro" Key="Joy_1" />
  </PrimaryFire>
</Root>
"""


def _flags(*names: str) -> int:
    value = 0
    for name in names:
        value |= 1 << FLAGS[name]
    return value


def _bindings(tmp_path):
    path = tmp_path / "Custom.4.2.binds"
    path.write_text(BINDS_XML, encoding="utf-8")
    return binds.parse(path)


# -- binds ---------------------------------------------------------------


def test_active_binds_file_from_start_preset(tmp_path):
    (tmp_path / "StartPreset.4.start").write_text(
        "Custom\nCustom\nCustom\nSaitekX52Pro", encoding="utf-8"
    )
    (tmp_path / "Custom.4.0.binds").write_text(BINDS_XML, encoding="utf-8")
    (tmp_path / "Custom.4.2.binds").write_text(BINDS_XML, encoding="utf-8")
    (tmp_path / "Custom.4.2.binds.1995691192.backup").write_text("x", encoding="utf-8")
    assert binds.preset_names(tmp_path) == ["Custom", "SaitekX52Pro"]
    assert binds.active_binds_file(tmp_path) == tmp_path / "Custom.4.2.binds"


def test_parse_collects_only_x52_keys(tmp_path):
    b = _bindings(tmp_path)
    assert b.actions["LandingGearToggle"] == ["Joy_9"]
    assert b.actions["DeployHardpointToggle"] == ["Joy_4"]
    assert b.actions["ThrottleAxis"] == ["Joy_ZAxis"]
    assert b.leds_for_action("ShipSpotLightToggle") == {"t1"}
    assert b.leds_for_action("PrimaryFire") == set()        # Trigger hat keine LED
    assert b.actions_for_led("t1") == ["LandingGearToggle", "ShipSpotLightToggle"]


# -- Zustand -------------------------------------------------------------


def test_conditions():
    s = GameState()
    s.apply_status({"Flags": _flags("LandingGearDown"), "GuiFocus": 6,
                    "LegalState": "Speeding"})
    assert s.check("LandingGearDown")
    assert s.check("!Supercruise")
    assert s.check("gui:GalaxyMap")
    assert s.check("legal:Speeding")
    assert not s.check("unbekannt")


def test_journal_docking_granted_until_docked():
    s = GameState()
    s.apply_event({"event": "DockingGranted", "timestamp": "2026-11-20T18:00:00Z"})
    assert s.check("event:DockingGranted")
    s.apply_event({"event": "Docked", "timestamp": "2026-11-20T18:01:00Z"})
    assert not s.check("event:DockingGranted")


def test_journal_under_attack_expires():
    s = GameState()
    s.apply_event({"event": "UnderAttack", "timestamp": "2026-11-20T18:00:00Z"})
    t0 = 1_795_197_600.0  # 2026-11-20T18:00:00Z
    assert s.check("event:UnderAttack", now=t0 + 5)
    assert not s.check("event:UnderAttack", now=t0 + 11)


def test_journal_follower_reads_new_lines(tmp_path):
    log = tmp_path / "Journal.2026-11-20T180000.01.log"
    log.write_text(json.dumps({"event": "Fileheader"}) + "\n", encoding="utf-8")
    f = JournalFollower(tmp_path)
    assert [e["event"] for e in f.poll()] == ["Fileheader"]
    with log.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"event": "DockingGranted"}) + "\n")
        fh.write('{"event": "Unvoll')  # halbe Zeile
    assert [e["event"] for e in f.poll()] == ["DockingGranted"]
    with log.open("a", encoding="utf-8") as fh:
        fh.write('staendig"}\n')
    assert [e["event"] for e in f.poll()] == ["Unvollstaendig"]


# -- Regeln --------------------------------------------------------------


def test_unbound_leds_are_not_managed(tmp_path):
    b = _bindings(tmp_path)
    levels = rules.evaluate(rules.DEFAULT_RULES, b, GameState())
    # T1/T2 (Fahrwerk, Lichter), B (Hardpoints), A (FSD), Schubhebel
    assert levels == {"t1": "inactive", "b": "inactive", "a": "inactive",
                      "throttle": "inactive"}


def test_highest_level_wins_on_shared_led(tmp_path):
    b = _bindings(tmp_path)
    s = GameState()
    s.apply_status({"Flags": _flags("LandingGearDown", "LightsOn")})
    levels = rules.evaluate(rules.DEFAULT_RULES, b, s)
    assert levels["t1"] == "active"
    assert levels["a"] == "blocked"      # FSD blockiert bei Fahrwerk
    s.apply_event({"event": "DockingGranted"})
    assert rules.evaluate(rules.DEFAULT_RULES, b, s)["t1"] == "alert"


def test_fsd_not_blocked_by_hardpoints_in_supercruise(tmp_path):
    b = _bindings(tmp_path)
    s = GameState()
    s.apply_status({"Flags": _flags("HardpointsDeployed", "Supercruise")})
    assert rules.evaluate(rules.DEFAULT_RULES, b, s)["a"] == "inactive"
    s.apply_status({"Flags": _flags("HardpointsDeployed")})
    assert rules.evaluate(rules.DEFAULT_RULES, b, s)["a"] == "blocked"


def test_modes_and_looks():
    s = GameState()
    assert rules.current_mode(s) == "default"
    s.apply_status({"Flags": _flags("HardpointsDeployed", "SilentRunning")})
    assert rules.current_mode(s) == "silent"
    schemes = rules.DEFAULT_SCHEMES
    assert rules.look_for("a", "inactive", "default", schemes) == "green"
    assert rules.look_for("fire", "active", "default", schemes) == "on"
    assert rules.look_for("a", "inactive", "hardpoints", schemes) == "red"


def test_render_flash():
    assert rules.render("amber-flash", "a", 0.1) == "amber"
    assert rules.render("amber-flash", "a", 0.6) == "off"
    assert rules.render("amber-red-flash", "a", 0.6) == "red"
    assert rules.render("flash", "fire", 0.6) == "off"
    assert rules.render("green", "a", 0.6) == "green"


def test_config_roundtrip():
    cfg = rules.load_config({})
    raw = rules.dump_config(cfg)
    raw["schemes"]["default"]["active"] = ["on", "red"]
    raw["rules"][0]["enabled"] = False
    again = rules.load_config(raw)
    assert again.schemes["default"]["active"] == ["on", "red"]
    assert again.rules[0].enabled is False
    assert len(again.rules) == len(rules.DEFAULT_RULES)
