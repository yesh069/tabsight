# Notebooks and df.plot

In Jupyter, a tabsight figure on the last line of a cell draws itself, like a matplotlib plot. You get an interactive chart with tooltips, formatted numbers and the same rules as everywhere else.

There are three ways to make one from a DataFrame:

```python
import pandas as pd

import tabsight as ts

orders = ts.load("examples/superstore_sample.csv")

fig = ts.chart(orders, "bar", x="Region", y="Sales")  # 1. the function
fig = orders.ts.bar(x="Region", y="Sales")  # 2. the .ts accessor
pd.options.plotting.backend = "tabsight"  # 3. pandas' own df.plot
fig = orders.plot.bar(x="Region", y="Sales")
print(fig.kind, "|", fig.title)
pd.options.plotting.backend = "matplotlib"
```

```text title="Output"
bar | Sum of Sales by Region
```

## The `.ts` accessor

Importing tabsight adds `.ts` to every DataFrame and Series, without changing any pandas setting. There is one method per chart kind (`orders.ts.treemap(...)`, `orders.ts.map(...)`), plus `orders.ts.chart(kind, ...)` (with `kind="auto"` by default), `orders.ts.recommend(...)`, `orders.ts.profile()`, `orders.ts.check()` and `orders.ts.aggregate(...)`. On a column: `orders["Profit"].ts.hist()`, `.line()`, `.bar()`, `.box()`.

## `df.plot` with tabsight

After `pd.options.plotting.backend = "tabsight"`, pandas' own plotting calls draw tabsight charts:

| pandas | tabsight |
|--------|----------|
| `df.plot()`, `.plot.line()` | `line`, or `multi_line` for several columns |
| `.plot.bar()`, `.plot.barh()` | `bar`, `hbar`; `stacked=True` stacks |
| `.plot.area()` | `area`, `stacked_area` |
| `.plot.pie()` | `donut` |
| `.plot.scatter()` | `scatter` |
| `.plot.hist()`, `.plot.box()` | `histogram`, `boxplot`; `by=` splits them |

Some differences from pandas are deliberate:

- **tabsight aggregates.** `df.plot.bar(x="Region", y="Sales")` draws one bar per region with the total, not one bar per row. When x is already unique, the result is the same.
- **No `x` means the index**, like pandas. A number index becomes a real number axis.
- **Several columns share one axis only when they share a unit.** Sales next to Quantity would flatten one of them, so tabsight stops and suggests a combo chart.
- **matplotlib styling** (`figsize`, `rot`, `ax`, `style`...) is ignored, with one warning. Use tabsight's own options instead: `title`, `theme`, `height`, `locale` and so on.
- `kind="kde"` and `"hexbin"` have no tabsight version; the error suggests the nearest kind.

```python
pd.options.plotting.backend = "tabsight"
try:
    orders.plot(x="Order_Date", y=["Sales", "Quantity"])
except ts.warnings.InvalidSpecError as error:
    print(error)
pd.options.plotting.backend = "matplotlib"
```

```text title="Output"
Sales, Quantity have different units (count, currency), so one axis would flatten one of them; plot them separately, or use ts.chart(df, 'combo', ...)
```

## Notebook size

Each chart is shown in a sandboxed frame that can't reach your notebook, and carries its own copy of ECharts (about 1 MB) so it works offline. A notebook with many charts grows accordingly. Once a session has shown about 10 MB of charts, tabsight suggests:

```python
# not run
ts.set_defaults(cdn=True)
```

This loads ECharts from jsDelivr instead, pinned by a hash so a changed file is refused. Charts then need the internet to draw.

## Reopening a saved notebook

JupyterLab only runs interactive output from cells you ran yourself. When you open a notebook someone else ran, or reopen your own after a restart, it counts as "not trusted", and JupyterLab removes the interactive chart. Notebooks viewed on GitHub don't run JavaScript either.

Install the `static` extra and every chart also carries a still picture of itself:

```bash
python -m pip install "tabsight[static]"
```

The picture sits under the live chart. While you work, the live chart covers it. In a reopened or untrusted notebook the live chart is removed and the picture shows instead of a blank space. Run the cell again, or trust the notebook (Command Palette → "Trust Notebook"), to get the interactive chart back. This was checked in JupyterLab 4.6.

The picture is drawn in Python by ECharts itself, running in dukpy, so it matches the live chart. It adds about 5–100 KB per chart, 0.2 seconds for a map and less for most charts. Pictures over 2 MB are left out. Density maps are drawn on a canvas, so they have no picture. `ts.set_defaults(picture=False)` turns pictures off.

You can also save the picture yourself:

```python
# not run
fig.to_svg("sales_by_region.svg")  # title, chart and notes, no browser needed
```
