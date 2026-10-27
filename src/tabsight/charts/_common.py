"""Helpers shared by the chart families: colour scales, numbers, figures."""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING, Any

from tabsight.figure import Figure
from tabsight.formats import locale_payload

if TYPE_CHECKING:
    from tabsight.aggregate import Measure
    from tabsight.charts import _Context

# Colour scales: sequential (darker = bigger) and diverging (orange below zero, blue above).
SEQ_LIGHT = ["#cadcef", "#9dbde0", "#6c9bcb", "#3f6fa8", "#1f3b5c"]
SEQ_DARK = ["#1d3a5c", "#2c5a86", "#3f7fbf", "#6ba6df", "#b6d6f3"]
DIV_LIGHT = ["#b4441c", "#e49a6d", "#f2e3c9", "#7fa7d0", "#1f4e8c"]
DIV_DARK = ["#e07b4c", "#8b4a2d", "#4d4636", "#2c5a86", "#6ba6df"]
# "No data" is a plain light grey, clearly apart from the lowest colour of every scale
NO_DATA = {"light": "#eceef1", "dark": "#2a2f36"}
POSITIVE = {"light": "#2f6aa8", "dark": "#6ba6df"}
NEGATIVE = {"light": "#c4572a", "dark": "#e07b4c"}


def num(v: Any) -> float | None:
    """A finite float, or None (for NaN, inf, text...)."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def is_dark(color: str) -> bool:
    r, g, b = (int(color[i : i + 2], 16) for i in (1, 3, 5))
    return (0.299 * r + 0.587 * g + 0.114 * b) < 128


def mode(ctx: _Context) -> str:
    return "dark" if is_dark(ctx.theme.tile) else "light"


def scale(values: Iterable[float | None], ctx: _Context) -> tuple[float, float, list[str], bool]:
    """(low, high, colours, diverging) for a colour scale over ``values``."""
    nums = [v for v in values if v is not None]
    lo, hi = (min(nums), max(nums)) if nums else (0.0, 1.0)
    dark = mode(ctx) == "dark"
    diverging = lo < 0 < hi
    if diverging:
        bound = max(abs(lo), abs(hi))
        lo, hi = -bound, bound
    if hi == lo:
        hi = lo + (abs(lo) or 1.0)
    ramp = (DIV_DARK if dark else DIV_LIGHT) if diverging else (SEQ_DARK if dark else SEQ_LIGHT)
    return lo, hi, ramp, diverging


def ramp_color(ramp: Sequence[str], t: float) -> str:
    t = min(1.0, max(0.0, t))
    pos = t * (len(ramp) - 1)
    i = min(int(pos), len(ramp) - 2)
    frac = pos - i
    a, b = ramp[i], ramp[i + 1]
    mix = [
        round(int(a[k : k + 2], 16) * (1 - frac) + int(b[k : k + 2], 16) * frac) for k in (1, 3, 5)
    ]
    return "#" + "".join(f"{c:02x}" for c in mix)


def visual_map(
    lo: float, hi: float, ramp: list[str], m: Measure, ctx: _Context, **extra: Any
) -> dict[str, Any]:
    """A continuous colour legend whose end labels are formatted like the data."""
    out = {
        "type": "continuous", "min": lo, "max": hi, "calculable": False, "orient": "horizontal",
        "left": "center", "bottom": 0, "itemWidth": 12, "itemHeight": 200, "inRange": {"color": ramp},
        "text": [ctx.fmt(hi, m, "compact"), ctx.fmt(lo, m, "compact")],
        "textStyle": {"color": ctx.theme.text_secondary},
    }  # fmt: skip
    out.update(extra)
    return out


def item_tooltip(ctx: _Context, m: Measure, **cfg: Any) -> dict[str, Any]:
    return {"trigger": "item", "fmt": ctx.js(m, "full"), "no_data": _no_data(), **cfg}


def fields_tooltip(fields: list[tuple[str, int, dict[str, Any]]], **cfg: Any) -> dict[str, Any]:
    """Tooltip listing several values of one item: (label, index in the item's array, format)."""
    return {
        "trigger": "item",
        "fields": [{"label": lb, "index": i, "fmt": f} for lb, i, f in fields],
        **cfg,
    }


def _no_data() -> str:
    from tabsight.i18n import text

    return text("no_data")


def figure(
    ctx: _Context, title: str, option: dict[str, Any] | None, height: int, **extra: Any
) -> Figure:
    return Figure(
        kind=extra.pop("kind", ctx.spec.kind), spec=ctx.spec, title=ctx.spec.title or title,
        subtitle=ctx.spec.subtitle, option=option, locales=locale_payload([ctx.locale]), theme=ctx.theme,
        height=height, notes=tuple(dict.fromkeys(ctx.notes)), decisions=tuple(dict.fromkeys(ctx.decisions)),
        facts=ctx.facts, **extra,
    )  # fmt: skip


def nice_ceiling(value: float) -> float:
    """1, 2, 2.5 or 5 times a power of ten, at or above ``value`` (for gauge scales)."""
    if value <= 0:
        return 1.0
    power = 10.0 ** math.floor(math.log10(value))
    for step in (1, 2, 2.5, 5, 10):
        if step * power >= value:
            return step * power
    return 10 * power
