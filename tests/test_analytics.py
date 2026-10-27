"""Trend lines, forecasts, outliers, reference lines, period comparisons and insights."""

from __future__ import annotations

import json
import warnings

import numpy as np
import pandas as pd
import pytest

import tabsight as ts
from tabsight import analytics
from tabsight.analytics import NotEnoughData
from tabsight.charts.pane import BAND_LOW, BAND_SPREAD
from tabsight.insight import THRESHOLDS
from tabsight.warnings import InvalidSpecError

from .conftest import assert_unchanged
from .test_html_security import ALLOWED_TAGS, EVIL, _parse


def shop(years: int = 4, start: str = "2019-01-01") -> pd.DataFrame:
    """Daily orders with a known shape: sales grow ~1% a month, December is always the
    best month, Gadgets sell most, and Repairs lose money everywhere."""
    days = pd.date_range(start, periods=years * 365, freq="D")
    rows = []
    for i, d in enumerate(days):
        month = i / 30.4
        base = 100 * (1.01**month) * (1.8 if d.month == 12 else 1.0)
        for product, share, margin in (
            ("Gadgets", 0.6, 0.2),
            ("Gizmos", 0.3, 0.1),
            ("Repairs", 0.1, -0.3),
        ):
            sales = round(base * share, 2)
            rows.append({"Date": d, "Product": product, "Region": ("North", "South")[i % 2],
                         "Sales": sales, "Profit": round(sales * margin, 2), "Margin": margin})  # fmt: skip
    return pd.DataFrame(rows)


@pytest.fixture(scope="module")
def data() -> pd.DataFrame:
    return shop()


# ---------------------------------------------------------------- the maths


def test_linear_trend_is_exact_on_a_line() -> None:
    fit = analytics.linear_trend([3.0, 5.0, 7.0, 9.0])
    assert (
        fit.slope == pytest.approx(2)
        and fit.intercept == pytest.approx(3)
        and fit.r2 == pytest.approx(1)
    )
    big = analytics.linear_trend(
        [1.0, 2.0, 3.0], [1.6e18, 1.6e18 + 1e9, 1.6e18 + 2e9]
    )  # timestamps
    assert big.slope == pytest.approx(1e-9)
    with_gaps = analytics.linear_trend([1.0, np.nan, 3.0, 4.0])
    assert with_gaps.n == 3 and with_gaps.slope == pytest.approx(1)


@pytest.mark.parametrize(
    "ys, xs", [([1.0, 2.0], None), ([np.nan] * 5, None), ([1.0, 2.0, 3.0], [5.0, 5.0, 5.0])]
)
def test_linear_trend_refuses_too_little(ys: list[float], xs: list[float] | None) -> None:
    with pytest.raises(NotEnoughData):
        analytics.linear_trend(ys, xs)


def test_holt_winters_learns_a_season_and_a_trend() -> None:
    t = np.arange(48)
    y = 100 + 2 * t + 20 * np.sin(2 * np.pi * t / 12)
    fc = analytics.forecast(y, 12, 12)
    truth = 100 + 2 * np.arange(48, 60) + 20 * np.sin(2 * np.pi * np.arange(48, 60) / 12)
    assert np.max(np.abs(np.array(fc.values) - truth)) < 0.01  # exact on a clean series
    noisy = analytics.forecast(y + np.random.default_rng(1).normal(0, 5, 48), 12, 12)
    assert np.max(np.abs(np.array(noisy.values) - truth)) < 3 * 5
    assert fc.method == "Holt-Winters (additive)" and fc.season == 12 and fc.history == 48
    assert all(lo <= v <= hi for v, lo, hi in zip(fc.values, fc.lower, fc.upper, strict=True))
    widths = [hi - lo for lo, hi in zip(fc.lower, fc.upper, strict=True)]
    assert widths == sorted(widths)  # the range widens with the horizon
    assert analytics.forecast(y, 12, 12) == fc  # repeatable


def test_forecast_needs_history_and_no_gaps() -> None:
    with pytest.raises(NotEnoughData, match="two full seasons"):
        analytics.forecast(np.arange(23.0), 3, 12)
    with pytest.raises(NotEnoughData, match="6 periods"):
        analytics.forecast([1.0, 2.0, 3.0, 4.0, 5.0], 3)
    with pytest.raises(NotEnoughData, match="gaps"):
        analytics.forecast([1.0, 2.0, np.nan, 4.0, 5.0, 6.0, 7.0], 3)
    assert analytics.forecast([1.0, 2.0, 3.0, 4.0, 5.0, 6.0], 2).method == "Holt's linear trend"


@pytest.mark.parametrize(
    "horizon, season", [(0, None), (121, None), (2.0, None), (True, None), (3, 1), (3, "12")]
)
def test_forecast_validates_its_arguments(horizon: object, season: object) -> None:
    with pytest.raises(InvalidSpecError):
        analytics.forecast(np.arange(30.0), horizon, season)  # type: ignore[arg-type]


def test_forecast_never_goes_below_zero_when_history_never_did() -> None:
    falling = [100.0 - 15 * i for i in range(7)]
    fc = analytics.forecast(falling, 6)
    assert min(fc.values) == 0 and min(fc.lower) == 0 and fc.clipped
    negative = analytics.forecast([v - 200 for v in falling], 3)
    assert min(negative.values) < 0 and not negative.clipped


def test_outliers_flag_and_never_remove() -> None:
    values = [float(v) for v in range(10, 30)] + [500.0]
    mask = analytics.outliers(values)
    assert mask.tolist() == [False] * 20 + [True]
    assert analytics.outliers(values, "zscore", 3).sum() == 1
    assert not analytics.outliers([5.0] * 30).any()  # no spread: nothing is unusual
    assert not analytics.outliers([1.0, 100.0, np.nan]).any()  # too few to judge
    with pytest.raises(InvalidSpecError):
        analytics.outliers(values, "magic")


def test_reference_values() -> None:
    v = [1.0, 2.0, 3.0, 4.0, 100.0, np.nan]
    assert analytics.reference_value(v, "mean") == pytest.approx(22)
    assert analytics.reference_value(v, "median") == 3
    assert analytics.reference_value(v, "p50") == 3 and analytics.reference_value(v, 7) == 7
    assert analytics.reference_value([np.nan], "mean") is None
    assert (
        analytics.reference_label("p90") == "90th percentile"
        and analytics.reference_label(5) == "Target"
    )
    with pytest.raises(InvalidSpecError):
        analytics.reference_value(v, "max")


# ---------------------------------------------------------------- period comparisons


def test_year_to_date_compares_the_same_days(data: pd.DataFrame) -> None:
    c = ts.compare(data, "Sales", "Date", as_of="2022-06-30")
    assert (str(c.start.date()), str(c.end.date())) == ("2022-01-01", "2022-06-30")
    assert (str(c.previous_start.date()), str(c.previous_end.date())) == (
        "2021-01-01",
        "2021-06-30",
    )
    assert c.current_label == "2022 to Jun 30, 2022" and c.as_of_source == "as asked"
    day = data["Date"]
    now = data.loc[(day >= "2022-01-01") & (day <= "2022-06-30"), "Sales"].sum()
    before = data.loc[(day >= "2021-01-01") & (day <= "2021-06-30"), "Sales"].sum()
    assert c.current == pytest.approx(now) and c.previous == pytest.approx(before)
    assert c.pct == pytest.approx(now / before - 1)
    assert json.loads(json.dumps(c.to_dict()))["as_of"] == "2022-06-30"


def test_a_whole_month_is_compared_with_the_whole_month_before(data: pd.DataFrame) -> None:
    c = ts.compare(data, "Sales", "Date", compare="previous_month", as_of="2021-11-30")
    assert str(c.previous_end.date()) == "2021-10-31" and c.previous_label == "Oct 2021"
    leap = ts.compare(
        shop(2, "2019-06-01"), "Sales", "Date", compare="previous_month", as_of="2020-02-29"
    )
    assert (str(leap.start.date()), str(leap.previous_end.date())) == ("2020-02-01", "2020-01-31")
    partial = ts.compare(data, "Sales", "Date", compare="previous_month", as_of="2021-03-30")
    assert str(partial.previous_end.date()) == "2021-02-28"  # Mar 1-30 against Feb 1-28


def test_fiscal_quarters_and_custom_windows(data: pd.DataFrame) -> None:
    q = ts.compare(
        data, "Sales", "Date", compare="previous_quarter", as_of="2021-06-30", fiscal_start=4
    )
    assert q.current_label == "FY2022 Q1" and q.previous_label == "FY2021 Q4"
    w = ts.compare(
        data, "Sales", "Date", compare="previous_period", window=("2021-03-01", "2021-05-31")
    )
    assert (str(w.previous_start.date()), str(w.previous_end.date())) == (
        "2020-11-29",
        "2021-02-28",
    )  # 92 days before 92 days
    yoy = ts.compare(data, "Sales", "Date", window=("2021-03-01", "2021-05-31"))
    assert (
        str(yoy.previous_start.date()) == "2020-03-01"
    )  # a filtered range against the same range a year back


def test_today_is_the_data_never_the_clock(data: pd.DataFrame) -> None:
    c = ts.compare(data, "Sales", "Date")
    assert str(c.as_of.date()) == str(data["Date"].max().date())
    sliver = pd.concat([data, data.tail(1).assign(Date=pd.Timestamp("2023-01-01"))])
    c2 = ts.compare(sliver, "Sales", "Date")
    assert c2.current_label == "2022" and "last complete year" in c2.as_of_source


def test_no_previous_data_is_said_plainly(data: pd.DataFrame) -> None:
    first = ts.compare(data, "Sales", "Date", as_of="2019-12-31")
    assert (
        first.change is None and first.pct is None and first.note == "no data for the previous year"
    )
    zero = data.assign(Sales=np.where(data["Date"].dt.year == 2021, 0.0, data["Sales"]))
    z = ts.compare(zero, "Sales", "Date", as_of="2022-12-31")
    assert z.pct is None and z.change is not None and "zero" in (z.note or "")


@pytest.mark.parametrize("kwargs, match", [
    ({"compare": "yoy"}, "compare="), ({"as_of": "yesterday"}, "as_of"), ({"date": "Product"}, "not a date"),
    ({"compare": "previous_period"}, "window="), ({"window": ("2021-05-01", "2021-01-01")}, "start before"),
    ({"y": "Nope"}, "not found"), ({"window": ("<script>", "2021-01-01")}, "two dates"),
    ({"window": "2021"}, "window must be"),
])  # fmt: skip
def test_compare_refuses_bad_input(
    data: pd.DataFrame, kwargs: dict[str, object], match: str
) -> None:
    args = {"y": "Sales", "date": "Date", **kwargs}
    with pytest.raises(InvalidSpecError, match=match):
        ts.compare(data, args.pop("y"), args.pop("date"), **args)  # type: ignore[arg-type]


# ---------------------------------------------------------------- insights


def test_insights_find_the_known_facts(data: pd.DataFrame) -> None:
    found = ts.insights(data, y=["Sales", "Profit"], x="Product", date="Date", max_items=20)
    text = found.show()
    assert {"change", "peak", "contributor", "negative", "seasonality", "trend"} <= set(
        found.kinds
    ), text
    assert "Gadgets makes up 60% of total Sales." in text
    assert "1 of 3 Product values have negative Profit: Repairs." in text
    assert "high every December" in text and "rose about" in text
    assert "because" not in text.lower() and "due to" not in text.lower()  # facts, never causes
    assert all(i.scope == "based on all data" for i in found)
    assert found.as_of == "2022-12-30"


def test_insights_pick_fields_themselves_and_are_repeatable(data: pd.DataFrame) -> None:
    before = data.copy(deep=True)
    first = ts.insights(data)
    assert_unchanged(before, data)
    assert first.to_dict() == ts.insights(data).to_dict()
    assert 1 <= len(first) <= 8 and json.loads(json.dumps(first.to_dict()))["insights"]


def test_rates_change_in_points_not_percent(data: pd.DataFrame) -> None:
    rates = data.assign(Rate=np.where(data["Date"].dt.year == 2022, 0.15, 0.12))
    found = ts.insights(rates, y="Rate", date="Date", max_items=20)
    change = next(i for i in found if i.kind == "change")
    assert "up 3.0 pp" in change.text


def test_insights_respect_as_of_and_thresholds(data: pd.DataFrame) -> None:
    early = ts.insights(data, y="Sales", date="Date", as_of="2020-06-30", max_items=20)
    assert "2022" not in early.show() and early.as_of == "2020-06-30"
    quiet = ts.insights(
        data, y="Sales", x="Product", thresholds={"contributor": 0.99, "concentration": 1.0}
    )
    assert "contributor" not in quiet.kinds
    with pytest.raises(InvalidSpecError, match="unknown threshold"):
        ts.insights(data, thresholds={"magic": 1})
    with pytest.raises(InvalidSpecError):
        ts.insights(data, thresholds={"contributor": True})
    with pytest.raises(InvalidSpecError):
        ts.insights(data, max_items=0)
    assert set(THRESHOLDS) >= {"contributor", "trend_r2", "outlier_k"}


def test_unusual_rows_are_counted_not_removed() -> None:
    df = pd.DataFrame({"Sales": [100.0 + (i % 7) for i in range(300)] + [9000.0, 12000.0]})
    found = ts.insights(df, y="Sales")
    outlier = next(i for i in found if i.kind == "outliers")
    assert outlier.text.startswith("2 rows have unusually large Sales") and len(df) == 302


def test_hostile_names_stay_text_in_insights() -> None:
    df = pd.DataFrame({"Name": EVIL, "Sales": [float(10 + i) for i in range(len(EVIL))]})
    df.loc[0, "Sales"] = 500.0
    found = ts.insights(df, y="Sales", x="Name")
    assert "<img" not in found._repr_html_() and "&lt;img" in found._repr_html_()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fig = ts.chart(df, "bar", x="Name", y="Sales", insights=True)
    assert fig.insights
    tags, handlers = _parse(fig.to_html())
    assert tags <= ALLOWED_TAGS and not handlers


def test_no_insights_is_said_plainly() -> None:
    flat = pd.DataFrame({"Group": ["a", "b"], "Sales": [1.0, 1.0]})
    assert "No insights found" in ts.insights(flat, y="Sales", x="Group").show()


# ---------------------------------------------------------------- on charts


def test_forecast_on_a_line_chart(data: pd.DataFrame) -> None:
    fig = ts.chart(data, "line", x="Date", y="Sales", freq="month", forecast=6)
    assert fig.option is not None
    labels = fig.option["xAxis"]["data"]
    assert len(labels) == 48 + 6 and labels[-1] == "Jun '23"
    names = [s["name"] for s in fig.option["series"]]
    assert names == ["Sales", "Estimate", BAND_LOW, BAND_SPREAD]
    estimate = fig.option["series"][1]
    assert estimate["lineStyle"]["type"] == "dashed"
    assert estimate["data"][47] == fig.option["series"][0]["data"][47]  # joins the last real point
    assert all(v is None for v in estimate["data"][:47]) and all(
        v is not None for v in estimate["data"][48:]
    )
    assert (
        fig.option["series"][0]["data"][48:] == [None] * 6
    )  # the real line stops where the data does
    tooltip = fig.option["tooltip"]["formatter"]["$tooltip"]
    assert tooltip["skip"] == [BAND_LOW, BAND_SPREAD] and "Estimate" in tooltip["bands"]
    assert fig.option["legend"]["data"] == ["Sales", "Estimate"]
    assert "Holt-Winters (additive) with a season of 12 months" in fig.explain()
    assert "long_forecast" not in fig.lint().codes


def test_forecast_starts_from_the_last_complete_period(data: pd.DataFrame) -> None:
    cut = data[data["Date"] <= "2022-11-10"]
    fig = ts.chart(cut, "line", x="Date", y="Sales", freq="month", forecast=3)
    assert fig.option is not None
    estimate = next(s for s in fig.option["series"] if s["name"] == "Estimate")
    assert len(fig.option["xAxis"]["data"]) == 47 + 2  # Nov 2022 is drawn, then Dec and Jan
    assert (
        estimate["data"][45] is not None and estimate["data"][46] is not None
    )  # Oct joins, Nov is estimated
    assert "starts from the last complete one" in fig.explain()


def test_too_little_history_gives_a_note_not_a_guess(data: pd.DataFrame) -> None:
    short = data[data["Date"] < "2019-11-01"]
    fig = ts.chart(short, "line", x="Date", y="Sales", freq="month", forecast=3)
    assert fig.option is not None and len(fig.option["series"]) == 1
    assert any("not enough data for a forecast" in n for n in fig.notes)


def test_trend_reference_band_and_outliers(data: pd.DataFrame) -> None:
    fig = ts.chart(data, "line", x="Date", y="Sales", freq="month", trend=True, ref=["mean", 5000],
                   band=("p25", "p75"), outliers=True)  # fmt: skip
    assert fig.option is not None
    trend = next(s for s in fig.option["series"] if s["name"] == "Trend")
    assert trend["data"][-1] > trend["data"][0]  # sales grow
    line = fig.option["series"][0]
    assert [d["name"] for d in line["markLine"]["data"]] == ["Average", "Target"]
    assert line["markLine"]["data"][1]["yAxis"] == 5000
    assert line["markLine"]["data"][0]["label"]["formatter"]["$label"]["unit"] == "currency"
    lo, hi = (line["markArea"]["data"][0][i]["yAxis"] for i in (0, 1))
    assert lo < hi
    circled = {fig.option["xAxis"]["data"][p["coord"][0]] for p in line["markPoint"]["data"]}
    assert {
        "Dec '19",
        "Dec '20",
        "Dec '21",
    } <= circled  # the December jumps stand out from the trend
    assert "flagged, never removed" in fig.explain()


def test_scatter_trend_and_hbar_reference(data: pd.DataFrame) -> None:
    fig = ts.chart(data, "scatter", x="Sales", y="Profit", trend=True)
    assert fig.option is not None and fig.option["series"][-1]["name"] == "Trend"
    assert "not proof that one causes the other" in fig.explain()
    bars = ts.chart(data, "hbar", x="Product", y="Sales", ref="median")
    assert bars.option is not None and "xAxis" in bars.option["series"][0]["markLine"]["data"][0]


def test_time_bars_stay_vertical(data: pd.DataFrame) -> None:
    fig = ts.chart(data, "bar", x="Date", y="Sales", freq="month", trend=True)
    assert (
        fig.kind == "bar" and fig.option is not None and fig.option["series"][-1]["name"] == "Trend"
    )


@pytest.mark.parametrize("kwargs, match", [
    ({"kind": "bar", "x": "Product", "trend": True}, "needs dates or numbers"),
    ({"kind": "scatter", "x": "Sales", "y": "Profit", "forecast": 3}, "forecast= works on"),
    ({"kind": "line", "x": "Profit", "forecast": 3}, "needs dates"),
    ({"kind": "donut", "x": "Product", "ref": "mean"}, "ref= works on"),
    ({"kind": "stacked_area", "x": "Date", "color": "Product", "trend": True}, "trend= works on"),
    ({"kind": "bar", "x": "Product", "compare": "previous_year"}, "KPI"),
    ({"kind": "bar", "x": "Product", "facet": "Region", "ref": "mean"}, "small multiples"),
    ({"kind": "line", "x": "Date", "forecast": 500}, "1-120"),
    ({"kind": "line", "x": "Date", "ref": "max"}, "'mean'"),
    ({"kind": "line", "x": "Date", "band": ("p25",)}, "pair"),
    ({"kind": "kpi", "compare": "yoy"}, "compare="),
])  # fmt: skip
def test_analytics_refuse_what_would_mislead(
    data: pd.DataFrame, kwargs: dict[str, object], match: str
) -> None:
    args = {"y": "Sales", **kwargs}
    with pytest.raises(InvalidSpecError, match=match):
        ts.chart(data, args.pop("kind"), **args)  # type: ignore[arg-type]


def test_kpi_compares_periods(data: pd.DataFrame) -> None:
    fig = ts.chart(data, "kpi", y="Sales", compare="previous_year", as_of="2022-06-30")
    assert fig.kpi is not None
    assert fig.kpi["detail"].startswith("2022 to Jun 30, 2022 · ▲ ")
    assert fig.kpi["detail"].endswith("vs 2021 to Jun 30, 2021")
    assert "data up to 2022-06-30" in fig.kpi["value_full"]
    assert "computer's clock is never used" in fig.explain()
    first = ts.chart(data, "kpi", y="Sales", compare="previous_year", as_of="2019-12-31")
    assert first.kpi is not None and "no data for the previous year" in first.kpi["detail"]
    rate = ts.chart(data.assign(Rate=0.1), "kpi", y="Rate", compare="previous_month")
    assert (rate.kpi is not None and "pp" in rate.kpi["detail"]) or "■" in rate.kpi["detail"]  # type: ignore[index]
    with pytest.raises(InvalidSpecError, match="date column"):
        ts.chart(data.drop(columns="Date"), "kpi", y="Sales", compare="previous_year")


def test_insights_under_a_chart(data: pd.DataFrame) -> None:
    fig = ts.chart(data, "line", x="Date", y="Sales", freq="month", insights=True)
    assert 1 <= len(fig.insights) <= 4
    page = fig.to_html()
    assert '<section class="ts-insights"' in page and "based on all data" in page
    assert fig.to_dict()["insights"][0]["text"] == fig.insights[0]["text"]
    assert "Insights shown under the chart:" in fig.explain()
    plain = ts.chart(data, "line", x="Date", y="Sales", freq="month")
    assert not plain.insights and "insights" not in plain.to_dict()


def test_analytics_options_round_trip_in_a_spec(data: pd.DataFrame) -> None:
    fig = ts.chart(data, "line", x="Date", y="Sales", freq="month", ref=["mean", 10], band=("p10", 20),
                   trend=True, forecast=3, season=12)  # fmt: skip
    spec = ts.ChartSpec.from_json(fig.spec.to_json())
    assert spec == fig.spec and spec.options["ref"] == ("mean", 10.0)


def test_analytics_never_change_the_input(data: pd.DataFrame) -> None:
    before = data.copy(deep=True)
    ts.chart(
        data,
        "line",
        x="Date",
        y="Sales",
        freq="month",
        forecast=6,
        trend=True,
        outliers=True,
        insights=True,
    )
    ts.chart(data, "kpi", y="Sales", compare="previous_month")
    ts.compare(data, "Profit", "Date")
    assert_unchanged(before, data)
