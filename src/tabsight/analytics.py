"""The analytics pane: trend lines, forecasts, outliers and reference lines.

Everything here is plain numpy, deterministic (no randomness, no clock) and bounded:
series are capped at ``MAX_POINTS`` before any fitting. The same numbers always give the
same result on every machine.
"""

from __future__ import annotations

import dataclasses
import math
import re
from collections.abc import Sequence
from typing import Any

import numpy as np
import pandas as pd

from tabsight.warnings import InvalidSpecError, safe_repr

__all__ = [
    "SEASONS",
    "Forecast",
    "Trend",
    "forecast",
    "linear_trend",
    "outliers",
    "reference_value",
]

MAX_POINTS = 5000  # longer series are fitted on their last MAX_POINTS values
SEASONS = {"month": 12, "quarter": 4, "week": 52, "day": 7, "hour": 24}  # "year" has none
MIN_POINTS_NO_SEASON = 6
Z95 = 1.96
_GRID = (0.05, 0.2, 0.35, 0.5, 0.65, 0.8, 0.95)
_PERCENTILE = re.compile(r"p(\d{1,2})")


class NotEnoughData(InvalidSpecError):
    """Too little history for the requested analysis."""


# ---------------------------------------------------------------- trend


@dataclasses.dataclass(frozen=True)
class Trend:
    """A least-squares straight line ``y = intercept + slope * x``."""

    slope: float
    intercept: float
    r2: float  # share of the variation the line explains (0-1)
    n: int

    def at(self, x: Any) -> Any:
        return self.intercept + self.slope * np.asarray(x, dtype="float64")


def linear_trend(
    y: Sequence[float] | np.ndarray, x: Sequence[float] | np.ndarray | None = None
) -> Trend:
    """Fit a straight line by least squares. ``x`` defaults to 0, 1, 2, ... Missing values are skipped."""
    ys = np.asarray(y, dtype="float64")
    xs = np.arange(len(ys), dtype="float64") if x is None else np.asarray(x, dtype="float64")
    if xs.shape != ys.shape:
        raise InvalidSpecError("x and y must have the same length")
    ok = np.isfinite(xs) & np.isfinite(ys)
    xs, ys = xs[ok][-MAX_POINTS:], ys[ok][-MAX_POINTS:]
    if len(ys) < 3 or np.ptp(xs) == 0:
        raise NotEnoughData("a trend line needs at least 3 points at different positions")
    # centre x first so huge x values (timestamps) don't lose precision
    x0 = xs.mean()
    dx = xs - x0
    slope = float((dx * (ys - ys.mean())).sum() / (dx * dx).sum())
    intercept = float(ys.mean() - slope * x0)
    fitted = intercept + slope * xs
    total = float(((ys - ys.mean()) ** 2).sum())
    r2 = 1.0 - float(((ys - fitted) ** 2).sum()) / total if total > 0 else 1.0
    return Trend(slope, intercept, max(0.0, min(1.0, r2)), len(ys))


# ---------------------------------------------------------------- forecast


@dataclasses.dataclass(frozen=True)
class Forecast:
    """Future values from Holt-Winters (additive), with a rough 95% range."""

    values: tuple[float, ...]
    lower: tuple[float, ...]
    upper: tuple[float, ...]
    season: int | None
    method: str
    alpha: float
    beta: float
    gamma: float | None
    history: int  # how many points it was fitted to
    clipped: bool = False  # values below zero were raised to zero (the history never went below)


def _run(
    y: list[float], season: int | None, a: float, b: float, g: float
) -> tuple[float, list[float], float, float, list[float]]:
    """One pass of Holt(-Winters). Returns SSE of one-step forecasts, the residuals and final state."""
    if season:
        # Start from the first two seasons: the trend is the step between their averages,
        # and each season's offset is measured from that sloped line, not from a flat
        # average (which would fold the trend into the season and lag every forecast).
        first = sum(y[:season]) / season
        trend = (sum(y[season : 2 * season]) / season - first) / season
        middle = (season - 1) / 2
        seasonal = [
            (y[i] + y[i + season]) / 2 - (first + trend * (i - middle) + trend * season / 2)
            for i in range(season)
        ]
        level = first + trend * (season - 1 - middle)  # the line's value at the end of season one
        start = season
    else:
        level, trend, seasonal, start = y[0], y[1] - y[0], [], 1
    residuals: list[float] = []
    for t in range(start, len(y)):
        s = seasonal[t % season] if season else 0.0
        guess = level + trend + s
        residuals.append(y[t] - guess)
        last_level = level
        level = a * (y[t] - s) + (1 - a) * (level + trend)
        trend = b * (level - last_level) + (1 - b) * trend
        if season:
            seasonal[t % season] = g * (y[t] - level) + (1 - g) * s
    sse = sum(r * r for r in residuals)
    return sse, residuals, level, trend, seasonal


def forecast(y: Sequence[float] | np.ndarray, horizon: int, season: int | None = None) -> Forecast:
    """Forecast ``horizon`` steps ahead.

    With a ``season`` (12 for months, 4 for quarters...) this is additive Holt-Winters and
    needs at least two full seasons of history; without one it is Holt's linear trend and
    needs at least 6 points. The smoothing weights are chosen on a fixed grid by the
    smallest one-step error, so the result is repeatable. The range is the typical
    one-step error times 1.96, widening as those errors add up over the horizon (the
    standard formula for additive Holt-Winters): a rough guide, not a guarantee.
    """
    if type(horizon) is not int or not 1 <= horizon <= 120:
        raise InvalidSpecError(
            f"forecast={safe_repr(horizon)} must be a whole number of periods 1-120"
        )
    if season is not None and (type(season) is not int or not 2 <= season <= 366):
        raise InvalidSpecError(f"season={safe_repr(season)} must be a whole number 2-366")
    ys = [float(v) for v in np.asarray(y, dtype="float64")[-MAX_POINTS:]]
    if any(not math.isfinite(v) for v in ys):
        raise NotEnoughData("a forecast needs a value for every period (no gaps)")
    need = 2 * season if season else MIN_POINTS_NO_SEASON
    if len(ys) < need:
        what = f"two full seasons ({need} periods)" if season else f"{need} periods"
        raise NotEnoughData(
            f"not enough data for a forecast: it needs {what}, and there are {len(ys)}"
        )
    best: tuple[float, float, float, float] | None = None
    for a in _GRID:
        for b in _GRID:
            for g in _GRID if season else (0.0,):
                sse = _run(ys, season, a, b, g)[0]
                if best is None or sse < best[0] - 1e-9 * max(1.0, best[0]):
                    best = (sse, a, b, g)
    if best is None:  # the grid is never empty; this keeps type checkers honest
        raise NotEnoughData("no forecast could be fitted")
    _, a, b, g = best
    _, residuals, level, trend, seasonal = _run(ys, season, a, b, g)
    sigma = float(np.std(residuals)) if residuals else 0.0
    n = len(ys)
    values, lower, upper = [], [], []
    growth = 0.0  # how one-step errors add up h steps ahead (Hyndman et al. 2008, additive model)
    for h in range(1, horizon + 1):
        v = level + h * trend + (seasonal[(n + h - 1) % season] if season else 0.0)
        if h > 1:
            j = h - 1
            c = a * (1 + j * b) + (g if season and j % season == 0 else 0.0)
            growth += c * c
        spread = Z95 * sigma * math.sqrt(1 + growth)
        values.append(v)
        lower.append(v - spread)
        upper.append(v + spread)
    clipped = False
    if min(ys) >= 0 and min(lower) < 0:
        clipped = min(values) < 0
        values = [max(0.0, v) for v in values]
        lower = [max(0.0, v) for v in lower]
    method = "Holt-Winters (additive)" if season else "Holt's linear trend"
    return Forecast(
        tuple(values),
        tuple(lower),
        tuple(upper),
        season,
        method,
        a,
        b,
        g if season else None,
        n,
        clipped,
    )


def next_periods(last: pd.Timestamp, grain: str, horizon: int) -> list[pd.Timestamp]:
    """The starts of the ``horizon`` periods after ``last`` (itself a period start)."""
    step = {"year": pd.DateOffset(years=1), "quarter": pd.DateOffset(months=3),
            "month": pd.DateOffset(months=1), "week": pd.DateOffset(weeks=1),
            "day": pd.DateOffset(days=1), "hour": pd.DateOffset(hours=1)}[grain]  # fmt: skip
    out, current = [], pd.Timestamp(last)
    for _ in range(horizon):
        current = current + step
        out.append(current)
    return out


# ---------------------------------------------------------------- outliers


def outliers(
    values: Sequence[float] | np.ndarray | pd.Series, method: str = "iqr", k: float | None = None
) -> np.ndarray:
    """A True/False mask of unusual values. Never removes anything.

    ``"iqr"``: beyond ``k`` (1.5) box heights from the middle half (Tukey's fences).
    ``"zscore"``: more than ``k`` (3) standard deviations from the mean.
    """
    v = np.asarray(values, dtype="float64")
    ok = np.isfinite(v)
    mask = np.zeros(len(v), dtype=bool)
    if ok.sum() < 4:
        return mask
    finite = v[ok]
    if method == "iqr":
        q1, q3 = np.percentile(finite, [25, 75])
        fence = (1.5 if k is None else k) * (q3 - q1)
        if fence == 0:
            return mask
        mask[ok] = (finite < q1 - fence) | (finite > q3 + fence)
    elif method == "zscore":
        sd = finite.std()
        if sd == 0:
            return mask
        mask[ok] = np.abs(finite - finite.mean()) > (3.0 if k is None else k) * sd
    else:
        raise InvalidSpecError(f"method={safe_repr(method)} must be 'iqr' or 'zscore'")
    return mask


# ---------------------------------------------------------------- reference lines


def reference_value(values: Sequence[float] | np.ndarray, ref: str | float) -> float | None:
    """``"mean"``, ``"median"``, ``"p90"`` (a percentile) or a constant, for the values shown."""
    if not isinstance(ref, str):
        return float(ref)
    v = np.asarray(values, dtype="float64")
    v = v[np.isfinite(v)]
    if not len(v):
        return None
    if ref == "mean":
        return float(v.mean())
    if ref == "median":
        return float(np.median(v))
    m = _PERCENTILE.fullmatch(ref)
    if m:
        return float(np.percentile(v, int(m.group(1))))
    raise InvalidSpecError(f"ref={safe_repr(ref)} must be 'mean', 'median', 'p0'-'p99' or a number")


def reference_label(ref: str | float) -> str:
    if not isinstance(ref, str):
        return "Target"
    if ref in ("mean", "median"):
        return {"mean": "Average", "median": "Median"}[ref]
    return f"{int(ref[1:])}th percentile"
