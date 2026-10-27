# Chart kinds

The 33 kinds a [`ChartSpec`](../guide/chart-specs.md) accepts. Kinds marked **now** can be drawn with [`ts.chart`](../guide/charts.md); the rest arrive in the phase shown. `kind="auto"` is not a kind of its own: it draws the best chart [`ts.recommend`](../guide/choosing-charts.md) finds for your fields.

| Family | Kind | Available |
|--------|------|-------|
| Comparison | `bar` | **now** |
| | `hbar` | **now** |
| | `grouped_bar` | **now** |
| | `lollipop` | 6 |
| | `bullet` | 6 |
| Part-to-whole | `stacked_bar` | **now** |
| | `stacked100_bar` | **now** |
| | `donut` | **now** |
| | `treemap` | 6 |
| | `sunburst` | 6 |
| | `waterfall` | 6 |
| | `funnel` | 6 |
| Trend | `line` | **now** |
| | `multi_line` | **now** |
| | `area` | **now** |
| | `stacked_area` | **now** |
| | `combo` | 6 |
| | `sparkline` | **now** |
| | `calendar_heatmap` | 6 |
| Flow | `sankey` | 6 |
| Relationship | `scatter` | 6 |
| | `bubble` | 6 |
| | `heatmap` | 6 |
| Distribution | `histogram` | 6 |
| | `boxplot` | 6 |
| Maps | `choropleth` | **now** |
| | `symbol_map` | **now** |
| | `density_map` | 6 |
| | `flow_map` | 6 |
| Single value | `kpi` | **now** |
| | `gauge` | 6 |
| Detail | `table` | **now** |
| Ranking | `pareto` | 6 |

Aliases: `map` → `choropleth`, `pie` → `donut`, `stackbar` → `stacked_bar`, `column` → `bar`, `box` → `boxplot`.

**Small multiples** (`facet=`) will work with bar, line, area, scatter and maps (Phase 6).
