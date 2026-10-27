# Making charts

`ts.chart` turns a DataFrame into a finished chart: grouped, summarised, formatted and styled, with a reason for anything it decided on your behalf. Tell it what to group by (`x`), what to measure (`y`), and optionally what to split by (`color`).

```python
import tabsight as ts

orders = ts.load("examples/superstore_sample.csv")
fig = ts.chart(orders, "bar", x="Region", y="Sales")
print(fig.title)
print(fig.kind, "|", fig.option["series"][0]["data"])
```

```text title="Output"
Sum of Sales by Region
bar | [87642.84, 79286.84, 64667.9, 43661.26]
```

The title was written for you, the regions are sorted largest first, and the axis, labels and tooltips are already formatted as money. To look at it, write it to a file and open it in any browser:

```python
# not run
fig.to_html("sales_by_region.html")
```

The file is a single page with everything inside it, chart library included, so it opens offline and can be emailed as is. In Jupyter, a figure on the last line of a cell displays itself. With the `static` extra installed, `fig.to_svg("sales_by_region.svg")` saves a still picture instead, for slides and documents.

## The everyday kinds

This page covers the everyday kinds: bars (`bar`, `hbar`, `grouped_bar`, `stacked_bar`, `stacked100_bar`), lines (`line`, `multi_line`, `area`, `stacked_area`, `sparkline`), `donut`, `kpi` and `table`. Scatter plots, treemaps, waterfalls, Sankey diagrams and the rest of the [33 kinds](../reference/chart-kinds.md) are in [more chart types](more-charts.md), and maps have [their own page](maps.md).

```python
monthly = ts.chart(orders, "multi_line", x="Order_Date", y="Sales", color="Region", freq="quarter")
print(monthly.title)
for note in monthly.notes:
    print("-", note)
```

```text title="Output"
Sum of Sales by Order Date
- the last quarter (Q1 2018) only has data up to Jan 1, 2018, so it looks low because it is incomplete
- 2 empty quarter(s) shown as gaps
```

That first note matters. The sample data ends on 1 January 2018, so the last quarter holds a single day of sales and the lines plunge. Without the note, anyone reading the chart would assume sales collapsed.

## Decisions it makes for you

A few rules from BI practice are applied by default:

- **Every label is readable.** Category labels are never skipped. If they're long or there are many of them, a bar chart turns horizontal instead, and the figure's notes say so.
- **Lines are never smoothed.** Smoothing invents values between your data points.
- **Bars start at zero, lines don't have to.** A bar's length is its value, so cutting the axis would mislead. A line is about change, so its axis follows the data.
- **One series, one colour.** Colour only changes when it means something. When it does, the same value gets the same colour in every chart.
- **Few slices.** A donut keeps the seven largest slices and folds the rest into a grey "Other".

```python
import pandas as pd

products = pd.DataFrame(
    {
        "Product": [
            "Executive leather office chair",
            "Standing desk with oak finish",
            "Wireless ergonomic keyboard",
            "27-inch 4K monitor",
        ],
        "Sales": [12_400.0, 9_850.0, 4_320.0, 7_990.0],
    }
)
long_names = ts.chart(products, "bar", x="Product", y="Sales")
print(long_names.kind, "|", long_names.notes)
```

```text title="Output"
hbar | ('drawn as horizontal bars so every label can be read',)
```

## KPI cards and tables

```python
kpi = ts.chart(orders, "kpi", y="Sales")
print(kpi.kpi["value_text"], "|", kpi.kpi["value_full"])

table = ts.chart(orders, "table", x=["Category", "Sub_Category"], y=["Sales", "Discount"])
print([c["name"] for c in table.table["columns"]])
for row in table.table["rows"][:5]:
    print(row)
```

```text title="Output"
$275.3K | $275,259
['Category', 'Sub Category', 'Sum of Sales', 'Avg Discount']
['Technology', 'Accessories', '$28,724', '18.9%']
['', 'Copiers', '$31,433', '17.9%']
['', 'Machines', '$26,987', '17.5%']
['', 'Phones', '$23,962', '11.4%']
['Office Supplies', 'Art', '$17,238', '13.6%']
```

Tables format each column consistently, right-align the numbers, and show a parent value like "Technology" once rather than on every row, the way a pivot table does.

## Overriding the defaults

Most of what you'd want to change is an argument: `title=`, `subtitle=`, `sort=`, `top=`, `agg=`, `unit=`, `currency=`, `decimals=`, `format=` (a [pattern](formatting.md#your-own-pattern)), `colors=` (pin colours), `theme=` and `height=`.

For anything else there's `fig.update`, which merges your changes into the underlying ECharts option:

```python
quiet = fig.update({"animation": False, "grid": {"left": 40}})
print(quiet.option["animation"], quiet.option["grid"]["left"])
```

```text title="Output"
False 40
```

`update` accepts plain values only. It refuses `formatter` strings, because an ECharts formatter string drops data into tooltips without escaping it, which is exactly how a chart gets turned into an attack.

## Using a chart in your own web page

`fig.to_dict()` is plain JSON. Serve it from your backend, load ECharts and the tabsight runtime (`ts.runtime_js()`) on the page, and call `tabsight.render(element, payload)`.

## Safety

A chart is a web page that other people open, so tabsight treats every value in your data as hostile:

- Data never becomes markup. Titles and captions are escaped, tooltips are built from escaped text, and tables and KPI cards are filled with `textContent`.
- The data travels in a JSON block that browsers never run, with `<`, `>` and `&` escaped so no value can close the tag.
- Each page carries a strict Content Security Policy. Only the exact scripts tabsight wrote may run, pinned by their SHA-256 hashes, and the page may not load or send anything over the network.
- In Jupyter, charts are shown inside a sandboxed frame, isolated from your notebook.

```python
hostile = pd.DataFrame({"Region": ["<img src=x onerror=alert(1)>"], "Sales": [10.0]})
page = ts.chart(hostile, "bar", x="Region", y="Sales").to_html()
print("<img src" in page.split("<script", 1)[0])
print("default-src 'none'" in page.replace("&#x27;", "'"))
```

```text title="Output"
False
True
```
