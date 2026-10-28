# Changelog

All notable changes are listed here. The project follows [Semantic Versioning](https://semver.org/).

## 0.1.0 (28 Oct 2026)

The first full release. Everything below, from 0.1.0a1, plus:

### Changed
- The project description no longer mentions LLMs.
- Installs with a plain `pip install tabsight`; the README, documentation home page and installation guide say so.
- The README (also the PyPI page) starts with a quick start, links the sample data it uses, and shows the PyPI version.
- The documentation's table of contents (`docs/README.md`) lists every page, and the quickstart ends by drawing a chart and a dashboard.
- `SECURITY.md` and the warnings-and-errors reference cover server mode, `tabsight serve`, decompression bombs, network shares and dashboard size steps.

## 0.1.0a1 (28 Oct 2026, first pre-release)

### Added: auto, command line and web apps
- `ts.auto(df)`: a whole dashboard from fixed rules on the column profile: KPI cards (money first, compared with the previous year when the dates allow), a line over time at a grain that suits the span, a map when a column holds places, bars by the smallest categories, filters and insights. `dash.decisions` says what was chosen and why; tiles are tried before they are added and the result is fitted under the size limit. Tables without measures count rows.
- `tabsight` command line (also `python -m tabsight`): `auto`, `chart` (HTML, SVG or PNG), `build` (a saved spec on new data), `serve`, `profile`, `check`, `clean`, `recommend`. Never overwrites its input.
- Server mode: `dash.server(url)` keeps the data in Python. The page posts its filters and gets back, per tile, a small table from the filtered rows, drawn by the same runtime (parity-tested against the offline page), or for tiles the browser can't recompute, the chart redrawn in Python. No size limit for the page; medians, distinct counts and scatter plots follow every filter. Requests are size-capped, shape-checked and filtered against known values; the page's CSP allows `connect-src` to that one origin only.
- `ts.web.fastapi_router`, `ts.web.flask_blueprint`, `ts.streamlit`, `ts.web.dash_iframe` and `ts.serve_payload`; `tabsight serve` runs server mode with Python's own HTTP server on 127.0.0.1.
- `fig.to_png()`: the SVG picture rasterised by resvg-py, no browser needed (`tabsight[png]`, which no longer uses Playwright). New `web` extra.
- Dashboards over the size limit shrink themselves in steps instead of stopping: coarser dates on the tiles that use them, then tiles grouped by a field with many values are drawn from all the data. Each step is reported (`dash.size_steps`, and a warning).
- Touch screens: a tap on a dashboard chart shows the tooltip, and pressing and holding filters (the tile is outlined while held).

### Security
- `tabsight serve` answers only requests addressed to its own host names, so a hostile web page can't read the served data by DNS rebinding; `--allow-host` adds names. Server-mode data requests must be `application/json` (415 otherwise in the FastAPI and Flask helpers).
- Deeply nested JSON sent to server mode gets a 400 instead of an internal error.
- Data values named like JavaScript object properties (`hasOwnProperty`, `__proto__`, `constructor`) no longer break or blank dashboard filtering. A label that is exactly `__proto__` no longer lets ECharts' text cache write to `Object.prototype`, and tabsight's pages now lock `Object.prototype`.
- `ts.load` refuses Excel files that would unpack to more than 1 GB or at an extreme compression ratio (decompression bombs; `defusedxml` already stopped XML bombs), and JSON nested too deeply to be a table.
- `ts.load` refuses Windows network-share paths (`\\server\share`), keeping the promise that tabsight never contacts another computer.

### Changed
- The documentation site is built with Zensical, the successor to Material for MkDocs (which reaches end of life on 5 May 2027), from the same `mkdocs.yml`.
- A dashboard spec file that isn't JSON now raises a clear `InvalidSpecError`.

### Added: dashboards completed
- Every aggregated chart kind is recomputed after filtering, each following its Python builder: lollipop, combo, gauge, bullet, funnel, Pareto, waterfall, heatmap, calendar heatmap, treemap, sunburst, Sankey, histogram (bins of all the data), box plot, scatter and bubble by category, lines over a number axis, and symbol, density and flow maps. Medians, distinct counts and box plots are exact from value lists; distinct counts store integer codes, never the values. Only single-row charts (scatter of rows, lat/lon maps) stay static.
- Trend lines, forecasts, reference lines, bands and outliers are refitted in the browser after filtering (JS ports of `analytics.py` and the analytics pane), and the insights panel is recomputed (change, peak and low, trend, contributor, concentration, losses), tagged "for current filters".
- Legend click highlights a series (Ctrl + click hides it); drag across a line chart's dates to filter a range; double-click drills down (year > quarter > month, and detected hierarchies) with breadcrumbs.
- Per tile: a chart-type menu (up to two other kinds the recommender finds fitting) and PNG export.
- Light/dark toggle that follows the computer's setting; `theme_toggle=False`, `switch=False`, `drill=False` turn features off.
- Tiles with their own data: `add(..., data=df, data_name="targets")`; filters apply where the field exists and other tiles say "Not affected by ..."; `bind(df, targets=new_df)`.

### Fixed
- Python: a missing funnel or Pareto stage was named "nan"; grouped scatter and number-axis lines silently dropped points whose colour value was missing; box plots of an ordered column were sorted by size; category insights named a missing value "nan"; a measure could be recorded twice in a chart's facts.

### Added: dashboards with cross-filtering
- `ts.Dashboard(title, data=df, filters=[...])` with `.add(kind, ..., w=)`, `.kpi(...)` and `.insights()`: tiles on a 12-column grid (one column on phones), in one offline HTML file or a notebook.
- Filters (value lists for categories, month ranges for dates), chips with remove buttons, "Reset all filters", and the view kept in the address (`#f=...`), checked against known values.
- Cross-filtering: clicking a bar, slice, map region, point or table row filters the other tiles; Ctrl/Shift + click adds values; clicking again removes; the "Other" bar filters to its members; the source tile highlights instead of filtering itself; `action="highlight"` and `"none"` per tile.
- Exact re-aggregation in the browser (`dashboard.js`) from one shared table of exact parts (sums, counts, minimums, maximums; never raw rows), with top N, Other, sorting, period gaps and `min_group_size` recomputed. Parity tests check the browser against `ts.chart` on the same filtered data.
- KPI comparisons follow date filters: the filtered months against the same months a period earlier.
- Tiles that can't be recomputed exactly say "Not affected by filters" and why. CSV download per tile (formula-safe), lazy drawing, every tile drawn before printing.
- `save()` / `load()` / `bind(new_df)` with strict validation of dashboard files.
- GitHub Sponsors button in the README, on the docs home page and in `.github/FUNDING.yml`.

### Added: analytics and insights
- `ts.insights(df)`: plain-English facts from fixed rules: change on the previous period, peak and low, trend direction, seasonality, biggest contributor, concentration, negative segments and outliers. Facts only, never causes; rates change in points; every threshold configurable; each insight tagged with the data it describes. `insights=True` lists them under a chart.
- `ts.compare(df, y, date)`: year, quarter and month comparisons on the same window shifted back, fiscal-year aware, `as_of=` for "today" (otherwise the latest date in the data, never the clock), `previous_period` with `window=`. A sliver of a new period falls back to the last complete one; no previous data says so instead of +100%. KPI cards take `compare=` and `as_of=`.
- Analytics pane on charts: `trend=True` (least squares, R² in `explain()`), `forecast=N` (additive Holt-Winters in numpy, `season=`, dashed "Estimate" with a range, needs two full seasons), `ref=` reference lines (mean, median, percentiles, constants), `band=` shaded bands, `outliers=True` (circled, never removed).
- `ts.analytics`: `linear_trend`, `forecast`, `outliers`, `reference_value` for your own use.
- Lint rules `weak_trend` and `long_forecast`.
- Still pictures: `fig.to_svg()` draws a chart (title, chart, notes, insights) to SVG in Python, with ECharts running in dukpy (`pip install tabsight[static]`); no browser or Node.js.
- Notebooks: with the `static` extra, each chart also carries its picture under the live chart, so a reopened (untrusted) notebook or one viewed on GitHub shows the chart instead of a blank space. `picture=False` turns it off. Checked in JupyterLab 4.6.
- Docs: "Trends, forecasts and insights" guide.

### Changed
- Bar charts over dates stay vertical; they no longer switch to horizontal bars when there are many periods.

### Added: every chart kind, small multiples, notebooks
- All 33 chart kinds can now be drawn. New: scatter and bubble (one dot per row, or per category with exact aggregation), histogram (rounded bar widths; `bins=`, `bin_width=`), box plot (Tukey whiskers, outliers), treemap and sunburst (levels from `x`), waterfall (floating bars that can cross zero, total at the end), funnel (share of previous and first stage), Pareto (running share, 80% guide), lollipop, bullet and gauge (`goal=` a number or a column), combo (bars and lines, two axes when units differ), heatmap, calendar heatmap, Sankey (cycles broken safely), density map and flow map.
- Lines and areas over a number: a real value axis (a sine wave is a curve), thinned with LTTB above 2,000 points.
- Small multiples: `facet=` draws one panel per value (up to 12) sharing one value scale, one category order, one colour per series and one legend; maps and histograms included.
- pandas plotting backend: `pd.options.plotting.backend = "tabsight"` makes `df.plot(...)` draw tabsight charts (line, bar, barh, area, pie, scatter, hist, box; `by=`, `stacked=`); matplotlib styling is ignored with one warning.
- `df.ts` and `series.ts` accessors: one method per chart kind, plus `chart`, `recommend`, `profile`, `check`, `aggregate`.
- `cdn` setting and a one-time tip when a notebook session passes 10 MB of inlined charts.
- The recommender now picks scatter, treemap, heatmap, combo and the others directly; eight labelled cases updated to the chart they always named as ideal.
- Docs: "More chart types", "Small multiples" and "Notebooks and df.plot" guides; chart kinds reference lists what each kind needs. Gallery shows all 33 kinds and small multiples.

### Fixed (found by running a real JupyterLab 4.6)
- A chart drawn while its notebook cell was off screen stayed squashed: charts now follow their own box size (ResizeObserver), not only the window.
- `df.plot.hist()` (pandas sends bins=10) drew 6 coarse bars: `bins=` now picks the round width whose bar count is closest.
- Monthly date axes crowded every label at notebook width: date labels that would overlap are now left out (dates are in order, so this can't mislead; category labels are still never skipped).
- The notebook frame was too short for notes under a chart and scrolled inside: it now makes room for them.
- The mouse wheel over a map zoomed the map instead of scrolling the page: maps now pan by dragging and the wheel scrolls.
- Warnings now point at the line of your own code (the notebook cell), not at a line inside pandas or tabsight.
- A run of unique numbers (a step, a row number) is a valid number axis for lines and scatter.
- Shown names: "China" and "United States" instead of Natural Earth's formal names.

### Added: world maps
- Maps: `ts.chart(df, "map", geo="County", y="Sales")` (a filled map, `choropleth`) and `"symbol_map"` (circles sized by value, from places or `lat=`/`lon=`).
- Bundled, offline map data from Natural Earth 5.1.2 (public domain), 3.1 MB: about 240 countries, level-1 regions for every country, and about 7,300 cities, built by `tools/build_geo.py` (mapshaper, TopoJSON, deterministic).
- Extra layers people use: UK nations and regions, French, Italian, Spanish and Philippine regions, and Ireland's 26 official counties.
- `ts.geo`: `detect`, `match`, `layers`, `country_code`, `coverage`, `version`. Matching on English, local and about 25 other languages' names, everyday names (UK, Holland, Éire), ISO codes and US postal codes; ignores case, accents, punctuation and words like "County".
- Map detection: the world, a country's regions, or cities; names at two levels (Georgia, Luxembourg, Punjab) settled by the other values, then a country column, then a note. Words like North/East/Central never choose a map on their own.
- Unmatched places are listed with "did you mean", shown on the chart and raised as a `DataWarning`; `geo_map=` fixes spellings. Rows are tagged with their region and aggregated exactly, so "Cork" and "Co. Cork" make one county.
- Equal Earth projection for the world (Mercator and Natural Earth on request), auto zoom to the data, dots for tiny countries, Alaska and Hawaii insets, "No data" in grey, diverging colours for negative values, place names in other languages (`geo_names=`).
- Maps keep their true shape at any size; only the needed shapes go into the page.
- The recommender suggests a map when at least 80% of a field's values are places, and `kind="auto"` draws it.
- Docs: "Maps" guide and a generated map coverage page with the 30 most-used countries checked against official lists.

### Fixed
- `ts.aggregate` crashed when a grouping column's name started with `__`.

### Added: choosing and checking charts
- `ts.recommend(data, x, y, color)`: ranks the chart kinds that fit, each with a score and a reason, lists the kinds it ruled out with reasons, and `why_not(kind)`. `.best` is the top one. Rules look at dates and their span, category counts and label lengths, whether a measure adds up, negative totals, IDs, nesting and units.
- `ts.chart(..., kind="auto")` draws the best recommendation; anything you pass still wins.
- `fig.explain()`: every decision tabsight made for a chart, in plain English.
- `fig.lint(ignore=..., strict=...)`: 17 design rules (`tabsight.lint.RULES`) with fixes and the `ts.chart` arguments that apply them. Reads the figure itself, so `fig.update()` patches are checked too. `ChartLintError` for strict mode.
- 70 labelled recommender cases (`tests/recommend_cases.py`); every automatic chart for them passes its own linter.
- When two categories are picked and the colour field has many values, the one with fewer values goes in the colours. With more than 8 lines, `auto` keeps the biggest 6.
- Docs: "Choosing a chart" guide and the lint rules reference.

### Fixed
- Grouping by an ordered categorical column crashed on pandas 2 while sorting (found by the recommender cases).
- Time-zone-aware dates crashed `ts.aggregate` with a month, quarter or year grain. They're now grouped by their own wall-clock date, or in the `tz` setting's zone when it's set (the setting existed but did nothing until now).
- pandas 2 printed FutureWarnings (`observed=False`, silent downcasting) from profiling, aggregation and charts.
- "Did you mean" hints in error messages are shortened like the rest of the message.

### Changed (after hands-on review)
- `ts.recommend` checks its fields: at least one column, each used once, names must be text.
- A number used as x (like Quantity) keeps numeric order and suggests a scatter plot; more than 15 distinct numbers leads to a table.
- More than 50 categories: horizontal bars of the top 20 plus Other; donuts are ruled out.
- Nested fields (Region and State): one bar per State, coloured by its Region, instead of a table. Grouped and 100% bars are ruled out for nested fields.
- A date with only one period gets a bar, not an invisible one-point line.
- An "Other" line in a multi-line chart starts hidden (one click in the legend shows it), because as a total it dwarfs the real lines.
- New lint rules: `mixed_units` (info) and `no_data` (warning). Stacking rules no longer fire when each bar has one segment. `ignore=None` is accepted.
- `explain()` wording: "multi-line chart", no repeated "averaged ... averaged"; a table without a measure says it's in natural order.

### Added: core charts
- `ts.chart`: bar, hbar, grouped, stacked and 100% stacked bars; line, multi-line, area, stacked area and sparkline; donut; KPI card; table. BI rules by default: all labels shown (switching to horizontal bars when labels are long), lines never smoothed, zero baseline for bars, one colour per series, the same colour for the same value across charts, top 7 + grey "Other" for donuts, grouped parents in tables.
- Notes on figures, including a warning when the last period is incomplete and would look low.
- `Figure`: `to_dict()` (plain JSON), `to_html()` (one offline file, or `cdn=True` with Subresource Integrity), `_repr_html_()` (sandboxed iframe in Jupyter), `update()` (safe deep merge).
- `tabsight.js` browser runtime and `ts.runtime_js()`. Number formatting is a line-by-line port of Python's, checked on 54,950 cases.
- Docs: "Making charts" guide.

### Security
- HTML pages carry a Content Security Policy: only tabsight's own inline scripts may run (SHA-256 pinned), no network access at all.
- Figure data in a non-executable JSON block with `<`, `>`, `&` and line separators escaped.
- Tooltips built from escaped text; colours re-validated in the browser; tables and KPI cards use `textContent`.
- `Figure.update` refuses `formatter` strings and `$` keys.
- Tests: hostile category names and titles in every chart kind, the page parsed for unexpected tags and event handlers, CSP hashes checked against every inline script, runtime checked for eval-like constructs; verified in a real browser.


### Changed (documentation redesign)
- Editorial redesign of the docs site: navy hero home page, logo colours throughout, wider reading column, code and its output shown as one unit, quieter tables (`overrides/home.html`, `docs/stylesheets/tabsight.css`).
- Guide pages rewritten to explain the problem first, with real examples and opinions, and tables only for reference lists.
- Every example's printed output is real: `tools/render_doc_outputs.py` runs each page and writes the output; `tests/test_docs.py` fails if any shown output is stale.

### Fixed (found by the real outputs)
- `print(profile["Sales"])` now prints one readable line instead of every internal field.
- % of total column name: `Sales (% of total, shown rows)` instead of `Sales (% of total (of shown rows))`.
- With a date first and `top=`, "Other" rows now stay inside each date instead of sinking below every date.


### Added (documentation and logo)
- Documentation in `docs/`: getting started, 12 user-guide pages, API reference generated from docstrings, formula functions, locales, chart kinds, warnings and errors, and security. Reads on GitHub and builds a MkDocs Material site.
- `tests/test_docs.py` runs every documentation example and checks the locale, formula, chart-kind, settings and check-code tables against the code.
- Synthetic sample dataset `examples/superstore_sample.csv` (generated by `tools/make_sample_data.py`).
- Logo and wordmark (`docs/assets/`), with a dark-mode wordmark for GitHub.
- Docs CI workflow, with GitHub Pages deployment once the repository is public.

### Fixed
- Report text (`Profile.show()`, `CheckReport.show()`, `CleanReport.show()`) used "→", which crashed `print()` on Windows consoles using cp1252; it now uses "->".


### Added: aggregation and correctness
- `ts.aggregate`: group-by through exact re-aggregation *parts* (sum/count for means, Σw·x and Σw for weighted averages, values for median and distinct count). A property test checks 150 random datasets: re-combining filtered parts always equals pandas on the filtered raw rows, for all 8 aggregations.
- Date buckets (`ts.bucket`): year, quarter, month, week, day, hour, minute, second; fiscal years and quarters; Monday/Sunday/Saturday weeks. Missing periods as gaps, zeros or left out.
- Top N + exact "Other" (with its member list), stable sorting (value, natural, ordered categories, custom lists, `by:<measure>`), automatic split by currency, `min_group_size` privacy suppression.
- `ts.table_calc`: running total, % of total (filtered or fixed), rank, difference, % difference, moving average; restarts per group.
- `ts.calc`: calculated fields with our own parser (no eval): arithmetic, comparisons, IF/ELSEIF/ELSE, AND/OR/NOT, 7 aggregates and 30 row functions, `$parameters`. Aggregate formulas stay exact after filtering.

### Fixed
- Date reader used the caller's success threshold for structural choices; with threshold 0 every column was read as year-first.


### Added: foundation
- `ts.load`: safe local file loading (CSV/TSV/TXT, Excel with defusedxml, Parquet with pyarrow >= 15, JSON). URLs are rejected; encodings detected (UTF-8, BOM, Windows-1252); delimiters sniffed; leading zeros kept.
- `ts.profile`: roles, units (including from column names), default aggregation by unit, IDs, years, coordinates, ordered text, currency-code columns, mixed-currency warnings, hierarchies, overrides, and schema save/load. Every guess records its reason.
- `ts.check`: data-quality report with a score; changes nothing.
- `ts.clean`: optional cleaning (`off` / `safe` / `auto`) with apply, undo and reusable saved decisions.
- `ts.format_number` / `ts.format_date`: compact, full and raw styles; 14 locales including Indian lakh/crore and German/French spacing; Excel-style patterns through a strict parser; fiscal years.
- Colour registry (stable, pinnable, hex-validated), palettes, WCAG contrast checks; light, dark and print themes.
- `ChartSpec`: 33 chart kinds, strict versioned JSON that never runs code.
- Settings: `ts.set_defaults(...)` and scoped `with ts.config(...)` (contextvars).
- Translations for month/day names in 7 languages; English UI words.

### Security
- `docs/SECURITY_CHECKLIST.md`, applied to every change.
- AST guard test forbidding `eval`/`exec`/`pickle`/`subprocess`, `.format()` on runtime strings, network modules, and file readers outside `io.py`.
- ruff bandit rules (`S`), pip-audit and npm audit CI job, Dependabot.
- Fuzz tests (hypothesis) on number formatting, pattern parsing and spec loading; malicious-input tests for every new input.

### Added
- Project setup: package skeleton (`src/` layout), `pyproject.toml` (Python 3.11–3.14), ruff, mypy, pytest, CI workflow, licences and NOTICE.
- Pinned third-party files with a hash lock: ECharts 6.1.0, topojson-client 3.1.0, Natural Earth 5.1.2 raw data (`tools/fetch_vendor.py`).
- ECharts feature check in Node (`tests/js/echarts_features.cjs`), see `docs/decisions/0001-echarts-version.md`.
