"""Choose the map for a column of place names, then match every value to a shape or point.

``detect`` scores three kinds of map against the distinct values: the world map
(countries), every country's level-1 layers (states, counties, nations...) and cities.
The highest share of matched values wins; equal shares prefer countries, then regions,
then cities. Names that exist at two levels (Georgia: a country and a US state) are
settled by the other values in the column, then by a country column, then a warning.
"""

from __future__ import annotations

import dataclasses
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from typing import Any

import pandas as pd

from tabsight.geo import names as gn
from tabsight.warnings import InvalidSpecError, safe_repr

__all__ = ["GeoMatch", "GeoTarget", "detect", "display_name", "match"]

LEVELS = ("country", "region", "city")
# Sales-territory words that are also real region names somewhere. They still match once
# the map is chosen, but never choose it.
GENERIC = frozenset(
    [
        "north",
        "south",
        "east",
        "west",
        "central",
        "centre",
        "center",
        "northeast",
        "north",
        "east",
        "northwest",
        "north",
        "west",
        "southeast",
        "south",
        "east",
        "southwest",
        "south",
        "west",
        "midwest",
        "mid",
        "west",
        "middle",
        "capital",
        "metropolitan",
        "coast",
        "coastal",
        "island",
        "islands",
        "upper",
        "lower",
        "eastern",
        "western",
        "northern",
        "southern",
        "interior",
        "border",
        "other",
        "unknown",
        "none",
        "all",
        "total",
        "online",
        "store",
        "national",
        "international",
        "domestic",
    ]
) | frozenset({"north east", "north west", "south east", "south west", "mid west"})
MIN_SHARE = 0.5  # below this, a column is not treated as places
SUGGEST_SHARE = 0.8  # the recommender only suggests a map when this share are places
MAX_VALUES = 20_000  # distinct values looked at


@dataclasses.dataclass(frozen=True)
class GeoTarget:
    """Which map a column belongs on."""

    level: str  # "country", "region" or "city"
    country: str | None = None  # ISO 3166-1 alpha-3, for region maps (and cities in one country)
    layer: str | None = None  # "admin1", "iso", "nation", "region"...
    share: float = 1.0  # share of distinct values that matched
    reason: str = ""

    @property
    def label(self) -> str:
        if self.level == "country":
            return "world map (countries)"
        if self.level == "city":
            where = f" in {_country_name(self.country)}" if self.country else ""
            return f"cities{where}"
        layer_type = _layer_info(self.country or "", self.layer or "admin1")["type"]
        return f"{_country_name(self.country)} map ({_plural(layer_type)})"


@dataclasses.dataclass(frozen=True)
class GeoMatch:
    """Every distinct value and what it matched, plus what didn't match and why."""

    target: GeoTarget
    ids: Mapping[str, str]  # value -> country code, region id or city number
    unmatched: tuple[tuple[str, str | None], ...] = ()  # (value, "did you mean")
    notes: tuple[str, ...] = ()  # ambiguous names and how they were settled

    @property
    def share(self) -> float:
        total = len(self.ids) + len(self.unmatched)
        return len(self.ids) / total if total else 0.0

    def show(self) -> str:
        lines = [f"{self.target.label}: {len(self.ids):,} of {len(self.ids) + len(self.unmatched):,} "
                 f"values matched ({self.share:.0%})"]  # fmt: skip
        if self.target.reason:
            lines.append(f"  chosen because {self.target.reason}")
        if self.unmatched:
            lines.append("Not matched:")
            for value, hint in self.unmatched[:20]:
                lines.append(
                    f"  {safe_repr(value)}"
                    + (f" (did you mean {safe_repr(hint)}?)" if hint else "")
                )
            if len(self.unmatched) > 20:
                lines.append(f"  ... and {len(self.unmatched) - 20:,} more")
        if self.notes:
            lines.append("Notes:")
            lines += [f"  {n}" for n in self.notes]
        return "\n".join(lines)

    def __str__(self) -> str:
        return self.show()

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": dataclasses.asdict(self.target),
            "ids": dict(self.ids),
            "unmatched": [{"value": v, "suggestion": s} for v, s in self.unmatched],
            "notes": list(self.notes),
        }


# ---------------------------------------------------------------- detection


def detect(
    values: Iterable[Any],
    *,
    context: Iterable[Any] | None = None,
    name: str | None = None,
    level: str | None = None,
    country: str | None = None,
    min_share: float = MIN_SHARE,
) -> GeoTarget | None:
    """The map these values belong on, or None if fewer than ``min_share`` look like places.

    ``context`` is an optional country column for the same rows; ``name`` the column
    name (a tie-breaker: "State" prefers regions). ``level`` and ``country`` restrict
    the search (``country`` accepts any country name or code).
    """
    if level is not None and level not in LEVELS:
        raise InvalidSpecError(f"level must be one of {LEVELS}")
    wanted = resolve_country(country) if country is not None else None
    distinct = [v for v in _distinct(values) if len(gn.key(v)) >= 2]  # a letter is not a place
    if not distinct:
        return None
    n = len(distinct)
    hint = _name_hint(name)
    context_countries = _context_countries(context)

    scores: list[tuple[float, int, GeoTarget]] = []
    if level in (None, "country") and wanted is None:
        hits = sum(1 for v in distinct if gn.lookup(v, gn.country_index()))
        scores.append((hits / n, _rank("country", hint), GeoTarget("country", share=hits / n,
                       reason=f"{hits:,} of {n:,} values are countries")))  # fmt: skip
    if level in (None, "region"):
        best = _best_region(distinct, wanted, context_countries)
        if best is not None:
            (country_code, layer), hits, why = best
            scores.append((hits / n, _rank("region", hint), GeoTarget("region", country_code, layer, hits / n,
                           f"{hits:,} of {n:,} values are {_plural(_layer_info(country_code, layer)['type'])} "
                           f"of {_country_name(country_code)}{why}")))  # fmt: skip
    if level in (None, "city"):
        index = gn.city_index()
        rows = gn.cities_data()
        hit_rows = [gn.lookup(v, index) for v in distinct]
        if wanted is not None:
            hit_rows = [
                tuple(i for i in r if rows[i][2] == wanted) if r else None for r in hit_rows
            ]
        hits = sum(1 for r in hit_rows if r)
        city_country = wanted or _single_country(hit_rows, rows)
        scores.append((hits / n, _rank("city", hint), GeoTarget("city", city_country, None, hits / n,
                       f"{hits:,} of {n:,} values are cities")))  # fmt: skip
    if not scores:
        return None
    share, _, target = max(scores, key=lambda s: (round(s[0], 6), s[1]))
    if share < min_share and level is None:
        return None
    return target


def _best_region(
    distinct: list[str], wanted: str | None, context: Counter[str]
) -> tuple[tuple[str, str], int, str] | None:
    names_index = gn.region_index()
    codes_index = gn.region_code_index()
    tally: Counter[tuple[str, str]] = Counter()
    for v in distinct:
        if gn.key(v) in GENERIC:
            continue  # "North", "East"... can't prove a country on their own (Cameroon has both)
        found = gn.lookup(v, names_index) or frozenset()
        code = gn.key(v)
        if 2 <= len(code) <= 3 and not code.isdigit():  # "A" or "01" proves nothing on its own
            found = found | codes_index.get(code, frozenset())
        for pair in {(c, layer) for c, layer, _ in found}:
            if wanted is None or pair[0] == wanted:
                tally[pair] += 1
    if not tally:
        return None
    pop = {c: e.get("pop", 0) for c, e in gn.geo_data()["countries"].items()}

    def rank(item: tuple[tuple[str, str], int]) -> tuple[Any, ...]:
        (c, layer), hits = item
        size = len(_layer_info(c, layer)["features"])
        # more matches; then the country column agrees; then the map the values fill best;
        # then Natural Earth's own level; then the more populous country (deterministic)
        return (
            hits,
            context.get(c, 0),
            round(hits / size, 6),
            layer == "admin1",
            pop.get(c, 0),
            c,
            layer,
        )

    (best, hits), *rest = sorted(tally.items(), key=rank, reverse=True)
    why = ""
    rivals = [c for (c, _), h in rest if h == hits and c != best[0]]
    if rivals and context.get(best[0], 0):
        why = " (the country column decided it)"
    elif rivals:
        why = f" (also matches {_country_name(rivals[0])}; pass country= to choose)"
    return best, hits, why


def _single_country(hit_rows: list[Any], rows: list[list[Any]]) -> str | None:
    """The country all matched cities can share, if there is one."""
    common: set[str] | None = None
    for r in hit_rows:
        if not r:
            continue
        here = {rows[i][2] for i in r}
        common = here if common is None else common & here
        if not common:
            return None
    return sorted(common)[0] if common and len(common) == 1 else None


# ---------------------------------------------------------------- matching


def match(
    values: Iterable[Any],
    target: GeoTarget,
    *,
    context: Iterable[Any] | None = None,
    overrides: Mapping[str, str] | None = None,
) -> GeoMatch:
    """Match every distinct value against ``target``. ``context`` is an optional country
    column (same rows as ``values``) that settles cities such as Paris, France vs Paris,
    Texas. ``overrides`` maps your spelling to a name or code (``{"Co. Cork": "Cork"}``)."""
    overrides = _check_overrides(overrides)
    vals = list(values)
    distinct = _distinct(vals)
    pairs = _value_contexts(vals, context) if context is not None else {}
    ids: dict[str, str] = {}
    unmatched: list[tuple[str, str | None]] = []
    notes: list[str] = []
    pool = _choices(target)
    for v in distinct:
        look = overrides.get(v, v)
        found = _match_one(look, target, pairs.get(v, set()), notes, v)
        if found is None:
            unmatched.append((v, gn.suggest(look, pool)))
        else:
            ids[v] = found
    return GeoMatch(target, ids, tuple(unmatched), tuple(dict.fromkeys(notes)))


def _match_one(
    value: str, target: GeoTarget, context: set[str], notes: list[str], shown: str
) -> str | None:
    if target.level == "country":
        found = gn.lookup(value, gn.country_index())
        if not found:
            return None
        if len(found) > 1:
            pop = gn.geo_data()["countries"]
            pick = max(sorted(found), key=lambda c: pop[c].get("pop", 0))
            notes.append(f"{safe_repr(shown)} could be {', '.join(_country_name(c) for c in sorted(found))}; "
                         f"used {_country_name(pick)}")  # fmt: skip
            return str(pick)
        return str(next(iter(found)))
    if target.level == "region":
        found = gn.lookup(value, gn.region_index()) or frozenset()
        code = gn.key(value)
        if len(code) <= 3:
            found = found | gn.region_code_index().get(code, frozenset())
        ids = sorted(
            rid for c, layer, rid in found if c == target.country and layer == target.layer
        )
        if not ids:
            return None
        if len(ids) > 1:
            # a region's own name beats another region's alternate name (Washington state
            # vs Washington, D.C.)
            features = _layer_info(target.country or "", target.layer or "admin1")["features"]
            own = [
                i
                for i in ids
                if gn.key(value)
                in {gn.key(features[i]["n"]), gn.key(features[i].get("local") or "")}
            ]
            if len(own) == 1:
                return str(own[0])
            notes.append(
                f"{safe_repr(shown)} matches {len(ids)} areas; used {features[ids[0]]['n']}"
            )
        return str(ids[0])
    rows = gn.cities_data()
    found_rows = gn.lookup(value, gn.city_index())
    if not found_rows:
        return None
    candidates = list(found_rows)
    if target.country:
        candidates = [i for i in candidates if rows[i][2] == target.country]
    if context:
        narrowed = [
            i for i in candidates if rows[i][2] in context or gn.key(rows[i][3] or "") in context
        ]
        candidates = narrowed or candidates
    if not candidates:
        return None
    countries = {rows[i][2] for i in candidates}
    if len(countries) > 1:
        top = rows[candidates[0]]
        notes.append(f"{safe_repr(shown)} is a city in {len(countries)} countries; used the largest "
                     f"({top[0]}, {_country_name(top[2])}); add a country column to choose")  # fmt: skip
    return str(candidates[0])


# ---------------------------------------------------------------- helpers


def resolve_country(value: Any) -> str:
    """ISO 3166-1 alpha-3 code for a country name or code (``"Ireland"``, ``"IE"``, ``"IRL"``)."""
    found = gn.lookup(value, gn.country_index()) if isinstance(value, str) else None
    if not found:
        hint = gn.suggest(value, [e["n"] for e in gn.geo_data()["countries"].values()])
        raise InvalidSpecError(
            f"unknown country {safe_repr(value)}"
            + (f"; did you mean {safe_repr(hint)}?" if hint else "")
        )
    pop = gn.geo_data()["countries"]
    return str(max(sorted(found), key=lambda c: pop[c].get("pop", 0)))


def display_name(target: GeoTarget, fid: str, lang: str = "english") -> str:
    """The name shown on the map for a matched id, in English, local or another language."""
    if target.level == "country":
        entry = gn.geo_data()["countries"][fid]
    elif target.level == "region":
        entry = _layer_info(target.country or "", target.layer or "admin1")["features"][fid]
    else:
        return str(gn.cities_data()[int(fid)][0])
    if lang in ("english", "en"):
        return str(entry["n"])
    if lang == "local":
        return str(entry.get("local") or entry["n"])
    return str((entry.get("names") or {}).get(lang) or entry["n"])


def _layer_info(country: str, layer: str) -> dict[str, Any]:
    try:
        return gn.geo_data()["layers"][country][layer]  # type: ignore[no-any-return]
    except KeyError:
        raise InvalidSpecError(f"no {safe_repr(layer)} map for {safe_repr(country)}") from None


def layers(country: str) -> list[str]:
    return sorted(gn.geo_data()["layers"].get(country, {}))


def _country_name(code: str | None) -> str:
    if code is None:
        return "the world"
    entry = gn.geo_data()["countries"].get(code)
    return str(entry["n"]) if entry else code


def _plural(word: str) -> str:
    word = (word or "region").lower()
    if word.endswith("y") and not word.endswith(("ay", "ey")):
        return word[:-1] + "ies"
    return word if word.endswith("s") else word + "s"


def _choices(target: GeoTarget) -> list[str]:
    if target.level == "country":
        return [e["n"] for e in gn.geo_data()["countries"].values()]
    if target.level == "region":
        return [
            e["n"]
            for e in _layer_info(target.country or "", target.layer or "admin1")[
                "features"
            ].values()
        ]
    rows = gn.cities_data()
    return [r[0] for r in rows if target.country is None or r[2] == target.country][:3000]


def _distinct(values: Iterable[Any]) -> list[str]:
    seen: dict[str, None] = {}
    for v in values:
        if v is None or (isinstance(v, float) and v != v) or v is pd.NA:
            continue
        text = str(v).strip()
        if text and text not in seen:
            seen[text] = None
            if len(seen) >= MAX_VALUES:
                break
    return list(seen)


def _context_countries(context: Iterable[Any] | None) -> Counter[str]:
    counts: Counter[str] = Counter()
    if context is None:
        return counts
    index = gn.country_index()
    for v in _distinct(context):
        found = gn.lookup(v, index)
        if found and len(found) == 1:
            counts[next(iter(found))] += 1
    return counts


def _value_contexts(values: list[Any], context: Iterable[Any]) -> dict[str, set[str]]:
    """For each value, the countries (and region keys) its rows mention."""
    out: dict[str, set[str]] = defaultdict(set)
    index = gn.country_index()
    for v, c in zip(values, context, strict=False):
        if v is None or c is None or (isinstance(c, float) and c != c):
            continue
        found = gn.lookup(str(c), index)
        bucket = out[str(v).strip()]
        if found:
            bucket.update(found)
        bucket.add(gn.key(str(c)))
    return out


def _check_overrides(overrides: Mapping[str, str] | None) -> dict[str, str]:
    if overrides is None:
        return {}
    if not isinstance(overrides, Mapping) or len(overrides) > 10_000:
        raise InvalidSpecError(
            "geo_map must be a dict of up to 10,000 {your value: place name or code}"
        )
    out = {}
    for k, v in overrides.items():
        if not isinstance(k, str) or not isinstance(v, str) or len(k) > 200 or len(v) > 200:
            raise InvalidSpecError("geo_map keys and values must be text of up to 200 characters")
        out[k.strip()] = v
    return out


_HINTS = {
    "country": {"country", "countries", "nation", "nations", "iso3", "iso2"},
    "region": {"state", "states", "province", "provinces", "county", "counties", "region", "regions",
               "prefecture", "canton", "land", "lander", "department", "territory", "oblast"},
    "city": {"city", "cities", "town", "towns", "place", "municipality", "location"},
}  # fmt: skip


def _name_hint(name: str | None) -> str | None:
    if not name:
        return None
    words = set(gn.key(name).split())
    for level, hint_words in _HINTS.items():
        if words & hint_words:
            return level
    return None


def _rank(level: str, hint: str | None) -> int:
    base = {"country": 3, "region": 2, "city": 1}[level]
    return base + (10 if hint == level else 0)
