"""Place names: normalising, the bundled name index and "did you mean".

Every country, region and city is matched on its English, local and official names, the
names Natural Earth has in about 25 languages, alternate names and ISO codes. Matching
ignores case, accents and punctuation, and a second pass drops words such as "County",
"State of" or "Province" (``Co. Cork`` = ``Cork``).
"""

from __future__ import annotations

import difflib
import gzip
import json
import re
import unicodedata
from collections import defaultdict
from functools import cache, lru_cache
from importlib import resources
from typing import Any

__all__ = ["affix_key", "city_index", "country_index", "geo_data", "key", "region_index", "suggest"]

_DATA = "tabsight.geo.data"
_NON_WORD = re.compile(r"[^\w]+", re.UNICODE)
_SPACES = re.compile(r"\s+")
_SAINT = re.compile(r"\bst\.\s*")
_SAINTE = re.compile(r"\bste\.\s*")
# Words that only say what kind of place it is. Dropped in the second matching pass.
_AFFIXES = frozenset(
    [
        "county",
        "co",
        "state",
        "of",
        "the",
        "province",
        "provincia",
        "prov",
        "region",
        "regione",
        "departement",
        "department",
        "dept",
        "prefecture",
        "oblast",
        "governorate",
        "canton",
        "kanton",
        "voivodeship",
        "district",
        "territory",
        "municipality",
        "autonomous",
        "community",
        "comunidad",
        "land",
        "bundesland",
        "republic",
        "emirate",
        "parish",
        "shire",
        "city",
    ]
)


def key(text: Any) -> str:
    """Normal form used for matching: case-folded, no accents or punctuation."""
    return _key(text if isinstance(text, str) else str(text))


@lru_cache(maxsize=200_000)
def _key(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    plain = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    plain = plain.casefold().replace("&", " and ").replace("ß", "ss")
    plain = _SAINTE.sub("sainte ", _SAINT.sub("saint ", plain))  # St. Louis = Saint Louis
    return _SPACES.sub(" ", _NON_WORD.sub(" ", plain).replace("_", " ")).strip()


def affix_key(text: Any) -> str:
    """``key`` without words like "County" or "Province"; empty if nothing else is left."""
    return " ".join(w for w in key(text).split() if w not in _AFFIXES)


@cache
def geo_data() -> dict[str, Any]:
    """The bundled name index (countries, level-1 layers, insets)."""
    data: dict[str, Any] = _read_json("names.json.gz")
    return data


@cache
def cities_data() -> list[list[Any]]:
    return _read_json("cities.json.gz")  # type: ignore[no-any-return]


@cache
def version() -> dict[str, Any]:
    return json.loads(resources.files(_DATA).joinpath("version.json").read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def _read_json(name: str) -> Any:
    raw = resources.files(_DATA).joinpath(name).read_bytes()
    return json.loads(gzip.decompress(raw).decode("utf-8"))


def _entry_keys(entry: dict[str, Any]) -> tuple[set[str], set[str]]:
    """(name keys, code keys) of one country or region entry."""
    names = {entry["n"], *(entry.get("names") or {}).values(), *(entry.get("alt") or [])}
    if entry.get("local"):
        names.add(entry["local"])
    name_keys = {key(n) for n in names if n}
    name_keys |= {
        k for k in (affix_key(n) for n in names if n) if len(k) >= 3
    }  # "Region X" is not "x"
    code_keys = {key(c) for c in entry.get("codes") or [] if c}
    if entry.get("iso"):
        code_keys.add(key(entry["iso"]))
        code_keys.add(key(entry["iso"].split("-", 1)[1]))
    name_keys.discard("")
    code_keys.discard("")
    return name_keys, code_keys


@cache
def country_index() -> dict[str, frozenset[str]]:
    """key -> ISO 3166-1 alpha-3 codes it can mean."""
    index: dict[str, set[str]] = defaultdict(set)
    for cid, entry in geo_data()["countries"].items():
        name_keys, code_keys = _entry_keys(entry)
        for k in name_keys | code_keys:
            index[k].add(cid)
    return {k: frozenset(v) for k, v in index.items()}


def region_index() -> dict[str, frozenset[tuple[str, str, str]]]:
    """key -> (country, layer, region id) it can mean, across every country and layer.

    Names and long codes (``US-CA``). Short codes (``CA``, ``BW``) collide between
    countries, so they live in ``region_code_index``.
    """
    return _region_indexes()[0]


def region_code_index() -> dict[str, frozenset[tuple[str, str, str]]]:
    """Short region codes (``CA``, ``NSW``), weighed together with the other values."""
    return _region_indexes()[1]


@cache
def _region_indexes() -> tuple[
    dict[str, frozenset[tuple[str, str, str]]], dict[str, frozenset[tuple[str, str, str]]]
]:
    names: dict[str, set[tuple[str, str, str]]] = defaultdict(set)
    codes: dict[str, set[tuple[str, str, str]]] = defaultdict(set)
    for country, layers in geo_data()["layers"].items():
        for layer, info in layers.items():
            for rid, entry in info["features"].items():
                name_keys, code_keys = _entry_keys(entry)
                where = (country, layer, rid)
                for k in name_keys:
                    names[k].add(where)
                for k in code_keys:
                    # "ca" is short and ambiguous; "ar z" (from AR-Z) is a full ISO code
                    (codes if len(k) <= 3 else names)[k].add(where)
    return (
        {k: frozenset(v) for k, v in names.items()},
        {k: frozenset(v) for k, v in codes.items()},
    )


@cache
def city_index() -> dict[str, tuple[int, ...]]:
    """key -> row numbers in the city table, most populous first."""
    index: dict[str, list[int]] = defaultdict(list)
    for i, row in enumerate(cities_data()):
        for name in {row[0], *row[1]}:
            for k in {key(name), affix_key(name)}:
                if k and i not in index[k]:
                    index[k].append(i)
    return {k: tuple(v) for k, v in index.items()}


def lookup(text: Any, index: dict[str, Any]) -> Any:
    """Exact key first, then without words like "County"."""
    k = key(text)
    if k in index:
        return index[k]
    k2 = affix_key(text)
    return index.get(k2) if len(k2) >= 3 else None


def suggest(text: Any, choices: list[str]) -> str | None:
    """The closest display name for a value that did not match, or None."""
    by_key = {key(c): c for c in choices}
    hit = difflib.get_close_matches(key(text), list(by_key), n=1, cutoff=0.75)
    return by_key[hit[0]] if hit else None
