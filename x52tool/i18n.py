"""Internationalisierung: laedt eine .lng-Datei und stellt t() bereit.

Spracherkennung (in dieser Reihenfolge):
  1. Feld ``language`` in der gespeicherten Konfiguration
  2. Umgebungsvariable LANGUAGE (erster Eintrag, z.B. "de_DE.UTF-8" -> "de")
  3. Umgebungsvariable LANG (gleich behandelt)
  4. Fallback: "en"

Format der .lng-Datei:
  - INI-aehnlich, [section] / key = value
  - Leerzeilen und Zeilen, die mit # beginnen, werden ignoriert
  - Werte duerfen {placeholder}-Platzhalter enthalten (Python .format()-Stil)
  - Zeilenfortsetzungen sind NICHT unterstuetzt (kein Backslash-Umbruch)
"""

from __future__ import annotations

import os
import re
from pathlib import Path

_LANG_DIR = Path(__file__).parent / "lang"
_FALLBACK = "en"

# Geladene Strings: {"section.key": "wert"}
_strings: dict[str, str] = {}
_active_lang: str = _FALLBACK


def _detect_lang(override: str | None = None) -> str:
    """Ermittelt die zu ladende Sprache."""
    if override:
        return override.split("_")[0].split(".")[0].lower()
    for var in ("LANGUAGE", "LANG"):
        val = os.environ.get(var, "")
        if val:
            code = val.split(":")[0]          # LANGUAGE kann "de:en" sein
            code = code.split("_")[0].split(".")[0].lower()
            if code and code != "c" and code != "posix":
                return code
    return _FALLBACK


def _load(lang: str) -> dict[str, str]:
    """Laedt eine .lng-Datei und gibt die geparsten Strings zurueck."""
    path = _LANG_DIR / f"{lang}.lng"
    if not path.exists():
        if lang != _FALLBACK:
            return _load(_FALLBACK)
        return {}

    result: dict[str, str] = {}
    section = ""
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = re.fullmatch(r"\[([^\]]+)\]", line)
        if m:
            section = m.group(1)
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            # \n in Werten als echten Zeilenumbruch interpretieren
            result[f"{section}.{key.strip()}"] = value.strip().replace("\\n", "\n")
    return result


def init(language_override: str | None = None) -> None:
    """Initialisiert i18n. Muss einmal beim Start aufgerufen werden.

    language_override: z.B. "de" oder "en" – ueberschreibt Env und Fallback.
    Wird typischerweise aus Settings.language bef&uuml;llt.
    """
    global _strings, _active_lang
    lang = _detect_lang(language_override)
    strings = _load(lang)
    # Fallback-Strings ergaenzen (fehlende Keys aus "en")
    if lang != _FALLBACK:
        fallback = _load(_FALLBACK)
        _strings = {**fallback, **strings}
    else:
        _strings = strings
    _active_lang = lang


def t(key: str, **kwargs: object) -> str:
    """Uebersetzt einen Schluessel der Form "section.key".

    Unbekannte Schluessel werden als letzter Fallback unveraendert
    zurueckgegeben, damit kein sichtbarer Absturz entsteht.

    Beispiel:
        t("main.btn_rescan")
        t("calib.status_ro", path="/dev/input/event5")
    """
    template = _strings.get(key, key)
    if kwargs:
        try:
            return template.format(**kwargs)
        except (KeyError, ValueError):
            return template
    return template


def active_language() -> str:
    """Gibt den aktuell geladenen Sprachcode zurueck (z.B. "de" oder "en")."""
    return _active_lang
