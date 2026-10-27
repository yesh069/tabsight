"""``fig.lint()``: check a finished chart against the rules of good chart design.

tabsight's defaults already follow these rules, so a chart built with defaults is
usually clean. The linter earns its keep when a choice was forced (``kind="donut"`` with
``top=12``, ``agg="sum"`` on a percentage) or the ECharts option was patched with
``fig.update()`` (smoothed lines, an axis that doesn't start at zero).

Each issue has a stable code, a severity (``warning`` or ``info``), a message, a fix in
plain English and, where one exists, the ``ts.chart`` arguments that apply the fix.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable, Iterator, Mapping
from typing import TYPE_CHECKING, Any

from tabsight.warnings import ChartLintError, InvalidSpecError, safe_repr

if TYPE_CHECKING:
    from tabsight.figure import Figure

__all__ = ["RULES", "LintIssue", "LintReport", "lint"]

# code: (severity, what the rule checks)
RULES: dict[str, tuple[str, str]] = {
    "pie_too_many_slices": ("warning", "a donut with more than 8 slices"),
    "pie_not_additive": ("warning", "a donut of averages or distinct counts, which don't add up to a whole"),
    "stacked_not_additive": ("warning", "stacked bars or areas of values that don't add up"),
    "stacked_with_negatives": ("warning", "stacked bars or areas with negative values"),
    "too_many_colors": ("warning", "more than 10 colours in one chart"),
    "too_many_lines": ("info", "more than 8 lines in one chart"),
    "smoothed_line": ("warning", "a smoothed line, which invents values between data points"),
    "bar_axis_not_zero": ("warning", "a bar chart whose value axis doesn't start at zero"),
    "labels_skipped": ("warning", "category labels hidden to save space"),
    "sum_of_rates": ("warning", "percentages, rates or averages added up"),
    "sum_of_ids": ("warning", "ID or code numbers added up"),
    "line_for_categories": ("warning", "a line drawn across unordered categories"),
    "single_category": ("info", "a bar chart with only one bar"),
    "incomplete_last_period": ("info", "a trend that ends on a period that isn't over"),
    "table_truncated": ("info", "a table that shows only some of its rows"),
    "mixed_units": ("info", "measures in different units sharing one axis"),
    "no_data": ("warning", "a chart with nothing to show"),
}  # fmt: skip

_BARS = ("bar", "hbar", "grouped_bar", "stacked_bar", "stacked100_bar")
_LINES = ("line", "multi_line", "area", "stacked_area", "sparkline")
_STACKED = ("stacked_bar", "stacked100_bar", "stacked_area")
_ADDITIVE = ("sum", "count")


@dataclasses.dataclass(frozen=True)
class LintIssue:
    code: str
    severity: str
    message: str
    fix: str
    change: Mapping[str, Any] | None = None  # ts.chart arguments that apply the fix

    def __str__(self) -> str:
        return f"{self.severity}: {self.code}: {self.message}. Fix: {self.fix}"


@dataclasses.dataclass(frozen=True)
class LintReport:
    issues: tuple[LintIssue, ...]
    ignored: tuple[str, ...] = ()

    def __iter__(self) -> Iterator[LintIssue]:
        return iter(self.issues)

    def __len__(self) -> int:
        return len(self.issues)

    def __bool__(self) -> bool:
        return bool(self.issues)

    @property
    def ok(self) -> bool:
        """True when there are no warnings (info-level notes are fine)."""
        return not any(i.severity == "warning" for i in self.issues)

    @property
    def codes(self) -> list[str]:
        return [i.code for i in self.issues]

    def show(self) -> str:
        if not self.issues:
            return "No problems found."
        lines = []
        for i in self.issues:
            lines += [f"{i.severity:<8}{i.code}", f"        {i.message}", f"        Fix: {i.fix}"]
        return "\n".join(lines)

    def __str__(self) -> str:
        return self.show()

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "issues": [
                {
                    "code": i.code,
                    "severity": i.severity,
                    "message": i.message,
                    "fix": i.fix,
                    "change": dict(i.change) if i.change is not None else None,
                }
                for i in self.issues
            ],
            "ignored": list(self.ignored),
        }


def lint(fig: Figure, *, ignore: Iterable[str] = (), strict: bool = False) -> LintReport:
    """Check ``fig``. ``ignore`` skips rule codes; ``strict=True`` raises
    ``ChartLintError`` when any warning is found."""
    if ignore is None:
        ignore = ()
    elif isinstance(ignore, str):
        ignore = (ignore,)
    elif not isinstance(ignore, list | tuple | set | frozenset):
        raise InvalidSpecError("ignore must be a rule code or a list of rule codes")
    skip = tuple(ignore)
    for code in skip:
        if code not in RULES:
            raise InvalidSpecError(f"unknown lint rule {safe_repr(code)}")
    found = [i for i in _check(fig) if i.code not in skip]
    report = LintReport(tuple(found), skip)
    if strict and not report.ok:
        raise ChartLintError(
            "chart has design problems: "
            + ", ".join(i.code for i in found if i.severity == "warning")
        )
    return report


def _issue(code: str, message: str, fix: str, change: Mapping[str, Any] | None = None) -> LintIssue:
    return LintIssue(code, RULES[code][0], message, fix, change)


def _check(fig: Figure) -> Iterator[LintIssue]:
    kind, facts, option = fig.kind, fig.facts, fig.option or {}
    measures: list[Mapping[str, Any]] = list(facts.get("measures", ()))
    categories = int(facts.get("categories", 0))
    series = int(facts.get("series", 0))

    for m in measures:
        col, agg = m.get("column"), m.get("agg")
        if agg != "sum":
            continue
        if m.get("role") == "id":
            yield _issue("sum_of_ids", f"{col} looks like an ID or code, and adding IDs up means nothing",
                         "count it instead", {"agg": "countd"})  # fmt: skip
        elif m.get("unit") in ("percent", "pp") or m.get("default_agg") in (
            "mean",
            "wavg",
            "median",
        ):
            yield _issue("sum_of_rates", f"{col} is a rate or an average, so its total is meaningless",
                         "average it instead", {"agg": "mean"})  # fmt: skip

    not_additive = [m.get("column") for m in measures if m.get("agg") not in _ADDITIVE]
    if kind == "donut":
        if categories > 8:
            yield _issue("pie_too_many_slices", f"{categories} slices are too many to compare",
                         "keep the 7 biggest and group the rest, or use horizontal bars", {"top": 7})  # fmt: skip
        if not_additive:
            yield _issue("pie_not_additive", f"{not_additive[0]} values don't add up to a whole, so the slices mean nothing",
                         "use bars", {"kind": "bar"})  # fmt: skip
    if "rows" in facts and facts["rows"] == 0:
        yield _issue("no_data", "there are no values to draw, so the chart is empty",
                     "check the filters and that the measure column has numbers")  # fmt: skip
    if kind in _STACKED and not facts.get("one_segment"):  # one segment per bar isn't a stack
        if not_additive:
            yield _issue("stacked_not_additive", f"{not_additive[0]} values don't add up, so the stacked totals mean nothing",
                         "put the bars side by side or draw one line each",
                         {"kind": "grouped_bar" if kind != "stacked_area" else "multi_line"})  # fmt: skip
        if facts.get("negative"):
            yield _issue("stacked_with_negatives", "negative values stack downwards and make the totals hard to read",
                         "put the bars side by side", {"kind": "grouped_bar"})  # fmt: skip
    if series > 10:
        yield _issue("too_many_colors", f"{series} colours are hard to tell apart",
                     "keep the biggest few and group the rest", {"top": 8})  # fmt: skip
    elif kind == "multi_line" and series > 8:
        yield _issue("too_many_lines", f"{series} lines overlap and are hard to follow",
                     "keep the biggest few", {"top": 6})  # fmt: skip

    if kind in _LINES:
        if any(isinstance(s, Mapping) and s.get("smooth") for s in option.get("series", [])):
            yield _issue("smoothed_line", "smoothing draws values that aren't in the data and can hide or invent peaks",
                         'remove the "smooth" setting from the update() patch')  # fmt: skip
        if not facts.get("x_time") and not facts.get("x_ordered"):
            yield _issue("line_for_categories", "a line implies an order, but these categories have none",
                         "use bars", {"kind": "bar"})  # fmt: skip
        if facts.get("partial_period"):
            yield _issue("incomplete_last_period", "the last period isn't over yet, so it looks lower than it will be",
                         "filter the data to complete periods, or keep the note that the chart already shows")  # fmt: skip
    if kind in _BARS:
        for axis in _axes(option, "value"):
            low = axis.get("min")
            if low is not None and low != 0:
                yield _issue("bar_axis_not_zero", f"the axis starts at {safe_repr(low)}, so bar lengths exaggerate the differences",
                             'remove "min" from the value axis')  # fmt: skip
                break
        if categories == 1 and series <= 1:
            yield _issue("single_category", "one bar has nothing to be compared with",
                         "show it as a single number", {"kind": "kpi", "x": None})  # fmt: skip
    for axis in _axes(option, "category"):
        interval = (axis.get("axisLabel") or {}).get("interval", 0)
        if interval not in (0, None) and not facts.get("date_labels_thinned"):
            yield _issue("labels_skipped", "some category labels are hidden, so readers can't tell which bar is which",
                         "use horizontal bars", {"kind": "hbar"} if kind == "bar" else None)  # fmt: skip
            break
    units = {m.get("unit") for m in measures if m.get("agg") not in ("count", "countd")}
    if (kind in _LINES or kind in _BARS) and len(units) > 1:
        yield _issue("mixed_units", f"{' and '.join(str(m.get('column')) for m in measures)} have different units "
                     "on one axis, so the smaller one looks flat",
                     "chart them separately; two-axis combo charts arrive in phase 6")  # fmt: skip
    if kind == "table" and int(facts.get("rows_total", 0)) > int(facts.get("rows_shown", 0)):
        yield _issue("table_truncated", f"only {facts['rows_shown']:,} of {facts['rows_total']:,} rows are shown",
                     "group by fewer columns or keep the top rows", {"top": 50})  # fmt: skip


def _axes(option: Mapping[str, Any], kind: str) -> list[Mapping[str, Any]]:
    out = []
    for key in ("xAxis", "yAxis"):
        axes = option.get(key)
        for axis in axes if isinstance(axes, list) else [axes]:
            if isinstance(axis, Mapping) and axis.get("type") == kind:
                out.append(axis)
    return out
