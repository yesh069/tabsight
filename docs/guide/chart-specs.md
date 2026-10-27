# Chart specs

A chart spec is a description of a chart: what kind it is, which columns go where, how to summarise and sort. It's plain JSON, so it can be saved next to a dashboard, sent from a web server to a browser, or written by hand.

Every chart is built from a spec, and every spec is validated before anything is drawn.

```python
import tabsight as ts

spec = ts.ChartSpec("bar", x="Region", y="Sales", sort="desc", top=10, title="Sales by region")
print(spec.to_json())
print(ts.ChartSpec.from_json(spec.to_json()) == spec)
```

```text title="Output"
{"kind": "bar", "sort": "desc", "tabsight_spec": 1, "title": "Sales by region", "top": 10, "x": "Region", "y": "Sales"}
True
```

## What a spec can say

`kind` is one of the [33 chart kinds](../reference/chart-kinds.md), and a few friendly aliases work too: `map` means `choropleth`, and `pie` means `donut`. The rest are optional: `x` and `y` (a list of `y` columns makes a combo chart), `color`, `size` and `facet` for small multiples, the map columns `geo`, `lat` and `lon`, and `source` and `target` for flows. You can also set how to aggregate (`agg`), sort (`sort`), limit (`top`), add a [table calculation](table-calculations.md) (`calc`), format (`unit`, `currency`, `decimals`, `format`), and give a `title` and `subtitle`.

Anything more specialised goes in `options`, which only accepts known keys: `trend`, `forecast`, `compare`, `log`, `y_min`, `y_max` and a few others listed in the [API reference](../reference/api.md#tabsight.spec.ChartSpec).

## Loading a spec someone else wrote

Specs get shared, so loading one has to be safe even when you don't trust where it came from. Every key is checked against a list of known keys, every value is checked for type and range, text is limited in length, and nothing in a spec is ever run as code:

```python
from tabsight.warnings import InvalidSpecError

for suspicious in (
    {"kind": "bar", "options": {"onclick": "alert(1)"}},
    {"kind": "bar", "title": "x" * 5000},
    {"kind": "bar", "format": "{0.__class__}"},
):
    try:
        ts.ChartSpec.from_dict(suspicious)
    except InvalidSpecError as err:
        print(err)
```

```text title="Output"
unknown option 'onclick'
title must be text of at most 300 characters
format pattern '{0.__class__}' is not supported; use forms like '#,##0', '0.0%', '"€"#,##0.00'
```
