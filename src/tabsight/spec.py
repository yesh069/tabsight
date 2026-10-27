"""ChartSpec: what a chart shows, as plain versioned JSON.

Loading a spec never runs code: every key is checked against an allow-list, every value
against a type and range, strings are length-limited, and unknown keys are rejected.
That makes it safe to load specs written by someone else.
"""

from __future__ import annotations

import dataclasses
import json
import re
from collections.abc import Callable, Mapping
from typing import Any

from tabsight.profile import AGGS, UNITS
from tabsight.warnings import InvalidSpecError, safe_repr

__all__ = ["CHART_KINDS", "SPEC_VERSION", "ChartSpec"]

SPEC_VERSION = 1
MAX_SPEC_BYTES = 1_000_000
MAX_NAME = 200
MAX_TITLE = 300

CHART_KINDS: tuple[str, ...] = (
    # comparison
    "bar", "hbar", "grouped_bar", "lollipop", "bullet",
    # part-to-whole
    "stacked_bar", "stacked100_bar", "donut", "treemap", "sunburst", "waterfall", "funnel",
    # trend
    "line", "multi_line", "area", "stacked_area", "combo", "sparkline", "calendar_heatmap",
    # flow
    "sankey",
    # relationship
    "scatter", "bubble", "heatmap",
    # distribution
    "histogram", "boxplot",
    # maps
    "choropleth", "symbol_map", "density_map", "flow_map",
    # single value
    "kpi", "gauge",
    # detail and ranking
    "table", "pareto",
)  # fmt: skip
ALIASES = {
    "map": "choropleth",
    "stackbar": "stacked_bar",
    "pie": "donut",
    "column": "bar",
    "box": "boxplot",
}
CALCS = ("running_total", "pct_of_total", "rank", "difference", "pct_difference")
_MOVING_AVG = re.compile(r"moving_avg:(\d{1,3})")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _name(value: Any, what: str) -> str:
    if not isinstance(value, str) or not value or len(value) > MAX_NAME or _CONTROL.search(value):
        raise InvalidSpecError(
            f"{what} {safe_repr(value)} must be a column name of 1-{MAX_NAME} characters"
        )
    return value


def _names(value: Any, what: str) -> str | tuple[str, ...]:
    if isinstance(value, list | tuple):
        if not 1 <= len(value) <= 20:
            raise InvalidSpecError(f"{what} takes 1-20 columns")
        return tuple(_name(v, what) for v in value)
    return _name(value, what)


def _text(value: Any, what: str) -> str:
    if not isinstance(value, str) or len(value) > MAX_TITLE or _CONTROL.search(value):
        raise InvalidSpecError(f"{what} must be text of at most {MAX_TITLE} characters")
    return value


def _choice(options: tuple[str, ...]) -> Callable[[Any, str], str]:
    def check(value: Any, what: str) -> str:
        if value not in options:
            raise InvalidSpecError(f"{what}={safe_repr(value)} must be one of {options}")
        return str(value)

    return check


def _int_range(lo: int, hi: int) -> Callable[[Any, str], int]:
    def check(value: Any, what: str) -> int:
        if type(value) is not int or not lo <= value <= hi:
            raise InvalidSpecError(f"{what}={safe_repr(value)} must be an integer {lo}-{hi}")
        return value

    return check


def _number(value: Any, what: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, int | float)
        or value != value
        or abs(value) > 1e300
    ):
        raise InvalidSpecError(f"{what}={safe_repr(value)} must be a finite number")
    return float(value)


def _bool(value: Any, what: str) -> bool:
    if not isinstance(value, bool):
        raise InvalidSpecError(f"{what} must be true or false")
    return value


def _sort(value: Any, what: str) -> str | tuple[str, ...]:
    if value in ("asc", "desc", "none"):
        return str(value)
    if (
        isinstance(value, list | tuple)
        and len(value) <= 1000
        and all(isinstance(v, str) and len(v) <= MAX_NAME for v in value)
    ):
        return tuple(value)
    if isinstance(value, str) and value.startswith("by:"):
        _name(value[3:], what)
        return value
    raise InvalidSpecError(
        f"{what} must be 'asc', 'desc', 'none', 'by:<column>' or a list of values"
    )


def _calc(value: Any, what: str) -> str:
    if value in CALCS:
        return str(value)
    if isinstance(value, str):
        m = _MOVING_AVG.fullmatch(value)
        if m and 2 <= int(m.group(1)) <= 365:
            return value
    raise InvalidSpecError(
        f"{what}={safe_repr(value)} must be one of {CALCS} or 'moving_avg:N' (N 2-365)"
    )


def _place_map(value: Any, what: str) -> dict[str, str]:
    """{your spelling: place name or code}, as passed to ``geo_map=``."""
    if not isinstance(value, Mapping) or len(value) > 10_000:
        raise InvalidSpecError(f"{what} must be an object of up to 10,000 {{value: place}} pairs")
    out = {}
    for k, v in value.items():
        out[_text(k, what)] = _text(v, what)
    return out


def _goal(value: Any, what: str) -> float | str:
    return _name(value, what) if isinstance(value, str) else _number(value, what)


def _date(value: Any, what: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise InvalidSpecError(f"{what} must be a date like '2017-12-31'")
    return value


_PERCENTILE = re.compile(r"p\d{1,2}")


def _ref_one(value: Any, what: str) -> str | float:
    if isinstance(value, str):
        if value in ("mean", "median") or _PERCENTILE.fullmatch(value):
            return value
        raise InvalidSpecError(
            f"{what}={safe_repr(value)} must be 'mean', 'median', 'p0'-'p99' or a number"
        )
    return _number(value, what)


def _ref(value: Any, what: str) -> tuple[str | float, ...]:
    """One reference line or up to 4: ``"mean"``, ``"median"``, ``"p90"`` or a number."""
    if isinstance(value, list | tuple):
        if not 1 <= len(value) <= 4:
            raise InvalidSpecError(f"{what} takes 1-4 reference lines")
        return tuple(_ref_one(v, what) for v in value)
    return (_ref_one(value, what),)


def _band(value: Any, what: str) -> tuple[str | float, str | float]:
    """A shaded band between two references, for example ``("p25", "p75")``."""
    if not isinstance(value, list | tuple) or len(value) != 2:
        raise InvalidSpecError(f"{what} must be a pair like ('p25', 'p75') or (100, 200)")
    return (_ref_one(value[0], what), _ref_one(value[1], what))


GEO_NAME_LANGUAGES = (
    "english", "local", "ar", "bn", "de", "el", "en", "es", "fa", "fr", "he", "hi", "hu", "id", "it",
    "ja", "ko", "nl", "pl", "pt", "ru", "sv", "tr", "uk", "ur", "vi", "zh", "zht",
)  # fmt: skip

# Options: allowed keys and their validators.
_OPTIONS: dict[str, Callable[[Any, str], Any]] = {
    "trend": _bool,
    "forecast": _int_range(1, 120),
    "season": _int_range(2, 366),
    "insights": _bool,
    "compare": _choice(("previous_year", "previous_quarter", "previous_month", "previous_period")),
    "ref": _ref,  # reference lines: "mean", "median", "p90" or a number, or a list of up to 4
    "band": _band,  # a shaded band between two references
    "outliers": _bool,
    "fixed": _bool,
    "log": _bool,
    "y_min": _number,
    "y_max": _number,
    "scale": _choice(("auto", "fixed")),
    "action": _choice(("filter", "highlight")),
    "cross_filter": _bool,
    "drill": _bool,
    "menu": _bool,
    "missing": _choice(("gap", "zero", "connect")),
    "weight": _name,
    "as_of": _date,
    "negative": _choice(("minus", "parens")),
    "freq": _choice(("year", "quarter", "month", "week", "day", "hour")),
    "projection": _choice(("equal_earth", "mercator", "natural")),
    "geo_names": _choice(GEO_NAME_LANGUAGES),
    "map": _text,  # "world" or a country name or code
    "level": _choice(("country", "region", "city")),
    "layer": _name,
    "geo_map": _place_map,
    "bins": _int_range(2, 200),
    "bin_width": _number,
    "goal": _goal,  # a target: a number, or a column holding one per row
    "total": _bool,  # waterfall: end with a total bar
}


@dataclasses.dataclass(frozen=True)
class ChartSpec:
    kind: str
    x: str | tuple[str, ...] | None = None
    y: str | tuple[str, ...] | None = None
    color: str | None = None
    size: str | None = None
    facet: str | None = None
    geo: str | None = None
    lat: str | None = None
    lon: str | None = None
    source: str | None = None
    target: str | None = None
    agg: str | None = None
    sort: str | tuple[str, ...] | None = None
    top: int | None = None
    calc: str | None = None
    unit: str | None = None
    currency: str | None = None
    decimals: int | None = None
    format: str | None = None
    title: str | None = None
    subtitle: str | None = None
    options: Mapping[str, Any] = dataclasses.field(default_factory=dict)

    def __post_init__(self) -> None:
        kind = ALIASES.get(self.kind, self.kind) if isinstance(self.kind, str) else self.kind
        if kind not in CHART_KINDS:
            raise InvalidSpecError(f"unknown chart kind {safe_repr(self.kind)}")
        object.__setattr__(self, "kind", kind)
        for key in ("x", "y"):
            value = getattr(self, key)
            if value is not None:
                object.__setattr__(self, key, _names(value, key))
        for key in ("color", "size", "facet", "geo", "lat", "lon", "source", "target"):
            value = getattr(self, key)
            if value is not None:
                _name(value, key)
        if self.agg is not None:
            _choice(AGGS)(self.agg, "agg")
        if self.sort is not None:
            object.__setattr__(self, "sort", _sort(self.sort, "sort"))
        if self.top is not None:
            _int_range(1, 1000)(self.top, "top")
        if self.calc is not None:
            _calc(self.calc, "calc")
        if self.unit is not None:
            _choice(UNITS)(self.unit, "unit")
        if self.currency is not None and not (
            isinstance(self.currency, str) and re.fullmatch(r"[A-Z]{3}", self.currency)
        ):
            raise InvalidSpecError("currency must be a 3-letter code")
        if self.decimals is not None:
            _int_range(0, 6)(self.decimals, "decimals")
        if self.format is not None:
            from tabsight.formats import parse_pattern

            parse_pattern(self.format)
        for key in ("title", "subtitle"):
            value = getattr(self, key)
            if value is not None:
                _text(value, key)
        if not isinstance(self.options, Mapping):
            raise InvalidSpecError("options must be an object")
        checked = {}
        for key, value in self.options.items():
            if key not in _OPTIONS:
                raise InvalidSpecError(f"unknown option {safe_repr(key)}")
            checked[key] = _OPTIONS[key](value, key)
        object.__setattr__(self, "options", checked)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"tabsight_spec": SPEC_VERSION}
        for f in dataclasses.fields(self):
            value = getattr(self, f.name)
            if value is None or (f.name == "options" and not value):
                continue
            out[f.name] = (
                list(value)
                if isinstance(value, tuple)
                else (dict(value) if f.name == "options" else value)
            )
        return out

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_dict(cls, data: Any) -> ChartSpec:
        if not isinstance(data, Mapping):
            raise InvalidSpecError("a chart spec must be an object")
        version = data.get("tabsight_spec", SPEC_VERSION)
        if version != SPEC_VERSION:
            raise InvalidSpecError(
                f"chart spec version {safe_repr(version)} is not supported (expected {SPEC_VERSION})"
            )
        allowed = {f.name for f in dataclasses.fields(cls)} | {"tabsight_spec"}
        unknown = set(data) - allowed
        if unknown:
            raise InvalidSpecError(f"unknown spec key(s) {sorted(map(safe_repr, unknown))}")
        kwargs = {k: v for k, v in data.items() if k != "tabsight_spec"}
        if "kind" not in kwargs:
            raise InvalidSpecError("a chart spec needs a 'kind'")
        return cls(**kwargs)

    @classmethod
    def from_json(cls, text: str | bytes) -> ChartSpec:
        if len(text) > MAX_SPEC_BYTES:
            raise InvalidSpecError("chart spec is too large")
        try:
            data = json.loads(text)
        except (ValueError, RecursionError) as err:
            raise InvalidSpecError(
                f"chart spec is not valid JSON: {safe_repr(str(err), 120)}"
            ) from None
        return cls.from_dict(data)
