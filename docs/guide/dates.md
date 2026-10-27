# Dates and periods

## Reading dates

Dates are often stored as text. tabsight reads them without changing your data:

- **ISO and numeric dates**: `2017-01-05`, `01/15/2017`, `15.01.2017`, `1-15-17`, with or without a time.
- **Mixed separators** in one column (`11-08-2016` and `6/16/2016`) are normalised.
- **Text months**: `5 Jan 2017`, `Jan 5, 2017`, `January 2017`, `05-Jan-17`, `2017-01`.
- **Whole-number years** (`2015`) in a column called Year or FY.

### Day or month first?

`01/02/2017` is ambiguous. tabsight:

1. looks for proof in the data: any first number above 12 means day-first; any second number above 12 means month-first;
2. if the data cannot decide, uses `dayfirst=` if you gave it;
3. otherwise assumes month-first and **warns**.

```python
import pandas as pd

import tabsight as ts

df = pd.DataFrame({"Date": ["16/06/2016", "01/02/2016"], "Sales": [1.0, 2.0]})
print(ts.profile(df)["Date"].dayfirst)  # True: 16 cannot be a month
```

## Grouping by period

`freq=` sets the grain for date dimensions in `ts.aggregate`:

```python
df = ts.load("examples/superstore_sample.csv")
monthly = ts.aggregate(df, "Order_Date", "Sales", freq="month")
print(monthly.values.head())
```

Grains: `year`, `quarter`, `month`, `week`, `day`, `hour`, `minute`, `second`. Each period is labelled by its start date. Use `freq={"Order_Date": "quarter", "Ship_Date": "month"}` for different grains per column.

`ts.bucket` gives the same period starts for any date values:

```python
dates = pd.Series(pd.to_datetime(["2017-02-14", "2017-05-31"]))
print(ts.bucket(dates, "quarter").tolist())
```

## Fiscal years

```python
fy = ts.aggregate(df, "Order_Date", "Sales", freq="year", fiscal_start=4)
print(fy.values)
print(ts.format_date(fy.values["Order_Date"].iloc[0], "year", fiscal_start=4))  # e.g. FY2014
```

Fiscal years are named by the calendar year they end in: FY2018 runs from April 2017 to March 2018. Quarters follow the fiscal year (`FY2018 Q1` = April–June 2017).

## Weeks

Weeks start on Monday (ISO) by default; use `week_start="sunday"` or `"saturday"`.

## Missing periods

A month with no orders is still a month. `missing=` decides how it shows:

| `missing=` | Result |
|------------|--------|
| `"gap"` (default) | The period is added with a missing value (lines show a gap) |
| `"zero"` | The period is added with 0 for sums and counts (bars show nothing) |
| `"connect"` | Missing periods are left out |

```python
sparse = pd.DataFrame({"d": ["01/15/2017", "03/02/2017"], "Sales": [10.0, 7.0]})
print(ts.aggregate(sparse, "d", "Sales", freq="month", missing="zero").values)
```

## "Today" is never the clock

Anything relative to "today" uses the latest date in the data or an explicit `as_of=`, so results do not change depending on when you run them.
