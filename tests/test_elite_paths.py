"""Tests fuer die Suche nach E:D-Bindings- und Journal-Ordnern."""

from __future__ import annotations

import os

import pytest

from x52tool.elite import paths

BINDINGS = "AppData/Local/Frontier Developments/Elite Dangerous/Options/Bindings"
JOURNAL = "Saved Games/Frontier Developments/Elite Dangerous"


def _make_prefix(pfx, *, bindings=True, journal=True, mtime=None, user="steamuser"):
    user_dir = pfx / "drive_c" / "users" / user
    if bindings:
        (user_dir / BINDINGS).mkdir(parents=True)
    if journal:
        jdir = user_dir / JOURNAL
        jdir.mkdir(parents=True)
        status = jdir / "Status.json"
        status.write_text("{}", encoding="utf-8")
        if mtime is not None:
            os.utime(status, (mtime, mtime))
    return user_dir


@pytest.fixture
def home(tmp_path, monkeypatch):
    """Leeres Home mit Steam, dessen zweite Bibliothek ausserhalb liegt."""
    home = tmp_path / "home"
    library = tmp_path / "mnt" / "GamesNVMe" / "SteamLibrary"
    steamapps = home / ".steam" / "steam" / "steamapps"
    steamapps.mkdir(parents=True)
    (steamapps / "libraryfolders.vdf").write_text(
        '"libraryfolders"\n{\n'
        f'  "0" {{ "path" "{home / ".steam" / "steam"}" }}\n'
        f'  "1" {{ "path" "{library}" }}\n'
        "}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(home))
    return home, library


def _steam_pfx(library):
    return library / "steamapps" / "compatdata" / paths.STEAM_APP_ID / "pfx"


def test_finds_both_dirs_in_second_steam_library(home):
    _home, library = home
    user_dir = _make_prefix(_steam_pfx(library))
    installs = paths.find_installs()
    assert len(installs) == 1
    assert installs[0].bindings == user_dir / BINDINGS
    assert installs[0].journal == user_dir / JOURNAL
    assert paths.find_journal_dirs() == [user_dir / JOURNAL]
    assert paths.find_bindings_dirs() == [user_dir / BINDINGS]


def test_most_recently_played_install_comes_first(home):
    home_dir, library = home
    _make_prefix(_steam_pfx(library), mtime=1_000_000)
    heroic = _make_prefix(
        home_dir / "Games" / "Heroic" / "Prefixes" / "EliteDangerous",
        mtime=2_000_000,
    )
    assert paths.find_journal_dirs()[0] == heroic / JOURNAL
    assert paths.find_bindings_dirs()[0] == heroic / BINDINGS


def test_renamed_saved_games_folder_is_found(home):
    _home, library = home
    user_dir = _make_prefix(_steam_pfx(library), journal=False)
    other = user_dir / "Gespeicherte Spiele" / "Frontier Developments" / "Elite Dangerous"
    other.mkdir(parents=True)
    (other / "Journal.2026-11-20T190000.01.log").write_text("", encoding="utf-8")
    assert paths.find_journal_dirs() == [other]


def test_no_status_json_means_no_age(tmp_path):
    jdir = tmp_path / "journal"
    jdir.mkdir()
    (jdir / "Journal.2026-11-20T190000.01.log").write_text("", encoding="utf-8")
    assert paths.is_journal_dir(jdir)
    assert paths.status_age(jdir) is None


def test_status_age(tmp_path):
    jdir = tmp_path / "journal"
    jdir.mkdir()
    status = jdir / "Status.json"
    status.write_text("{}", encoding="utf-8")
    os.utime(status, (1000, 1000))
    assert paths.status_age(jdir, now=1030) == 30


def test_empty_dir_is_not_a_journal_dir(tmp_path):
    assert not paths.is_journal_dir(tmp_path)
    assert not paths.is_journal_dir(tmp_path / "fehlt")
