# Dates and periods

Dates cause more quiet mistakes than anything else in business data. They're stored as text, in several formats in the same column, and nobody agrees whether `03/04` is March or April. This page covers how tabsight reads them and how to group by them.

## Reading dates

tabsight handles ISO dates (`2017-01-05`), numeric dates with any separator (`01/15/2017`, `15.01.2017`, `1-15-17`), dates with times, and written dates (`5 Jan 2017`, `January 2017`, `05-Jan-17`). A column that mixes separators, like `11-08-2016` next to `6/16/2016`, is fine.

The interesting part is day/month order. tabsight looks for proof in the data: a value like `16/06/2016` can only be day-first.

```python
import pandas as pd

import tabsight as ts

uk = pd.DataFrame({"Date": ["16/06/2016", "01/02/2016", "03/04/2016"], "Sales": [1.0, 2.0, 3.0]})
field = ts.profile(uk)["Date"]
print(field.dayfirst, field.reasons)
```

```text title="Output"
True ('text that reads as dates', '100% parse as %d/%m/%Y')
```

When nothing in the data settles it, tabsight assumes month-first and warns you, because a wrong guess here moves every number to the wrong month. Pass `dayfirst=True` (or set it once with `ts.set_defaults(dayfirst=True)`) when you know.

## Grouping by period

Use `freq=` with `ts.aggregate`:

```python
orders = ts.load("examples/superstore_sample.csv")
quarterly = ts.aggregate(orders, "Order_Date", "Sales", freq="quarter")
print(quarterly.values.head(4))
```

```text title="Output"
  Order_Date     Sales
0 2014-01-01  12909.32
1 2014-04-01  22017.30
2 2014-07-01  19969.01
3 2014-10-01  18426.13
```

The available grains are `year`, `quarter`, `month`, `week`, `day`, `hour`, `minute` and `second`. Each period is labelled by its start date; [formatting](formatting.md) turns that into `Q1 2014` when you display it. With several date columns, pass a dict: `freq={"Order_Date": "month", "Ship_Date": "week"}`.

## Fiscal years

Many organisations don't start their year in January. Tell tabsight which month yours starts:

```python
fiscal = ts.aggregate(orders, "Order_Date", "Sales", freq="year", fiscal_start=4)
for start, sales in fiscal.values.itertuples(index=False):
    print(
        ts.format_date(start, "year", fiscal_start=4),
        ts.format_number(sales, "currency", "compact"),
    )
```

```text title="Output"
FY2014 $12.9K
FY2015 $78.7K
FY2016 $70.3K
FY2017 $65.6K
FY2018 $47.7K
```

Fiscal years are named after the calendar year they end in, so FY2015 runs from April 2014 to March 2015. Quarters follow along: with an April start, FY2015 Q1 is April to June 2014.

Weeks start on Monday (the ISO standard) unless you pass `week_start="sunday"` or `"saturday"`.

## Months with no data

If nobody ordered anything in February, February still exists. `missing=` decides how it shows up:

```python
sparse = pd.DataFrame({"Date": ["01/15/2017", "03/02/2017"], "Sales": [10.0, 7.0]})
print(ts.aggregate(sparse, "Date", "Sales", freq="month").values)
print(ts.aggregate(sparse, "Date", "Sales", freq="month", missing="zero").values)
```

```text title="Output"
        Date  Sales
0 2017-01-01   10.0
1 2017-02-01    NaN
2 2017-03-01    7.0
        Date  Sales
0 2017-01-01   10.0
1 2017-02-01    0.0
2 2017-03-01    7.0
```

The default, `"gap"`, adds the month with no value, so a line chart shows a break rather than pretending sales were zero. `"zero"` suits bar charts. `"connect"` leaves the month out entirely.

## "Today" comes from your data

tabsight never reads the system clock. Anything relative to today, like future-date checks or year-to-date, uses the latest date in your data or an `as_of=` you pass in, so a report gives the same answer whenever you run it.
