"""The analytics pane on a chart: trend lines, forecasts, reference lines and bands, outliers.

Python fits everything; the browser only draws it. A forecast is dashed, labelled
"Estimate" and shown with a rough range; it is never mixed into the real data.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd

from tabsight import analytics
from tabsight.formats import format_date
from tabsight.i18n import text
from tabsight.warnings import InvalidSpecError

if TYPE_CHECKING:
    from tabsight.charts import _Context

TREND_KINDS = ("line", "multi_line", "area", "bar", "scatter", "bubble")
FORECAST_KINDS = ("line", "multi_line", "area")
REF_KINDS = ("bar", "hbar", "lollipop", "line", "multi_line", "area", "scatter", "bubble")
OUTLIER_KINDS = ("line", "multi_line", "area", "bar")
MAX_FORECAST_SERIES = 6
TREND = "Trend"
BAND_LOW, BAND_SPREAD = "​estimate-low", "​estimate-range"  # helper series, never shown


def asked(ctx: _Context) -> bool:
    o = ctx.spec.options
    return any(o.get(k) for k in ("trend", "forecast", "ref", "band", "outliers"))


def check_kind(ctx: _Context, kind: str) -> None:
    """Refuse analytics on chart kinds they don't fit, before anything is drawn."""
    o = ctx.spec.options
    for key, kinds in (("trend", TREND_KINDS), ("forecast", FORECAST_KINDS), ("ref", REF_KINDS),
                       ("band", REF_KINDS), ("outliers", OUTLIER_KINDS)):  # fmt: skip
        if o.get(key) and kind not in kinds:
            raise InvalidSpecError(
                f"{key}= works on {', '.join(kinds)} charts, not {kind.replace('_', ' ')}"
            )


def check(ctx: _Context, kind: str, x_time: bool, x_numeric: bool = False) -> None:
    """Refuse analytics that would mislead on this chart, with a reason."""
    o = ctx.spec.options
    check_kind(ctx, kind)
    along = x_time or x_numeric or kind in ("scatter", "bubble")
    if (o.get("trend") or o.get("outliers")) and not along:
        raise InvalidSpecError(
            "a trend line needs dates or numbers along the x-axis; between categories it would invent an order"
        )
    if o.get("forecast") and not x_time:
        raise InvalidSpecError("forecast= needs dates along the x-axis")
    if kind == "stacked_area" and (o.get("trend") or o.get("forecast")):
        raise InvalidSpecError("trend and forecast lines aren't drawn on stacked areas")


def _num(v: Any) -> float:
    if isinstance(v, dict):
        v = v.get("value")
    if isinstance(v, list):
        v = v[-1]
    return float(v) if isinstance(v, int | float) and not isinstance(v, bool) else float("nan")


def _real(series: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        s
        for s in series
        if s.get("type") in ("line", "bar") and not str(s.get("name", "")).startswith("Other (")
    ]


def _dashed(name: str, data: list[Any], color: str, width: float = 1.5) -> dict[str, Any]:
    return {"type": "line", "name": name, "data": data, "smooth": False, "showSymbol": False, "symbol": "none",
            "lineStyle": {"type": "dashed", "width": width, "color": color}, "itemStyle": {"color": color},
            "emphasis": {"disabled": True}, "z": 3}  # fmt: skip


def _legend_on(option: dict[str, Any], ctx: _Context) -> None:
    from tabsight.charts._build import _legend

    if "legend" not in option:
        option["legend"] = _legend(ctx)
        option.setdefault("grid", {})["top"] = max(40, option.get("grid", {}).get("top", 0))
    names = [s["name"] for s in option["series"] if not str(s["name"]).startswith("​")]
    option["legend"]["data"] = list(dict.fromkeys(names))


# ---------------------------------------------------------------- category axes (dates)


def apply_category(option: dict[str, Any], ctx: _Context, *, kind: str, x_values: list[Any], grain: str | None,
                   x_time: bool, partial: bool) -> None:  # fmt: skip
    """Trend, forecast, outliers and reference lines for bar and line charts with a category x-axis."""
    o = ctx.spec.options
    check(ctx, kind, x_time)
    series = _real(option["series"])
    if not series:
        return
    horizontal = kind == "hbar"
    n_real = len(series[0]["data"])  # periods with real data, before any estimate is added
    if o.get("forecast"):
        _forecast(option, ctx, series, x_values, grain or "month", partial)
    if o.get("trend"):
        for s in series[:MAX_FORECAST_SERIES]:
            ys = np.array([_num(v) for v in s["data"][:n_real]], dtype="float64")
            n = len(ys) - (1 if partial else 0)
            try:
                fit = analytics.linear_trend(ys[:n])
            except analytics.NotEnoughData:
                ctx.notes.append("not enough points for a trend line")
                break
            line: list[Any] = [round(float(v), 10) for v in fit.at(np.arange(len(ys)))]
            line += [None] * (len(option["xAxis"]["data"]) - len(line))
            name = TREND if len(series) == 1 else f"{s['name']} {TREND.lower()}"
            option["series"].append(
                _dashed(
                    name,
                    line,
                    s["itemStyle"]["color"] if "itemStyle" in s else ctx.colors.palette[0],
                )
            )
            ctx.facts.setdefault("trend_r2", []).append(fit.r2)
            ctx.decisions.append(
                f"the {name.lower()} is a straight line fitted by least squares (R² {fit.r2:.2f}: it explains "
                f"{fit.r2:.0%} of the ups and downs)"
            )
    if o.get("outliers"):
        _flag(option, ctx, series, partial, n_real)
    _refs(
        option, ctx, [v for s in series for v in (_num(x) for x in s["data"][:n_real])], horizontal
    )
    if len(option["series"]) > len(series) and (o.get("trend") or o.get("forecast")):
        _legend_on(option, ctx)


def _forecast(option: dict[str, Any], ctx: _Context, series: list[dict[str, Any]], x_values: list[Any],
              grain: str, partial: bool) -> None:  # fmt: skip
    horizon = int(ctx.spec.options["forecast"])
    season = ctx.spec.options.get("season", analytics.SEASONS.get(grain))
    labels: list[str] = option["xAxis"]["data"]
    n_fit = len(labels) - (1 if partial else 0)
    if n_fit < 1 or not isinstance(x_values[-1], pd.Timestamp):
        return
    extra = analytics.next_periods(
        pd.Timestamp(x_values[-1]), grain, horizon - (1 if partial else 0)
    )
    style = "compact" if grain in ("month", "day") and len(labels) > 8 else "full"
    future = [
        format_date(t, grain, style, locale=ctx.locale, fiscal_start=ctx.settings.fiscal_start)
        for t in extra
    ]
    total = len(labels) + len(future)
    drawn = []
    for s in series[:MAX_FORECAST_SERIES]:
        ys = [_num(v) for v in s["data"]][:n_fit]
        try:
            fc = analytics.forecast(ys, horizon, season)
        except analytics.NotEnoughData as err:
            ctx.notes.append(
                f"{text('not_enough_forecast', ctx.locale.split('_')[0])}: {str(err).split(': ', 1)[-1]}"
            )
            ctx.facts["forecast_skipped"] = True
            return
        drawn.append((s, fc))
    if not drawn:
        return
    labels.extend(future)
    for s in option["series"]:
        s["data"] = list(s["data"]) + [None] * (total - len(s["data"]))
    single = len(drawn) == 1
    bands: dict[str, dict[str, list[Any]]] = {}
    for s, fc in drawn:
        color = s["itemStyle"]["color"] if "itemStyle" in s else ctx.colors.palette[0]
        name = text("estimate") if single else f"{s['name']} ({text('estimate').lower()})"
        start = n_fit - 1  # the estimate joins the last real point, so the line doesn't break
        data: list[Any] = [None] * total
        data[start] = _num(s["data"][start])
        low: list[Any] = [None] * total
        high: list[Any] = [None] * total
        for h, (v, lo, hi) in enumerate(zip(fc.values, fc.lower, fc.upper, strict=True)):
            data[n_fit + h] = round(v, 10)
            low[n_fit + h], high[n_fit + h] = round(lo, 10), round(hi, 10)
        option["series"].append(_dashed(name, data, color, 2))
        bands[name] = {"low": low, "high": high}
        if single:
            option["series"].append({"type": "line", "name": BAND_LOW, "data": low, "stack": "ts-band", "symbol": "none",
                                     "lineStyle": {"opacity": 0}, "silent": True, "z": 1})  # fmt: skip
            spread = [
                None if a is None else round(b - a, 10) for a, b in zip(low, high, strict=True)
            ]
            option["series"].append({"type": "line", "name": BAND_SPREAD, "data": spread, "stack": "ts-band",
                                     "symbol": "none", "lineStyle": {"opacity": 0}, "silent": True, "z": 1,
                                     "areaStyle": {"color": color, "opacity": 0.14}})  # fmt: skip
        fc0 = fc
    fmt = option["tooltip"]["formatter"]["$tooltip"]
    fmt["skip"] = [BAND_LOW, BAND_SPREAD]
    fmt["bands"] = bands
    fmt.setdefault("series_fmt", {}).update({n: fmt["fmt"] for n in bands})
    weights = f"alpha {fc0.alpha:.2f}, beta {fc0.beta:.2f}" + (
        f", gamma {fc0.gamma:.2f}" if fc0.gamma is not None else ""
    )
    season_text = f"a season of {fc0.season} {grain}s" if fc0.season else "no season"
    ctx.decisions.append(
        f"the next {horizon} {grain}s are an estimate: {fc0.method} with {season_text}, fitted to "
        f"{fc0.history} {grain}s ({weights}); dashed so it never passes for real data"
    )
    ctx.decisions.append(
        "the shaded range is the typical one-step error times 1.96, widening as errors add up further "
        "ahead: a rough guide, not a guarantee"
        if single
        else "ranges are shown in tooltips; shading is for a single line only"
    )
    if partial:
        ctx.decisions.append(
            "the last period isn't over, so the estimate starts from the last complete one"
        )
    if any(fc.clipped for _, fc in drawn):
        ctx.decisions.append(
            "estimates below zero were raised to zero, because the history never goes below it"
        )
    ctx.facts["forecast"] = horizon
    ctx.facts["forecast_history"] = fc0.history


def _flag(
    option: dict[str, Any], ctx: _Context, series: list[dict[str, Any]], partial: bool, n_real: int
) -> None:
    """Mark points far from the series' own trend (Tukey's fences on the residuals). Flagged, never removed."""
    count = 0
    for s in series[:MAX_FORECAST_SERIES]:
        ys = np.array([_num(v) for v in s["data"][:n_real]], dtype="float64")
        n = len(ys) - (1 if partial else 0)
        try:
            fit = analytics.linear_trend(ys[:n])
        except analytics.NotEnoughData:
            continue
        resid = ys[:n] - fit.at(np.arange(n))
        mask = analytics.outliers(resid, "iqr", 1.5)
        points = [
            {"coord": [int(i), float(ys[i])], "value": float(ys[i])} for i in np.flatnonzero(mask)
        ]
        if points:
            count += len(points)
            s["markPoint"] = {"symbol": "circle", "symbolSize": 13, "silent": True, "data": points, "label": {"show": False},
                              "itemStyle": {"color": "transparent", "borderColor": "#d62728", "borderWidth": 2}}  # fmt: skip
    ctx.facts["outliers"] = count
    ctx.decisions.append(
        f"{count} unusual point{'s' if count != 1 else ''} circled: far from the line's own trend (beyond 1.5 box "
        "heights of the middle half of the gaps); flagged, never removed"
    )


def _refs(option: dict[str, Any], ctx: _Context, values: list[float], horizontal: bool) -> None:
    o = ctx.spec.options
    refs = o.get("ref") or ()
    band = o.get("band")
    if not refs and not band:
        return
    target = next(
        s for s in option["series"] if s.get("type") in ("line", "bar", "scatter", "pictorialBar")
    )
    axis = "xAxis" if horizontal else "yAxis"
    value_axis: dict[str, Any] = option[axis] if isinstance(option.get(axis), dict) else {}
    fmt = (value_axis.get("axisLabel", {}).get("formatter") or {}).get("$fmt") or {"unit": "number"}
    lines = []
    for ref in refs:
        v = analytics.reference_value(values, ref)
        if v is None:
            continue
        label = analytics.reference_label(ref)
        lines.append({axis: v, "name": label,
                      "label": {"formatter": {"$label": {**fmt, "style": "compact"}, "prefix": label + " "},
                                "position": "insideEndTop", "color": ctx.theme.text_secondary}})  # fmt: skip
        ctx.decisions.append(f"a reference line marks the {label.lower()} ({_how(ref)})")
    if lines:
        target["markLine"] = {"symbol": "none", "silent": True, "data": lines,
                              "lineStyle": {"type": "dashed", "color": ctx.theme.text_secondary, "width": 1}}  # fmt: skip
    if band:
        lo, hi = (analytics.reference_value(values, b) for b in band)
        if lo is not None and hi is not None:
            lo, hi = min(lo, hi), max(lo, hi)
            target["markArea"] = {"silent": True, "itemStyle": {"color": ctx.theme.accent, "opacity": 0.08},
                                  "data": [[{axis: lo}, {axis: hi}]]}  # fmt: skip
            ctx.decisions.append(
                f"a shaded band runs from the {analytics.reference_label(band[0]).lower()} to the "
                f"{analytics.reference_label(band[1]).lower()}"
            )
    ctx.facts["refs"] = len(lines) + (1 if band else 0)


def _how(ref: str | float) -> str:
    if not isinstance(ref, str):
        return "a constant you gave"
    return (
        "of the values shown"
        if ref in ("mean", "median")
        else "of the values shown: that share of them lie below it"
    )


# ---------------------------------------------------------------- value axes (scatter, numeric x)


def apply_points(
    option: dict[str, Any], ctx: _Context, *, kind: str, xs: np.ndarray, ys: np.ndarray
) -> None:
    """Trend and reference lines on charts with numbers on both axes."""
    check(ctx, kind, False, x_numeric=True)
    o = ctx.spec.options
    if o.get("trend"):
        try:
            fit = analytics.linear_trend(ys, xs)
        except analytics.NotEnoughData:
            ctx.notes.append("not enough points for a trend line")
        else:
            ok = np.isfinite(xs)
            lo, hi = float(xs[ok].min()), float(xs[ok].max())
            line = _dashed(
                TREND,
                [[lo, float(fit.at(lo))], [hi, float(fit.at(hi))]],
                ctx.theme.text_secondary,
                2,
            )
            option["series"].append(line)
            ctx.facts.setdefault("trend_r2", []).append(fit.r2)
            ctx.decisions.append(
                f"the trend line is fitted by least squares over all points (R² {fit.r2:.2f}: it explains "
                f"{fit.r2:.0%} of the spread); a trend is a pattern, not proof that one causes the other"
            )
    _refs(option, ctx, [float(v) for v in ys if np.isfinite(v)], horizontal=False)
