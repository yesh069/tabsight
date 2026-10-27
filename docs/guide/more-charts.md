# More chart types

Beyond bars and lines, tabsight draws relationships, distributions, parts of a whole, flows and single values. Every one follows the same rules as the everyday kinds: numbers are aggregated exactly and formatted by their unit, labels are readable, and `fig.explain()` says what was decided.

```python
import pandas as pd

import tabsight as ts

orders = ts.load("examples/superstore_sample.csv")
```

## Relationships: scatter and bubble

With two number columns, a scatter draws one dot per row. The axes fit the data rather than start at zero, because position matters here, not length:

```python
fig = ts.chart(orders, "scatter", x="Sales", y="Profit", color="Category")
print(fig.title, "|", [s["name"] for s in fig.option["series"]])
```

```text title="Output"
Profit vs Sales by Category | ['Furniture', 'Office Supplies', 'Technology']
```

With a category on x and two measures, it draws one dot per category instead, aggregated exactly. A third measure makes it a bubble chart, where circle area grows with the value:

```python
fig = ts.chart(orders, "bubble", x="Sub_Category", y=["Sales", "Profit", "Quantity"])
print(fig.title)
```

```text title="Output"
Profit vs Sales by Sub Category
```

More than 5,000 points are sampled evenly, and the chart says so.

## Distributions: histogram and box plot

```python
fig = ts.chart(orders, "histogram", x="Sales")
print(fig.decisions[1])
```

```text title="Output"
bar width from the spread of the middle half of the data (Freedman-Diaconis), rounded: 21 bars
```

The bar width is chosen from the spread of the middle half of the data and rounded, so the edges are numbers people use. `bins=20` asks for about 20 bars and `bin_width=100` fixes the width.

A box plot shows the middle half of the values as a box with the median inside. Whiskers reach the furthest values within 1.5 times the box height, and dots beyond them are outliers. Hover a box to see all five numbers.

```python
fig = ts.chart(orders, "boxplot", x="Category", y="Profit")
low, q1, median, q3, high = fig.option["series"][0]["data"][0]["value"]
print(f"median {median:.2f}, middle half {q1:.2f} to {q3:.2f}")
```

```text title="Output"
median 9.88, middle half -28.27 to 56.18
```

## Lines over a number

When x is a number rather than a date or a category, it runs along a real number axis, so points sit at their true distances. This is how a sine wave becomes a curve rather than 126 category labels:

```python
import numpy as np

wave = pd.DataFrame({"angle": np.arange(0, 6.3, 0.05)})
wave["sine"] = np.sin(wave["angle"])
fig = ts.chart(wave, "line", x="angle", y="sine")
print(fig.title, "|", fig.option["xAxis"]["type"], "axis,", len(fig.option["series"][0]["data"]), "points")
```

```text title="Output"
sine by angle | value axis, 126 points
```

Lines with more than 2,000 points are thinned with LTTB, which keeps peaks and dips, and the chart says how many points it shows.

## Parts of a whole: treemap, sunburst, waterfall, funnel

A treemap or sunburst takes one or more levels in `x`. Both need a total that adds up, so an average is refused with a reason:

```python
fig = ts.chart(orders, "treemap", x=["Category", "Sub_Category"], y="Sales")
print([(d["name"], d["note"]) for d in fig.option["series"][0]["data"]])
try:
    ts.chart(orders, "treemap", x="Category", y="Discount")
except ts.warnings.InvalidSpecError as error:
    print(error)
```

```text title="Output"
[('Technology', '40.4% of the total'), ('Office Supplies', '31.1% of the total'), ('Furniture', '28.6% of the total')]
a treemap shows parts of a whole, but Discount is averaged, which doesn't add up; use bars
```

A waterfall walks from one total to another. Each bar starts where the last ended, blue adds and orange takes away, and the last bar is the total from zero. Steps keep the order they appear in the data:

```python
bridge = pd.DataFrame(
    {"Step": ["Revenue", "Costs", "Marketing", "Grants", "Tax"], "Amount": [1000, -420, -180, 60, -45]}
)
fig = ts.chart(bridge, "waterfall", x="Step", y="Amount")
print([(d["name"], d["value"][4]) for d in fig.option["series"][0]["data"]])
```

```text title="Output"
[('Revenue', 1000.0), ('Costs', 580.0), ('Marketing', 400.0), ('Grants', 460.0), ('Tax', 415.0), ('Total', 415.0)]
```

A funnel's tooltip shows how much of the previous and of the first stage each one keeps:

```python
stages = pd.DataFrame({"Stage": ["Visited", "Signed up", "Paid"], "Users": [12000, 3400, 420]})
fig = ts.chart(stages, "funnel", x="Stage", y="Users")
print([d.get("note") for d in fig.option["series"][0]["data"]])
```

```text title="Output"
[None, '28% of the previous stage; 28% of the first', '12% of the previous stage; 4% of the first']
```

## Ranking: Pareto

Bars largest first, with a line that adds them up to 100% and a dashed guide at 80%:

```python
fig = ts.chart(orders, "pareto", x="Sub_Category", y="Sales")
print(fig.decisions[-2])
```

```text title="Output"
bars largest first; the line adds them up: 10 of 13 make 80% of the total
```

## Flows and grids: Sankey and heatmaps

A Sankey diagram draws flows from a `source` column to a `target` column, with band width showing the value. A heatmap puts `x` across, `color` down and colours each cell by the measure. Negative values get a diverging scale. A calendar heatmap gives each day a square:

```python
fig = ts.chart(orders, "sankey", source="Segment", target="Category", y="Sales")
print(len(fig.option["series"][0]["links"]), "flows")
fig = ts.chart(orders, "heatmap", x="Order_Date", color="Category", y="Profit", freq="year")
print(fig.decisions[-2])
```

```text title="Output"
9 flows
columns are Order_Date, rows are Category; darker means bigger
```

## Against a goal: bullet and gauge; two measures: combo

```python
reps = pd.DataFrame({"Rep": ["Ann", "Bo"], "Sales": [120.0, 80.0], "Target": [100.0, 100.0]})
fig = ts.chart(reps, "bullet", x="Rep", y="Sales", goal="Target")
print([d["note"] for d in fig.option["series"][1]["data"]])
fig = ts.chart(orders, "combo", x="Region", y=["Sales", "Quantity"])
print(next(d for d in fig.decisions if "two axes" in d))
```

```text title="Output"
['goal $100.00 (120% of it)', 'goal $100.00 (80% of it)']
two axes because the units differ (count, currency): bars on the left, lines on the right
```

A `goal` can be one number for everything or a column with one per row. A combo draws the first measure as bars and the others as lines, on a second axis when the units differ. One axis would flatten the smaller one.
