"""Group-by with exact re-aggregation, date buckets, top N + "Other", and missing periods.

Every result is computed through *parts* (PLAN.md section 5.2): sums and counts for
means, Σ(w·x) and Σw for weighted averages, raw values for medians and distinct counts.
Combining parts again after filtering gives exactly the same numbers as computing from
the raw rows, which is what the browser runtime will rely on. One code path is used for
both, so they cannot drift apart.

The input DataFrame is never changed.
"""

from __future__ import annotations

import dataclasses
import difflib
import math
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any

import numpy as np
import pandas as pd

from tabsight.colors import natural_key
from tabsight.formulas import (
    AGGREGATES,
    CalcField,
    Call,
    evaluate_aggregate,
    evaluate_node,
    validate_params,
)
from tabsight.i18n import text
from tabsight.io import as_frame
from tabsight.profile import AGGS, Profile, _prepare, profile
from tabsight.read import read_dates, read_numbers
from tabsight.settings import resolve
from tabsight.warnings import DataWarning, InvalidSpecError, safe_repr, warn

__all__ = [
    "GRAINS",
    "PARTS",
    "Aggregation",
    "Measure",
    "aggregate",
    "bucket",
    "build_parts",
    "combine_parts",
]

GRAINS = ("year", "quarter", "month", "week", "day", "hour", "minute", "second")
PARTS: dict[str, tuple[str, ...]] = {
    "sum": ("sum",),
    "count": ("count",),
    "mean": ("sum", "count"),
    "min": ("min",),
    "max": ("max",),
    "wavg": ("wsum", "wtotal"),
    "countd": ("values",),
    "median": ("values",),
}
ROWS = "__rows"
OTHER_FLAG = "__other"
SUPPRESSED_FLAG = "__suppressed"
MAX_FILL_ROWS = 1_000_000
MAX_PERIODS = 100_000
_NUMERIC_AGGS = {"sum", "mean", "median", "wavg"}
_ZERO_WHEN_EMPTY = {"sum", "count", "countd"}


@dataclasses.dataclass(frozen=True)
class Measure:
    """One measure: a column (or ``None`` for a row count) and how to aggregate it."""

    column: str | None
    agg: str
    weight: str | None = None
    name: str | None = None

    def __post_init__(self) -> None:
        if self.agg not in PARTS:
            raise InvalidSpecError(f"agg {safe_repr(self.agg)} must be one of {tuple(PARTS)}")
        if self.agg == "wavg" and not self.weight:
            raise InvalidSpecError("agg='wavg' needs weight=<column>")
        if self.column is None and self.agg != "count":
            raise InvalidSpecError("a measure without a column can only count rows")

    @property
    def label(self) -> str:
        if self.name:
            return self.name
        if self.column is None:
            return "Rows"
        return self.column


@dataclasses.dataclass(frozen=True)
class Aggregation:
    """The result of :func:`aggregate`: tidy rows plus what was assumed."""

    frame: pd.DataFrame
    dims: tuple[str, ...]
    measures: tuple[Measure, ...]
    other: Mapping[str, tuple[Any, ...]] = dataclasses.field(default_factory=dict)
    categories: Mapping[str, int] = dataclasses.field(default_factory=dict)
    notes: tuple[str, ...] = ()
    suppressed: int = 0
    outputs: tuple[str, ...] = ()  # measure and calculated-field columns, in the order asked for

    @property
    def values(self) -> pd.DataFrame:
        """Only the dimension and output columns (no internal helper columns)."""
        outputs = self.outputs or tuple(
            m.label for m in self.measures if not m.label.startswith("__")
        )
        return self.frame[[*self.dims, *outputs]]


# ---------------------------------------------------------------- date buckets


def bucket(
    values: pd.Series, grain: str, *, fiscal_start: int = 1, week_start: str = "monday"
) -> pd.Series:
    """Start of the period each date falls in (``2017-02-14`` by month → ``2017-02-01``).

    Fiscal years start in month ``fiscal_start``; quarters follow the fiscal year.
    """
    if grain not in GRAINS:
        raise InvalidSpecError(f"grain must be one of {GRAINS}")
    v = pd.to_datetime(values, errors="coerce")
    if grain in ("year", "quarter"):
        valid = v.notna()
        months = (
            (v.dt.year.fillna(2000).astype("int64") * 12) + v.dt.month.fillna(1).astype("int64") - 1
        )
        offset = (v.dt.month.fillna(1).astype("int64") - fiscal_start) % 12
        months = months - (offset % 3 if grain == "quarter" else offset)
        out = pd.to_datetime(
            pd.DataFrame({"year": months // 12, "month": months % 12 + 1, "day": 1}),
            errors="coerce",
        )
        out = out.where(valid)
        out.index = values.index
        return out
    if grain == "month":
        return v.dt.to_period("M").dt.start_time.where(v.notna())
    if grain == "week":
        shift = {"monday": 0, "sunday": 1, "saturday": 2}[week_start]
        days = (v.dt.day_of_week + shift) % 7
        return v.dt.normalize() - pd.to_timedelta(days, unit="D")
    if grain == "day":
        return v.dt.normalize()
    return v.dt.floor({"hour": "h", "minute": "min", "second": "s"}[grain])


def _period_range(start: pd.Timestamp, end: pd.Timestamp, grain: str) -> pd.DatetimeIndex:
    freq = {
        "year": "12MS", "quarter": "3MS", "month": "MS", "week": "7D",
        "day": "D", "hour": "h", "minute": "min", "second": "s",
    }[grain]  # fmt: skip
    return pd.date_range(start, end, freq=freq)


# ---------------------------------------------------------------- parts


def _part_name(i: int, part: str) -> str:
    return f"__m{i}_{part}"


def build_parts(
    frame: pd.DataFrame, dims: Sequence[str], measures: Sequence[Measure]
) -> pd.DataFrame:
    """Group ``frame`` by ``dims`` and store the re-aggregatable parts of each measure.

    ``frame`` must already hold numeric measure columns (see :func:`aggregate`).
    """
    work = pd.DataFrame(index=frame.index)
    for d in dims:
        work[d] = frame[d]
    for i, m in enumerate(measures):
        if m.column is None:
            continue
        col = frame[m.column]
        if m.agg == "wavg":
            if m.weight is None:  # also rejected by Measure itself
                raise InvalidSpecError("agg='wavg' needs weight=<column>")
            w = pd.to_numeric(frame[m.weight], errors="coerce")
            both = col.notna() & w.notna()
            work[_part_name(i, "wsum")] = (col * w).where(both)
            work[_part_name(i, "wtotal")] = w.where(both)
        else:
            work[_part_name(i, "src")] = col
    work[ROWS] = 1

    if dims:
        grouped = work.groupby(list(dims), dropna=False, sort=False, observed=True)
    else:
        grouped = work.groupby(np.zeros(len(work), dtype=np.int8), sort=False)
    out = pd.DataFrame({ROWS: grouped[ROWS].sum()})
    for i, m in enumerate(measures):
        src = _part_name(i, "src")
        if m.column is None:
            out[_part_name(i, "count")] = out[ROWS]
        elif m.agg == "wavg":
            out[_part_name(i, "wsum")] = grouped[_part_name(i, "wsum")].sum(min_count=1)
            out[_part_name(i, "wtotal")] = grouped[_part_name(i, "wtotal")].sum(min_count=1)
        elif m.agg in ("sum", "mean"):
            out[_part_name(i, "sum")] = grouped[src].sum(min_count=1)
            if m.agg == "mean":
                out[_part_name(i, "count")] = grouped[src].count()
        elif m.agg == "count":
            out[_part_name(i, "count")] = grouped[src].count()
        elif m.agg in ("min", "max"):
            out[_part_name(i, m.agg)] = getattr(grouped[src], m.agg)()
        else:  # countd, median: keep the values themselves
            # pandas-stubs does not model tuple results from agg; behaviour is tested.
            out[_part_name(i, "values")] = grouped[src].agg(  # type: ignore[type-var]
                lambda s: tuple(s.dropna().tolist())
            )
    out = out.reset_index(drop=not dims)
    return out


def combine_parts(
    parts: pd.DataFrame,
    dims: Sequence[str],
    measures: Sequence[Measure],
    min_group_size: int | None = None,
) -> pd.DataFrame:
    """Re-aggregate parts to ``dims`` and compute the final measure values exactly."""
    cols = [c for c in parts.columns if c.startswith("__")]
    if dims:
        grouped = parts.groupby(list(dims), dropna=False, sort=False, observed=True)
    else:
        grouped = parts.groupby(np.zeros(len(parts), dtype=np.int8), sort=False)
    agg: dict[str, Any] = {}
    for c in cols:
        if c.endswith("_min"):
            agg[c] = "min"
        elif c.endswith("_max"):
            agg[c] = "max"
        elif c.endswith("_values"):
            agg[c] = lambda s: tuple(v for t in s for v in t)
        elif c in (OTHER_FLAG, SUPPRESSED_FLAG):
            agg[c] = "max"
        else:
            agg[c] = lambda s: s.sum(min_count=1)
    combined = grouped.agg(agg) if agg else grouped.size().to_frame(ROWS)
    combined = combined.reset_index(drop=not dims)
    for i, m in enumerate(measures):
        combined[m.label] = _finish(combined, i, m)
    if min_group_size is not None:
        small = combined[ROWS].fillna(0) < min_group_size
        for m in measures:
            combined[m.label] = combined[m.label].where(~small)
        combined[SUPPRESSED_FLAG] = small
    return combined


def _finish(frame: pd.DataFrame, i: int, m: Measure) -> pd.Series:
    def part(name: str) -> pd.Series:
        return frame[_part_name(i, name)]

    if m.agg == "sum":
        return part("sum").astype("float64")
    if m.agg == "count":
        return part("count").fillna(0).astype("int64")
    if m.agg == "mean":
        count = part("count").astype("float64")
        return (part("sum").astype("float64") / count).where(count > 0)
    if m.agg in ("min", "max"):
        return part(m.agg)
    if m.agg == "wavg":
        total = part("wtotal").astype("float64")
        return (part("wsum").astype("float64") / total).where(total != 0)
    if m.agg == "countd":
        return part("values").map(lambda t: len(set(t))).astype("int64")
    return part("values").map(lambda t: float(np.median(t)) if len(t) else math.nan)


# ---------------------------------------------------------------- preparing inputs


def _unknown(name: object, names: Iterable[str]) -> InvalidSpecError:
    names = list(names)
    hint = difflib.get_close_matches(str(name)[:200], names, n=1)
    return InvalidSpecError(
        f"column {safe_repr(name)} not found" + (f"; did you mean {hint[0]!r}?" if hint else "")
    )


def _as_measures(measures: Any, prof: Profile) -> list[Measure]:
    if measures is None:
        return []
    if isinstance(measures, str | Measure | Mapping):
        measures = [measures]
    out = []
    for m in measures:
        if isinstance(m, Measure):
            out.append(m)
        elif isinstance(m, str):
            if m not in prof:
                raise _unknown(m, prof.names())
            agg = (
                prof[m].agg
                if prof[m].agg in PARTS
                else ("countd" if prof[m].role == "id" else "count")
            )
            out.append(Measure(m, agg))
        elif isinstance(m, Mapping):
            extra = set(m) - {"column", "agg", "weight", "name"}
            if extra:
                raise InvalidSpecError(f"unknown measure key(s) {sorted(map(safe_repr, extra))}")
            column = m.get("column")
            if column is not None and not isinstance(column, str):
                raise InvalidSpecError("measure 'column' must be a column name")
            agg = m.get("agg") or (
                prof[column].agg if column is not None and column in prof else "count"
            )
            if agg not in AGGS or agg == "none":
                raise InvalidSpecError(f"agg {safe_repr(agg)} is not allowed for a measure")
            out.append(Measure(column, agg, m.get("weight"), m.get("name")))
        else:
            raise InvalidSpecError(f"cannot use {type(m).__name__} as a measure")
    labels = [m.label for m in out]
    if len(set(labels)) != len(labels):
        out = [
            dataclasses.replace(m, name=f"{m.label} ({m.agg})")
            if labels.count(m.label) > 1 and not m.name
            else m
            for m in out
        ]
    return out


def _numeric(col: pd.Series, field_source: str) -> pd.Series:
    if field_source == "text-number":
        reading = read_numbers(col, threshold=0.0)
        if reading is not None:
            return reading.values
    values = pd.to_numeric(col, errors="coerce").astype("float64")
    return values.where(np.isfinite(values))


def _time_values(col: pd.Series, prof: Profile, name: str) -> pd.Series:
    field = prof[name]
    if field.source == "integer-year":
        years = pd.to_numeric(col, errors="coerce")
        return pd.to_datetime(years.astype("Int64").astype("string") + "-01-01", errors="coerce")
    if pd.api.types.is_datetime64_any_dtype(col):
        return col
    reading = read_dates(col, dayfirst=field.dayfirst, threshold=0.0)
    return reading.values if reading is not None else pd.to_datetime(col, errors="coerce")


# ---------------------------------------------------------------- the main entry point


def aggregate(
    data: Any,
    dims: str | Sequence[str] | None = None,
    measures: Any = None,
    *,
    freq: str | Mapping[str, str] | None = None,
    top: int | None = None,
    sort: str | Sequence[str] | None = None,
    missing: str | None = None,
    min_group_size: int | None = None,
    fiscal_start: int | None = None,
    week_start: str | None = None,
    params: Mapping[str, Any] | None = None,
    prof: Profile | None = None,
) -> Aggregation:
    """Group ``data`` by ``dims`` and aggregate ``measures`` exactly.

    - ``measures``: column names (aggregated by their profiled default), ``Measure``
      objects or dicts like ``{"column": "Discount", "agg": "wavg", "weight": "Sales"}``.
    - ``freq``: date grain for time dimensions (``"month"``), or a dict per column.
    - ``top``: keep the top N values of the first dimension; the rest become one
      exact "Other" row whose members are listed in ``result.other``.
    - ``sort``: ``"desc"`` / ``"asc"`` by the first measure, ``"none"`` for natural
      order, ``"by:<measure>"``, or an explicit list of values.
    - ``missing``: missing time periods as ``"gap"`` (NaN), ``"zero"`` or ``"connect"``
      (left out).
    - ``min_group_size``: hide values of groups with fewer rows (privacy).
    - ``measures`` may also hold calculated fields from ``ts.calc(...)``; ``params``
      supplies their ``$Name`` parameter values.
    """
    settings = resolve(
        missing=missing,
        min_group_size=min_group_size,
        fiscal_start=fiscal_start,
        week_start=week_start,
    )
    frame, _ = _prepare(as_frame(data))
    prof = prof if prof is not None else profile(frame, quiet=True)
    dim_list = [dims] if isinstance(dims, str) else list(dims or [])
    for d in dim_list:
        if d not in frame.columns:
            raise _unknown(d, frame.columns)
    if len(set(dim_list)) != len(dim_list):
        raise InvalidSpecError("each dimension can only be used once")
    if measures is None:
        requested: list[Any] = []
    elif isinstance(measures, list | tuple):
        requested = list(measures)
    else:
        requested = [measures]
    calcs = [m for m in requested if isinstance(m, CalcField)]
    measure_list = _as_measures([m for m in requested if not isinstance(m, CalcField)], prof)
    plain = iter(measure_list)
    outputs = [m.name if isinstance(m, CalcField) else next(plain).label for m in requested]
    if len(set(outputs)) != len(outputs):
        raise InvalidSpecError(f"output names must be unique: {outputs}")
    notes: list[str] = []

    # Never add up different currencies: split by the currency column automatically.
    codes = [f.name for f in prof.fields if f.currency_code_column and f.distinct > 1]
    if (
        codes
        and codes[0] not in dim_list
        and any(
            m.column is not None and prof[m.column].unit == "currency" and m.agg in _NUMERIC_AGGS
            for m in measure_list
            if m.column in prof
        )
    ):
        dim_list.append(codes[0])
        note = f"split by {safe_repr(codes[0])} so different currencies are never added together"
        notes.append(note)
        warn(note, DataWarning)

    # Working copy: only the needed columns, read as proper types.
    work: dict[str, pd.Series] = {}
    grains: dict[str, str] = {}
    for d in dim_list:
        col = frame[d]
        if prof[d].role == "time":
            grain = freq.get(d) if isinstance(freq, Mapping) else freq
            grain = grain or prof[d].grain or "day"
            if grain not in GRAINS:
                raise InvalidSpecError(f"freq for {safe_repr(d)} must be one of {GRAINS}")
            grains[d] = grain
            work[d] = bucket(
                _time_values(col, prof, d), grain,
                fiscal_start=settings.fiscal_start, week_start=settings.week_start,
            )  # fmt: skip
        else:
            work[d] = col

    # Calculated fields: row-level ones become a column; each aggregate inside an
    # aggregate formula becomes a hidden exact measure (so filtering stays exact).
    param_values = validate_params(params, [p for c in calcs for p in c.params])
    extra: dict[str, pd.Series] = {}
    agg_calcs: list[tuple[CalcField, dict[Call, str]]] = []
    if calcs:
        used = {f for c in calcs for f in c.fields}
        typed = _typed_frame(frame, prof, used)
        for i, c in enumerate(calcs):
            c.check_fields(list(frame.columns))
            if c.name in frame.columns:
                raise InvalidSpecError(
                    f"calculated field {safe_repr(c.name)} has the same name as a column"
                )
            if c.level == "row":
                extra[c.name] = _calc_numbers(evaluate_node(c.tree, typed, param_values), c.name)
                measure_list.append(Measure(c.name, "sum"))
                continue
            mapping: dict[Call, str] = {}
            for j, call in enumerate(c.aggregates):
                hidden = f"__calc{i}_{j}"
                values = evaluate_node(call.args[0], typed, param_values)
                agg_name = AGGREGATES[call.fn]
                if agg_name not in ("count", "countd"):
                    values = _calc_numbers(values, f"{c.name}: {call.fn}")
                extra[hidden] = values
                measure_list.append(Measure(hidden, agg_name, name=hidden))
                mapping[call] = hidden
            agg_calcs.append((c, mapping))

    def finish(result: pd.DataFrame) -> pd.DataFrame:
        """Evaluate aggregate formulas on combined values (and respect hidden groups)."""
        if not agg_calcs:
            return result
        result = result.copy()
        for c, mapping in agg_calcs:
            values = evaluate_aggregate(
                c, {call: result[h] for call, h in mapping.items()}, param_values
            )
            if SUPPRESSED_FLAG in result:
                values = values.where(~result[SUPPRESSED_FLAG].astype(bool))
            result[c.name] = values
        return result

    for m in measure_list:
        for name in (m.column, m.weight):
            if name is None or name in work:
                continue
            if name in extra:
                work[name] = extra[name]
                continue
            if name not in frame.columns:
                raise _unknown(name, frame.columns)
            field = prof[name]
            if m.agg in _NUMERIC_AGGS or name == m.weight:
                if field.role in ("dimension", "text") and field.source not in ("text-number",):
                    raise InvalidSpecError(
                        f"{safe_repr(name)} is text; use agg='count' or 'countd' instead of {m.agg!r}"
                    )
                if field.role == "id" and m.agg in ("sum", "mean"):
                    warn(
                        f"{safe_repr(name)} looks like an ID; adding up IDs is usually wrong",
                        DataWarning,
                    )
                work[name] = _numeric(frame[name], field.source)
            elif m.agg in ("min", "max") and field.role == "time":
                work[name] = _time_values(frame[name], prof, name)
            elif m.agg in ("min", "max"):
                work[name] = _numeric(frame[name], field.source)
            else:
                work[name] = frame[name]
    working = pd.DataFrame(work, index=frame.index)

    parts = build_parts(working, dim_list, measure_list)
    other: dict[str, tuple[Any, ...]] = {}
    categories: dict[str, int] = {}
    primary = outputs[0] if outputs else None
    if top is not None and dim_list and primary is not None:
        # Top N applies to the first category dimension (never to dates): with
        # [Month, Region] it keeps the top regions across all months.
        top_dim = next((d for d in dim_list if d not in grains), None)
        if top_dim is None:
            notes.append("top N ignored: every dimension is a date")
        else:
            parts, other, categories = _top_n(parts, top_dim, measure_list, top, finish, primary)
    result = finish(combine_parts(parts, dim_list, measure_list, settings.min_group_size))
    suppressed = int(result[SUPPRESSED_FLAG].sum()) if SUPPRESSED_FLAG in result else 0
    if suppressed:
        notes.append(
            f"{suppressed} group(s) hidden: {text('fewer_than', n=settings.min_group_size)} rows"
        )

    time_dims = [d for d in dim_list if d in grains]
    if time_dims and settings.missing != "connect":
        result, fill_note = _fill_periods(
            result, dim_list, time_dims[0], grains[time_dims[0]], measure_list, settings.missing
        )
        if fill_note:
            notes.append(fill_note)
    result = _sort(result, dim_list, primary, outputs, prof, grains, sort)
    return Aggregation(
        frame=result.reset_index(drop=True),
        dims=tuple(dim_list),
        measures=tuple(measure_list),
        other=other,
        categories=categories,
        notes=tuple(notes),
        suppressed=suppressed,
        outputs=tuple(outputs),
    )


def _typed_frame(frame: pd.DataFrame, prof: Profile, names: Iterable[str]) -> pd.DataFrame:
    """Columns used by formulas, read as numbers or dates where the profile says so."""
    cols: dict[str, pd.Series] = {}
    for name in names:
        if name not in frame.columns:
            continue
        field = prof[name]
        if field.role == "time":
            cols[name] = _time_values(frame[name], prof, name)
        elif field.role == "measure" or field.source == "text-number":
            cols[name] = _numeric(frame[name], field.source)
        else:
            cols[name] = frame[name]
    return pd.DataFrame(cols, index=frame.index)


def _calc_numbers(values: pd.Series, what: str) -> pd.Series:
    if pd.api.types.is_bool_dtype(values):
        return values.astype("float64")
    numbers = pd.to_numeric(values, errors="coerce")
    if numbers.notna().sum() < values.notna().sum():
        raise InvalidSpecError(f"{safe_repr(what)} gives text; use COUNT or COUNTD for text")
    numbers = numbers.astype("float64")
    return numbers.where(np.isfinite(numbers))


def _top_n(
    parts: pd.DataFrame,
    dim: str,
    measures: list[Measure],
    n: int,
    finish: Callable[[pd.DataFrame], pd.DataFrame],
    key: str,
) -> tuple[pd.DataFrame, dict[str, tuple[Any, ...]], dict[str, int]]:
    if type(n) is not int or not 1 <= n <= 1000:
        raise InvalidSpecError("top must be an integer 1-1000")
    totals = finish(combine_parts(parts, [dim], measures))
    totals = totals.assign(_k=totals[dim].map(natural_key))
    totals = totals.sort_values([key, "_k"], ascending=[False, True], na_position="last")
    values = totals[dim].tolist()
    count = len(values)
    if count <= n + 1:  # never hide a single value inside "Other"
        return parts, {}, {dim: count}
    keep, rest = values[:n], values[n:]
    label = f"{text('other')} ({len(rest)})"
    parts = parts.copy()
    in_rest = ~parts[dim].isin(keep)
    parts[dim] = parts[dim].astype("object").where(~in_rest, label)
    parts[OTHER_FLAG] = in_rest
    members = tuple(sorted(rest, key=natural_key))
    return parts, {dim: members}, {dim: count}


def _fill_periods(
    result: pd.DataFrame,
    dims: list[str],
    time_dim: str,
    grain: str,
    measures: list[Measure],
    mode: str,
) -> tuple[pd.DataFrame, str | None]:
    times = result[time_dim].dropna()
    if times.empty:
        return result, None
    periods = _period_range(times.min(), times.max(), grain)
    if len(periods) > MAX_PERIODS:
        return result, f"too many {grain}s to fill gaps ({len(periods):,}); gaps left as they are"
    others = [d for d in dims if d != time_dim]
    if others:
        combos = result[others].drop_duplicates()
        if len(combos) * len(periods) > MAX_FILL_ROWS:
            return result, "too many combinations to fill missing periods; gaps left as they are"
        grid = combos.merge(pd.DataFrame({time_dim: periods}), how="cross")
    else:
        grid = pd.DataFrame({time_dim: periods})
    filled = grid.merge(result, on=[*others, time_dim], how="left") if len(grid) else result
    missing_rows = filled[ROWS].isna()
    if mode == "zero":
        for m in measures:
            if m.agg in _ZERO_WHEN_EMPTY:
                filled[m.label] = filled[m.label].where(~missing_rows, 0)
    filled[ROWS] = filled[ROWS].fillna(0).astype("int64")
    added = int(missing_rows.sum())
    return filled, (
        f"{added} empty {grain}(s) shown as {'0' if mode == 'zero' else 'gaps'}" if added else None
    )


def _sort(
    result: pd.DataFrame,
    dims: list[str],
    primary: str | None,
    outputs: Sequence[str],
    prof: Profile,
    grains: Mapping[str, str],
    sort: str | Sequence[str] | None,
) -> pd.DataFrame:
    if not dims:
        return result
    keys: list[str] = []
    asc: list[bool] = []
    work = result.copy()
    if OTHER_FLAG in work:
        work["_other"] = work[OTHER_FLAG].fillna(False).astype(bool)
        keys.append("_other")
        asc.append(True)  # "Other" always last
    first = dims[0]
    if isinstance(sort, list | tuple):
        order = {v: i for i, v in enumerate(sort)}
        work["_s"] = work[first].map(lambda v: order.get(v, len(order)))
        keys.append("_s")
        asc.append(True)
    elif first in grains or (sort is None and prof[first].ordered) or sort == "none":
        if first in grains:
            work["_s"] = work[first]
        elif prof[first].ordered:
            order = {v: i for i, v in enumerate(prof[first].ordered or ())}
            work["_s"] = work[first].map(lambda v: order.get(str(v), len(order)))
        else:
            work["_s"] = work[first].map(natural_key)
        keys.append("_s")
        asc.append(True)
    elif primary is not None:
        by = primary
        if isinstance(sort, str) and sort.startswith("by:"):
            by = sort[3:]
            if by not in outputs:
                raise _unknown(by, outputs)
        totals = work.groupby(first, dropna=False, sort=False)[by].transform("sum")
        work["_s"] = totals
        keys.append("_s")
        asc.append(sort == "asc")
    work["_n"] = work[first].map(natural_key)
    keys.append("_n")
    asc.append(True)
    for d in dims[1:]:
        col = f"_d_{d}"
        work[col] = work[d] if d in grains else work[d].map(natural_key)
        keys.append(col)
        asc.append(True)
    work = work.sort_values(keys, ascending=asc, kind="mergesort", na_position="last")
    return work.drop(
        columns=[c for c in work.columns if c.startswith("_") and not c.startswith("__")]
    )
