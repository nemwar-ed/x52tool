"""Tests fuer die dauerhafte x52d-Konfiguration (x52tool/x52d_conf.py)."""

from __future__ import annotations

import pytest

from x52tool import x52d_conf

SAMPLE = """\
[Clock]
# PrimaryFormat controls the clock format
FormatPrimary=12hr

[LED]
# The LED settings
Fire=on
A=green
"""


@pytest.fixture
def conf(tmp_path, monkeypatch):
    path = tmp_path / "x52d.conf"
    path.write_text(SAMPLE, encoding="utf-8")
    monkeypatch.setenv("X52TOOL_X52D_CONF", str(path))
    return path


def test_replace_existing_key_keeps_comments(conf):
    assert x52d_conf.set_value("Clock", "FormatPrimary", "24hr")
    text = conf.read_text(encoding="utf-8")
    assert "FormatPrimary=24hr" in text
    assert "12hr" not in text
    assert "# PrimaryFormat controls the clock format" in text


def test_key_lookup_is_case_insensitive(conf):
    assert x52d_conf.set_value("led", "a", "red")
    assert x52d_conf.get("LED", "A") == "red"
    assert conf.read_text(encoding="utf-8").count("A=") == 1


def test_new_key_is_added_to_its_section(conf):
    assert x52d_conf.set_value("LED", "t1", "amber")
    lines = conf.read_text(encoding="utf-8").splitlines()
    assert lines.index("T1=amber") == lines.index("A=green") + 1


def test_new_section_is_appended(conf):
    assert x52d_conf.set_value("Brightness", "mfd", "64")
    assert x52d_conf.get("brightness", "mfd") == "64"
    assert "[Brightness]\nMFD=64" in conf.read_text(encoding="utf-8")


def test_missing_file_is_not_ready(tmp_path, monkeypatch):
    monkeypatch.setenv("X52TOOL_X52D_CONF", str(tmp_path / "fehlt.conf"))
    assert not x52d_conf.is_ready()
    assert not x52d_conf.set_value("LED", "A", "red")
    assert x52d_conf.read_all() == {}
