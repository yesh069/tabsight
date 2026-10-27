# Chart kinds

The 33 kinds a [`ChartSpec`](../guide/chart-specs.md) accepts. Every one of them can be drawn with [`ts.chart`](../guide/charts.md). `kind="auto"` is not a kind of its own: it draws the best chart [`ts.recommend`](../guide/choosing-charts.md) finds for your fields.

| Family | Kind | What it needs |
|--------|------|---------------|
| Comparison | `bar` | `x` (categories), `y` |
| | `hbar` | `x`, `y` |
| | `grouped_bar` | `x`, `y`, `color` (or several `y` in one unit) |
| | `lollipop` | `x`, `y` |
| | `bullet` | `x`, `y`, `goal` (a number or a column) |
| Part-to-whole | `stacked_bar` | `x`, `y`, `color` |
| | `stacked100_bar` | `x`, `y`, `color` |
| | `donut` | `x`, `y` (a total that adds up) |
| | `treemap` | `x` (one or more levels), `y` (adds up) |
| | `sunburst` | `x` (two or more levels), `y` (adds up) |
| | `waterfall` | `x` (steps, in order), `y` (changes) |
| | `funnel` | `x` (stages), `y` |
| Trend | `line` | `x` (dates or numbers), `y` |
| | `multi_line` | `x`, `y`, `color` |
| | `area` | `x`, `y` |
| | `stacked_area` | `x`, `y`, `color` |
| | `combo` | `x`, `y` with two or more measures (bars, then lines) |
| | `sparkline` | `x`, `y` |
| | `calendar_heatmap` | `x` (dates, by day), `y` |
| Flow | `sankey` | `source`, `target`, `y` (or counts rows) |
| Relationship | `scatter` | `x` and `y` numbers (a dot per row), or `x` categories and two `y` |
| | `bubble` | as scatter, plus `size` (or a third `y`) |
| | `heatmap` | `x` (columns), `color` (rows), `y` |
| Distribution | `histogram` | `x` (numbers); `bins=` or `bin_width=` |
| | `boxplot` | `y` (numbers), `x` to compare groups |
| Maps | `choropleth` | `geo` (countries or regions), `y` |
| | `symbol_map` | `geo` (any places) or `lat` and `lon`, `y` |
| | `density_map` | as symbol map |
| | `flow_map` | `source` and `target` (places), `y` |
| Single value | `kpi` | `y` |
| | `gauge` | `y`, optional `goal` |
| Detail | `table` | `x` and/or `y` |
| Ranking | `pareto` | `x`, `y` (adds up) |

Aliases: `map` → `choropleth`, `pie` → `donut`, `stackbar` → `stacked_bar`, `column` → `bar`, `box` → `boxplot`.

**Small multiples** (`facet=`) work with the bar kinds, lollipop, the line and area kinds, scatter, histogram, choropleth, symbol and density maps. See [small multiples](../guide/small-multiples.md).
