"""``ts.check(df)``: a data-quality report that changes nothing.

All work is bounded: distinct-value comparisons are capped, and examples in messages are
shortened with ``safe_repr``. "Future dates" are only checked against an explicit
``as_of`` date, because library code never reads the clock.
"""

from __future__ import annotations

import dataclasses
import difflib
from collections.abc import Iterable
from typing import Any

import numpy as np
import pandas as pd

from tabsight.io import as_frame
from tabsight.profile import Profile, _prepare, profile, tokens
from tabsight.read import read_dates, read_numbers
from tabsight.warnings import safe_repr

__all__ = ["CheckReport", "Issue", "check"]

PLACEHOLDERS = frozenset(
    {"n/a", "na", "-", "--", "null", "none", "nan", "?", "", "#n/a", "missing", "unknown"}
)
MAX_DISTINCT_COMPARE = 300
_PENALTY = {"error": 15, "warning": 5, "info": 1}
_DATE_PAIRS = (
    ({"order"}, {"ship", "shipped", "delivery", "delivered"}),
    (
        {"start", "begin", "from", "open", "opened", "created"},
        {"end", "finish", "to", "close", "closed", "resolved"},
    ),
)


@dataclasses.dataclass(frozen=True)
class Issue:
    severity: str  # "error", "warning" or "info"
    code: str
    column: str | None
    message: str
    count: int = 0
    examples: tuple[str, ...] = ()


@dataclasses.dataclass(frozen=True)
class CheckReport:
    rows: int
    columns: int
    issues: tuple[Issue, ...]

    @property
    def score(self) -> int:
        """Data quality score out of 100 (100 = no issues found)."""
        penalty = sum(_PENALTY[i.severity] for i in self.issues)
        return max(0, 100 - penalty)

    def for_column(self, column: str) -> list[Issue]:
        return [i for i in self.issues if i.column == column]

    def show(self) -> str:
        lines = [
            f"Data check: {self.rows:,} rows, {self.columns} columns. Quality score {self.score}/100"
        ]
        for severity in ("error", "warning", "info"):
            group = [i for i in self.issues if i.severity == severity]
            if group:
                lines += ["", severity.capitalize() + "s:"]
                for i in group:
                    where = f"[{i.column}] " if i.column is not None else ""
                    ex = f"  e.g. {', '.join(i.examples)}" if i.examples else ""
                    lines.append(f"  - {where}{i.message}{ex}")
        if not self.issues:
            lines.append("No issues found.")
        return "\n".join(lines)

    def __str__(self) -> str:
        return self.show()

    def to_dict(self) -> dict[str, Any]:
        return {
            "rows": self.rows,
            "columns": self.columns,
            "score": self.score,
            "issues": [dataclasses.asdict(i) for i in self.issues],
        }


def _examples(values: Iterable[Any], n: int = 3) -> tuple[str, ...]:
    return tuple(safe_repr(v, 40) for v in list(values)[:n])


def check(
    data: Any,
    *,
    prof: Profile | None = None,
    as_of: str | pd.Timestamp | None = None,
) -> CheckReport:
    """Report data-quality issues. Nothing is changed."""
    frame, notes = _prepare(as_frame(data))
    issues: list[Issue] = []
    if frame.empty:
        issues.append(Issue("error", "empty", None, "the data has no rows or no columns"))
        return CheckReport(len(frame), len(frame.columns), tuple(issues))
    prof = prof if prof is not None else profile(frame, quiet=True)
    issues += [Issue("info", "note", None, n) for n in notes + list(prof.notes)]
    as_of_ts = pd.Timestamp(as_of) if as_of is not None else None

    for field in prof.fields:
        col = frame[field.name]
        issues += _column_issues(field.name, col, field.role, field.unit, field.source, as_of_ts)
    issues += _date_order_issues(frame, prof)

    dupes = int(frame.duplicated().sum())
    if dupes:
        issues.append(
            Issue(
                "warning",
                "duplicate_rows",
                None,
                f"{dupes:,} exact duplicate rows (kept; use dedupe=True to drop)",
                dupes,
            )
        )
    order = {"error": 0, "warning": 1, "info": 2}
    issues.sort(key=lambda i: (order[i.severity], i.column or "", i.code))
    return CheckReport(len(frame), len(frame.columns), tuple(issues))


def _column_issues(
    name: str, col: pd.Series, role: str, unit: str, source: str, as_of: pd.Timestamp | None
) -> list[Issue]:
    out: list[Issue] = []
    n = len(col)
    missing = int(col.isna().sum())
    if missing == n:
        return [Issue("warning", "all_missing", name, "every value is missing", missing)]
    if missing:
        out.append(
            Issue(
                "info", "missing", name, f"{missing:,} missing values ({missing / n:.1%})", missing
            )
        )
    non_null = col.dropna()
    if non_null.nunique() == 1 and n > 1:
        out.append(Issue("info", "no_variation", name, "every value is the same", n))

    if pd.api.types.is_numeric_dtype(col) and not pd.api.types.is_bool_dtype(col):
        values = pd.to_numeric(non_null, errors="coerce").astype("float64")
        inf = int(np.isinf(values).sum())
        if inf:
            out.append(
                Issue(
                    "warning",
                    "infinite",
                    name,
                    f"{inf:,} infinite values (treated as missing)",
                    inf,
                )
            )
        finite = values[np.isfinite(values)]
        if role == "measure" and len(finite) >= 20:
            q1, q3 = finite.quantile([0.25, 0.75])
            fence = 3 * (q3 - q1)
            if fence > 0:
                outliers = finite[(finite < q1 - fence) | (finite > q3 + fence)]
                if len(outliers):
                    out.append(
                        Issue("info", "outliers", name, f"{len(outliers):,} unusually large or small values (flagged, not removed)",
                              len(outliers), _examples(outliers.sort_values(ascending=False)))
                    )  # fmt: skip
            if unit == "count" and (finite < 0).any():
                neg = int((finite < 0).sum())
                out.append(
                    Issue(
                        "info",
                        "negative_counts",
                        name,
                        f"{neg:,} negative values in a count (returns?)",
                        neg,
                    )
                )
        return out

    if pd.api.types.is_datetime64_any_dtype(col):
        out += _date_value_issues(name, non_null, as_of)
        return out

    if not (pd.api.types.is_object_dtype(col) or pd.api.types.is_string_dtype(col)):
        return out

    kinds = non_null.map(lambda v: type(v).__name__)
    if kinds.nunique() > 1:
        counts = kinds.value_counts()
        out.append(
            Issue("warning", "mixed_types", name, "mixed value types: " + ", ".join(f"{k} ({v})" for k, v in counts.items()),
                  int(counts.iloc[1:].sum()))
        )  # fmt: skip
    text = non_null.astype(str)
    placeholder = text.str.strip().str.lower().isin(PLACEHOLDERS)
    if placeholder.any():
        out.append(
            Issue("warning", "placeholders", name, f"{int(placeholder.sum()):,} placeholder values that mean 'missing'",
                  int(placeholder.sum()), _examples(text[placeholder].unique()))
        )  # fmt: skip
    untrimmed = text != text.str.strip()
    if untrimmed.any():
        out.append(
            Issue("warning", "untrimmed", name, f"{int(untrimmed.sum()):,} values with extra spaces at the start or end",
                  int(untrimmed.sum()), _examples(text[untrimmed].unique()))
        )  # fmt: skip
    out += _spelling_issues(name, text[~placeholder])

    if source == "text-date":
        reading = read_dates(col)
        if reading is not None:
            failed = int(reading.values.isna().sum() - col.isna().sum())
            if failed > 0:
                out.append(Issue("warning", "unparsed_dates", name, f"{failed:,} values could not be read as dates",
                                 failed, reading.failed_examples))  # fmt: skip
            out += _date_value_issues(name, reading.values.dropna(), as_of)
    elif source == "text-number":
        reading_n = read_numbers(col)
        if reading_n is not None:
            out.append(Issue("info", "numbers_as_text", name, f"numbers stored as text ({reading_n.unit})",
                             len(non_null), _examples(text.head(3))))  # fmt: skip
            failed = int(reading_n.values.isna().sum() - col.isna().sum())
            if failed > 0:
                out.append(Issue("warning", "unparsed_numbers", name, f"{failed:,} values could not be read as numbers",
                                 failed, reading_n.failed_examples))  # fmt: skip
    return out


def _spelling_issues(name: str, text: pd.Series) -> list[Issue]:
    out: list[Issue] = []
    counts = text.str.strip().value_counts()
    if counts.empty or len(counts) > 5_000:
        return out
    lowered = counts.groupby(counts.index.str.lower()).agg(lambda s: list(s.index))
    variants = [v for v in lowered if len(v) > 1]
    if variants:
        n = sum(len(v) for v in variants)
        out.append(
            Issue("warning", "case_variants", name, f"{len(variants)} value(s) spelled with different capitals",
                  n, _examples(" / ".join(v[:3]) for v in variants))
        )  # fmt: skip
    if len(counts) <= MAX_DISTINCT_COMPARE:
        words = [w for w in counts.index if len(w) >= 4]
        pairs = []
        seen: set[frozenset[str]] = set()
        for w in words:
            for m in difflib.get_close_matches(w, words, n=3, cutoff=0.8):
                key = frozenset((w, m))
                if m == w or w.lower() == m.lower() or key in seen:
                    continue
                seen.add(key)
                rare, common = sorted((w, m), key=lambda x: counts[x])
                if counts[rare] <= max(1, 0.05 * counts[common]):
                    pairs.append(f"{safe_repr(rare, 30)} -> {safe_repr(common, 30)}?")
        if pairs:
            out.append(
                Issue(
                    "info",
                    "possible_typos",
                    name,
                    f"{len(pairs)} possible typo(s)",
                    len(pairs),
                    tuple(pairs[:3]),
                )
            )
    return out


def _date_value_issues(name: str, values: pd.Series, as_of: pd.Timestamp | None) -> list[Issue]:
    out = []
    old = values[values < pd.Timestamp("1901-01-01")]
    if len(old):
        out.append(Issue("warning", "suspicious_dates", name, f"{len(old):,} dates before 1901 (often a placeholder)",
                         len(old), _examples(old.dt.date)))  # fmt: skip
    if as_of is not None:
        future = values[values > as_of]
        if len(future):
            out.append(Issue("warning", "future_dates", name, f"{len(future):,} dates after {as_of.date()}",
                             len(future), _examples(future.dt.date)))  # fmt: skip
    return out


def _date_order_issues(frame: pd.DataFrame, prof: Profile) -> list[Issue]:
    times = [f for f in prof.fields if f.role == "time" and f.grain != "year"]
    out = []
    for first_words, second_words in _DATE_PAIRS:
        firsts = [f for f in times if tokens(f.name) & first_words]
        seconds = [f for f in times if tokens(f.name) & second_words]
        for a in firsts:
            for b in seconds:
                if a.name == b.name:
                    continue
                da, db = _as_dates(frame[a.name], a.dayfirst), _as_dates(frame[b.name], b.dayfirst)
                bad = int((db < da).sum())
                if bad:
                    out.append(
                        Issue(
                            "warning",
                            "date_order",
                            b.name,
                            f"{bad:,} rows where {safe_repr(b.name)} is before {safe_repr(a.name)}",
                            bad,
                        )
                    )
    return out


def _as_dates(col: pd.Series, dayfirst: bool | None) -> pd.Series:
    reading = read_dates(col, dayfirst=dayfirst)
    return reading.values if reading is not None else pd.Series(pd.NaT, index=col.index)
