# Dashboards

A dashboard puts several tiles on one page, with filters and cross-filtering, in a single offline HTML file. Click a bar and every other tile filters to it. The numbers stay exact, because tabsight re-adds the stored parts of each measure rather than averaging averages.

```python
import tabsight as ts

orders = ts.load("examples/superstore_sample.csv")

dash = (
    ts.Dashboard("Sales performance", data=orders, filters=["Region", "Order_Date", "Segment"])
    .kpi("Sales", compare="previous_year")
    .kpi("Profit")
    .kpi("Quantity")
    .kpi("Discount")
    .add("map", geo="State", y="Sales")
    .add("line", x="Order_Date", y="Sales", freq="month")
    .add("hbar", x="Sub_Category", y="Profit")
    .add("donut", x="Segment", y="Sales")
    .add("table", x=["Region", "Category"], y=["Sales", "Profit"])
    .insights()
)
print(dash)
```

```text title="Output"
<Dashboard 'Sales performance': 9 tiles, filters ['Region', 'Order_Date', 'Segment']>
```

```python
# not run
dash.to_html("sales_dashboard.html")  # one file, opens offline in any browser
```

In a notebook, a dashboard on the last line of a cell displays itself.

## Building one

- `ts.Dashboard(title, data=df, filters=[...])` starts it. `subtitle=`, `theme=`, `locale=`, `currency=` and `palette=` apply to every tile.
- `.add(kind, ...)` adds a tile and takes any [`ts.chart`](charts.md) arguments, including `kind="auto"`. `w=` sets its width in columns of a 12-column grid. KPIs default to 3, tables to 12 and everything else to 6. On a phone, every tile takes the full width.
- `.kpi("Sales")` is a shortcut for a KPI card. `compare="previous_year"` adds the change on last year (see [comparing periods](analytics.md#comparing-periods)).
- `.insights()` adds a panel of [plain-English insights](analytics.md).
- `theme_toggle=False`, `switch=False` and `drill=False` turn off the light/dark button, the chart-type menu and drill-down.

Each value keeps one colour in every tile: West is the same colour in the stacked bars as in the donut.

## What the viewer can do

- **Filter** with the bar at the top: a list of values for each category field, and a from–to month range for each date field.
- **Click a bar, slice, map region, point or table row** to filter every other tile to it. Ctrl or Shift + click adds or removes more values. Clicking the same mark again removes the filter. Clicking the grey "Other" bar filters to everything inside it.
- **See what is filtered.** Each filter shows as a chip with an × to remove it, plus "Reset all filters".
- **The clicked tile highlights instead of filtering itself**, so you still see what you picked against the rest.
- **Share the view.** The filters are kept in the page address (`#f=...`), so a copied link opens the same view. This works when the file is hosted somewhere; a `file://` address only works on the computer that has the file.
- **Drag across a line chart's dates** to filter that range; the selection stays drawn on the chart.
- **Click a legend item** to highlight that series and fade the others; click it again to undo. Ctrl + click hides the series.
- **Double-click to drill down:** a year opens its quarters, a quarter its months, and a category its sub-categories when tabsight has found that hierarchy (Category → Sub-Category, Region → City). Breadcrumbs above the chart lead back up.
- **Change a tile's chart type** from its menu. The menu offers up to two other kinds that fit the same fields, chosen by the [recommender](choosing-charts.md).
- **Switch between light and dark.** The page follows the computer's setting unless you passed `theme=`; the button in the filter bar switches.
- **Save a tile as PNG**, or **download its numbers as CSV** with the filters applied. In CSVs, cells that start with `=`, `+`, `-` or `@` are made safe for Excel.

A tile with `action="highlight"` only highlights the matching marks elsewhere instead of filtering, and `action="none"` makes it ignore clicks.

## How the numbers stay exact

The page never holds your raw rows. tabsight stores **one shared table**, grouped by every field the dashboard uses, with the parts each measure needs:

| Measure | Stored | Recomputed after a filter as |
|---------|--------|------------------------------|
| sum | the sum | the sum of the sums |
| count | the count | the sum of the counts |
| average | the sum and the count | Σsum ÷ Σcount, never an average of averages |
| min / max | the min / max | the min of the mins / max of the maxes |

```python
table = dash.build()["data"]
print(table["rows"], "grouped rows instead of", len(orders), "orders;", table["size_mb"], "MB")
print(sorted(c for c in table["dims"] if not c.startswith("__")))
```

```text title="Output"
1173 grouped rows instead of 1200 orders; 0.056 MB
['Category', 'City', 'Order_Date|month', 'Region', 'Segment', 'Ship_Mode', 'State', 'Sub_Category']
```

This sample is small, so almost every order is its own group; with thousands of orders per state and month, the table stays the same size while the data grows. Date filters work by month, so a date can't multiply the table by its days. If the table would be larger than `max_size_mb` (5 MB by default), tabsight stops and names the fields with the most values. You can then use a coarser `freq=`, fewer filter fields or `top=`.

After a filter, the browser re-ranks the top N and the "Other" group, re-sorts the bars, and redraws each tile. Tests run the browser code and `ts.chart` on the same filtered data and check that every tile gives the same numbers.

`min_group_size` (see [settings](settings.md)) also applies after filtering: a group with too few rows is hidden in the browser too.

## Tiles that are drawn from all the data

Almost every tile is recomputed after filtering. Only charts that draw single rows can't be, because the page never holds your rows:

```python
coords = orders.assign(lat=40.0, lon=-100.0)
dash2 = (
    ts.Dashboard("Mixed", data=coords)
    .add("scatter", x="Sales", y="Profit")
    .add("symbol_map", lat="lat", lon="lon", y="Sales")
    .add("bar", x="Region", y="Customer_ID", agg="countd")
)
for tile in dash2.build()["tiles"]:
    first = tile["views"][0]["themes"]["light"]
    print(tile["views"][0]["kind"], "-", first.get("static", "recomputed"))
```

```text title="Output"
scatter - a scatter of single rows needs the rows themselves, which the page doesn't hold
symbol_map - maps of coordinates draw single rows, which the page doesn't hold
bar - recomputed
```

When a filter is active, those tiles say "Not affected by filters" and why, so nothing looks wrong silently.

- **Recomputed after filtering:** every bar, line and area kind (including lines over a number axis, up to 2,000 x values), donut, lollipop, combo, KPI, gauge and bullet, table, funnel, Pareto, waterfall, heatmap, calendar heatmap, treemap, sunburst, Sankey, histogram, box plot, scatter and bubble by category, and filled, symbol, density and flow maps.
- **Medians, distinct counts and box plots** are exact too. For these the page keeps the values of each group, up to 200,000 in total. Distinct counts keep numbered codes, never the values themselves, so a count of customer IDs never puts an ID in the file. Medians and box plots are left static when `min_group_size` is set, because one value of a small group would show.
- **Histograms keep the bins of all the data**, so the bars stay in the same place while you filter. Only the counts change.
- **Waterfall steps keep their order** from all the data while you filter.
- **Drawn from all the data:** a scatter of single rows (numbers on both axes), maps placed by `lat=`/`lon=`, and lines with more than 2,000 x values (which are thinned).

## Trend lines, forecasts and insights after filtering

Trend lines, forecasts, reference lines, bands and circled outliers are refitted to the filtered data, with the same rules as in Python (see [trends, forecasts and insights](analytics.md)). A forecast that has too little history after filtering is replaced by the note "not enough data for a forecast".

The insights panel is recomputed too. Change on the previous period, peaks and lows, trends, biggest contributors, concentration and losses describe the current filters, and each is tagged "for current filters". Seasonality and unusual rows need every row of the data, so they keep the version for all the data and are tagged "based on all data".

Tests run the browser code and Python on the same filtered data and check that the trend lines, forecasts, reference lines and insights match.

## Tiles with their own data

A tile can show another table, for example targets next to actual sales:

```python
import pandas as pd

targets = pd.DataFrame(
    {"Region": ["Central", "East", "South", "West"], "Target": [60000, 90000, 50000, 80000]}
)
dash3 = (
    ts.Dashboard("Against target", data=orders, filters=["Region", "Segment"])
    .add("bar", x="Region", y="Sales")
    .add("bar", x="Region", y="Target", data=targets, data_name="targets")
)
print(sorted(dash3.build()["datasets"]))
```

```text title="Output"
['targets']
```

A filter applies to every tile whose data has that field. Here Region filters both tiles. Segment exists only in the orders, so the targets tile says "Not affected by Segment" instead of looking filtered when it isn't. Joining tables is not done for you.

A saved dashboard remembers the dataset's name; give it new data with `bind(new_orders, targets=new_targets)`.

## Saving and reusing

A dashboard saves as plain JSON, without the data:

```python
import json

spec = dash.to_dict()
print(json.dumps(spec)[:120], "...")
```

```text title="Output"
{"tabsight_dashboard": 1, "title": "Sales performance", "filters": ["Region", "Order_Date", "Segment"], "tiles": [{"kind ...
```

```python
# not run
dash.save("sales.json")

# next month: the same dashboard on new data
ts.Dashboard.load("sales.json").bind(new_orders).to_html("sales_november.html")
```

`bind` checks that every column the dashboard needs exists in the new data, and suggests the closest name if one was renamed. Loading a file someone else wrote is safe: every key is checked against a fixed list, values must be plain JSON, and each tile is validated like a `ts.chart` call.

## Not built yet

- touch gestures beyond tapping (long-press to filter)
- server mode, where filtering runs on a server for data too big for one file (Phase 9)
