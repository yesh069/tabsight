"""World maps: bundled shapes, place-name matching and map detection.

Everything here works offline from data bundled with tabsight (Natural Earth, public
domain): about 240 countries, level-1 regions for every country (states, provinces,
counties...) with useful groupings such as the UK's nations, and about 7,300 cities.

    ts.geo.detect(df["County"])        # which map these values belong on
    ts.geo.match(df["County"])         # every value matched, with what didn't match and why
    ts.geo.layers("United Kingdom")    # ['admin1', 'nation', 'region']
    ts.geo.coverage()                  # one row per country: regions, type, layers
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

import pandas as pd

from tabsight.geo import names as _names
from tabsight.geo.detection import GeoMatch, GeoTarget, resolve_country
from tabsight.geo.detection import detect as _detect
from tabsight.geo.detection import layers as _layers
from tabsight.geo.detection import match as _match
from tabsight.warnings import InvalidSpecError

__all__ = [
    "GeoMatch",
    "GeoTarget",
    "country_code",
    "coverage",
    "detect",
    "layers",
    "match",
    "version",
]


def detect(
    values: Iterable[Any],
    *,
    country_column: Iterable[Any] | None = None,
    level: str | None = None,
    country: str | None = None,
) -> GeoTarget | None:
    """Which map ``values`` belong on: the world, a country's regions, or cities.

    Returns ``None`` when fewer than half of the distinct values are places. Pass a
    ``country_column`` (same rows) to settle names that exist in several countries,
    or ``level`` / ``country`` to narrow the search."""
    name = values.name if isinstance(values, pd.Series) else None
    return _detect(values, context=country_column, name=str(name) if name is not None else None,
                   level=level, country=country)  # fmt: skip


def match(
    values: Iterable[Any],
    *,
    country_column: Iterable[Any] | None = None,
    level: str | None = None,
    country: str | None = None,
    layer: str | None = None,
    geo_map: Mapping[str, str] | None = None,
) -> GeoMatch:
    """Match every distinct value to a country, region or city. Unmatched values are
    listed with a "did you mean" suggestion; ``geo_map`` fixes your own spellings."""
    vals = list(values)
    target = detect(pd.Series(vals, name=getattr(values, "name", None)), country_column=country_column,
                    level=level, country=country)  # fmt: skip
    if target is None:
        raise InvalidSpecError(
            "these values don't look like countries, regions or cities; pass level= or country="
        )
    if layer is not None:
        if target.country is None or layer not in _layers(target.country):
            raise InvalidSpecError(
                f"no layer {layer!r} here; choose from {_layers(target.country or '')}"
            )
        target = GeoTarget("region", target.country, layer, target.share, "as asked")
    return _match(vals, target, context=country_column, overrides=geo_map)


def layers(country: str) -> list[str]:
    """The region layers bundled for a country (``"admin1"`` is Natural Earth's level 1)."""
    return _layers(resolve_country(country))


def country_code(name: str) -> str:
    """ISO 3166-1 alpha-3 code for a country name or code: ``"Ireland"`` -> ``"IRL"``."""
    return resolve_country(name)


def coverage() -> pd.DataFrame:
    """One row per country: name, code, number of level-1 regions, what they are, layers."""
    data = _names.geo_data()
    rows = []
    for code, info in sorted(data["countries"].items(), key=lambda kv: kv[1]["n"]):
        country_layers = data["layers"].get(code, {})
        admin1 = country_layers.get("admin1", {"features": {}, "type": ""})
        rows.append({
            "country": info["n"], "code": code, "regions": len(admin1["features"]),
            "region_type": admin1["type"], "layers": ", ".join(sorted(country_layers)),
        })  # fmt: skip
    return pd.DataFrame(rows)


def version() -> dict[str, Any]:
    """The bundled map data version (Natural Earth release and build settings)."""
    return dict(_names.version())
