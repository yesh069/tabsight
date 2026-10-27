import json

import numpy as np
import pandas as pd
import pytest

from tabsight.check import check
from tabsight.clean import clean
from tabsight.warnings import CleanWarning, InvalidSpecError

from .conftest import assert_unchanged


@pytest.fixture
def messy() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Region": ["West ", "west", "West", "East", "N/A", "East", "Easst", "West"] * 3,
            "Sales": ["$1,200.00", "$35.50", "($20.00)", "$10", "$5", "$7", "$8", "$9"] * 3,
            "Order_Date": ["01/02/2017", "03/04/2017", "05/06/2017", "07/08/2017"] * 6,
            "Ship_Date": ["01/03/2017", "03/01/2017", "05/07/2017", "07/09/2017"] * 6,
            "Qty": [1, 2, 3, 4, 5, 6, 7, 8] * 3,
        }
    )


def codes(report: object) -> set[str]:
    return {i.code for i in report.issues}  # type: ignore[attr-defined]


def test_check_finds_issues_and_changes_nothing(messy: pd.DataFrame) -> None:
    before = messy.copy(deep=True)
    report = check(messy)
    assert_unchanged(before, messy)
    found = codes(report)
    assert {
        "untrimmed",
        "case_variants",
        "placeholders",
        "numbers_as_text",
        "date_order",
        "duplicate_rows",
    } <= found
    assert 0 <= report.score < 100
    assert "Quality score" in report.show()
    json.dumps(report.to_dict())  # serialisable


def test_check_typos_outliers_and_future_dates() -> None:
    df = pd.DataFrame(
        {
            "City": ["Dublin"] * 40 + ["Dubiln"],
            "Amount": [*list(np.linspace(10, 20, 40)), 10000.0],
            "When": pd.to_datetime(["2020-01-01"] * 40 + ["2030-01-01"]),
        }
    )
    report = check(df, as_of="2025-01-01")
    found = codes(report)
    assert {"possible_typos", "outliers", "future_dates"} <= found
    assert "future_dates" not in codes(check(df))  # no clock without as_of


def test_check_empty_and_infinite() -> None:
    assert codes(check(pd.DataFrame())) == {"empty"}
    assert "infinite" in codes(check(pd.DataFrame({"x": [1.0, np.inf, 2.0]})))


def test_safe_mode_applies_only_safe_fixes(messy: pd.DataFrame) -> None:
    before = messy.copy(deep=True)
    out, report = clean(messy)
    assert_unchanged(before, messy)
    assert out is not messy
    assert "N/A" not in out["Region"].dropna().tolist()
    assert out["Region"].iloc[0] == "West"  # trimmed
    assert "west" in out["Region"].tolist()  # case merge is only suggested
    assert out["Sales"].dtype == "float64" and out["Sales"].iloc[2] == -20.0
    # ambiguous day/month order: dates are only suggested
    assert not pd.api.types.is_datetime64_any_dtype(out["Order_Date"])
    actions = {s.action for s in report.suggestions}
    assert {"merge_case", "parse_dates"} <= actions
    assert "Reported only" in report.show()


def test_auto_mode_and_apply_undo(messy: pd.DataFrame) -> None:
    out, report = clean(messy, mode="auto", dayfirst=True)
    assert set(out["Region"].dropna()) == {"West", "East", "Easst"}
    assert out["Order_Date"].iloc[0] == pd.Timestamp("2017-02-01")
    restored = report.undo("Region")
    assert restored["Region"].tolist() == messy["Region"].tolist()

    _, safe_report = clean(messy)
    sid = next(s.id for s in safe_report.suggestions if s.action == "merge_case")
    merged = safe_report.apply(sid)
    assert "west" not in merged["Region"].tolist()
    with pytest.raises(KeyError):
        safe_report.apply("nope")


def test_off_mode_changes_nothing(messy: pd.DataFrame) -> None:
    out, report = clean(messy, mode="off")
    assert_unchanged(messy, out)
    assert out is not messy
    assert not report.applied and report.suggestions


def test_dedupe_only_when_asked(messy: pd.DataFrame) -> None:
    out, _ = clean(messy)
    assert len(out) == len(messy)
    out2, report = clean(messy, dedupe=True)
    assert len(out2) < len(messy)
    assert any(c.action == "dedupe" and c.count > 0 for c in report.applied)


def test_excel_serial_dates_suggested() -> None:
    df = pd.DataFrame({"Invoice_Date": [43831, 43832, 43900]})
    out, _report = clean(df, mode="auto")
    assert out["Invoice_Date"].iloc[0] == pd.Timestamp("2020-01-01")


def test_decisions_round_trip_on_new_data(messy: pd.DataFrame) -> None:
    _, report = clean(messy, mode="auto", dayfirst=True)
    saved = report.to_json()
    next_month = messy.copy()
    next_month.loc[0, "Region"] = "  west  "
    out, _again = clean(next_month, decisions=saved)
    assert out["Region"].iloc[0] == "West"
    assert out["Order_Date"].iloc[0] == pd.Timestamp("2017-02-01")
    with pytest.warns(CleanWarning, match="missing column"):
        clean(next_month.drop(columns=["Qty", "Region"]), decisions=saved)


@pytest.mark.parametrize(
    "bad",
    [
        {"tabsight_clean": 2, "actions": []},
        {"tabsight_clean": 1, "actions": [{"action": "rm -rf"}]},
        {
            "tabsight_clean": 1,
            "actions": [{"action": "parse_dates", "column": "a", "format": "%(evil)s"}],
        },
        {
            "tabsight_clean": 1,
            "actions": [{"action": "merge_case", "column": "a", "mapping": {"a": 1}}],
        },
        {"tabsight_clean": 1, "actions": [{"action": "trim", "column": "a", "code": "x"}]},
        {"tabsight_clean": 1, "actions": "nope"},
        {"tabsight_clean": 1, "actions": [], "extra": True},
    ],
)
def test_malicious_decisions_are_rejected(bad: object) -> None:
    with pytest.raises(InvalidSpecError):
        clean(pd.DataFrame({"a": ["x"]}), decisions=bad)


def test_bad_mode() -> None:
    with pytest.raises(InvalidSpecError):
        clean(pd.DataFrame({"a": [1]}), mode="aggressive")
