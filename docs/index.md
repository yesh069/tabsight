---
template: home.html
hide:
  - navigation
  - toc
---

Most chart tools take your columns at face value. They sum discounts, treat zip codes as numbers, and average averages when you filter. tabsight starts one step earlier: it works out what each column actually is, tells you why it thinks so, and only then does the maths.

Here it is on a small sales file that ships with the repository:

```python
import tabsight as ts

orders = ts.load("examples/superstore_sample.csv")
print(ts.profile(orders))
```

```text title="Output"
Profile: 1,200 rows, 18 columns

Column        Role       Unit       Agg     Why
Row_ID        id         none       countd  name says it is an ID/code; never summed
Order_ID      id         none       countd  name says it is an ID/code
Order_Date    time       none       none    text that reads as dates; 100% parse as %m/%d/%Y
Ship_Date     time       none       none    text that reads as dates; 100% parse as %m/%d/%Y
Ship_Mode     dimension  none       none    categories
Customer_ID   id         none       countd  name says it is an ID/code
Segment       dimension  none       none    categories
Country       dimension  none       none    categories
City          dimension  none       none    categories
State         dimension  none       none    categories
Postal_Code   id         none       countd  name says it is an ID/code
Region        dimension  none       none    categories
Category      dimension  none       none    categories
Sub_Category  dimension  none       none    categories
Sales         measure    currency   sum     name suggests money
Quantity      measure    count      sum     name suggests a count
Discount      measure    percent    mean    name suggests a percentage; values stored as fractions (0.15 = 15%); averaged, because totals of rates/prices/scores are meaningless
Profit        measure    currency   sum     name suggests money

Hierarchies:
  Category -> Sub_Category
  Region -> City
  Region -> State
```

Nothing was configured. The IDs will never be added up, the discount will be averaged rather than summed, and the dates were read as month-first because a value like `01/15` settles it. Every one of those decisions can be changed with one argument, and none of them touched `orders` itself.

## The numbers stay right when people filter

Dashboards get filtered. Re-adding sums after a filter is easy; re-averaging an average is not, and it is where hand-built dashboards quietly go wrong. tabsight keeps every aggregation in a form that can be recombined exactly:

```python
by_region = ts.aggregate(orders, "Region", ["Sales", "Discount"])
print(by_region.values)
```

```text title="Output"
    Region     Sales  Discount
0     East  87642.84      0.17
1     West  79286.84      0.15
2  Central  64667.90      0.15
3    South  43661.26      0.17
```

## It formats numbers the way a finance team would

```python
print(ts.format_number(2_297_200.86, "currency", "compact"))
print(ts.format_number(1234.5, "currency", locale="de_DE", currency="EUR", decimals=2))
print(ts.format_number(1_230_000, "currency", "compact", locale="en_IN", currency="INR"))
```

```text title="Output"
$2.3M
1.234,50 €
₹12.3L
```

## Where to start

If you have five minutes, the [quickstart](getting-started/quickstart.md) walks through one file from loading to calculated fields. If you want to know why tabsight behaves the way it does, read [how tabsight thinks](getting-started/concepts.md). The [user guide](guide/loading-data.md) covers each feature in depth.

tabsight is in early development. Reading, profiling, cleaning, formatting, exact aggregation and the first [charts](guide/charts.md) are done; the chart recommender is next, then world maps and dashboards. The [roadmap](project/roadmap.md) has the details.
