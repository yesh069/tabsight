"""Table calculations, computed after aggregation (and after filters), as in Tableau.

``running_total``, ``pct_of_total``, ``rank``, ``difference``, ``pct_difference`` and
``moving_avg:N``. They run *along* one dimension (time by default) and restart for
each combination of the other dimensions.

``pct_of_total`` uses the total of the rows given (the filtered total). Pass
``fixed_total=`` to divide by an overall total instead; the label says which was used.
"""

from __future__ import annotations

import dataclasses
import re

import numpy as np
import pandas as pd

from tabsight.aggregate import Aggregation
from tabsight.spec import CALCS
from tabsight.warnings import DataWarning, InvalidSpecError, safe_repr, warn

__all__ = ["CALC_LABELS", "table_calc"]

_MOVING = re.compile(r"moving_avg:(\d{1,3})")
CALC_LABELS = {
    "running_total": "running total",
    "pct_of_total": "% of total",
    "rank": "rank",
    "difference": "difference",
    "pct_difference": "% difference",
}
_ADDITIVE_ONLY = {"running_total", "pct_of_total"}


def _parse(calc: str) -> tuple[str, int | None]:
    if calc in CALCS:
        return calc, None
    m = _MOVING.fullmatch(calc) if isinstance(calc, str) else None
    if m and 2 <= int(m.group(1)) <= 365:
        return "moving_avg", int(m.group(1))
    raise InvalidSpecError(
        f"calc {safe_repr(calc)} must be one of {CALCS} or 'moving_avg:N' (N 2-365)"
    )


def table_calc(
    result: Aggregation,
    calc: str,
    *,
    measure: str | None = None,
    along: str | None = None,
    fixed_total: float | None = None,
    name: str | None = None,
) -> Aggregation:
    """Return a new Aggregation with one extra column holding the table calculation."""
    kind, window = _parse(calc)
    labels = [m.label for m in result.measures]
    measure = measure or (labels[0] if labels else None)
    if measure not in labels:
        raise InvalidSpecError(
            f"measure {safe_repr(measure)} is not in this result; choose from {labels}"
        )
    agg = next(m.agg for m in result.measures if m.label == measure)
    if kind in _ADDITIVE_ONLY and agg not in ("sum", "count", "countd"):
        warn(
            f"{CALC_LABELS[kind]} of an {agg} ({safe_repr(measure)}) is usually not meaningful; "
            "consider a sum or a weighted average",
            DataWarning,
        )
    dims = list(result.dims)
    if along is None:
        time_dims = [d for d in dims if pd.api.types.is_datetime64_any_dtype(result.frame[d])]
        along = time_dims[0] if time_dims else (dims[0] if dims else None)
    if along is not None and along not in dims:
        raise InvalidSpecError(f"along={safe_repr(along)} must be one of the dimensions {dims}")
    partition = [d for d in dims if d != along]

    frame = result.frame
    values = pd.to_numeric(frame[measure], errors="coerce").astype("float64")
    if along is not None and pd.api.types.is_datetime64_any_dtype(frame[along]):
        order = frame[along].rank(method="first").to_numpy()
    else:
        order = np.arange(len(frame), dtype="float64")  # keep the result's existing order
    work = pd.DataFrame({"v": values, "_o": order}, index=frame.index)
    groups = [frame[d].astype("object").fillna("\x00missing") for d in partition]
    work = work.sort_values("_o", kind="mergesort")
    v = work["v"]
    # One group for everything when there is nothing to restart on.
    keys = [g.loc[work.index] for g in groups] or [pd.Series(0, index=work.index)]
    by = v.groupby(keys, sort=False)

    if kind == "running_total":
        out = v.fillna(0).groupby(keys, sort=False).cumsum()
    elif kind == "pct_of_total":
        total = (
            pd.Series(float(fixed_total), index=v.index)
            if fixed_total is not None
            else by.transform("sum")
        )
        out = (v / total).where(total != 0)
    elif kind == "rank":
        out = by.rank(ascending=False, method="min")
    elif kind in ("difference", "pct_difference"):
        prev = by.shift(1)
        out = v - prev if kind == "difference" else ((v - prev) / prev.abs()).where(prev != 0)
    else:
        if window is None:  # _parse always sets it for moving averages
            raise InvalidSpecError("moving_avg needs a window")
        out = by.transform(lambda s: s.rolling(window, min_periods=1).mean())
    out = out.reindex(frame.index)

    suffix = f"moving avg {window}" if kind == "moving_avg" else CALC_LABELS[kind]
    if kind == "pct_of_total":
        suffix += " (fixed)" if fixed_total is not None else " (of shown rows)"
    column = name or f"{measure} ({suffix})"
    new_frame = frame.copy()
    new_frame[column] = out.astype("Int64") if kind == "rank" else out
    note = f"{column}: computed along {along!r}" + (
        f", restarting for each {', '.join(partition)}" if partition else ""
    )
    return dataclasses.replace(result, frame=new_frame, notes=(*result.notes, note))
