# 0001: Pin ECharts 6.1.0

- Date: 2026-10-27
- Status: accepted

## Context

The plan first named ECharts 5.5.1. ECharts 6.0.0 was released on 30 Jul 2025 and 6.1.0 on 19 May 2026 (npm `latest` tag as of 27 Oct 2026). Version 6 adds dynamic theme switching, which the dashboard light/dark toggle needs.

## Check

`tests/js/echarts_features.cjs` renders every feature the plan relies on with the bundled `echarts.min.js`, server-side in Node. All 19 checks pass on 6.1.0:

- server-side SVG rendering
- `registerMap` with Natural Earth GeoJSON, plus a custom Equal Earth projection (our own formula, no d3) with a verified inverse
- LTTB sampling on a 5,000-point line, and large-mode scatter with 20,000 points
- decal pattern fills (accessibility: colour is not the only cue)
- `chart.setTheme()` dynamic theme switching
- treemap, sunburst, Sankey, funnel, gauge, box plot, calendar heatmap, cartesian heatmap
- `lines` (flow map) and scatter on a geo component
- brush and dataZoom components

The aria label is attached to the page element, which does not exist in server-side rendering, so it is checked in the browser tests (the dashboard tests).

## Decision

Pin **ECharts 6.1.0**, inlined from `src/tabsight/render/static/echarts.min.js` (1,121,883 bytes). The SHA-256 is recorded in `tools/vendor.lock.json`. Fall back to 5.6 only if a later phase finds a blocking problem.

## Notes found during setup

- Natural Earth `ne_110m_admin_0_countries` has only 177 countries; small countries are missing. `ne_50m_admin_0_countries` has 242. Level 0 is built from the 50m file.
- Natural Earth admin-1 (10m) has 4,596 regions, matching the plan's estimate.
- `mapshaper` 0.7.98 (build-time only) pulls in a deprecated `geographiclib` dependency. It is never shipped; npm install runs with `--ignore-scripts`.
