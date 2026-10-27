"""ts.recommend, ts.chart(kind="auto"), fig.explain() and fig.lint()."""

from __future__ import annotations

import json
import warnings
from collections.abc import Callable
from functools import cache
from typing import Any

import pandas as pd
import pytest

import tabsight as ts
from tabsight.lint import RULES
from tabsight.warnings import ChartLintError, InvalidSpecError

from .recommend_cases import CASES, frame


@cache
def data() -> tuple[pd.DataFrame, ts.Profile]:
    df = frame()
    return df, ts.profile(df, quiet=True)


def _id(case: tuple[dict[str, object], str, str | None, str]) -> str:
    return ",".join(f"{k}={v}" for k, v in case[0].items())


# ---------------------------------------------------------------- the labelled cases


def test_case_set_is_big_enough() -> None:
    assert len(CASES) >= 60
    assert len({_id(c) for c in CASES}) == len(CASES)  # no duplicates


@pytest.mark.parametrize("case", CASES, ids=_id)
def test_recommender_matches_the_labelled_case(
    case: tuple[dict[str, Any], str, str | None, str],
) -> None:
    fields, best, ideal, _why = case
    df, prof = data()
    recs = ts.recommend(df, prof=prof, **fields)
    assert recs.best.kind == best, recs.show()
    assert recs[0].kind == (ideal or best), recs.show()


@pytest.mark.parametrize("case", CASES, ids=_id)
def test_auto_charts_pass_their_own_linter(
    case: tuple[dict[str, Any], str, str | None, str],
) -> None:
    fields, best, _ideal, _why = case
    df, prof = data()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fig = ts.chart(df, "auto", prof=prof, **fields)
    # The recommender never picks a chart its own linter warns about.
    assert fig.lint().ok, fig.lint().show()
    assert fig.decisions[0].startswith(best.replace("_", " ") + " chosen automatically")


# ---------------------------------------------------------------- recommend


def test_recommendations_are_ranked_and_explained() -> None:
    df, prof = data()
    recs = ts.recommend(df, x="Region", y="Revenue", prof=prof)
    scores = [r.score for r in recs]
    assert scores == sorted(scores, reverse=True)
    assert all(0 <= s <= 100 and r.reason for s, r in zip(scores, recs, strict=True))
    assert recs.best.kind == "bar" and recs.best.available and recs.best.phase is None
    assert all(
        r.available and r.phase is None for r in recs
    )  # since Phase 6 every kind can be drawn
    assert len({r.kind for r in recs}) == len(recs)  # each kind once
    assert recs.best.spec == ts.ChartSpec("bar", x="Region", y="Revenue")


def test_rejections_say_why() -> None:
    df, prof = data()
    recs = ts.recommend(df, x="Region", y="Discount_Rate", prof=prof)
    assert "donut" not in [r.kind for r in recs]
    assert "don't add up" in dict(recs.rejected)["donut"]
    assert "don't add up" in recs.why_not("pie")  # aliases work
    assert recs.why_not("bar").startswith("bar is suggested with score")
    assert "does not fit" in recs.why_not("sankey")
    with pytest.raises(InvalidSpecError, match="unknown chart kind"):
        recs.why_not("<script>")
    text = recs.show()
    assert text.startswith("Charts for 1 category field, 1 measure:") and "Ruled out:" in text
    negative = ts.recommend(df, x="Order_Date", y="Profit", prof=prof)
    assert "area" in dict(negative.rejected) and "area" not in [r.kind for r in negative]


def test_recommend_is_deterministic_and_json_safe() -> None:
    df, _ = data()
    a = ts.recommend(df, x="Order_Date", y="Revenue", color="Segment").to_dict()
    b = ts.recommend(
        df.sample(frac=1, random_state=3), x="Order_Date", y="Revenue", color="Segment"
    ).to_dict()
    assert a == b  # row order doesn't matter
    assert json.loads(json.dumps(a)) == a
    assert a["items"][0]["spec"]["options"] == {"freq": "quarter"}


def test_recommend_rejects_bad_fields() -> None:
    df, _ = data()
    with pytest.raises(InvalidSpecError, match="did you mean 'Revenue'"):
        ts.recommend(df, x="Region", y="Revenu")
    with pytest.raises(InvalidSpecError, match="once"):
        ts.recommend(df, x="Region", color="Region", y="Revenue")
    hostile = "<img src=x onerror=alert(1)>\n" + "x" * 500
    with pytest.raises(InvalidSpecError) as err:
        ts.recommend(df, x=hostile, y="Revenue")
    assert "\n" not in str(err.value) and len(str(err.value)) < 150


def test_recommend_reads_other_inputs() -> None:
    rows = [{"Team": t, "Points": p} for t, p in [("A", 3), ("B", 5), ("C", 1)]]
    assert ts.recommend(rows, x="Team", y="Points").best.kind == "bar"
    hostile = pd.DataFrame({"<b>Team</b>": ["</script>", "x"], "Points": [1, 2]})
    recs = ts.recommend(hostile, x="<b>Team</b>", y="Points")
    assert recs.best.kind == "bar"
    fig = ts.chart(hostile, "auto", x="<b>Team</b>", y="Points")
    assert "</script>" not in fig.to_html().split("application/json")[1].split("</script>")[0]


# ---------------------------------------------------------------- auto and explain


def test_auto_uses_the_recommendation(store: pd.DataFrame) -> None:
    fig = ts.chart(store, "auto", x="Order_Date", y="Sales")
    assert fig.kind == "line" and fig.spec.options["freq"]
    assert "to suit the time span" in fig.explain()
    asked = ts.chart(store, "auto", x="Order_Date", y="Sales", freq="month")
    assert asked.spec.options["freq"] == "month" and "(as asked)" in asked.explain()
    kept = ts.chart(store, "auto", x="Region", y="Sales", top=2)
    assert kept.spec.top == 2


def test_explain_lists_every_decision(store: pd.DataFrame) -> None:
    fig = ts.chart(store, "bar", x="Region", y="Sales")
    text = fig.explain()
    assert text.splitlines()[0] == "Sum of Sales by Region (bar chart)"
    assert "- bar chart, as asked" in text
    assert "Sales is summed" in text and "sorted largest first" in text
    assert "starts at zero" in text and "currency in USD for en_US" in text
    donut = ts.chart(store, "donut", x="Sub_Category", y="Sales")
    assert "the rest are grouped as Other" in donut.explain()
    assert "Notes shown on the chart:" in donut.explain()
    many = ts.chart(data()[0], "bar", x="Country", y="Revenue")
    assert many.kind == "hbar" and "switched to horizontal bars: 25 categories" in many.explain()
    kpi = ts.chart(store, "kpi", y="Discount", agg="mean")
    assert kpi.explain().startswith("Avg") or "(KPI card)" in kpi.explain()
    assert "Discount is averaged: as asked" in kpi.explain()
    table = ts.chart(store, "table", x=["Category", "Sub_Category"], y="Sales")
    assert "(table)" in table.explain() and "shown once" in table.explain()


def test_decisions_and_facts_stay_out_of_the_page(store: pd.DataFrame) -> None:
    fig = ts.chart(store, "bar", x="Region", y="Sales")
    assert fig.decisions and fig.facts
    assert "decisions" not in fig.to_dict() and "facts" not in fig.to_dict()


# ---------------------------------------------------------------- lint


def _lint_triggers() -> dict[str, Callable[[pd.DataFrame], ts.Figure]]:
    return {
        "pie_too_many_slices": lambda d: ts.chart(d, "donut", x="Product", y="Revenue", top=12),
        "pie_not_additive": lambda d: ts.chart(d, "donut", x="Region", y="Discount_Rate"),
        "stacked_not_additive": lambda d: ts.chart(
            d, "stacked_bar", x="Region", y="Unit_Price", color="Segment"
        ),
        "stacked_with_negatives": lambda d: ts.chart(
            d, "stacked_bar", x="Product", y="Profit", color="Segment"
        ),
        "too_many_colors": lambda d: ts.chart(
            d, "grouped_bar", x="Region", y="Revenue", color="Product"
        ),
        "too_many_lines": lambda d: ts.chart(
            d, "multi_line", x="Order_Date", y="Revenue", color="Product", top=9, freq="year"
        ),
        "smoothed_line": lambda d: ts.chart(d, "line", x="Order_Date", y="Revenue").update(
            {"series": [{"smooth": True}]}
        ),
        "bar_axis_not_zero": lambda d: ts.chart(d, "bar", x="Region", y="Revenue").update(
            {"yAxis": {"min": 50000}}
        ),
        "labels_skipped": lambda d: ts.chart(d, "bar", x="Product", y="Revenue").update(
            {"xAxis": {"axisLabel": {"interval": 2}}}
        ),
        "sum_of_rates": lambda d: ts.chart(d, "bar", x="Region", y="Discount_Rate", agg="sum"),
        "sum_of_ids": lambda d: ts.chart(
            d.assign(Store_ID=range(len(d))), "bar", x="Region", y="Store_ID", agg="sum"
        ),
        "line_for_categories": lambda d: ts.chart(d, "line", x="Region", y="Revenue"),
        "single_category": lambda d: ts.chart(
            d[d["Region"] == "North"], "bar", x="Region", y="Revenue"
        ),
        "incomplete_last_period": lambda d: ts.chart(
            d[d["Order_Date"] < "2024-03-01"], "line", x="Order_Date", y="Revenue", freq="year"
        ),
        "table_truncated": lambda d: ts.chart(d, "table", x="Order_ID", y="Revenue"),
        "mixed_units": lambda d: ts.chart(d, "line", x="Order_Date", y=["Revenue", "Units"]),
        "no_data": lambda d: ts.chart(d.iloc[0:0], "bar", x="Region", y="Revenue"),
    }


def test_every_lint_rule_has_a_trigger() -> None:
    assert set(_lint_triggers()) == set(RULES)
    assert all(sev in ("warning", "info") for sev, _ in RULES.values())


@pytest.mark.parametrize("code", list(RULES))
def test_lint_rule_fires(code: str) -> None:
    df, _ = data()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fig = _lint_triggers()[code](df)
    report = fig.lint()
    assert code in report.codes, report.show()
    issue = next(i for i in report if i.code == code)
    assert issue.severity == RULES[code][0] and issue.message and issue.fix
    assert code in str(issue)
    assert code not in fig.lint(ignore=[code]).codes
    assert json.loads(json.dumps(report.to_dict()))["issues"]


def test_lint_fixes_can_be_applied() -> None:
    df, _ = data()
    fig = ts.chart(df, "donut", x="Product", y="Revenue", top=12)
    change = next(i.change for i in fig.lint() if i.code == "pie_too_many_slices")
    assert change == {"top": 7}
    fixed = ts.chart(df, "donut", x="Product", y="Revenue", **change)
    assert "pie_too_many_slices" not in fixed.lint().codes


def test_default_charts_are_clean(store: pd.DataFrame) -> None:
    for fig in (
        ts.chart(store, "bar", x="Region", y="Sales"),
        ts.chart(store, "donut", x="Sub_Category", y="Sales"),
        ts.chart(store, "stacked_bar", x="Category", y="Sales", color="Segment"),
        ts.chart(store, "kpi", y="Sales"),
    ):
        report = fig.lint()
        assert report.ok and not report and report.show() == "No problems found."


def test_lint_options() -> None:
    df, _ = data()
    fig = ts.chart(df, "bar", x="Region", y="Revenue").update({"yAxis": {"min": 50000}})
    with pytest.raises(ChartLintError, match="bar_axis_not_zero"):
        fig.lint(strict=True)
    assert fig.lint(ignore="bar_axis_not_zero", strict=True).ok
    with pytest.raises(InvalidSpecError, match="unknown lint rule"):
        fig.lint(ignore=["no_such_rule"])
    info_only = ts.chart(df, "table", x="Order_ID", y="Revenue")
    assert info_only.lint(strict=True).ok  # info never raises


def test_lint_messages_are_safe() -> None:
    df, _ = data()
    fig = ts.chart(df, "bar", x="Region", y="Revenue").update({"yAxis": {"min": "<b>" + "9" * 300}})
    message = next(i.message for i in fig.lint() if i.code == "bar_axis_not_zero")
    assert len(message) < 160


# ---------------------------------------------------------------- found by hands-on review


def test_recommend_validates_its_fields() -> None:
    df, prof = data()
    for kw, message in [
        ({}, "pick at least one column"),
        ({"x": [], "y": []}, "pick at least one column"),
        ({"x": "Revenue", "y": "Revenue"}, "used once"),
        ({"x": "Region", "y": ["Revenue", "Revenue"]}, "used once"),
        ({"x": 5, "y": "Revenue"}, "column name"),
        ({"x": ["Region"] * 21, "y": "Revenue"}, "up to 20"),
    ]:
        with pytest.raises(InvalidSpecError, match=message):
            ts.recommend(df, prof=prof, **kw)
    long = "C" * 150
    with pytest.raises(InvalidSpecError) as err:
        ts.recommend(df.rename(columns={"Region": long}), x=long[:-1], y="Revenue")
    assert len(str(err.value)) < 200  # the "did you mean" hint is shortened too


def test_numeric_x_keeps_numeric_order() -> None:
    df, prof = data()
    recs = ts.recommend(df, x="Units", y="Revenue", prof=prof)
    assert recs.best.kind == "scatter" and recs[1].kind == "bar"
    assert recs[1].spec.sort == "none" and "donut" in dict(recs.rejected)
    fig = ts.chart(df, "bar", x="Units", y="Revenue", sort="none", prof=prof)
    labels = fig.option["xAxis"]["data"]
    assert labels == sorted(labels, key=int)
    assert (
        ts.recommend(df, x="Revenue", y="Units", prof=prof).best.kind == "scatter"
    )  # many numbers: dots, not bars


def test_very_many_categories_keep_the_top_bars() -> None:
    many = pd.DataFrame({"Store": [f"Store {i % 80}" for i in range(400)], "Revenue": range(400)})
    recs = ts.recommend(many, x="Store", y="Revenue")
    assert recs.best.kind == "hbar" and recs.best.spec.top == 20
    assert "too many" in dict(recs.rejected)["donut"] and "bar" in dict(recs.rejected)
    fig = ts.chart(many, "auto", x="Store", y="Revenue")
    assert len(fig.option["yAxis"]["data"]) == 21 and fig.lint().ok  # 20 + Other


def test_one_period_is_not_a_line() -> None:
    one = pd.DataFrame({"D": pd.to_datetime(["2024-03-01"] * 3), "V": [1.0, 2.0, 3.0]})
    recs = ts.recommend(one, x="D", y="V")
    assert recs.best.kind == "bar" and "at least two" in dict(recs.rejected)["line"]


def test_nested_fields_draw_child_bars_coloured_by_parent() -> None:
    df, prof = data()
    for x, color in [("Category", "Product"), ("Product", "Category")]:
        recs = ts.recommend(df, x=x, y="Revenue", color=color, prof=prof)
        assert recs.best.kind == "treemap"
        bars = next(r for r in recs if r.kind == "stacked_bar")
        assert (bars.spec.x, bars.spec.color) == ("Product", "Category")
        assert "grouped_bar" in dict(recs.rejected)
    fig = ts.chart(df, "stacked_bar", x="Product", y="Profit", color="Category", prof=prof)
    assert fig.facts["one_segment"] and not fig.lint().codes  # negatives, but nothing stacks


def test_time_zone_aware_dates() -> None:
    days = pd.DataFrame(
        {"D": pd.date_range("2024-01-31 22:00", periods=6, freq="h", tz="UTC"), "V": 1.0}
    )
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # no "dropping time zone" noise either
        by_utc = ts.aggregate(days, "D", "V", freq="month").values
    assert list(by_utc["V"]) == [2.0, 4.0]  # 22:00 and 23:00 UTC are still January
    with ts.config(tz="Asia/Kolkata"):  # UTC+5:30: all six are February there
        assert list(ts.aggregate(days, "D", "V", freq="month").values["V"]) == [6.0]
    with ts.config(tz="Mars/Olympus"), pytest.raises(InvalidSpecError, match="time zone"):
        ts.aggregate(days, "D", "V", freq="month")
    assert ts.chart(days, "auto", x="D", y="V").kind in ("line", "bar")


def test_table_without_measure_says_natural_order(store: pd.DataFrame) -> None:
    fig = ts.chart(store, "table", x="Region")
    assert "natural order" in fig.explain()
    rows = [r[0] for r in fig.table["rows"]]
    assert rows == sorted(rows)


def test_explain_wording() -> None:
    df, prof = data()
    fig = ts.chart(df, "multi_line", x="Order_Date", y="Discount_Rate", color="Region", prof=prof)
    text = fig.explain()
    assert "(multi-line chart)" in text
    assert "Discount_Rate is averaged: " in text and "averaged, because" not in text


def test_lint_ignore_types() -> None:
    df, _ = data()
    fig = ts.chart(df, "bar", x="Region", y="Revenue")
    assert fig.lint(ignore=None).ok and fig.lint(ignore={"no_data"}).ok
    with pytest.raises(InvalidSpecError, match="rule code"):
        fig.lint(ignore=5)  # type: ignore[arg-type]


def test_other_line_starts_hidden() -> None:
    df, prof = data()
    kw = {"x": "Order_Date", "y": "Revenue", "color": "Product", "top": 3, "prof": prof}
    fig = ts.chart(df, "multi_line", freq="year", **kw)
    hidden = fig.option["legend"]["selected"]
    assert list(hidden.values()) == [False] and next(iter(hidden)).startswith("Other (")
    assert "Other line starts hidden" in fig.explain()
    stacked = ts.chart(df, "stacked_area", **kw)
    assert "selected" not in stacked.option["legend"]  # in a stack, Other is part of the total
