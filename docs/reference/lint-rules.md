# Lint rules

What `fig.lint()` checks. Each rule has a stable code you can pass to `ignore=`. Warnings are design mistakes. Info items are things a reader should know. `fig.lint(strict=True)` raises `ChartLintError` on warnings only.

| Code | Severity | Flags | Suggested change |
|------|----------|-------|------------------|
| `pie_too_many_slices` | warning | A donut with more than 8 slices | `top=7` |
| `pie_not_additive` | warning | A donut of averages, rates or distinct counts | `kind="bar"` |
| `stacked_not_additive` | warning | Stacked bars or areas of values that don't add up | side-by-side bars or one line each |
| `stacked_with_negatives` | warning | Stacked bars or areas with negative totals | `kind="grouped_bar"` |
| `too_many_colors` | warning | More than 10 colours in one chart | `top=8` |
| `too_many_lines` | info | More than 8 lines (and at most 10) | `top=6` |
| `smoothed_line` | warning | A smoothed line, added with `fig.update()` | remove `smooth` |
| `bar_axis_not_zero` | warning | Bars whose value axis doesn't start at zero | remove `min` |
| `labels_skipped` | warning | Category labels hidden to save space | `kind="hbar"` |
| `sum_of_rates` | warning | A percentage, rate or average that was summed | `agg="mean"` |
| `sum_of_ids` | warning | ID or code numbers that were summed | `agg="countd"` |
| `line_for_categories` | warning | A line across categories that have no order | `kind="bar"` |
| `single_category` | info | A bar chart with one bar | `kind="kpi"` |
| `incomplete_last_period` | info | A trend ending on a period that isn't over | filter to complete periods |
| `table_truncated` | info | A table showing only its first 500 rows | `top=50` |
| `mixed_units` | info | Measures in different units (money and a count) on one axis | chart them separately |
| `no_data` | warning | A chart with no values to draw | check filters and the measure column |
| `weak_trend` | info | A trend line with R² under 0.1: it explains under a tenth of the ups and downs | `trend=False` |
| `long_forecast` | warning | A forecast longer than half the history it was fitted to | `forecast=` half the history |

The checks read the figure itself, including any `fig.update()` patch, so a smoothed line or a cut axis is caught however it got there. See [choosing a chart](../guide/choosing-charts.md) for examples.
