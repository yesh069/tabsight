# Trends, forecasts and insights

tabsight can add the "analytics pane" of a BI tool to a chart: trend lines, forecasts, reference lines, bands and flagged outliers. It can also compare periods and write plain-English insights. Everything is computed in Python by fixed rules, with no randomness, so the same data always gives the same result.

## Plain-English insights

`ts.insights` reads a table and states what the numbers show:

```python
import tabsight as ts

orders = ts.load("examples/superstore_sample.csv")
print(ts.insights(orders))
```

```text title="Output"
- Sales is down 6.5% in 2017 compared with 2016.
- Average Discount is up 1.0 pp in 2017 compared with 2016.
- Sales peaked in Jul 2014 ($9.3K, +20% vs Jun 2014).
- Quantity peaked in Jan 2017 (294, +36% vs Dec 2016).
- Standard Class makes up 62% of total Sales.
- Consumer makes up 55% of total Quantity.
- Sales was lowest in Mar 2014 ($3K).
- Quantity was lowest in Feb 2016 (113).
```

With no fields given, it picks up to three measures, three category columns and the first date column. Name them to focus it:

```python
found = ts.insights(orders, y="Profit", x="Sub_Category", date="Order_Date")
print(found)
```

```text title="Output"
- Profit is up 109% in 2017 compared with 2016.
- 2 of 13 Sub Category values have negative Profit: Chairs and Machines.
- Profit peaked in Jan 2014 ($920.6).
- Profit was lowest in Jan 2016 (-$828.9).
```

The rules, in the order they usually rank:

| Rule | Example |
|------|---------|
| Change on the previous period | "Sales is down 6.5% in 2017 compared with 2016." |
| Negative segments | "2 of 13 Sub Category values have negative Profit: Chairs and Machines." |
| Trend direction | "Monthly Sales rose about 1.1% per month from Jan 2019 to Dec 2022." |
| Peak and low | "Sales peaked in Jul 2014 ($9.3K, +20% vs Jun 2014)." |
| Seasonality | "Sales is high every December: in the top 3 months of each year from 2019 to 2022." |
| Concentration | "The top 3 State values make up 51% of Sales: California, New York and Texas." |
| Biggest contributor | "Standard Class makes up 62% of total Sales." |
| Outliers | "21 rows have unusually large Sales ($949.5 or more)." |

Every sentence states a fact, never a cause: tabsight says sales fell, not why. Rates such as a discount move in percentage points ("up 1.0 pp"), not in percent of themselves. A period that isn't over is left out of peaks, lows and trends, because it would look like a drop.

Each rule speaks only when the numbers are clear. A trend needs a straight line to explain at least 30% of the ups and downs, and a leader needs at least 15% of the total. Outliers must be beyond three box heights from the middle half, and no more than 2% of rows. `thresholds=` changes any of these; `tabsight.insight.THRESHOLDS` lists them all.

Add `insights=True` to a chart to list the facts about exactly its fields under it:

```python
fig = ts.chart(orders, "line", x="Order_Date", y="Sales", freq="month", insights=True)
for item in fig.insights:
    print(item["text"], f"({item['scope']})")
```

```text title="Output"
Sales is down 6.5% in 2017 compared with 2016. (based on all data)
Sales peaked in Jul 2014 ($9.3K, +20% vs Jun 2014). (based on all data)
Standard Class makes up 62% of total Sales. (based on all data)
Consumer makes up 54% of total Sales. (based on all data)
```

Each insight carries a tag saying which data it describes. Dashboards recompute them when the viewer filters and mark them "for current filters".

## Comparing periods

`ts.compare` sets a measure in the current period against the same window one period earlier:

```python
c = ts.compare(orders, "Sales", "Order_Date")
print(c)
print(c.as_of.date(), "-", c.as_of_source)
```

```text title="Output"
Sales: 2017 vs 2016: -6.5%
2017-12-31 - the end of the last complete year (the data has only 1 day of the next one)
```

The rules:

- **"Today" comes from the data, never the clock.** It is the latest date in the data, so the result is the same on every machine. `as_of="2017-06-30"` sets it yourself.
- **The same window, shifted back.** A year that isn't over is compared with the same days of last year, never with a whole year. A whole month is compared with the whole month before.
- **A sliver is not a period.** If the data runs only a few days into a new year, as this sample does (one order on 1 Jan 2018), the last complete year is compared instead, and `as_of_source` says so.
- **No data, no percentage.** When the earlier window is empty, the result says "no data for the previous year" rather than a misleading +100%.

```python
print(ts.compare(orders, "Sales", "Order_Date", as_of="2017-06-30"))
print(ts.compare(orders, "Sales", "Order_Date", compare="previous_month", as_of="2017-11-30"))
print(
    ts.compare(
        orders,
        "Sales",
        "Order_Date",
        compare="previous_quarter",
        fiscal_start=4,
        as_of="2017-06-30",
    )
)
print(ts.compare(orders, "Sales", "Order_Date", as_of="2014-12-31").note)
```

```text title="Output"
Sales: 2017 to Jun 30, 2017 vs 2016 to Jun 30, 2016: -24.1%
Sales: Nov 2017 vs Oct 2017: +0.2%
Sales: FY2018 Q1 vs FY2017 Q4: -15.7%
no data for the previous year
```

`compare=` takes `"previous_year"` (the default), `"previous_quarter"`, `"previous_month"`, or `"previous_period"` with `window=(start, end)`, which compares that window with the one just before it. Fiscal years follow `fiscal_start`.

A KPI card does the same with `compare=`:

```python
kpi = ts.chart(orders, "kpi", y="Sales", compare="previous_year")
print(kpi.kpi["value_text"], "|", kpi.kpi["detail"])
```

```text title="Output"
$63.1K | 2017 · ▼ 6.5% vs 2016
```

## Trend lines

`trend=True` fits a straight line by least squares, on a chart with dates or numbers along the x-axis:

```python
fig = ts.chart(orders, "line", x="Order_Date", y="Sales", freq="month", trend=True)
print([s["name"] for s in fig.option["series"]])
print(fig.lint().codes)
```

```text title="Output"
['Sales', 'Trend']
['incomplete_last_period', 'weak_trend']
```

`explain()` gives the line's R²: the share of the ups and downs it explains. Here it is 3%, so lint points out (`weak_trend`) that monthly sales have no clear direction. It also notes that the last month isn't over. On a scatter plot the trend line is a pattern, not proof that one thing causes the other, and the explanation says so.

A trend line between categories (regions, products) would invent an order, so tabsight refuses it.

## Forecasts

`forecast=6` estimates the next six periods:

```python
fig = ts.chart(orders, "line", x="Order_Date", y="Sales", freq="month", forecast=6)
print(fig.option["xAxis"]["data"][-7:])
print(next(d for d in fig.decisions if "estimate:" in d))
```

```text title="Output"
["Dec '17", "Jan '18", "Feb '18", "Mar '18", "Apr '18", "May '18", "Jun '18"]
the next 6 months are an estimate: Holt-Winters (additive) with a season of 12 months, fitted to 48 months (alpha 0.05, beta 0.05, gamma 0.05); dashed so it never passes for real data
```

- **Holt-Winters (additive)**, written in numpy. The season length comes from the date grain: 12 for months, 4 for quarters, 52 for weeks, 7 for days. `season=` overrides it. Yearly data, or `season` left out where there is none, uses Holt's linear trend.
- **At least two full seasons of history** (24 months for monthly data), or 6 periods without a season. With less, there is no forecast, only the note "not enough data for a forecast".
- **Dashed and labelled "Estimate"**, joined to the last real point, so it never passes for real data.
- **A shaded range** for a single line: the typical one-step error times 1.96, widening as errors add up further ahead. It is a rough guide, not a guarantee. Tooltips show the range for every line.
- **A period that isn't over is not used.** The estimate starts from the last complete period.
- **Never below zero** when the history never went below zero.
- **Repeatable.** The smoothing weights are chosen on a fixed grid by the smallest one-step error, with no random starts.

Lint warns when a forecast reaches further ahead than half the history behind it.

## Reference lines and bands

```python
fig = ts.chart(orders, "bar", x="Sub_Category", y="Profit", ref=["mean", 0], band=("p25", "p75"))
print([d["name"] for d in fig.option["series"][0]["markLine"]["data"]])
```

```text title="Output"
['Average', 'Target']
```

`ref=` takes `"mean"`, `"median"`, a percentile like `"p90"`, a number, or a list of up to four. `band=` shades between two of them. Both work on bars, lines, areas, scatter and lollipops. The values come from what the chart shows, so an average line is the average bar.

## Outliers

`outliers=True` circles points that sit far from the line's own trend: beyond 1.5 box heights of the middle half of the gaps (Tukey's fences). Points are flagged, never removed.

```python
fig = ts.chart(orders, "line", x="Order_Date", y="Profit", freq="month", outliers=True)
circled = fig.option["series"][0]["markPoint"]["data"]
print([fig.option["xAxis"]["data"][p["coord"][0]] for p in circled])
```

```text title="Output"
["Jan '16"]
```

`ts.analytics.outliers(values)` gives the same flags for any list of numbers, and `ts.analytics.linear_trend` and `ts.analytics.forecast` are there for your own use.
