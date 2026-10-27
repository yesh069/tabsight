"""Translations: UI words and month/day names. English ships complete; others fall back to it.

Placeholders like ``{n}`` are filled by a small regex, never by ``str.format``, so a
translation string cannot read object attributes.
"""

from __future__ import annotations

import json
import re
from functools import cache
from importlib import resources
from typing import Any

from tabsight.warnings import InvalidSpecError

__all__ = ["LANGUAGES", "month_name", "text", "weekday_name"]

LANGUAGES = ("en", "de", "fr", "es", "it", "nl", "pt")
_PLACEHOLDER = re.compile(r"\{([a-z_]{1,30})\}")


@cache
def _load(lang: str) -> dict[str, Any]:
    if lang not in LANGUAGES:
        lang = "en"
    raw = resources.files(__name__).joinpath(f"{lang}.json").read_text(encoding="utf-8")
    data = json.loads(raw)
    for key in ("months", "months_short"):
        if not (isinstance(data.get(key), list) and len(data[key]) == 12):
            raise InvalidSpecError(f"translation {lang}: {key} must list 12 names")
    for key in ("weekdays", "weekdays_short"):
        if not (isinstance(data.get(key), list) and len(data[key]) == 7):
            raise InvalidSpecError(f"translation {lang}: {key} must list 7 names")
    ui = data.get("ui", {})
    if not isinstance(ui, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in ui.items()
    ):
        raise InvalidSpecError(f"translation {lang}: ui must map words to strings")
    return dict(data)


def text(key: str, lang: str = "en", **params: object) -> str:
    """A UI word in ``lang`` (falling back to English, then to the key itself)."""
    template = _load(lang)["ui"].get(key) or _load("en")["ui"].get(key) or key
    return _PLACEHOLDER.sub(lambda m: str(params.get(m.group(1), m.group(0))), template)


def month_name(month: int, lang: str = "en", short: bool = True) -> str:
    return str(_load(lang)["months_short" if short else "months"][month - 1])


def weekday_name(weekday: int, lang: str = "en", short: bool = True) -> str:
    """``weekday`` 0 = Monday."""
    return str(_load(lang)["weekdays_short" if short else "weekdays"][weekday])
