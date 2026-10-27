import math

import pandas as pd
import pytest

from tabsight.aggregate import aggregate
from tabsight.tablecalc import table_calc
from tabsight.warnings import DataWarning, InvalidSpecError


@pytest.fixture
def monthly() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Month": pd.to_datetime(
                ["2017-01-05", "2017-02-05", "2017-03-05", "2017-01-09", "2017-02-09", "2017-03-09"]
            ),
            "Region": ["W", "W", "W", "E", "E", "E"],
            "Sales": [10.0, 20.0, 30.0, 1.0, 2.0, 4.0],
        }
    )


def col(res: object, name: str) -> list[float]:
    return res.frame[name].tolist()  # type: ignore[attr-defined]


def test_running_total_restarts_per_region(monthly: pd.DataFrame) -> None:
    res = aggregate(monthly, ["Month", "Region"], "Sales", freq="month")
    out = table_calc(res, "running_total")
    f = out.frame.sort_values(["Region", "Month"])
    assert f["Sales (running total)"].tolist() == [1.0, 3.0, 7.0, 10.0, 30.0, 60.0]
    assert any("along 'Month'" in n for n in out.notes)


def test_pct_of_total_filtered_and_fixed(monthly: pd.DataFrame) -> None:
    res = aggregate(monthly, "Region", "Sales")
    shown = table_calc(res, "pct_of_total").frame.set_index("Region")[
        "Sales (% of total, shown rows)"
    ]
    assert shown["W"] == pytest.approx(60 / 67)
    fixed = table_calc(res, "pct_of_total", fixed_total=134.0).frame.set_index("Region")
    assert fixed["Sales (% of total, fixed total)"]["W"] == pytest.approx(60 / 134)


def test_rank_difference_and_moving_average(monthly: pd.DataFrame) -> None:
    res = aggregate(monthly[monthly.Region == "W"], "Month", "Sales", freq="month")
    assert col(table_calc(res, "rank"), "Sales (rank)") == [3, 2, 1]
    diff = col(table_calc(res, "difference"), "Sales (difference)")
    assert math.isnan(diff[0]) and diff[1:] == [10.0, 10.0]
    pct = col(table_calc(res, "pct_difference"), "Sales (% difference)")
    assert pct[1:] == [1.0, 0.5]
    assert col(table_calc(res, "moving_avg:2"), "Sales (moving avg 2)") == [10.0, 15.0, 25.0]


def test_rank_ties_share_the_best_rank() -> None:
    df = pd.DataFrame({"g": ["a", "b", "c"], "v": [5.0, 5.0, 1.0]})
    res = aggregate(df, "g", "v")
    ranks = table_calc(res, "rank").frame.set_index("g")["v (rank)"]
    assert ranks.to_dict() == {"a": 1, "b": 1, "c": 3}


def test_meaningless_combinations_warn_and_bad_calcs_fail(monthly: pd.DataFrame) -> None:
    res = aggregate(monthly, "Region", {"column": "Sales", "agg": "mean"})
    with pytest.warns(DataWarning, match="not meaningful"):
        table_calc(res, "running_total")
    for bad in ("moving_avg:1", "moving_avg:9999", "evil", "rank;drop"):
        with pytest.raises(InvalidSpecError):
            table_calc(res, bad)
    with pytest.raises(InvalidSpecError):
        table_calc(res, "rank", measure="Nope")
    with pytest.raises(InvalidSpecError):
        table_calc(res, "rank", along="Month")


def test_table_calc_does_not_change_the_input_result(monthly: pd.DataFrame) -> None:
    res = aggregate(monthly, "Region", "Sales")
    before = res.frame.copy()
    table_calc(res, "pct_of_total")
    pd.testing.assert_frame_equal(before, res.frame)
