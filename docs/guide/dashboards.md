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

Each value keeps one colour in every tile: West is the same colour in the stacked bars as in the donut.

## What the viewer can do

- **Filter** with the bar at the top: a list of values for each category field, and a from–to month range for each date field.
- **Click a bar, slice, map region, point or table row** to filter every other tile to it. Ctrl or Shift + click adds or removes more values. Clicking the same mark again removes the filter. Clicking the grey "Other" bar filters to everything inside it.
- **See what is filtered.** Each filter shows as a chip with an × to remove it, plus "Reset all filters".
- **The clicked tile highlights instead of filtering itself**, so you still see what you picked against the rest.
- **Share the view.** The filters are kept in the page address (`#f=...`), so a copied link opens the same view. This works when the file is hosted somewhere; a `file://` address only works on the computer that has the file.
- **Download a tile's numbers** as CSV, with the filters applied. Cells that start with `=`, `+`, `-` or `@` are made safe for Excel.

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
1153 grouped rows instead of 1200 orders; 0.047 MB
['Category', 'Order_Date|month', 'Region', 'Segment', 'State', 'Sub_Category']
```

This sample is small, so almost every order is its own group; with thousands of orders per state and month, the table stays the same size while the data grows. Date filters work by month, so a date can't multiply the table by its days. If the table would be larger than `max_size_mb` (5 MB by default), tabsight stops and names the fields with the most values. You can then use a coarser `freq=`, fewer filter fields or `top=`.

After a filter, the browser re-ranks the top N and the "Other" group, re-sorts the bars, and redraws each tile. Tests run the browser code and `ts.chart` on the same filtered data and check that every tile gives the same numbers.

`min_group_size` (see [settings](settings.md)) also applies after filtering: a group with too few rows is hidden in the browser too.

## Tiles that are drawn from all the data

Some tiles can't be recomputed exactly from the shared table, so they are drawn from all the data. When a filter is active they say "Not affected by filters" and why, so nothing looks wrong silently:

```python
dash2 = (
    ts.Dashboard("Mixed", data=orders)
    .add("scatter", x="Sales", y="Profit")
    .add("bar", x="Region", y="Customer_ID", agg="countd")
)
for tile in dash2.build()["tiles"]:
    print(tile["figure"]["kind"], "-", tile.get("static", "recomputed"))
```

```text title="Output"
scatter - scatter tiles are not recomputed after filtering yet
bar - distinct counts can't be recomputed exactly from the shared table
```

- **Recomputed after filtering:** bar, horizontal bar, grouped, stacked and 100% stacked bars, line, multi-line, area, stacked area, donut, KPI (with or without a comparison), table and filled map.
- **Drawn from all the data:** scatter and bubble (one dot per row), histogram, box plot, treemap, sunburst, waterfall, funnel, Pareto, lollipop, bullet, gauge, combo, heatmaps, Sankey, symbol, density and flow maps, and any tile using a median, distinct count or weighted average.

Trend lines, forecasts and reference lines are shown while nothing is filtered and hidden when a filter is on, because they describe all the data. The insights panel says the same when filters are active.

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

These parts of the plan come later:

- drill-down, such as year to quarter to month, with breadcrumbs
- dragging across an axis to filter a range
- legend clicks that highlight a series
- tiles with their own data
- a light/dark toggle in the page
- switching a tile's chart type, or saving a tile as PNG
- recomputing insights, trend lines and forecasts in the browser after filtering
