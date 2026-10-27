"""Dashboards: several tiles, filters and cross-filtering, in one offline HTML file.

How the numbers stay exact after the viewer filters (PLAN sections 5.2 and 9.2):

- tabsight stores **one shared table**, grouped by every field the dashboard uses (tile
  dimensions, filter fields, date periods), holding the exact re-aggregation parts of
  each measure: sums and counts for averages, weighted sums for weighted averages, and
  minimums and maximums. The raw rows are never stored.
- In the browser, ``dashboard.js`` keeps the rows that match the filters, adds their
  parts up again and redraws each tile. Python and the browser follow the same rules;
  parity tests run both on the same filters.
- Tiles whose numbers can't be recomputed exactly (medians, distinct counts, scatter
  plots of raw rows, and the other kinds listed in ``STATIC_REASONS``) are drawn from
  all the data and say "not affected by filters" so nothing looks wrong silently.

A dashboard is saved as plain JSON with no data (``save``/``load``) and can be pointed at
new data with ``bind``. Loading someone else's file is safe: every key is checked
against an allow-list, values are plain JSON, and charts are validated as they are built.
"""

from __future__ import annotations

import copy
import dataclasses
import json
import warnings
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from tabsight.aggregate import Measure, _numeric, _part_name, _time_values, bucket, build_parts
from tabsight.charts._build import OTHER_COLOR
from tabsight.colors import ColorRegistry, natural_key
from tabsight.figure import Figure
from tabsight.formats import format_date, js_spec, locale_payload
from tabsight.i18n import text
from tabsight.io import as_frame
from tabsight.profile import Profile, _prepare, profile
from tabsight.settings import resolve
from tabsight.theme import Theme, get_theme
from tabsight.warnings import InvalidSpecError, safe_repr

__all__ = ["DASHBOARD_VERSION", "Dashboard"]

DASHBOARD_VERSION = 1
MAX_TILES = 40
MAX_FILTERS = 12
MAX_FILE_BYTES = 1_000_000
FILTER_GRAIN = "month"  # date filters work by month, so a day-level date can't blow up the table
MAX_FILTER_VALUES = 2000
LIVE_KINDS = ("bar", "hbar", "grouped_bar", "stacked_bar", "stacked100_bar", "line", "multi_line", "area",
              "stacked_area", "donut", "kpi", "table", "choropleth")  # fmt: skip
EXACT_AGGS = ("sum", "count", "mean", "min", "max")
TILE_KEYS = frozenset({
    "kind", "x", "y", "color", "agg", "sort", "top", "freq", "title", "subtitle", "unit", "currency", "decimals",
    "format", "geo", "lat", "lon", "map", "level", "layer", "geo_map", "geo_names", "projection", "size", "goal",
    "bins", "bin_width", "source", "target", "trend", "forecast", "season", "ref", "band", "outliers", "insights",
    "compare", "as_of", "height", "w", "action",
})  # fmt: skip
_TOP_KEYS = frozenset({"tabsight_dashboard", "title", "subtitle", "filters", "tiles", "theme", "locale",
                       "currency", "palette", "insights"})  # fmt: skip
DEFAULT_WIDTH = {"kpi": 3, "gauge": 3, "bullet": 6, "table": 12, "sparkline": 3}
GRAINS_FINE_TO_COARSE = ("hour", "day", "week", "month", "quarter", "year")


def _plain(value: Any, where: str, depth: int = 0) -> Any:
    """Plain JSON only: strings, numbers, booleans, None, lists and string-keyed objects."""
    if depth > 4:
        raise InvalidSpecError(f"{where} is nested too deeply")
    if value is None or isinstance(value, bool | int | str):
        if isinstance(value, str) and len(value) > 1000:
            raise InvalidSpecError(f"{where} is too long")
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise InvalidSpecError(f"{where} must be a finite number")
        return value
    if isinstance(value, list | tuple):
        if len(value) > 1000:
            raise InvalidSpecError(f"{where} holds too many items")
        return [_plain(v, where, depth + 1) for v in value]
    if isinstance(value, Mapping):
        if len(value) > 10_000:
            raise InvalidSpecError(f"{where} holds too many items")
        return {_plain(k, where, depth + 1) if isinstance(k, str) else _bad_key(where): _plain(v, where, depth + 1)
                for k, v in value.items()}  # fmt: skip
    raise InvalidSpecError(f"{where} must be plain JSON, not {type(value).__name__}")


def _bad_key(where: str) -> str:
    raise InvalidSpecError(f"{where} keys must be text")


def _text(value: Any, what: str, limit: int = 300) -> str:
    if not isinstance(value, str) or len(value) > limit:
        raise InvalidSpecError(f"{what} must be text of at most {limit} characters")
    return value


def _check_tile(tile: Mapping[str, Any]) -> dict[str, Any]:
    unknown = sorted(set(tile) - TILE_KEYS)
    if unknown:
        import difflib

        hint = difflib.get_close_matches(unknown[0], TILE_KEYS, n=1)
        raise InvalidSpecError(
            f"unknown tile setting {safe_repr(unknown[0])}"
            + (f"; did you mean {hint[0]!r}?" if hint else "")
        )
    out = {k: _plain(v, f"tile {k}") for k, v in tile.items() if v is not None}
    if not isinstance(out.get("kind", "auto"), str):
        raise InvalidSpecError("tile kind must be text")
    w = out.get("w")
    if w is not None and (type(w) is not int or not 1 <= w <= 12):
        raise InvalidSpecError("w (tile width) must be a whole number of columns 1-12")
    if out.get("action", "filter") not in ("filter", "highlight", "none"):
        raise InvalidSpecError("action must be 'filter', 'highlight' or 'none'")
    return out


@dataclasses.dataclass
class _Built:
    payload: dict[str, Any]
    figures: list[Figure]
    report: list[str]


class Dashboard:
    """A dashboard: tiles laid out on a 12-column grid, filters, and cross-filtering.

    >>> dash = ts.Dashboard("Sales", data=orders, filters=["Region", "Order_Date"])
    >>> dash.kpi("Sales").kpi("Profit").add("bar", x="Category", y="Sales").to_html("sales.html")

    Clicking a bar, slice, map region or table row filters every other tile; Ctrl or
    Shift + click adds values; clicking again removes them. The numbers are re-aggregated
    exactly in the browser from one shared, pre-aggregated table (no raw rows).
    """

    def __init__(
        self,
        title: str = "Dashboard",
        data: Any = None,
        *,
        subtitle: str | None = None,
        filters: Sequence[str] = (),
        theme: str | None = None,
        locale: str | None = None,
        currency: str | None = None,
        palette: str | None = None,
    ) -> None:
        self.title = _text(title, "title")
        self.subtitle = _text(subtitle, "subtitle") if subtitle is not None else None
        if isinstance(filters, str):
            filters = [filters]
        if len(filters) > MAX_FILTERS or not all(isinstance(f, str) and f for f in filters):
            raise InvalidSpecError(f"filters must be up to {MAX_FILTERS} column names")
        self.filters = list(dict.fromkeys(filters))
        self.theme = theme
        self.locale = locale
        self.currency = currency
        self.palette = palette
        resolve(locale=locale, currency=currency, palette=palette)  # validate now, not at build
        if theme is not None:
            get_theme(theme)
        self.tiles: list[dict[str, Any]] = []
        self.insight_count = 0
        self.data = None if data is None else as_frame(data)

    # ------------------------------------------------------------ building it up

    def add(
        self, kind: str = "auto", *, w: int | None = None, action: str = "filter", **chart: Any
    ) -> Dashboard:
        """Add a tile: any ``ts.chart`` arguments, plus ``w`` (width, 1-12 columns) and
        ``action`` (``"filter"``: clicks filter the other tiles; ``"highlight"``: they only
        highlight; ``"none"``)."""
        if len(self.tiles) >= MAX_TILES:
            raise InvalidSpecError(f"a dashboard holds at most {MAX_TILES} tiles")
        if "data" in chart or "facet" in chart:
            raise InvalidSpecError(
                "tiles use the dashboard's data, without small multiples, for now"
            )
        self.tiles.append(_check_tile({"kind": kind, "w": w, "action": action, **chart}))
        return self

    def kpi(self, y: str, *, w: int = 3, **chart: Any) -> Dashboard:
        """Add a KPI card; ``compare="previous_year"`` adds the change on last year."""
        return self.add("kpi", y=y, w=w, **chart)

    def insights(self, max_items: int = 6) -> Dashboard:
        """Add a panel of plain-English insights about the dashboard's data."""
        if type(max_items) is not int or not 1 <= max_items <= 20:
            raise InvalidSpecError("max_items must be a whole number 1-20")
        self.insight_count = max_items
        return self

    # ------------------------------------------------------------ saving and loading

    def to_dict(self) -> dict[str, Any]:
        """The dashboard as plain JSON, without any data."""
        out: dict[str, Any] = {"tabsight_dashboard": DASHBOARD_VERSION, "title": self.title,
                               "filters": list(self.filters), "tiles": copy.deepcopy(self.tiles)}  # fmt: skip
        for key in ("subtitle", "theme", "locale", "currency", "palette"):
            if getattr(self, key) is not None:
                out[key] = getattr(self, key)
        if self.insight_count:
            out["insights"] = self.insight_count
        return out

    def save(self, path: str | Path) -> None:
        Path(path).write_text(
            json.dumps(self.to_dict(), indent=1, ensure_ascii=False), encoding="utf-8"
        )

    @classmethod
    def from_dict(cls, data: Any) -> Dashboard:
        if not isinstance(data, Mapping):
            raise InvalidSpecError("a dashboard file must hold an object")
        unknown = sorted(set(data) - _TOP_KEYS)
        if unknown:
            raise InvalidSpecError(f"unknown dashboard key {safe_repr(unknown[0])}")
        if data.get("tabsight_dashboard", DASHBOARD_VERSION) != DASHBOARD_VERSION:
            raise InvalidSpecError(f"this tabsight reads dashboard version {DASHBOARD_VERSION}")
        tiles = data.get("tiles", [])
        if not isinstance(tiles, list) or len(tiles) > MAX_TILES:
            raise InvalidSpecError(f"tiles must be a list of at most {MAX_TILES}")
        dash = cls(
            data.get("title", "Dashboard"), subtitle=data.get("subtitle"), filters=data.get("filters", ()),
            theme=data.get("theme"), locale=data.get("locale"), currency=data.get("currency"),
            palette=data.get("palette"),
        )  # fmt: skip
        for tile in tiles:
            if not isinstance(tile, Mapping):
                raise InvalidSpecError("each tile must be an object")
            dash.tiles.append(_check_tile(tile))
        if data.get("insights"):
            dash.insights(data["insights"])
        return dash

    @classmethod
    def load(cls, path: str | Path) -> Dashboard:
        raw = Path(path).read_bytes()
        if len(raw) > MAX_FILE_BYTES:
            raise InvalidSpecError("dashboard file is too large")
        return cls.from_dict(json.loads(raw.decode("utf-8")))

    def bind(self, data: Any) -> Dashboard:
        """The same dashboard on new data. Every column it needs must exist ("did you mean" otherwise)."""
        frame = as_frame(data)
        missing = sorted(self._columns() - set(map(str, frame.columns)))
        if missing:
            import difflib

            hint = difflib.get_close_matches(missing[0], [str(c) for c in frame.columns], n=1)
            raise InvalidSpecError(
                f"the new data has no column {safe_repr(missing[0])}"
                + (f"; did you mean {hint[0]!r}?" if hint else "")
            )
        out = Dashboard.from_dict(self.to_dict())
        out.data = frame
        return out

    def _columns(self) -> set[str]:
        cols = set(self.filters)
        for tile in self.tiles:
            for key in ("x", "y", "color", "geo", "lat", "lon", "size", "source", "target"):
                v = tile.get(key)
                cols |= {v} if isinstance(v, str) else set(v or ())
            if isinstance(tile.get("goal"), str):
                cols.add(tile["goal"])
        return cols

    # ------------------------------------------------------------ output

    def build(self) -> dict[str, Any]:
        """The page payload: tiles, bindings and the shared table (plain JSON)."""
        return self._build().payload

    def to_html(self, path: str | Path | None = None, *, cdn: bool = False) -> str:
        """One offline HTML file. ``cdn=True`` loads ECharts from jsDelivr (pinned by hash)."""
        from tabsight.render.dashboard_html import dashboard_page

        built = self._build()
        theme = get_theme(self.theme or resolve().theme)
        document = dashboard_page(built.payload, theme, cdn=cdn)
        if path is not None:
            Path(path).write_text(document, encoding="utf-8")
        return document

    def _repr_html_(self) -> str:
        from tabsight.render.html import srcdoc_iframe
        from tabsight.settings import current

        document = self.to_html(cdn=current().cdn)
        rows = 0
        width = 0
        for tile in self.build_layout():
            if width + tile[1] > 12:
                rows += 1
                width = 0
            width += tile[1]
        return srcdoc_iframe(document, 220 + 470 * (rows + 1))

    def build_layout(self) -> list[tuple[str, int]]:
        return [
            (t.get("kind", "auto"), t.get("w") or DEFAULT_WIDTH.get(t.get("kind", ""), 6))
            for t in self.tiles
        ]

    def __repr__(self) -> str:
        return f"<Dashboard {self.title!r}: {len(self.tiles)} tiles, filters {self.filters}>"

    # ------------------------------------------------------------ the build

    def _build(self) -> _Built:
        if self.data is None:
            raise InvalidSpecError("this dashboard has no data yet: pass data= or call .bind(df)")
        if not self.tiles:
            raise InvalidSpecError("add at least one tile (dash.add(...) or dash.kpi(...))")
        from tabsight.charts import chart

        settings = resolve(locale=self.locale, currency=self.currency, palette=self.palette)
        theme: Theme = get_theme(self.theme or settings.theme)
        frame, _ = _prepare(self.data)
        prof = profile(frame, quiet=True)
        for f in self.filters:
            if f not in prof:
                raise InvalidSpecError(f"filter column {safe_repr(f)} not found")
        common: dict[str, Any] = {
            "locale": self.locale,
            "currency": self.currency,
            "palette": self.palette,
            "theme": theme,
        }

        def draw(tile: Mapping[str, Any], colors: Mapping[str, str] | None) -> Figure:
            args = {k: v for k, v in tile.items() if k not in ("w", "action")}
            kind = args.pop("kind", "auto")
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                return chart(frame, kind, prof=prof, colors=colors, **common, **args)

        first = [draw(t, None) for t in self.tiles]
        # One colour per value across the whole dashboard (a region keeps its colour everywhere).
        registry = ColorRegistry(settings.palette)
        for fig in first:
            for col in _colour_fields(fig):
                registry.assign(_labels_of(frame, col, prof))
        pinned = registry.mapping()
        figures = [draw(t, pinned) for t in self.tiles]

        table = _SharedTable(
            frame, prof, settings.fiscal_start, settings.week_start, settings.locale
        )
        tiles: list[dict[str, Any]] = []
        report: list[str] = []
        for i, (tile, fig) in enumerate(zip(self.tiles, figures, strict=True)):
            binding, why = _binding(fig, tile, table, prof, frame, i)
            entry: dict[str, Any] = {
                "id": f"t{i}",
                "w": tile.get("w") or DEFAULT_WIDTH.get(fig.kind, 6),
                "action": tile.get("action", "filter"),
                "figure": fig.to_dict(),
            }
            if binding is None:
                entry["static"] = why
                report.append(f"tile {i + 1} ({fig.kind}) is drawn from all the data: {why}")
            else:
                entry["binding"] = binding
            tiles.append(entry)
        filters = [table.filter(f) for f in self.filters]
        payload = table.payload(settings.max_size_mb)
        insights: list[dict[str, Any]] = []
        if self.insight_count:
            from tabsight.insight import insights as find

            ys = list(dict.fromkeys(m["column"] for f in figures for m in f.facts.get("measures", ())
                                    if m["column"] in prof and prof[m["column"]].role == "measure"))  # fmt: skip
            found = find(
                frame, y=ys or None, max_items=self.insight_count, locale=settings.locale, prof=prof
            )
            insights = [i.to_dict() for i in found]
        page = {
            "tabsight_dashboard": DASHBOARD_VERSION,
            "title": self.title,
            "subtitle": self.subtitle,
            "theme": theme.to_dict(),
            "locales": locale_payload([settings.locale]),
            "unknown": text("unknown"),
            "other": text("other"),
            "min_group_size": settings.min_group_size,
            "fiscal_start": settings.fiscal_start,
            "filters": filters,
            "colors": pinned,
            "other_color": OTHER_COLOR,
            "csv_safe": settings.csv_safe,
            "tiles": tiles,
            "data": payload,
            "insights": insights,
            "words": {
                "reset": text("reset_filters"),
                "all_data": text("based_on_all_data"),
                "current": text("for_current_filters"),
                "csv": text("download_csv"),
                "no_data": text("no_data"),
                "not_filtered": text("filter_not_applied"),
            },
        }
        return _Built(page, figures, report)


# ---------------------------------------------------------------- the shared table


def _colour_fields(fig: Figure) -> list[str]:
    spec = fig.spec
    if fig.kind in ("donut",) and isinstance(spec.x, str):
        return [spec.x]
    return [spec.color] if spec.color else []


def _labels_of(frame: pd.DataFrame, col: str, prof: Profile) -> list[str]:
    if prof[col].role == "time":
        return []
    values = frame[col].dropna().astype(str).unique().tolist()
    return sorted(values, key=natural_key)


def _key(value: Any) -> str | None:
    if value is None or (isinstance(value, float) and np.isnan(value)) or value is pd.NaT:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return str(value)


def _date_key(value: Any, grain: str) -> str | None:
    if value is None or pd.isna(value):
        return None
    ts = pd.Timestamp(value)
    return ts.strftime("%Y-%m-%dT%H:00") if grain == "hour" else ts.strftime("%Y-%m-%d")


class _SharedTable:
    """Collects the dimensions and measures every tile needs, then groups once."""

    def __init__(
        self, frame: pd.DataFrame, prof: Profile, fiscal_start: int, week_start: str, locale: str
    ):
        self.frame, self.prof = frame, prof
        self.fiscal_start, self.week_start, self.locale = fiscal_start, week_start, locale
        self.dims: dict[str, pd.Series] = {}  # column id -> keys
        self.meta: dict[str, dict[str, Any]] = {}
        self.measures: list[Measure] = []
        self.labels: dict[str, dict[str, dict[str, str]]] = {}

    def dim(self, field: str, grain: str | None = None) -> str:
        """The column id for ``field`` (at ``grain`` for dates), adding it if new."""
        time = self.prof[field].role == "time"
        if time:
            grain = grain or self.prof[field].grain or "day"
            if grain not in GRAINS_FINE_TO_COARSE:
                grain = "day"
        col = f"{field}|{grain}" if time else field
        if col in self.dims:
            return col
        if time:
            dates = _time_values(self.frame[field], self.prof, field)
            buckets = bucket(
                dates, str(grain), fiscal_start=self.fiscal_start, week_start=self.week_start
            )
            keys = pd.Series(
                [_date_key(v, str(grain)) for v in buckets], index=self.frame.index, dtype="object"
            )
            distinct = sorted({k for k in keys if k is not None})
            self.labels[col] = {
                style: {k: format_date(pd.Timestamp(k), str(grain), style, locale=self.locale,
                                       fiscal_start=self.fiscal_start) for k in distinct}
                for style in ("full", "compact")
            }  # fmt: skip
        else:
            keys = pd.Series(
                [_key(v) for v in self.frame[field]], index=self.frame.index, dtype="object"
            )
        self.dims[col] = keys
        self.meta[col] = {
            "field": field,
            "grain": grain if time else None,
            "title": field.replace("_", " "),
        }
        return col

    def periods(self, col: str) -> list[str]:
        """Every period from the first to the last, gaps included (lines show them as gaps)."""
        keys = sorted({k for k in self.dims[col] if k is not None})
        grain = self.meta[col]["grain"]
        if len(keys) < 2 or grain not in ("year", "quarter", "month", "week", "day"):
            return keys
        step = {"year": pd.DateOffset(years=1), "quarter": pd.DateOffset(months=3), "month": pd.DateOffset(months=1),
                "week": pd.DateOffset(weeks=1), "day": pd.DateOffset(days=1)}[grain]  # fmt: skip
        out: list[str] = []
        t, end = pd.Timestamp(keys[0]), pd.Timestamp(keys[-1])
        while t <= end and len(out) < 100_000:
            out.append(t.strftime("%Y-%m-%d"))
            t = t + step
        labels = self.labels[col]
        for k in out:
            for style in ("full", "compact"):
                labels[style].setdefault(k, format_date(pd.Timestamp(k), grain, style, locale=self.locale,
                                                        fiscal_start=self.fiscal_start))  # fmt: skip
        return out

    def window(self, name: str, keys: pd.Series) -> str:
        self.dims[name] = keys.astype("object")
        self.meta[name] = {"field": name, "grain": None, "title": name, "hidden": True}
        return name

    def measure(self, column: str | None, agg: str) -> dict[str, str]:
        m = Measure(column, agg)
        if m not in self.measures:
            self.measures.append(m)
        i = self.measures.index(m)
        if column is None:
            return {"count": "__rows"}
        names = {
            "sum": ("sum",),
            "mean": ("sum", "count"),
            "count": ("count",),
            "min": ("min",),
            "max": ("max",),
        }
        return {p: _part_name(i, p) for p in names[agg]}

    def filter(self, field: str) -> dict[str, Any]:
        time = self.prof[field].role == "time"
        col = self.dim(field, FILTER_GRAIN if time else None)
        keys = sorted(
            {k for k in self.dims[col] if k is not None}, key=natural_key if not time else None
        )
        if not time and self.prof[field].ordered:
            order = {v: i for i, v in enumerate(self.prof[field].ordered or ())}
            keys.sort(key=lambda k: order.get(k, len(order)))
        if any(k is None for k in self.dims[col]):
            keys.append(None)
        if len(keys) > MAX_FILTER_VALUES:
            raise InvalidSpecError(
                f"{safe_repr(field)} has {len(keys):,} values, too many for a filter list (at most {MAX_FILTER_VALUES:,})"
            )
        return {"field": field, "title": field.replace("_", " "), "col": col, "type": "range" if time else "in",
                "values": keys}  # fmt: skip

    def payload(self, max_mb: float) -> dict[str, Any]:
        work = pd.DataFrame(dict(self.dims), index=self.frame.index)
        dims = list(self.dims)
        for m in self.measures:
            if m.column is None or m.column in work:
                continue
            work[m.column] = _numeric(self.frame[m.column], self.prof[m.column].source)
        parts = build_parts(work, dims, self.measures)
        out: dict[str, Any] = {
            "rows": len(parts),
            "dims": {},
            "nums": {},
            "labels": self.labels,
            "meta": self.meta,
        }
        for col in dims:
            values = parts[col].astype("object").where(parts[col].notna(), None).tolist()
            distinct = list(dict.fromkeys(values))
            index = {v: i for i, v in enumerate(distinct)}
            out["dims"][col] = {"values": distinct, "codes": [index[v] for v in values]}
        for col in parts.columns:
            if col in self.dims:
                continue
            nums = pd.to_numeric(parts[col], errors="coerce").astype("float64")
            out["nums"][col] = [None if not np.isfinite(v) else (int(v) if float(v).is_integer() and abs(v) < 2**53 else float(v))
                                for v in nums]  # fmt: skip
        size = len(json.dumps(out, separators=(",", ":"), allow_nan=False)) / 1e6
        out["size_mb"] = round(size, 3)
        if size > max_mb:
            widest = sorted(dims, key=lambda c: -len(out["dims"][c]["values"]))[:3]
            raise InvalidSpecError(
                f"the dashboard's data table would be {size:.1f} MB ({len(parts):,} rows), over the "
                f"{max_mb:g} MB limit. The fields with the most values are "
                + ", ".join(
                    f"{self.meta[c]['field']} ({len(out['dims'][c]['values']):,})" for c in widest
                )
                + ". Use a coarser freq= for dates, fewer filter fields, top= on large categories, or "
                "ts.set_defaults(max_size_mb=...)"
            )
        return out


# ---------------------------------------------------------------- bindings


def _binding(fig: Figure, tile: Mapping[str, Any], table: _SharedTable, prof: Profile, frame: pd.DataFrame,
             i: int) -> tuple[dict[str, Any] | None, str]:  # fmt: skip
    """How the browser recomputes this tile, or None and the reason it can't exactly."""
    kind, spec, facts = fig.kind, fig.spec, fig.facts
    if kind not in LIVE_KINDS:
        return None, f"{kind.replace('_', ' ')} tiles are not recomputed after filtering yet"
    measures = list(facts.get("measures", ()))
    for m in measures:
        if m["agg"] not in EXACT_AGGS:
            what = {
                "countd": "distinct counts",
                "median": "medians",
                "wavg": "weighted averages",
            }.get(m["agg"], m["agg"])
            return None, f"{what} can't be recomputed exactly from the shared table"
    if any(f.currency_code_column and f.distinct > 1 for f in prof.fields):
        return None, "amounts in several currencies are split by currency"
    option = fig.option or {}
    if (
        kind in ("line", "area", "multi_line", "stacked_area")
        and (option.get("xAxis") or {}).get("type") == "value"
    ):
        return None, "lines over a number axis are drawn from all the data"
    b: dict[str, Any] = {"kind": kind}
    parts = [
        {"parts": table.measure(m["column"], m["agg"]), "agg": m["agg"], "label": m["column"],
         "full": m["full"], "compact": m["compact"]}
        for m in measures
    ]  # fmt: skip
    if not measures and kind in ("choropleth", "kpi"):
        count = js_spec("count", "full", locale=table.locale)
        parts = [{"parts": {"count": "__rows"}, "agg": "count", "label": "Rows", "full": count,
                  "compact": js_spec("count", "compact", locale=table.locale)}]  # fmt: skip
    b["measures"] = parts
    dims = [spec.x] if isinstance(spec.x, str) else list(spec.x or ())
    freq = spec.options.get("freq")
    if kind == "kpi":
        b["shape"] = "value"
        b["dims"] = []
        how = spec.options.get("compare")
        if how:
            date = next((f.name for f in prof.fields if f.role == "time"), None)
            if date is None or how == "previous_period":
                return None, "this comparison isn't recomputed after filtering"
            from tabsight.periods import compare

            c = compare(frame, measures[0]["column"], date, compare=how, as_of=spec.options.get("as_of"),
                        agg=measures[0]["agg"], locale=table.locale, prof=prof)  # fmt: skip
            day = _time_values(frame[date], prof, date).dt.normalize()
            flag = pd.Series(np.where((day >= c.start) & (day <= c.end), "cur",
                                      np.where((day >= c.previous_start) & (day <= c.previous_end), "prev", None)),
                             index=frame.index)  # fmt: skip
            b["compare"] = {
                "how": how, "window": table.window(f"__w{i}", flag), "month": table.dim(date, "month"),
                "date_field": date, "current_label": c.current_label, "previous_label": c.previous_label,
                "shift": {"previous_year": 12, "previous_quarter": 3, "previous_month": 1}[how],
                "pct_fmt": js_spec("percent", "full", locale=table.locale, decimals=1),
                "pp": (prof[measures[0]["column"]].unit in ("percent", "pp")) if measures else False,
                "pp_fmt": js_spec("pp", "full", locale=table.locale, decimals=1,
                                  percent_scale=(prof[measures[0]["column"]].percent_scale or "fraction") if measures else "fraction"),
            }  # fmt: skip
        return b, ""
    if kind == "choropleth":
        geo = facts.get("geo_field")
        if not geo:
            return None, "this map can't be recomputed after filtering"
        b["shape"] = "geo"
        b["dims"] = [table.dim(geo)]
        b["shapes"] = facts.get("geo_shapes", {})
        b["click"] = b["dims"][0]
        return b, ""
    if kind == "table":
        b["shape"] = "rows"
        b["dims"] = [table.dim(d, freq if prof[d].role == "time" else None) for d in dims]
        b["formats"] = facts.get("column_formats", [])
        b["sort"] = _sort_rule(spec, prof, dims[0] if dims else None, bool(measures))
        b["order"] = _order(spec, prof, dims[0]) if dims else None
        b["top"] = spec.top
        b["click"] = b["dims"][0] if b["dims"] else None
        return b, ""
    x = dims[0]
    time = prof[x].role == "time"
    grain = freq or prof[x].grain or "day"
    xcol = table.dim(x, grain if time else None)
    b["dims"] = [xcol] + ([table.dim(spec.color)] if spec.color else [])
    b["shape"] = "series" if spec.color else "category"
    b["time"] = time
    b["click"] = xcol
    if time:
        b["periods"] = table.periods(xcol)
    b["sort"] = "time" if time else _sort_rule(spec, prof, x, True)
    b["order"] = None if time else _order(spec, prof, x)
    top = spec.top
    if kind == "donut" and top is None:
        top = 7
    b["top"] = top
    b["missing"] = (
        "zero"
        if kind in ("bar", "hbar", "grouped_bar", "stacked_bar", "stacked100_bar")
        else resolve().missing
    )
    b["horizontal"] = kind == "hbar"
    return b, ""


def _sort_rule(spec: Any, prof: Profile, first: str | None, has_measures: bool) -> str:
    sort = spec.sort
    if isinstance(sort, tuple):
        return "order"
    if first is not None and prof[first].role == "time":
        return "time"
    if sort is None and first is not None and prof[first].ordered:
        return "order"
    if sort == "none" or (not has_measures and sort is None):
        return "natural"
    if isinstance(sort, str) and sort.startswith("by:"):
        return "desc"
    return "asc" if sort == "asc" else "desc"


def _order(spec: Any, prof: Profile, first: str) -> list[str] | None:
    if isinstance(spec.sort, tuple):
        return [str(v) for v in spec.sort]
    if prof[first].ordered:
        return [str(v) for v in prof[first].ordered or ()]
    return None
