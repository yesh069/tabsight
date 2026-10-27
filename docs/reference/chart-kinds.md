# Chart kinds

The 33 kinds a [`ChartSpec`](../guide/chart-specs.md) accepts. Drawing arrives in stages; the phase column says when.

| Family | Kind | Phase |
|--------|------|-------|
| Comparison | `bar` | 3 |
| | `hbar` | 3 |
| | `grouped_bar` | 3 |
| | `lollipop` | 6 |
| | `bullet` | 6 |
| Part-to-whole | `stacked_bar` | 3 |
| | `stacked100_bar` | 3 |
| | `donut` | 3 |
| | `treemap` | 6 |
| | `sunburst` | 6 |
| | `waterfall` | 6 |
| | `funnel` | 6 |
| Trend | `line` | 3 |
| | `multi_line` | 3 |
| | `area` | 3 |
| | `stacked_area` | 3 |
| | `combo` | 6 |
| | `sparkline` | 3 |
| | `calendar_heatmap` | 6 |
| Flow | `sankey` | 6 |
| Relationship | `scatter` | 6 |
| | `bubble` | 6 |
| | `heatmap` | 6 |
| Distribution | `histogram` | 6 |
| | `boxplot` | 6 |
| Maps | `choropleth` | 5 |
| | `symbol_map` | 5 |
| | `density_map` | 6 |
| | `flow_map` | 6 |
| Single value | `kpi` | 3 |
| | `gauge` | 6 |
| Detail | `table` | 3 |
| Ranking | `pareto` | 6 |

Aliases: `map` → `choropleth`, `pie` → `donut`, `stackbar` → `stacked_bar`, `column` → `bar`, `box` → `boxplot`.

**Small multiples** (`facet=`) will work with bar, line, area, scatter and maps (Phase 6).
