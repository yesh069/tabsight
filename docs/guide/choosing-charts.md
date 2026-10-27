# Choosing a chart

Picking the chart is where most charts go wrong. A donut of average discounts, a stacked area of profit that dips below zero, a line drawn across regions as if West came after East. Each is a valid call to a plotting library, and each misleads.

tabsight has three tools for this. `ts.recommend` ranks the charts that fit the fields you picked and says why. `kind="auto"` draws the best of them. And every figure can tell you what it decided (`fig.explain()`) and check itself against the rules of good chart design (`fig.lint()`). All three are plain rules written in Python, with no model and no randomness, so the same data always gets the same answer.

## Ask for a recommendation

Give `ts.recommend` the same fields you'd give `ts.chart`: what to group by (`x`, and optionally `color`) and what to measure (`y`).

```python
import tabsight as ts

orders = ts.load("examples/superstore_sample.csv")
print(ts.recommend(orders, x="Sub_Category", y="Discount"))
```

```text title="Output"
Charts for 1 category field, 1 measure:

   90  bar             a measure by category: bars, largest first, are easiest to compare
   80  hbar            horizontal bars work too, and suit longer labels
   50  lollipop        a lighter alternative to bars  (phase 6)
   40  table           a table lists exact values

Ruled out:
       donut           these values are averages or distinct counts, which don't add up to a whole
       treemap         these values are averages or distinct counts, which don't add up to a whole
       line            a line implies an order between categories; use bars
```

Each suggestion has a score out of 100 and a reason. Charts that arrive in a later phase are still listed, marked with their phase, so you can see where the ranking is going. The "Ruled out" list is often the most useful part. Discount is a rate, so tabsight averages it, and averages don't add up to a whole. A donut or a treemap of them would show shares of a total that doesn't exist.

The same fields with a different measure get a different answer:

```python
recs = ts.recommend(orders, x="Region", y="Sales")
for r in recs:
    print(f"{r.score:>3}  {r.kind:<10} {'now' if r.available else f'phase {r.phase}'}")
print("best:", recs.best.kind)
print(recs.why_not("line"))
```

```text title="Output"
 90  bar        now
 80  hbar       now
 76  donut      now
 50  lollipop   phase 6
 40  table      now
best: bar
a line implies an order between categories; use bars
```

`recs.best` is the top chart that can be drawn today. `recs.why_not(kind)` answers the question people actually ask: "why didn't it pick a line?"

## What the rules look at

The rules start from what the fields are and then look at the data itself:

- **Dates.** A date and a measure is a trend, so a line comes first. The date grain is chosen from the span: days for a couple of months, months for a few years, quarters up to ten years, then years.
- **How many values a category has.** Up to 6 parts can be a donut. More than 15 bars, or labels longer than 16 characters, turn horizontal. More than 8 lines keep the biggest 6 and group the rest as Other.
- **Whether the measure adds up.** Sums and counts do. Averages, medians and distinct counts don't, which rules out donuts, treemaps and stacked charts.
- **Negative values.** A total that goes below zero can't be a slice, an area or part of a stack.
- **IDs.** Grouping by an order number gives one bar per row, so a table wins.
- **Nesting.** When every sub-category belongs to one category, a treemap shows both levels.
- **Units.** Two measures in different units (money and a count) need two axes.

When two categories are picked and the colour field has many values, tabsight swaps them so the field with fewer values goes in the colours.

```python
recs = ts.recommend(orders, x="Segment", y="Sales", color="Sub_Category")
print(recs.best.kind, recs.best.spec.x, "/", recs.best.spec.color)
print(recs.best.reason)
```

```text title="Output"
stacked_bar Sub_Category / Segment
totals per Sub_Category, split by Segment; Segment has fewer values, so it goes in the colours
```

## Let it draw: `kind="auto"`

```python
fig = ts.chart(orders, "auto", x="Order_Date", y="Sales", color="Region")
print(fig.kind, fig.spec.options)
```

```text title="Output"
multi_line {'freq': 'quarter'}
```

The x and colour fields come from the recommendation, so it doesn't matter which slot you put the date in. Any argument you give still wins: `freq="month"` or `top=3` is kept as you asked.

## What did it decide? `fig.explain()`

Every figure, automatic or not, records each choice made on your behalf:

```python
print(fig.explain())
```

```text title="Output"
Sum of Sales by Order Date (multi-line chart)

- multi line chosen automatically (score 92): one line per Region; next best: stacked area (80)
- Sales is summed: name suggests money
- Order_Date is grouped by quarter (to suit the time span) and shown in time order
- lines are straight between real data points, never smoothed
- a missing period is left as a gap
- Region values take colours from the classic10 palette in sorted order, so each value keeps its colour in every chart
- Sales is formatted as currency in USD for en_US; short on the axis, in full in tooltips

Notes shown on the chart:
- the last quarter (Q1 2018) only has data up to Jan 1, 2018, so it looks low because it is incomplete
- 2 empty quarter(s) shown as gaps
```

The notes at the bottom are the ones printed on the chart itself. The decisions above them are only in `explain()`, so the page stays uncluttered.

## Check a chart: `fig.lint()`

tabsight's defaults follow the rules, so a default chart is usually clean. The linter matters when a choice was forced, or when the ECharts option was changed with `fig.update()`.

```python
fig = ts.chart(orders, "donut", x="Sub_Category", y="Discount", top=12)
print(fig.lint())
```

```text title="Output"
warning pie_too_many_slices
        13 slices are too many to compare
        Fix: keep the 7 biggest and group the rest, or use horizontal bars
warning pie_not_additive
        Discount values don't add up to a whole, so the slices mean nothing
        Fix: use bars
```

```python
fig = ts.chart(orders, "line", x="Order_Date", y="Sales", freq="quarter")
smooth = fig.update({"series": [{"smooth": True}], "yAxis": {"min": 20000}})
report = smooth.lint()
print(report.codes, report.ok)
```

```text title="Output"
['smoothed_line', 'incomplete_last_period'] False
```

The axis starting at 20,000 isn't flagged: a line is about change, so its axis may follow the data. On bars it would be a warning.

Warnings are mistakes worth fixing. Info items are things to be aware of: that last quarter still isn't over. Each issue also has a `change`, the `ts.chart` arguments that apply the fix, when one exists:

```python
for issue in ts.chart(orders, "bar", x="Region", y="Discount", agg="sum").lint():
    print(issue.code, issue.change)
```

```text title="Output"
sum_of_rates {'agg': 'mean'}
```

Pass `ignore=[...]` to skip rules you've decided don't apply. In a pipeline, `fig.lint(strict=True)` raises `ChartLintError` on any warning, so a misleading chart never ships. The full list is in [lint rules](../reference/lint-rules.md).

## How good are the recommendations?

The rules are checked against 70 labelled cases in [`tests/recommend_cases.py`](https://github.com/yesh069/tabsight/blob/main/tests/recommend_cases.py). Each case lists the fields, the chart a careful analyst would draw today, and the chart they'd draw once every kind exists. The labels come from chart-design practice, not from tabsight's output. Two labels changed after review, and the comments say why.

All 70 pass. Every chart that `kind="auto"` draws for them also passes `lint()` with no warnings, so tabsight never recommends something its own linter would flag. This is our own regression set, written by the same people as the rules. It shows the rules do what we meant, not that they match what every analyst would choose. If you disagree with a case, please open an issue.
