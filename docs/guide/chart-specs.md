# Chart specs

A `ChartSpec` describes **what a chart shows** as plain, versioned JSON: the kind of chart, which columns go where, how to aggregate and sort, and options. Charts themselves are drawn from Phase 3 onwards; specs exist now so they can be saved, loaded and validated.

```python
import tabsight as ts

spec = ts.ChartSpec(
    "bar",
    x="Region",
    y="Sales",
    sort="desc",
    top=10,
    title="Sales by Region",
    options={"menu": True},
)
text = spec.to_json()
print(text)
print(ts.ChartSpec.from_json(text) == spec)
```

## Fields

| Field | Meaning |
|-------|---------|
| `kind` | One of the [33 chart kinds](../reference/chart-kinds.md). Aliases: `map`, `pie`, `stackbar`, `column`, `box` |
| `x`, `y` | Column names; `y` can be a list (combo charts) |
| `color`, `size`, `facet` | Columns for colour, size and small multiples |
| `geo`, `lat`, `lon` | Map columns |
| `source`, `target` | Sankey and flow maps |
| `agg` | Aggregation (`sum`, `mean`, `wavg`...) |
| `sort` | `"asc"`, `"desc"`, `"none"`, `"by:<column>"` or a list of values |
| `top` | Top N (1–1000) |
| `calc` | Table calculation (`running_total`, `moving_avg:3`...) |
| `unit`, `currency`, `decimals`, `format` | Formatting |
| `title`, `subtitle` | Up to 300 characters |
| `options` | Allow-listed extras: `trend`, `forecast`, `compare`, `fixed`, `log`, `y_min`, `y_max`, `scale`, `action`, `cross_filter`, `drill`, `menu`, `missing`, `weight`, `as_of`, `negative`, `freq`, `projection`, `geo_names`, `insights`, `season` |

## Loading specs is safe

Specs are often saved and shared, so loading one never runs code:

- every key is checked against an allow-list; unknown keys are rejected
- every value is checked for type and range
- strings are length-limited and may not contain control characters
- JSON input is limited to 1 MB

```python
from tabsight.warnings import InvalidSpecError

try:
    ts.ChartSpec.from_dict({"kind": "bar", "options": {"onclick": "alert(1)"}})
except InvalidSpecError as err:
    print(err)
```
