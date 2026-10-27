# Roadmap

tabsight is built in phases. Each phase is finished and tested before the next one starts. The full plan, with every design decision, is [`PLAN.md`](https://github.com/yesh069/tabsight/blob/main/PLAN.md) in the repository.

| Phase | What | Status |
|-------|------|--------|
| 0 | Project setup, pinned and hash-checked third-party files, CI | Done |
| 1 | Foundation: loading, profiling, checking, cleaning, formatting, colours, themes, settings, chart specs | Done |
| 2 | Aggregation and correctness: exact parts, dates, top N, table calculations, calculated fields | Done |
| 3 | Core charts (bar, line, area, donut, KPI, table) as offline HTML, plus the browser runtime | Done |
| 4 | Chart recommender ("Show Me" with reasons), chart linter, `explain()` | Done |
| 5 | World maps: countries, states/provinces/counties for every country, cities | Done |
| 6 | Advanced charts: heatmaps, treemaps, Sankey, scatter, distributions, small multiples; numeric x-axis for lines; `df.plot` backend and `df.ts` accessor for notebooks | Done |
| 7 | Analytics and insights: trend lines, forecasts, comparisons, plain-English insights; still SVG pictures and saved-notebook fallback | Done |
| 8 | Dashboards: cross-filtering, filters, shareable links, exact re-aggregation in the browser (drill-down and brushing still to come) | Mostly done |
| 9 | `ts.auto(df)` one-line dashboards, command line, web-framework helpers, optional PNG export | Planned |
| 10 | First release on PyPI | Planned |

## Later (Tier 2)

PPTX and PDF export, big data through DuckDB, story pages, ready-made templates, data-quality tiles, brand themes, simple joins, and more chart types (radar, Gantt, slope).

## Not planned

Street-map backgrounds (they need the internet), currency conversion, live auto-refresh, a drag-and-drop builder, logins and sharing, and LLM features. The reasons are in `PLAN.md` section 22.
