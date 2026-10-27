"""Choropleth and symbol maps (Phase 5).

The place column is matched to the bundled shapes first (``tabsight.geo``), then each
row is tagged with its region id and aggregated exactly like any other chart, so
"Cork" and "Co. Cork" add up to one county and unmatched rows are reported, never
silently dropped. Only the shapes this map needs go into the page.
"""

from __future__ import annotations

import gzip
import json
import math
from collections.abc import Sequence
from functools import cache
from importlib import resources
from typing import TYPE_CHECKING, Any

import pandas as pd

from tabsight.aggregate import Measure, aggregate
from tabsight.charts import _build
from tabsight.charts._common import DIV_DARK, DIV_LIGHT, NO_DATA, POSITIVE, SEQ_DARK, SEQ_LIGHT
from tabsight.charts._common import is_dark as _is_dark
from tabsight.charts._common import num as _num
from tabsight.charts._common import ramp_color as _ramp_color
from tabsight.figure import Figure
from tabsight.formats import locale_payload
from tabsight.geo import detection as gd
from tabsight.geo import names as gn
from tabsight.i18n import text
from tabsight.warnings import DataWarning, InvalidSpecError, safe_repr, warn

if TYPE_CHECKING:
    from tabsight.charts import _Context

__all__ = ["map_chart"]

GEO_COLUMN = "__tabsight_place"
MAX_POINTS = 3000
_SEQ_LIGHT, _SEQ_DARK, _DIV_LIGHT, _DIV_DARK, _NO_DATA = (
    SEQ_LIGHT,
    SEQ_DARK,
    DIV_LIGHT,
    DIV_DARK,
    NO_DATA,
)
_COUNTRY_WORDS = {"country", "countries", "nation", "iso3", "iso2"}


def map_chart(frame: pd.DataFrame, ctx: _Context, height: int | None) -> Figure:
    spec = ctx.spec
    opts = spec.options
    dark = _is_dark(ctx.theme.tile)
    lang = opts.get("geo_names", "english")

    if spec.kind == "flow_map":
        return _flow_map(frame, ctx, height, dark, lang)
    if spec.lat or spec.lon:
        if not (spec.lat and spec.lon):
            raise InvalidSpecError("pass both lat= and lon= for a map of coordinates")
        if spec.kind == "choropleth":
            raise InvalidSpecError(
                "a choropleth colours regions; use kind='symbol_map' for lat/lon points"
            )
        return _coordinate_map(frame, ctx, height, dark)

    geo = spec.geo or (spec.x if isinstance(spec.x, str) else None)
    if geo is None:
        raise InvalidSpecError(f"a {spec.kind} needs geo=<column of places> (or lat= and lon=)")
    for name in (geo, spec.lat, spec.lon):
        if name is not None and name not in ctx.prof:
            raise InvalidSpecError(f"column {safe_repr(name)} not found")
    values = frame[geo]
    context_col = _country_column(frame, ctx, geo)
    context = frame[context_col] if context_col else None
    target = _target(values, geo, context, opts)
    if spec.kind == "choropleth" and target.level == "city":
        raise InvalidSpecError(
            f"{geo} holds cities, which are points: use kind='symbol_map' (or map=/level= to choose regions)"
        )
    matched = gd.match(values, target, context=context, overrides=opts.get("geo_map"))
    ctx.decisions.append(f"{geo} is drawn on the {target.label}: {target.reason or 'as asked'}")
    if context_col:
        ctx.decisions.append(f"{context_col} is used to tell apart places with the same name")
    ctx.notes.extend(matched.notes)
    _report_unmatched(frame, geo, matched, ctx)

    ids = frame[geo].map(lambda v: matched.ids.get(str(v).strip()) if pd.notna(v) else None)
    work = frame.assign(**{GEO_COLUMN: ids})
    work = work[work[GEO_COLUMN].notna()]
    measures = ctx.measures() if spec.y is not None else [Measure(None, "count")]
    m = measures[0]
    if len(measures) > 1:
        raise InvalidSpecError("a map shows one measure; pass a single y= column")
    result = aggregate(work, GEO_COLUMN, measures, prof=None, missing="connect")
    ctx.notes.extend(n for n in result.notes if GEO_COLUMN not in n)
    values_by_id = {
        str(k): _num(v)
        for k, v in zip(result.values[GEO_COLUMN], result.values[m.label], strict=True)
    }

    if spec.kind == "choropleth":
        option, maps = _choropleth(target, values_by_id, m, ctx, dark, lang)
        # Dashboards re-colour the map after filtering: which shape each spelling belongs to.
        names = maps[0]["names"]
        ctx.facts["geo_shapes"] = {
            raw: names[fid] for raw, fid in matched.ids.items() if fid in names
        }
        ctx.facts["geo_field"] = geo
    else:
        points = [
            (_point(target, fid), _place_name(target, fid, lang), v)
            for fid, v in values_by_id.items()
        ]
        base = (
            target
            if target.level == "region"
            else gd.GeoTarget("region", target.country, "admin1")
            if target.country
            else None
        )
        option, maps = _symbols(points, base, m, ctx, dark, lang, insets=target.country == "USA")
        if spec.kind == "density_map":
            option = _to_density(option, m, ctx)
    ctx.describe_format(measures, "; in tooltips and the legend")
    ctx.facts.update(
        categories=len(values_by_id), series=1, rows=len(values_by_id),
        negative=any(v is not None and v < 0 for v in values_by_id.values()), x_time=False,
    )  # fmt: skip
    return _figure(ctx, measures, geo, option, maps, height)


# ---------------------------------------------------------------- choosing the map


def _target(values: pd.Series, geo: str, context: pd.Series | None, opts: Any) -> gd.GeoTarget:
    wanted = opts.get("map")
    level = opts.get("level")
    layer = opts.get("layer")
    if wanted is not None and gn.key(wanted) == "world":
        if level not in (None, "country", "city"):
            raise InvalidSpecError(
                "map='world' shows countries or cities; use map=<country> for its regions"
            )
        target = gd.detect(values, level=level or "country", name=geo)
        if target is None:
            raise _no_match(values, geo)
        return target
    country = gd.resolve_country(wanted) if wanted is not None else None
    if layer is not None:
        if country is None:
            raise InvalidSpecError(
                "layer= needs map=<country>, for example map='GBR', layer='nation'"
            )
        if layer not in gd.layers(country):
            raise InvalidSpecError(f"{gd._country_name(country)} has no {safe_repr(layer)} layer; "
                                   f"choose from {gd.layers(country)}")  # fmt: skip
        target = gd.detect(values, level="region", country=country, name=geo)
        reason = target.reason if target and target.layer == layer else "as asked"
        return gd.GeoTarget("region", country, layer, target.share if target else 0.0, reason)
    if country is not None and level is None:
        level = "region"
    target = gd.detect(values, context=context, name=geo, level=level, country=country)
    if target is None:
        raise _no_match(values, geo)
    return target


def _no_match(values: pd.Series, geo: str) -> InvalidSpecError:
    sample = ", ".join(safe_repr(v) for v in list(dict.fromkeys(values.dropna().astype(str)))[:3])
    return InvalidSpecError(
        f"{safe_repr(geo)} doesn't look like countries, regions or cities ({sample}...); "
        "pass map='world' or map=<country>, or geo_map={your value: place} for unusual spellings"
    )


def _country_column(frame: pd.DataFrame, ctx: _Context, geo: str) -> str | None:
    """A column whose name says it holds countries, to settle names like Paris or Punjab."""
    for col in frame.columns:
        if (
            col != geo
            and set(gn.key(col).split()) & _COUNTRY_WORDS
            and ctx.prof[col].role == "dimension"
        ):
            return str(col)
    return None


def _report_unmatched(frame: pd.DataFrame, geo: str, matched: gd.GeoMatch, ctx: _Context) -> None:
    if not matched.unmatched:
        return
    bad = {v for v, _ in matched.unmatched}
    rows = int(frame[geo].map(lambda v: pd.notna(v) and str(v).strip() in bad).sum())
    examples = "; ".join(
        safe_repr(v) + (f" (did you mean {safe_repr(h)}?)" if h else "")
        for v, h in matched.unmatched[:3]
    )
    note = (f"{len(bad):,} place(s) in {rows:,} row(s) didn't match the map and are left out: {examples}"
            + ("..." if len(bad) > 3 else "") + "; geo_map= can fix spellings")  # fmt: skip
    ctx.notes.append(note)
    warn(note, DataWarning)


# ---------------------------------------------------------------- choropleth


def _choropleth(
    target: gd.GeoTarget,
    values: dict[str, float | None],
    m: Measure,
    ctx: _Context,
    dark: bool,
    lang: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    reg, entry = _shapes(target, lang)
    names = entry["names"]
    numbers = [v for v in values.values() if v is not None]
    lo, hi = (min(numbers), max(numbers)) if numbers else (0.0, 1.0)
    diverging = lo < 0 < hi
    ramp = (_DIV_DARK if dark else _DIV_LIGHT) if diverging else (_SEQ_DARK if dark else _SEQ_LIGHT)
    if diverging:
        bound = max(abs(lo), abs(hi))
        lo, hi = -bound, bound
        ctx.decisions.append("colours diverge from zero because some values are negative")
    else:
        ctx.decisions.append("darker colour means a bigger value; regions without data are grey")
    if hi == lo:
        hi = lo + (abs(lo) or 1.0)
    option = _build._base(ctx)
    option["tooltip"]["trigger"] = "item"
    option["tooltip"]["formatter"] = {"$tooltip": {"trigger": "item", "fmt": ctx.js(m, "full"),
                                                   "no_data": text("no_data")}}  # fmt: skip
    option["geo"] = _geo_component(reg, target, ctx, dark)
    data = [{"name": names[fid], "value": v} for fid, v in values.items() if fid in names]
    option["series"] = [{"type": "map", "geoIndex": 0, "name": ctx.measure_title(m), "data": data}]
    option["visualMap"] = {
        "type": "continuous", "seriesIndex": 0, "min": lo, "max": hi, "calculable": False,
        "orient": "horizontal", "left": "center", "bottom": 0, "itemWidth": 12, "itemHeight": 200,
        "inRange": {"color": ramp}, "text": [ctx.fmt(hi, m, "compact"), ctx.fmt(lo, m, "compact")],
        "textStyle": {"color": ctx.theme.text_secondary},
    }  # fmt: skip
    if target.level == "country":
        dots = _tiny_dots(values, names, lo, hi, ramp)
        if dots:
            option["series"].append(dots)
            ctx.decisions.append(
                "tiny countries (like Singapore) are drawn as dots so they can be seen"
            )
        _auto_zoom(option["geo"], [gn.geo_data()["countries"][fid]["label"] for fid in values])
    return option, [entry]


def _tiny_dots(values: dict[str, float | None], names: dict[str, str], lo: float, hi: float,
               ramp: list[str]) -> dict[str, Any] | None:  # fmt: skip
    countries = gn.geo_data()["countries"]
    data = []
    for fid, v in values.items():
        info = countries.get(fid)
        if info and info["tiny"] and v is not None:
            data.append({"name": names[fid], "value": [*info["label"], v],
                         "itemStyle": {"color": _ramp_color(ramp, (v - lo) / (hi - lo))}})  # fmt: skip
    if not data:
        return None
    return {"type": "scatter", "coordinateSystem": "geo", "geoIndex": 0, "symbolSize": 7,
            "itemStyle": {"borderColor": "#ffffff", "borderWidth": 1}, "data": data, "z": 5}  # fmt: skip


# ---------------------------------------------------------------- symbol maps


def _symbols(
    points: Sequence[tuple[list[float] | None, str, float | None]], base: gd.GeoTarget | None, m: Measure, ctx: _Context,
    dark: bool, lang: str, *, insets: bool,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:  # fmt: skip
    base_target = base or gd.GeoTarget("country")
    reg, entry = _shapes(base_target, lang)
    kept = [(xy, name, v) for xy, name, v in points if xy is not None and v is not None]
    kept.sort(key=lambda p: -abs(p[2]))  # big circles first, so small ones are drawn on top
    if len(kept) > MAX_POINTS:
        ctx.notes.append(f"showing the {MAX_POINTS:,} largest of {len(kept):,} points")
        kept = kept[:MAX_POINTS]
    biggest = max((abs(p[2]) for p in kept), default=1.0) or 1.0
    pos, neg = ("#6ba6df", "#e07b4c") if dark else ("#2f6aa8", "#c4572a")
    data = []
    for coords, name, v in kept:
        lon, lat = _inset_point(coords) if insets else coords
        size = 5 + 25 * math.sqrt(abs(v) / biggest)
        data.append({"name": name, "value": [lon, lat, v], "symbolSize": round(size, 1),
                     "itemStyle": {"color": neg if v < 0 else pos}})  # fmt: skip
    option = _build._base(ctx)
    option["tooltip"]["trigger"] = "item"
    option["tooltip"]["formatter"] = {"$tooltip": {"trigger": "item", "fmt": ctx.js(m, "full"),
                                                   "no_data": text("no_data")}}  # fmt: skip
    option["geo"] = _geo_component(reg, base_target, ctx, dark, silent=True)
    option["series"] = [{"type": "scatter", "coordinateSystem": "geo", "geoIndex": 0, "data": data,
                         "itemStyle": {"opacity": 0.78, "borderColor": ctx.theme.tile, "borderWidth": 1},
                         "emphasis": {"scale": 1.15}}]  # fmt: skip
    ctx.decisions.append("circle area grows with the value (the largest is 30 pixels across)")
    if base is None:
        _auto_zoom(option["geo"], [p[0] for p in kept])
    return option, [entry]


def _coordinate_map(frame: pd.DataFrame, ctx: _Context, height: int | None, dark: bool) -> Figure:
    spec = ctx.spec
    lat, lon = str(spec.lat), str(spec.lon)
    for col in (lat, lon):
        if col not in ctx.prof:
            raise InvalidSpecError(f"column {safe_repr(col)} not found")
    label = spec.geo
    dims = [lat, lon] + ([label] if label else [])
    work = frame.assign(
        **{
            lat: pd.to_numeric(frame[lat], errors="coerce"),
            lon: pd.to_numeric(frame[lon], errors="coerce"),
        }
    )
    bad = (
        work[lat].isna()
        | work[lon].isna()
        | ~work[lat].between(-90, 90)
        | ~work[lon].between(-180, 180)
    )
    if bad.any():
        ctx.notes.append(f"{int(bad.sum()):,} row(s) without valid coordinates are left out")
    work = work[~bad]
    measures = ctx.measures() if spec.y is not None else [Measure(None, "count")]
    m = measures[0]
    result = aggregate(work, dims, measures[:1], prof=None, missing="connect").values
    points = [
        (
            [float(r[lon]), float(r[lat])],
            str(r[label]) if label else f"{r[lat]:.3f}, {r[lon]:.3f}",
            _num(r[m.label]),
        )
        for _, r in result.iterrows()
    ]
    ctx.decisions.append(f"points placed at {lat} and {lon}, on the world map zoomed to the data")
    option, maps = _symbols(
        points, None, m, ctx, dark, spec.options.get("geo_names", "english"), insets=False
    )
    if spec.kind == "density_map":
        option = _to_density(option, m, ctx)
    ctx.describe_format(measures, "; in tooltips")
    ctx.facts.update(categories=len(points), series=1, rows=len(points), x_time=False,
                     negative=any((p[2] or 0) < 0 for p in points))  # fmt: skip
    return _figure(ctx, measures, label or f"{lat}/{lon}", option, maps, height)


def _to_density(option: dict[str, Any], m: Measure, ctx: _Context) -> dict[str, Any]:
    """Replace the circles with a heat layer: where many or big values sit close together glows."""
    points = option["series"][0]["data"]
    peak = max((abs(p["value"][2] or 0) for p in points), default=1.0) or 1.0
    dark = _is_dark(ctx.theme.tile)
    option["series"] = [{"type": "heatmap", "coordinateSystem": "geo", "geoIndex": 0, "pointSize": 10,
                         "blurSize": 18, "data": [[*p["value"][:2], abs(p["value"][2] or 0)] for p in points]}]  # fmt: skip
    heat = (["#3b2f1e", "#9c6a1d", "#f28e2b", "#e5626f", "#ffb3c1"] if dark
            else ["#fff3d6", "#ffc46b", "#f28e2b", "#d1495b", "#7a1f5c"])  # fmt: skip
    option["visualMap"] = {"type": "continuous", "seriesIndex": 0, "min": 0, "max": peak, "show": False,
                           "inRange": {"color": heat}}  # fmt: skip
    option["tooltip"]["show"] = False  # a heat layer has no single item to describe
    ctx.decisions[:] = [d for d in ctx.decisions if not d.startswith("circle area")]
    ctx.decisions.append(
        "a heat layer: colour builds up where many or large values sit close together"
    )
    return option


def _flow_map(
    frame: pd.DataFrame, ctx: _Context, height: int | None, dark: bool, lang: str
) -> Figure:
    """Curved lines from a source place to a target place, wider for bigger values."""
    spec = ctx.spec
    source, target_col = spec.source, spec.target
    if not source or not target_col:
        raise InvalidSpecError(
            "a flow map needs source=<places> and target=<places> (and y=<measure>)"
        )
    for col in (source, target_col):
        if col not in ctx.prof:
            raise InvalidSpecError(f"column {safe_repr(col)} not found")
    both = pd.concat([frame[source], frame[target_col]], ignore_index=True)
    target = _target(both, source, None, spec.options)
    matched = gd.match(both, target, overrides=spec.options.get("geo_map"))
    ctx.decisions.append(f"places are on the {target.label}: {target.reason or 'as asked'}")
    ctx.notes.extend(matched.notes)
    _report_unmatched(pd.DataFrame({source: both}), source, matched, ctx)

    def place(v: Any) -> str | None:
        return matched.ids.get(str(v).strip()) if pd.notna(v) else None

    work = frame.assign(
        **{"__from": frame[source].map(place), "__to": frame[target_col].map(place)}
    )
    work = work[work["__from"].notna() & work["__to"].notna() & (work["__from"] != work["__to"])]
    measures = ctx.measures() if spec.y is not None else [Measure(None, "count")]
    m = measures[0]
    result = aggregate(work, ["__from", "__to"], measures[:1], prof=None, missing="connect").values
    flows = [
        (str(a), str(b), _num(v))
        for a, b, v in zip(result["__from"], result["__to"], result[m.label], strict=True)
    ]
    flows = sorted((f for f in flows if f[2] is not None and f[2] > 0), key=lambda f: -(f[2] or 0))
    if len(flows) > 100:
        ctx.notes.append(f"showing the 100 largest of {len(flows):,} flows")
        flows = flows[:100]
    base: gd.GeoTarget | None = None
    if target.level == "region":
        base = target
    elif target.level == "city" and target.country:
        base = gd.GeoTarget("region", target.country, "admin1")
    reg, entry = _shapes(base or gd.GeoTarget("country"), lang)
    insets = target.country == "USA" and base is not None
    biggest = max((f[2] or 0 for f in flows), default=1.0) or 1.0
    color = POSITIVE["dark" if dark else "light"]
    lines: list[dict[str, Any]] = []
    ends: dict[str, list[float]] = {}
    for a, b, v in flows:
        pa, pb = _point(target, a), _point(target, b)
        if pa is None or pb is None:
            continue
        if insets:
            pa, pb = _inset_point(pa), _inset_point(pb)
        na, nb = _place_name(target, a, lang), _place_name(target, b, lang)
        lines.append({"name": f"{na} \u2192 {nb}", "coords": [pa, pb], "value": v,
                      "lineStyle": {"width": round(1 + 7 * (v or 0) / biggest, 2)}})  # fmt: skip
        ends[na], ends[nb] = pa, pb
    option = _build._base(ctx)
    option["geo"] = _geo_component(reg, base or gd.GeoTarget("country"), ctx, dark, silent=True)
    option["series"] = [
        {"type": "lines", "coordinateSystem": "geo", "geoIndex": 0, "data": lines, "zlevel": 1,
         "lineStyle": {"color": color, "opacity": 0.55, "curveness": 0.25},
         "emphasis": {"lineStyle": {"opacity": 0.9}}},
        {"type": "scatter", "coordinateSystem": "geo", "geoIndex": 0, "symbolSize": 6, "zlevel": 2,
         "data": [{"name": n, "value": pt} for n, pt in ends.items()], "itemStyle": {"color": color},
         "label": {"show": len(ends) <= 15, "formatter": "{b}", "position": "right", "fontSize": 10,
                   "color": ctx.theme.text_secondary}, "tooltip": {"show": False}},
    ]  # fmt: skip
    option["tooltip"].update(
        {
            "trigger": "item",
            "formatter": {"$tooltip": {"trigger": "item", "fmt": ctx.js(m, "full")}},
        }
    )
    if base is None:
        _auto_zoom(option["geo"], list(ends.values()))
    ctx.decisions.append(f"lines run from {source} to {target_col}; wider means bigger")
    ctx.describe_format(measures, "; in tooltips")
    ctx.facts.update(categories=len(lines), series=1, rows=len(lines), x_time=False, negative=False)
    from tabsight.charts import _pretty

    title = (
        spec.title
        or f"{_pretty(ctx.measure_title(m))} from {_pretty(source)} to {_pretty(target_col)}"
    )
    return Figure(
        kind=spec.kind, spec=spec, title=title, subtitle=spec.subtitle, option=option,
        locales=locale_payload([ctx.locale]), theme=ctx.theme, height=height or 480,
        notes=tuple(dict.fromkeys(ctx.notes)), decisions=tuple(dict.fromkeys(ctx.decisions)),
        facts=ctx.facts, maps=(entry,),
    )  # fmt: skip


# ---------------------------------------------------------------- shapes and layout


def _shapes(target: gd.GeoTarget, lang: str) -> tuple[str, dict[str, Any]]:
    """Map name and the payload entry the browser registers with ECharts."""
    if target.level == "region" and target.country:
        topo = dict(_country_topo(target.country))
        layer = target.layer or "admin1"
        topo["objects"] = {layer: topo["objects"][layer]}
        ids = [g["id"] for g in topo["objects"][layer]["geometries"] if "id" in g]
        name = f"ts-{target.country}-{layer}"
        shape_target = gd.GeoTarget("region", target.country, layer)
        obj = layer
    else:
        topo = _world_topo()
        ids = [g["id"] for g in topo["objects"]["countries"]["geometries"]]
        name, obj, shape_target = "ts-world", "countries", gd.GeoTarget("country")
    names = _unique_names(shape_target, ids, lang)
    return name, {"name": name, "topo": topo, "object": obj, "names": names}


def _unique_names(target: gd.GeoTarget, ids: list[str], lang: str) -> dict[str, str]:
    """Display names, made unique (Natural Earth has two areas called Cork, city and county)."""
    out: dict[str, str] = {}
    seen: dict[str, int] = {}
    for fid in sorted(ids):
        name = gd.display_name(target, fid, lang)
        seen[name] = seen.get(name, 0) + 1
        out[fid] = name if seen[name] == 1 else f"{name} ({seen[name]})"
    return out


def _geo_component(
    reg: str, target: gd.GeoTarget, ctx: _Context, dark: bool, *, silent: bool = False
) -> dict[str, Any]:
    t = ctx.theme
    # layoutSize is set in the browser so the map fits the tile without stretching (see "fit")
    geo: dict[str, Any] = {
        "map": reg, "roam": "move",  # drag to pan; the wheel keeps scrolling the page "scaleLimit": {"min": 1, "max": 20}, "layoutCenter": ["50%", "46%"],
        "layoutSize": "90%", "silent": silent, "label": {"show": False}, "select": {"disabled": True},
        "itemStyle": {"areaColor": _NO_DATA["dark" if dark else "light"], "borderColor": t.tile, "borderWidth": 0.6},
        "emphasis": {"label": {"show": False}, "itemStyle": {"borderColor": t.text, "borderWidth": 1.2,
                                                            "areaColor": "inherit"}},
    }  # fmt: skip
    if target.level != "region":
        name = ctx.spec.options.get("projection", "equal_earth")
        geo["projection"] = {"$projection": name}
        (x0, _), (x1, _) = project(name, -180, 0), project(name, 180, 0)
        (_, y0), (_, y1) = project(name, 0, 84), project(name, 0, -56)
        geo["_aspect"] = round((x1 - x0) / (y1 - y0), 4)
        ctx.decisions.append(
            {"equal_earth": "Equal Earth projection, so every country keeps its true relative area",
             "mercator": "Mercator projection (as asked); it makes places near the poles look bigger",
             "natural": "Natural Earth projection (as asked)"}[ctx.spec.options.get("projection", "equal_earth")]
        )  # fmt: skip
    else:
        info = gn.geo_data()["layers"][target.country or ""][target.layer or "admin1"]["features"]
        lats = [e["label"][1] for e in info.values() if e.get("label")]
        mid = (min(lats) + max(lats)) / 2 if lats else 0.0
        geo["aspectScale"] = round(max(0.3, math.cos(math.radians(mid))), 3)
        boxes = [e["bbox"] for e in info.values()]
        width = max(b[2] for b in boxes) - min(b[0] for b in boxes)
        height = max(b[3] for b in boxes) - min(b[1] for b in boxes)
        geo["_aspect"] = round(width * geo["aspectScale"] / max(height, 1e-6), 4)
        if target.country == "USA":
            ctx.decisions.append(
                "Alaska and Hawaii are moved and scaled below the other states (insets)"
            )
    return geo


def _auto_zoom(geo: dict[str, Any], points: list[list[float]]) -> None:
    """Zoom the world map to where the data is, when it covers only part of the world."""
    pts = [p for p in points if p]
    if not pts:
        return
    lons, lats = [p[0] for p in pts], [p[1] for p in pts]
    span_lon, span_lat = max(lons) - min(lons), max(lats) - min(lats)
    zoom = min(320 / max(span_lon + 20, 1), 140 / max(span_lat + 14, 1))
    if zoom < 1.6:
        return
    # with a projection, ECharts reads center in projected coordinates
    cx, cy = project(
        geo["projection"]["$projection"], (min(lons) + max(lons)) / 2, (min(lats) + max(lats)) / 2
    )
    geo["center"] = [round(cx, 3), round(cy, 3)]
    geo["zoom"] = round(min(zoom, 12.0), 2)


def _figure(ctx: _Context, measures: list[Measure], place: str, option: dict[str, Any],
            maps: list[dict[str, Any]], height: int | None) -> Figure:  # fmt: skip
    from tabsight.charts import _pretty

    title = ctx.spec.title or text(
        "by", measure=_pretty(ctx.measure_title(measures[0])), dimension=_pretty(place)
    )
    return Figure(
        kind=ctx.spec.kind, spec=ctx.spec, title=title, subtitle=ctx.spec.subtitle, option=option,
        locales=locale_payload([ctx.locale]), theme=ctx.theme, height=height or 480,
        notes=tuple(dict.fromkeys(ctx.notes)), decisions=tuple(dict.fromkeys(ctx.decisions)),
        facts=ctx.facts, maps=tuple(maps),
    )  # fmt: skip


# ---------------------------------------------------------------- projections
# The same formulas as tabsight.js (checked against it by tests/test_maps.py).

_EE = (1.340264, -0.081106, 0.000893, 0.003796, math.sqrt(3) / 2)


def project(name: str, lon: float, lat: float) -> tuple[float, float]:
    """Projected [x, y] (y downwards, scaled by 100) as the browser computes it."""
    lam, phi = math.radians(lon), math.radians(lat)
    if name == "mercator":
        phi = math.radians(max(-85.0, min(85.0, lat)))
        return lam * 100, -math.log(math.tan(math.pi / 4 + phi / 2)) * 100
    if name == "natural":
        p2 = phi * phi
        p4 = p2 * p2
        x = lam * (0.8707 - 0.131979 * p2 + p4 * (-0.013791 + p4 * (0.003971 * p2 - 0.001529 * p4)))
        y = phi * (1.007226 + p2 * (0.015085 + p4 * (-0.044475 + 0.028874 * p2 - 0.005916 * p4)))
        return x * 100, -y * 100
    a1, a2, a3, a4, m = _EE
    theta = math.asin(m * math.sin(phi))
    t2 = theta * theta
    t6 = t2 * t2 * t2
    x = lam * math.cos(theta) / (m * (a1 + 3 * a2 * t2 + t6 * (7 * a3 + 9 * a4 * t2)))
    y = theta * (a1 + a2 * t2 + t6 * (a3 + a4 * t2))
    return x * 100, -y * 100


# ---------------------------------------------------------------- data helpers


def _point(target: gd.GeoTarget, fid: str) -> list[float] | None:
    if target.level == "city":
        row = gn.cities_data()[int(fid)]
        return [row[5], row[4]]
    if target.level == "country":
        return list(gn.geo_data()["countries"][fid]["label"])
    feature = gn.geo_data()["layers"][target.country or ""][target.layer or "admin1"]["features"][
        fid
    ]
    return list(feature["label"]) if feature.get("label") else None


def _place_name(target: gd.GeoTarget, fid: str, lang: str) -> str:
    if target.level == "city":
        row = gn.cities_data()[int(fid)]
        return f"{row[0]}, {gd._country_name(row[2])}"
    return gd.display_name(target, fid, lang)


def _inset_point(point: list[float]) -> list[float]:
    """Move a point in Alaska or Hawaii the same way the US map moves those states."""
    lon, lat = point
    insets = gn.geo_data()["insets"]["USA"]
    t = (
        insets["US-AK"]
        if lat > 50 and lon < -129
        else insets["US-HI"]
        if lat < 23 and lon < -154
        else None
    )
    if t is None:
        return point
    cx, cy, sx, sy, nx, ny = t
    return [round(nx + (lon - cx) * sx, 4), round(ny + (lat - cy) * sy, 4)]


@cache
def _world_topo() -> dict[str, Any]:
    return _read_topo("world.topo.json.gz")


@cache
def _country_topo(iso3: str) -> dict[str, Any]:
    if not (len(iso3) == 3 and iso3.isalpha() and iso3.isupper()):
        raise InvalidSpecError(f"bad country code {safe_repr(iso3)}")
    return _read_topo(f"admin1/{iso3}.topo.json.gz")


def _read_topo(name: str) -> dict[str, Any]:
    raw = resources.files("tabsight.geo.data").joinpath(name).read_bytes()
    return json.loads(gzip.decompress(raw).decode("utf-8"))  # type: ignore[no-any-return]
