# How tabsight thinks

tabsight makes a lot of decisions for you. This page explains the few rules those decisions follow, so the defaults stop being surprising.

## It suggests; you decide

Every decision tabsight makes about your data is a suggestion with a reason attached. You can read the reason and you can change the decision in one argument. Nothing is hidden behind a setting you can't reach.

That's also why tabsight warns rather than stops. If your data has two currencies in one column, you get a warning and the totals are split by currency; you don't get an exception at 5 pm on a Friday. If you'd rather it did stop, turn on strict mode with `ts.set_defaults(strict=True)`.

## It never changes your data

Every function works on a copy. You can hand tabsight the DataFrame your whole notebook depends on and get it back untouched. This is checked by a test that calls every public function and compares the input before and after.

The one place values change is cleaning, and that's opt-in. tabsight separates *reading* data from *changing* it:

- Reading happens all the time. It's how tabsight knows `"01/15/2017"` is a date and `"$1,234.50"` is a number. It works on a temporary copy, so your data doesn't change.
- Cleaning only happens when you call `ts.clean`. It returns a new DataFrame and a report listing every change, and any change can be undone.

## Roles

Each column gets one role, and the role decides what tabsight is willing to do with it. A *dimension* is something you group by, such as Region. A *measure* is something you add up or average, such as Sales. *Time* columns are dates, or whole-number years. An *id* is counted but never summed, which is the whole point of recognising it. *coord* is latitude or longitude, and *text* is long free text that nobody charts.

## Exact numbers, even after filtering

This is the rule that shapes the most code. When a dashboard viewer filters to one region, every chart has to recompute. Sums are easy: add the remaining sums. Averages are not. The average of three regional averages is not the average of the orders in those regions, and medians can't be recombined at all.

So tabsight never stores a finished average. It stores the *parts*: a sum and a count for a mean, Σ(weight × value) and Σweight for a weighted average, and the values themselves for a median. Recombining the parts after a filter gives exactly what you'd get from the raw rows. Here's what that looks like:

```python
import tabsight as ts
from tabsight.aggregate import build_parts, combine_parts

orders = ts.load("examples/superstore_sample.csv")
discount = ts.Measure("Discount", "mean")

parts = build_parts(orders, ["Region", "Segment"], [discount])
west = parts[parts["Region"] == "West"]
print(combine_parts(west, ["Segment"], [discount])[["Segment", "Discount"]])
print(orders[orders.Region == "West"].groupby("Segment").Discount.mean())
```

```text title="Output"
       Segment  Discount
0  Home Office      0.14
1     Consumer      0.14
2    Corporate      0.15
Segment
Consumer       0.14
Corporate      0.15
Home Office    0.14
Name: Discount, dtype: float64
```

The two results match. A property-based test checks the same thing for thousands of random datasets and filters, across all eight aggregations.

## Same input, same output

There's no randomness, no reading of the clock, and no network. Ties are broken by name, so "same input, same output" holds even for sorting and colours. Anything relative to "today" uses the latest date in your data, or an `as_of=` date you pass in. A report you run on Monday matches the one you run on Friday.
