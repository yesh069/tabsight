"""``ts.clean(df)``: optional cleaning that lists every change and can undo it.

Modes:

- ``"off"``: changes nothing; everything is listed as a suggestion.
- ``"safe"`` (default for ``ts.clean``): only fixes that cannot change meaning.
- ``"auto"``: also applies the suggestions.

The input DataFrame is never modified. Decisions can be saved (``report.to_dict()``) and
re-applied to next month's data with ``ts.clean(new_df, decisions=saved)``.
"""

from __future__ import annotations

import dataclasses
import json
import re
from collections.abc import Callable, Mapping
from typing import Any

import pandas as pd

from tabsight.check import PLACEHOLDERS, CheckReport, check
from tabsight.io import as_frame
from tabsight.profile import _prepare, profile, tokens
from tabsight.read import read_dates, read_numbers
from tabsight.warnings import CleanWarning, InvalidSpecError, safe_repr, warn

__all__ = ["Change", "CleanReport", "Suggestion", "clean"]

MODES = ("off", "safe", "auto")
DECISIONS_VERSION = 1
_MAX_MAPPING = 10_000
_DATE_FORMAT_RE = re.compile(r"(%[YymdbBHMSf]|[ ./:T-])+")


@dataclasses.dataclass(frozen=True)
class Change:
    column: str | None
    action: str
    count: int
    detail: str


@dataclasses.dataclass(frozen=True)
class Suggestion:
    id: str
    column: str | None
    action: str
    detail: str
    params: dict[str, Any] = dataclasses.field(default_factory=dict)


# ---------------------------------------------------------------- actions
# Each action takes a column and params and returns (new column, number of values changed).


def _placeholders(col: pd.Series, params: Mapping[str, Any]) -> tuple[pd.Series, int]:
    text = col.astype("string")
    mask = col.notna() & text.str.strip().str.lower().isin(PLACEHOLDERS)
    return col.mask(mask), int(mask.sum())


def _trim(col: pd.Series, params: Mapping[str, Any]) -> tuple[pd.Series, int]:
    is_str = col.map(lambda v: isinstance(v, str))
    stripped = col.where(~is_str, col[is_str].str.strip() if is_str.any() else col)
    changed = int((is_str & (stripped != col)).sum())
    return stripped, changed


def _merge_case(col: pd.Series, params: Mapping[str, Any]) -> tuple[pd.Series, int]:
    mapping = params["mapping"]
    new = col.map(lambda v: mapping.get(v, v) if isinstance(v, str) else v)
    return new, int((new != col).fillna(False).sum())


def _parse_numbers(col: pd.Series, params: Mapping[str, Any]) -> tuple[pd.Series, int]:
    reading = read_numbers(col, threshold=0.0)
    if reading is None:
        return col, 0
    return reading.values, int(col.notna().sum())


def _parse_dates(col: pd.Series, params: Mapping[str, Any]) -> tuple[pd.Series, int]:
    fmt = params["format"]
    reading = read_dates(col, dayfirst=fmt.startswith("%d"), threshold=0.0)
    if reading is not None and reading.format == fmt:
        parsed = reading.values
    else:  # saved format from another file layout: apply it directly
        text = col.astype("string").str.strip()
        normal = text.str.replace(r"(?<=\d)[-.](?=\d)", "/", regex=True) if "/" in fmt else text
        parsed = pd.to_datetime(normal, format=fmt, errors="coerce")
    return parsed, int(parsed.notna().sum())


def _excel_serial(col: pd.Series, params: Mapping[str, Any]) -> tuple[pd.Series, int]:
    days = pd.to_numeric(col, errors="coerce")
    parsed = pd.Timestamp("1899-12-30") + pd.to_timedelta(days, unit="D")
    return parsed, int(days.notna().sum())


_ACTIONS: dict[str, Callable[[pd.Series, Mapping[str, Any]], tuple[pd.Series, int]]] = {
    "placeholders_to_missing": _placeholders,
    "trim": _trim,
    "merge_case": _merge_case,
    "parse_numbers": _parse_numbers,
    "parse_dates": _parse_dates,
    "excel_serial_dates": _excel_serial,
}
_ORDER = [*list(_ACTIONS), "dedupe"]


def _validate_params(action: str, params: Mapping[str, Any]) -> dict[str, Any]:
    if action not in _ACTIONS and action != "dedupe":
        raise InvalidSpecError(f"unknown cleaning action {safe_repr(action)}")
    if action == "parse_dates":
        fmt = params.get("format")
        if not (isinstance(fmt, str) and len(fmt) <= 40 and _DATE_FORMAT_RE.fullmatch(fmt)):
            raise InvalidSpecError(
                f"parse_dates format {safe_repr(fmt)} is not a simple strptime format"
            )
        return {"format": fmt}
    if action == "merge_case":
        mapping = params.get("mapping")
        if (
            not isinstance(mapping, Mapping)
            or len(mapping) > _MAX_MAPPING
            or not all(isinstance(k, str) and isinstance(v, str) and len(k) <= 500 and len(v) <= 500
                       for k, v in mapping.items())
        ):  # fmt: skip
            raise InvalidSpecError(
                "merge_case mapping must map up to 10,000 short strings to strings"
            )
        return {"mapping": dict(mapping)}
    return {}


# ---------------------------------------------------------------- report


class CleanReport:
    """What cleaning did and suggests. Methods return a new DataFrame each time."""

    def __init__(self, original: pd.DataFrame, mode: str, check_report: CheckReport) -> None:
        self.mode = mode
        self.applied: list[Change] = []
        self.suggestions: list[Suggestion] = []
        self.check = check_report
        self._original = original
        self._columns: dict[str, pd.Series] = {}
        self._decisions: list[dict[str, Any]] = []
        self._dedupe = False
        self._current = original

    @property
    def data(self) -> pd.DataFrame:
        return self._current

    def show(self) -> str:
        lines = [
            f"Clean report (mode={self.mode!r}). Quality score before cleaning: {self.check.score}/100"
        ]
        lines += ["", "Applied:"] + (
            [
                f"  - [{c.column}] {c.detail} ({c.count:,} values)"
                if c.column
                else f"  - {c.detail}"
                for c in self.applied
            ]
            or ["  (nothing)"]
        )
        lines += ["", "Suggested (not applied; use report.apply(id) or mode='auto'):"] + (
            [f"  - {s.id}: [{s.column}] {s.detail}" for s in self.suggestions] or ["  (nothing)"]
        )
        reported = [i for i in self.check.issues if i.code in _REPORT_ONLY]
        if reported:
            lines += ["", "Reported only:"] + [
                f"  - [{i.column}] {i.message}" if i.column else f"  - {i.message}"
                for i in reported
            ]
        return "\n".join(lines)

    def __str__(self) -> str:
        return self.show()

    def apply(self, target: str) -> pd.DataFrame:
        """Apply one suggestion by id, or every suggestion for a column."""
        chosen = [s for s in self.suggestions if target in (s.id, s.column)]
        if not chosen:
            raise KeyError(f"no suggestion {safe_repr(target)}; see report.suggestions")
        for s in chosen:
            self._run(s.column, s.action, s.params, s.detail)
            self.suggestions.remove(s)
        self._rebuild()
        return self._current

    def undo(self, column: str) -> pd.DataFrame:
        """Restore one column's original values."""
        if column not in self._columns:
            raise KeyError(f"column {safe_repr(column)} was not changed")
        del self._columns[column]
        self.applied = [c for c in self.applied if c.column != column]
        self._decisions = [d for d in self._decisions if d.get("column") != column]
        self._rebuild()
        return self._current

    def to_dict(self) -> dict[str, Any]:
        """The applied decisions, to reuse with ``ts.clean(new_df, decisions=...)``."""
        return {"tabsight_clean": DECISIONS_VERSION, "actions": [dict(d) for d in self._decisions]}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    # internal

    def _base(self, column: str) -> pd.Series:
        return self._columns.get(column, self._original[column])

    def _run(self, column: str | None, action: str, params: Mapping[str, Any], detail: str) -> None:
        if action == "dedupe":
            self._dedupe = True
            self._decisions.append({"action": "dedupe"})
            self.applied.append(Change(None, "dedupe", 0, detail))
            return
        if column is None:
            return
        new, count = _ACTIONS[action](self._base(column), params)
        self._columns[column] = new
        self._decisions.append({"action": action, "column": column, **params})
        self.applied.append(Change(column, action, count, detail))

    def _rebuild(self) -> None:
        if not self._columns and not self._dedupe:
            self._current = self._original.copy()
            return
        data = {
            name: self._columns.get(name, self._original[name]) for name in self._original.columns
        }
        frame = pd.DataFrame(data, index=self._original.index)
        if self._dedupe:
            before = len(frame)
            frame = frame.drop_duplicates()
            self.applied = [c if c.action != "dedupe" else dataclasses.replace(c, count=before - len(frame))
                            for c in self.applied]  # fmt: skip
        self._current = frame


_REPORT_ONLY = {"possible_typos", "outliers", "duplicate_rows", "unparsed_dates", "unparsed_numbers",
                "suspicious_dates", "future_dates", "date_order", "mixed_types", "infinite"}  # fmt: skip


# ---------------------------------------------------------------- planning


def clean(
    data: Any,
    mode: str = "safe",
    *,
    dedupe: bool = False,
    dayfirst: bool | None = None,
    decisions: Any = None,
) -> tuple[pd.DataFrame, CleanReport]:
    """Return a cleaned copy and a report. The input is never changed."""
    if mode not in MODES:
        raise InvalidSpecError(f"mode must be one of {MODES}, not {safe_repr(mode)}")
    frame, _ = _prepare(as_frame(data))
    report = CleanReport(frame, mode, check(frame))

    if decisions is not None:
        for step in _parse_decisions(decisions):
            column = step.get("column")
            if column is not None and column not in frame.columns:
                warn(
                    f"saved cleaning step for missing column {safe_repr(column)} skipped",
                    CleanWarning,
                )
                continue
            params = {k: v for k, v in step.items() if k not in ("action", "column")}
            report._run(column, step["action"], params, f"re-applied saved step {step['action']}")
        report._rebuild()
        return report.data, report

    planned = _plan(frame, dayfirst, dedupe)
    counter = 0
    for safe, column, action, params, detail in sorted(planned, key=lambda p: _ORDER.index(p[2])):
        if mode == "auto" or (mode == "safe" and safe):
            report._run(column, action, params, detail)
        else:
            counter += 1
            report.suggestions.append(Suggestion(f"s{counter}", column, action, detail, params))
    report._rebuild()
    return report.data, report


def _plan(
    frame: pd.DataFrame, dayfirst: bool | None, dedupe: bool
) -> list[tuple[bool, str | None, str, dict[str, Any], str]]:
    """List every possible fix as (safe?, column, action, params, description)."""
    plan: list[tuple[bool, str | None, str, dict[str, Any], str]] = []
    prof = profile(frame, quiet=True, dayfirst=dayfirst)
    for field in prof.fields:
        name = field.name
        col = frame[name]
        if not (pd.api.types.is_object_dtype(col) or pd.api.types.is_string_dtype(col)):
            if (
                pd.api.types.is_numeric_dtype(col)
                and tokens(name) & {"date", "day", "dt"}
                and col.dropna().between(20_000, 60_000).all()
                and len(col.dropna())
            ):
                plan.append((False, name, "excel_serial_dates", {},
                             "numbers look like Excel serial dates; convert to dates"))  # fmt: skip
            continue
        text = col.dropna().astype(str)
        if text.str.strip().str.lower().isin(PLACEHOLDERS).any():
            plan.append(
                (
                    True,
                    name,
                    "placeholders_to_missing",
                    {},
                    "placeholder values (N/A, -, null...) set to missing",
                )
            )
        if (text != text.str.strip()).any():
            plan.append((True, name, "trim", {}, "removed extra spaces at the start/end"))
        mapping = _case_mapping(text.str.strip())
        if mapping:
            sample = ", ".join(
                f"{safe_repr(k, 20)} -> {safe_repr(v, 20)}" for k, v in list(mapping.items())[:3]
            )
            plan.append((False, name, "merge_case", {"mapping": mapping},
                         f"merge {len(mapping)} spelling variant(s) into the most common spelling ({sample})"))  # fmt: skip
        if field.source == "text-number":
            reading = read_numbers(col)
            if reading is not None:
                full = reading.success == 1.0
                plan.append((full and reading.decimal == ".", name, "parse_numbers", {},
                             f"convert text to numbers ({reading.unit}, decimal {reading.decimal!r})"))  # fmt: skip
        if field.source == "text-date" and field.date_format:
            reading_d = read_dates(col, dayfirst=dayfirst)
            if reading_d is not None:
                proven = not reading_d.assumed or dayfirst is not None
                full = reading_d.success == 1.0
                how = (
                    "order proven by the data"
                    if not reading_d.assumed
                    else (
                        "order from dayfirst="
                        if dayfirst is not None
                        else "order assumed month-first"
                    )
                )
                plan.append((proven and full, name, "parse_dates", {"format": field.date_format},
                             f"convert text to dates ({field.date_format}, {how})"))  # fmt: skip
    if dedupe:
        dupes = int(frame.duplicated().sum())
        if dupes:
            plan.append(
                (True, None, "dedupe", {}, f"dropped {dupes:,} exact duplicate rows (dedupe=True)")
            )
    return plan


def _case_mapping(text: pd.Series) -> dict[str, str]:
    counts = text.value_counts()
    if len(counts) > 50_000:
        return {}
    mapping: dict[str, str] = {}
    groups: dict[str, list[str]] = {}
    for value in counts.index:
        groups.setdefault(value.lower(), []).append(value)
    for variants in groups.values():
        if len(variants) < 2:
            continue
        best = sorted(variants, key=lambda v: (-counts[v], v))[0]
        for v in variants:
            if v != best:
                mapping[v] = best
        if len(mapping) > _MAX_MAPPING:
            return {}
    return mapping


def _parse_decisions(decisions: Any) -> list[dict[str, Any]]:
    if isinstance(decisions, str):
        if len(decisions) > 20_000_000:
            raise InvalidSpecError("saved decisions are too large")
        decisions = json.loads(decisions)
    if not isinstance(decisions, Mapping) or decisions.get("tabsight_clean") != DECISIONS_VERSION:
        raise InvalidSpecError("not saved tabsight cleaning decisions")
    if set(decisions) - {"tabsight_clean", "actions"}:
        raise InvalidSpecError("unknown keys in saved cleaning decisions")
    actions = decisions.get("actions")
    if not isinstance(actions, list) or len(actions) > 10_000:
        raise InvalidSpecError("'actions' must be a list of at most 10,000 steps")
    steps = []
    for step in actions:
        if not isinstance(step, Mapping) or not isinstance(step.get("action"), str):
            raise InvalidSpecError("each step needs an 'action'")
        column = step.get("column")
        if column is not None and not (isinstance(column, str) and len(column) <= 200):
            raise InvalidSpecError("step 'column' must be a short string")
        extra = set(step) - {"action", "column", "format", "mapping"}
        if extra:
            raise InvalidSpecError(f"unknown step key(s) {sorted(map(safe_repr, extra))}")
        params = _validate_params(step["action"], step)
        steps.append({"action": step["action"], "column": column, **params})
    return steps
