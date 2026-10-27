# Changelog

All notable changes are listed here. The project follows [Semantic Versioning](https://semver.org/).

## Unreleased

### Added (Phase 5: world maps)
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

### Fixed (Phase 5)
- `ts.aggregate` crashed when a grouping column's name started with `__`.

### Added (Phase 4: choosing and checking charts)
- `ts.recommend(data, x, y, color)`: ranks the chart kinds that fit, each with a score and a reason, lists the kinds it ruled out with reasons, and `why_not(kind)`. Charts from later phases are listed with their phase; `.best` is the best one drawable today. Rules look at dates and their span, category counts and label lengths, whether a measure adds up, negative totals, IDs, nesting and units.
- `ts.chart(..., kind="auto")` draws the best recommendation; anything you pass still wins.
- `fig.explain()`: every decision tabsight made for a chart, in plain English.
- `fig.lint(ignore=..., strict=...)`: 17 design rules (`tabsight.lint.RULES`) with fixes and the `ts.chart` arguments that apply them. Reads the figure itself, so `fig.update()` patches are checked too. `ChartLintError` for strict mode.
- 70 labelled recommender cases (`tests/recommend_cases.py`); every automatic chart for them passes its own linter.
- When two categories are picked and the colour field has many values, the one with fewer values goes in the colours. With more than 8 lines, `auto` keeps the biggest 6.
- Docs: "Choosing a chart" guide and the lint rules reference.

### Fixed (Phase 4)
- Grouping by an ordered categorical column crashed on pandas 2 while sorting (found by the recommender cases).
- Time-zone-aware dates crashed `ts.aggregate` with a month, quarter or year grain. They're now grouped by their own wall-clock date, or in the `tz` setting's zone when it's set (the setting existed but did nothing until now).
- pandas 2 printed FutureWarnings (`observed=False`, silent downcasting) from profiling, aggregation and charts.
- "Did you mean" hints in error messages are shortened like the rest of the message.

### Changed (after hands-on review of Phase 4)
- `ts.recommend` checks its fields: at least one column, each used once, names must be text.
- A number used as x (like Quantity) keeps numeric order and suggests a scatter plot; more than 15 distinct numbers leads to a table.
- More than 50 categories: horizontal bars of the top 20 plus Other; donuts are ruled out.
- Nested fields (Region and State): one bar per State, coloured by its Region, instead of a table. Grouped and 100% bars are ruled out for nested fields.
- A date with only one period gets a bar, not an invisible one-point line.
- An "Other" line in a multi-line chart starts hidden (one click in the legend shows it), because as a total it dwarfs the real lines.
- New lint rules: `mixed_units` (info) and `no_data` (warning). Stacking rules no longer fire when each bar has one segment. `ignore=None` is accepted.
- `explain()` wording: "multi-line chart", no repeated "averaged ... averaged"; a table without a measure says it's in natural order.

### Added (Phase 3: core charts)
- `ts.chart`: bar, hbar, grouped, stacked and 100% stacked bars; line, multi-line, area, stacked area and sparkline; donut; KPI card; table. BI rules by default: all labels shown (switching to horizontal bars when labels are long), lines never smoothed, zero baseline for bars, one colour per series, the same colour for the same value across charts, top 7 + grey "Other" for donuts, grouped parents in tables.
- Notes on figures, including a warning when the last period is incomplete and would look low.
- `Figure`: `to_dict()` (plain JSON), `to_html()` (one offline file, or `cdn=True` with Subresource Integrity), `_repr_html_()` (sandboxed iframe in Jupyter), `update()` (safe deep merge).
- `tabsight.js` browser runtime and `ts.runtime_js()`. Number formatting is a line-by-line port of Python's, checked on 54,950 cases.
- Docs: "Making charts" guide.

### Security (Phase 3)
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
- Documentation in `docs/`: getting started, 12 user-guide pages, API reference generated from docstrings, formula functions, locales, chart kinds, warnings and errors, roadmap and security. Reads on GitHub and builds a MkDocs Material site.
- `tests/test_docs.py` runs every documentation example and checks the locale, formula, chart-kind, settings and check-code tables against the code.
- Synthetic sample dataset `examples/superstore_sample.csv` (generated by `tools/make_sample_data.py`).
- Logo and wordmark (`docs/assets/`), with a dark-mode wordmark for GitHub.
- Docs CI workflow, with GitHub Pages deployment once the repository is public.

### Fixed
- Report text (`Profile.show()`, `CheckReport.show()`, `CleanReport.show()`) used "→", which crashed `print()` on Windows consoles using cp1252; it now uses "->".


### Added (Phase 2: aggregation and correctness)
- `ts.aggregate`: group-by through exact re-aggregation *parts* (sum/count for means, Σw·x and Σw for weighted averages, values for median and distinct count). A property test checks 150 random datasets: re-combining filtered parts always equals pandas on the filtered raw rows, for all 8 aggregations.
- Date buckets (`ts.bucket`): year, quarter, month, week, day, hour, minute, second; fiscal years and quarters; Monday/Sunday/Saturday weeks. Missing periods as gaps, zeros or left out.
- Top N + exact "Other" (with its member list), stable sorting (value, natural, ordered categories, custom lists, `by:<measure>`), automatic split by currency, `min_group_size` privacy suppression.
- `ts.table_calc`: running total, % of total (filtered or fixed), rank, difference, % difference, moving average; restarts per group.
- `ts.calc`: calculated fields with our own parser (no eval): arithmetic, comparisons, IF/ELSEIF/ELSE, AND/OR/NOT, 7 aggregates and 30 row functions, `$parameters`. Aggregate formulas stay exact after filtering.

### Fixed
- Date reader used the caller's success threshold for structural choices; with threshold 0 every column was read as year-first.


### Added (Phase 1: foundation)
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
- `docs/SECURITY_CHECKLIST.md`, applied in every phase.
- AST guard test forbidding `eval`/`exec`/`pickle`/`subprocess`, `.format()` on runtime strings, network modules, and file readers outside `io.py`.
- ruff bandit rules (`S`), pip-audit and npm audit CI job, Dependabot.
- Fuzz tests (hypothesis) on number formatting, pattern parsing and spec loading; malicious-input tests for every new input.

### Added (Phase 0)
- Phase 0 project setup: package skeleton (`src/` layout), `pyproject.toml` (Python 3.11–3.14), ruff, mypy, pytest, CI workflow, licences and NOTICE.
- Pinned third-party files with a hash lock: ECharts 6.1.0, topojson-client 3.1.0, Natural Earth 5.1.2 raw data (`tools/fetch_vendor.py`).
- ECharts feature check in Node (`tests/js/echarts_features.cjs`), see `docs/decisions/0001-echarts-version.md`.
