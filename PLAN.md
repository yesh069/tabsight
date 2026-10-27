# tabsight - Build Plan

**BI-quality charts, world maps and dashboards from a pandas DataFrame. Rule-based. No LLM. One offline HTML file.**

Name: **tabsight** (tab(le) + insight), confirmed. As of 27 Oct 2026 it is free on PyPI, on npm (`tabsight` and `tabsight-js`) and as a GitHub user/organisation name. `tabviz`, the name used in the old guide, is already taken.

Python: **3.11–3.14**, with **3.13 as the main version** for development and testing.

This is an open-source product, not an assignment. There is no deadline: each phase is built properly and finished before the next starts.

Guiding rule: **tabsight suggests, the user decides.**

---

## Contents

1. Research: what already exists
2. What makes tabsight stand out
3. Design principles and user control
4. Reading data (always) and cleaning (optional)
5. Aggregation, calculations and correctness
6. Dates, units and formatting
7. World maps
8. How people will use it
9. Architecture
10. Package layout
11. Chart catalogue
12. The recommender
13. Analytics and insights
14. Dashboards
15. Security, privacy and licences
16. Performance
17. Compatibility and engineering
18. Tests
19. Benchmarks
20. Build order
21. Risks
22. Out of scope (decided on purpose)
23. Needed before building

---

## 1. Research: what already exists

| Tool | What it does well | Where it falls short for our goal |
|------|-------------------|-----------------------------------|
| **PyGWalker** (Kanaries) | Tableau-like drag-and-drop UI inside Jupyter | Manual, with no automatic "Show Me" recommender. Its static HTML export cannot compute or save edits. No Python API for building a dashboard. Weak geo. |
| **Lux** (Berkeley) | Shows chart suggestions automatically when you print a DataFrame | Not maintained (last push about 2024). Notebook only. No dashboards, maps or business formatting. |
| **Vizro** (McKinsey) | Dashboards from config (Pydantic, YAML), with interacting charts | Needs a running Dash server, so no single offline file. You choose every chart yourself. |
| **Plotly / Plotly Express** | Many charts, built-in US-state and country maps | Maps stop at US states and countries. Charts are separate, so no dashboard cross-filtering in an HTML file. Formatting is left to you. |
| **pyecharts** | Python wrapper for ECharts | Default ECharts look. No profiling, recommending, unit formatting or dashboard runtime. |
| **Perspective** (FINOS) | Very fast data grid and pivots for streaming data | Built for engineers. No Tableau-style dashboards or maps. |
| **GlyphX, PlotaViz** | A `suggest` command, or a rule-plus-score engine | GlyphX's natural-language feature needs an LLM key. PlotaViz is a desktop app, not a library. |
| **LIDA, Data Formulator** (Microsoft) | LLM picks and writes the charts | Needs an LLM. Results change between runs. |
| **Draco** (UW) | Chart rules written as logic constraints | A research tool that needs a solver. |
| **Superset, Metabase, Tableau** | Full BI platforms | Servers or paid products, not a pip package. |

**The gap:** no pip package takes a DataFrame and automatically returns BI-quality charts, maps for every country and region, and a cross-filtering dashboard as one offline HTML file, with explained choices, written insights and no LLM.

---

## 2. What makes tabsight stand out

### Core
1. **One line to a full dashboard.** `ts.auto(df)` (or `tabsight auto data.csv` on the command line) profiles the data, picks KPIs, charts and maps, and writes one offline HTML file with filters.
2. **"Show Me" with reasons.** A ranked list with a reason for each chart and why others were rejected. Deterministic and tested against a labelled set of cases.
3. **Formatting right by default.** Units are detected, so `$2.3M`, `15.6%`, `3.2 days` and `Jan 2017` show up everywhere automatically, in any locale.
4. **Correct numbers after filtering.** Averages, ratios and medians stay exact when a viewer filters in the browser (section 5). Many hand-built dashboards get this wrong.
5. **Chart linter.** `fig.lint()` checks a BI-quality checklist and returns warnings with fixes.
6. **World maps at three levels, offline.** Countries, then states/provinces/counties for every country (Irish counties, Indian states, German Länder and so on), plus about 7,000 cities. The right map is detected automatically from the values. Deeper district levels can be downloaded if the user opts in.
7. **Cross-filtering in a static file.** Click or drag-select to filter every other tile. Drill-down, chips, reset, and a shareable URL state, all with no server.
8. **Automatic hierarchies.** It detects Category → Sub-Category and Country → State → City, then uses them for drill-down and treemaps without any setup.
9. **The same colour for the same value everywhere.** One colour registry per dashboard, with stable colour order.
10. **Spec-first.** Every chart and dashboard is versioned JSON. It works in FastAPI, Flask, Streamlit and Dash, and a saved dashboard can be refreshed with new data.
11. **Optional cleaning that shows every change.** Off by default, with every change listed and undoable when it is used.
12. **Small, safe install.** Only pandas is required. Output works offline, has no network calls and escapes every data value.

### Tier 1 extras (part of the main build)
13. **Auto-insights in plain English**, from rules, never an LLM.
14. **Analytics pane:** trend line, reference lines and bands, forecast labelled "Estimate", outliers.
15. **Period comparisons:** YoY, MoM, YTD, previous period, and fiscal years.
16. **Table calculations:** running total, % of total, rank, moving average, difference.
17. **Safe calculated fields and parameters**, using our own parser and never `eval`.
18. **Locales and translations:** number formats plus UI words ("Other", "No data", "Reset filters").
19. **Accessibility:** colour-blind palettes, keyboard use, screen-reader labels, alt-text, "view as table", WCAG AA contrast.

### Tier 2 (later phases)
20. PPTX and PDF export.
21. Big data via DuckDB/SQL.
22. Story pages.
23. Ready templates (Sales, HR, Finance, Marketing).
24. Data-quality scorecard tile.
25. Brand themes.
26. Simple joins across two tables.

27. More chart types: radar, Gantt, slope / dumbbell.
28. npm package for the JS runtime (`tabsight-js`).

**Not planned:** see section 22 for the full list and the reason for each.

---

## 3. Design principles and user control

### The 6 rules behind every feature
1. **Never change the user's data.** Work on internal copies only.
2. **A smart default, but always overridable.** Every guess can be changed in one argument.
3. **Warn, don't block.** Problems show up as warnings, not errors, unless the user asks for strict mode.
4. **Show every guess.** The user can always see what was assumed and why.
5. **Extras are opt-in.** Anything that adds or estimates information is off or clearly labelled.
6. **Private and offline by default.** No network calls, no telemetry, and only the data charts need gets embedded.

### Feature-by-feature control

Rows 53–60 were added in the second review and rows 61–68 in the third. They sit in their topic group, so the numbers are not in order.

**Data and preparation**

| # | Feature | Default | User control |
|---|---------|---------|--------------|
| 1 | Cleaning | Off | `ts.clean(df)` or `clean="safe"` / `"auto"` |
| 2 | Quality check | Warnings only | `ts.check(df)` report, or `quiet=True` |
| 3 | Profiling (roles, units) | Auto-detected | `overrides={...}`, or save/load a schema file |
| 4 | Date reading | Inferred, used only inside the chart | `date_format=`, `dayfirst=True` |
| 5 | Aggregation | **Depends on the unit:** sum for amounts and counts, mean for rates, prices and scores | `agg="sum"`, `"mean"`, `"median"`, `"countd"`, `"none"` and so on |
| 6 | Already-aggregated data | Detected (one row per category), so it isn't summed twice | `agg="none"` |
| 7 | Input types | pandas | polars (needs pyarrow), a list of dicts, CSV/Excel/Parquet path |
| 8 | Hierarchies | Auto-detected | `hierarchies={"Product": ["Category", "Sub_Category"]}` or `False` |
| 53 | Order of text values | Known orders detected (months, weekdays, sizes, Likert, Low/Medium/High) | `order=["Bronze", "Silver", "Gold"]` |
| 54 | Mixed currencies in one column | Warning, never summed together | Filter one currency, or `split_by="Currency"` |
| 61 | File encoding | UTF-8, then UTF-8 with BOM, then Windows-1252, with a warning | `encoding="latin-1"` |
| 62 | Weighted average | Plain average; linter suggests weighting when an amount column exists | `agg="wavg", weight="Sales"` |

**Choosing charts**

| # | Feature | Default | User control |
|---|---------|---------|--------------|
| 9 | Recommender | Suggests a ranked list | Pick any chart; an odd choice gives a warning, not an error |
| 10 | Explanation | On request | `fig.explain()` |
| 11 | Auto dashboard | Starting point | `include=`, `exclude=`, `max_tiles=`, then export the spec, edit and reload |

**How charts look**

| # | Feature | Default | User control |
|---|---------|---------|--------------|
| 12 | Number formatting | Auto | `unit=`, `decimals=`, `currency=`, `locale=`, `format="#,##0.0"`, `negative="parens"` |
| 13 | Raw values | Always kept in tooltips and exports | Cannot be turned off |
| 14 | Sorting | By value for rankings, natural order for time | `sort=` asc / desc / none / custom list / by another measure |
| 15 | Top N + "Other" | On above 8–15 categories, with a "Top 10 of 17" note | `top=20` or `top=None` |
| 16 | Colours | Auto, stable, same value → same colour | `colors={...}`, `palette=` |
| 17 | Theme | Tableau-like light | `theme="dark"`, `"print"`, custom |
| 18 | Titles | Generated ("Sum of Sales by Region") | `title=`, `subtitle=` |
| 19 | Axis | Zero baseline for bars, data range for lines and scatter | `y_min=`, `y_max=`, `log=True` |
| 20 | Escape hatch | — | `fig.update({...})` edits the raw ECharts option |
| 55 | Small multiples | Off | `facet="Region"` (one mini chart per value, shared axes) |

**Analysis extras**

| # | Feature | Default | User control |
|---|---------|---------|--------------|
| 21 | Auto-insights | On in `auto()`, off in single charts | `insights=False`, thresholds |
| 22 | Trend line | Off | `trend=True` |
| 23 | Forecast | Off | `forecast=6`, dashed with a band and labelled "Estimate" |
| 24 | Outliers | Flagged, never removed | `outliers=False` |
| 25 | Period comparison | Off | `compare="previous_year"` |
| 26 | Table calculations | Off | `calc="running_total"`, `"pct_of_total"`, `"rank"`, `"moving_avg:3"`, `"difference"` |
| 27 | % of total base | The **filtered** total | `fixed=True` uses the overall total (like Tableau FIXED) |
| 28 | Calculated fields | — | `ts.calc("Margin = SUM(Profit) / SUM(Sales)")` |
| 63 | Reference date ("today") | Latest date in the data | `as_of="2017-12-31"` |
| 64 | Forecast season length | From the date grain (12 monthly, 4 quarterly, 52 weekly, 7 daily) | `season=` |

**Dates**

| # | Feature | Default | User control |
|---|---------|---------|--------------|
| 29 | Fiscal year | Calendar year | `fiscal_start=4` (April) |
| 30 | Week start | Monday (ISO) | `week_start="sunday"` |
| 31 | Missing periods | Shown as gaps on lines, zero on bars | `missing="zero"`, `"gap"` or `"connect"` |
| 32 | Time zone | As in the data | `tz="Europe/Dublin"` |

**Maps**

| # | Feature | Default | User control |
|---|---------|---------|--------------|
| 33 | Map level and country | Detected from the values | `map="IRL"`, `level=1` |
| 34 | Name matching | Names, local names, ISO codes, aliases | `geo_map={"Co. Cork": "Cork"}` |
| 35 | Unmatched names | Reported, never dropped silently | Warning + tooltip note |
| 36 | Ambiguous cities | Use the country or state column; else the most populous, with a warning | `country=` column, `geo_map=` |
| 37 | Projection | Equal Earth (world), local best fit (regions) | `projection="mercator"` |
| 38 | District level | Not available offline | `ts.geo.download("IND", level=2)` (opt-in) |
| 39 | Custom shapes | — | `geojson="my_regions.json"` |
| 56 | Place name language | English | `geo_names="local"` or a language code (`"de"`, `"hi"`, `"zh"`) |
| 57 | Map colour scale when filtered | Rescales to the filtered data; legend shows the new range | `scale="fixed"` keeps the full-data range |

**Dashboard and interaction**

| # | Feature | Default | User control |
|---|---------|---------|--------------|
| 40 | Cross-filtering (click and drag) | On | `cross_filter=False`, per tile |
| 41 | Drill-down | On for dates and detected hierarchies | `drill=False` or a custom hierarchy |
| 42 | Tile menu | On | `menu=False` or choose the items |
| 43 | Layout | Auto grid | `w=`, `h=`, order, manual grid |
| 44 | URL state | On (filters saved in the address) | `url_state=False` |
| 58 | Light/dark toggle for the viewer | Shown; follows the system setting | `theme_toggle=False` |
| 59 | Data per tile | All tiles use the dashboard's data | `data=other_df` on a tile; filters skip tiles without that field |
| 65 | What a click does | Filters the other tiles; legend click highlights | `action="highlight"` per tile |
| 66 | Multi-select | Ctrl/Shift + click adds values | — |

**Output, privacy and safety**

| # | Feature | Default | User control |
|---|---------|---------|--------------|
| 45 | Data in the HTML | Aggregated rows only | `embed="raw"`, `exclude_columns=` |
| 46 | Network | None | `cdn=True` |
| 47 | File size | Estimated before building, warning above 5 MB | `max_size=` or server mode |
| 48 | Linter | Warnings (Python `warnings` categories) | `ignore=[...]`, `strict=True` |
| 49 | Determinism | Same input → same output | — |
| 50 | Saved specs | Versioned | Old specs still load |
| 51 | Optional dependencies | Core needs only pandas | `tabsight[excel,parquet,polars,png]` now; `pptx`, `duckdb` later |
| 60 | Output for plain ECharts | Named formatters that need `tabsight.js` | `fig.to_dict(pure=True)` pre-formats labels (some features lost) |
| 67 | Small-group protection | Off | `min_group_size=5` hides smaller groups |
| 68 | CSV formula protection | On | `csv_safe=False` |

**Settings**

| # | Feature | How it works |
|---|---------|--------------|
| 52 | Where settings come from | **Per chart → per dashboard → `with ts.config(...)` block → `ts.set_defaults(...)` → built-in default.** Scoped settings live in `contextvars`, so they are safe in web servers with many users at once. `ts.set_defaults` changes the whole program (typically once at start-up). Calling `ts.config(...)` without `with` does nothing, so tabsight warns and points to `set_defaults`. |

---

## 4. Reading data (always) and cleaning (optional)

Most users clean data their own way, so tabsight never forces cleaning.

| | Reading (always on) | Cleaning (optional) |
|---|---|---|
| What it does | Works out roles, units and formats so charts draw correctly | Changes values: trims, merges spellings, fixes types |
| Changes your data? | **No.** Temporary internal copy | Only in a new copy, with a report |
| Example | Reads `"2017-01-05"` text as a date *for the axis only* | Turns `west` into `West` |

### 4.1 Reading rules
- **Name checks use whole-word tokens, not substrings.** `Lifetime_Value` is not a time field. Names are split on `_`, spaces and camelCase.
- **Data is checked before the name.** Date parsing must succeed for at least 95% of values.
- **IDs:** a name token in `{id, code, key, zip, postal}`, or all values distinct → dimension, never summed. Leading zeros are kept.
- **Low-cardinality integers** (years, ratings 1-5) → discrete dimension.
- **Percent scale** is decided once per column from its range, not separately for each value.
- **Booleans** → dimension (Yes/No). **Timedelta** → duration measure. **Categorical dtype** keeps its order (ordinal).
- **A meaningful index** (DatetimeIndex, named index) is turned into a column; MultiIndex columns are flattened with `" / "`.
- **Geo detection:** at least 80% of values match the bundled world names or codes (section 7). Latitude/longitude pairs are found by name and range.
- **Hierarchy detection:** if every value of B maps to exactly one value of A (Sub-Category → Category), they form a hierarchy. To avoid false hierarchies, only columns with fewer than 500 distinct values are considered, IDs are excluded, and the parent must have fewer distinct values than the child.
- **Units from column names:** `Sales (€)`, `Weight_kg`, `Price_USD`, `Duration_hrs` give the unit directly. This beats guessing from words and is checked first.
- **Ordered text values:** built-in orders are detected for months (`Jan`, `January`), weekdays, quarters, sizes (`XS`–`XXL`), Likert scales (`Strongly disagree` … `Strongly agree`) and levels (`Low`, `Medium`, `High`). These columns sort in their natural order, never alphabetically. Overridable with `order=[...]`.
- **Mixed currencies:** if a measure sits next to a currency-code column (`Currency` with `EUR`, `USD`, `GBP`), tabsight warns "Sales mixes 3 currencies" and never sums across them. It suggests filtering one currency or `split_by="Currency"`. There is no exchange-rate conversion (section 22).
- **File encoding:** when given a file path (Python or command line), tabsight tries UTF-8, then UTF-8 with BOM, then Windows-1252, and warns which one was used. The widely shared Superstore CSV is Windows-1252, so this matters. `encoding=` overrides it.
- **Speed:** types are detected on a 10,000-row sample first, then confirmed on the full column only for the chosen type.
- **Memory:** only the columns a chart uses are copied, never the whole DataFrame. On pandas 3, copy-on-write makes these copies cheap.
- **Stable order:** whenever values tie (in sorting, top N or colour assignment), ties are broken by name, so the same input always gives the same output.

### 4.2 Edge cases (each has a defined behaviour and a test)

| Case | Behaviour |
|------|-----------|
| Empty DataFrame | A friendly "No data" chart, never a crash |
| One row | KPI or table |
| All-null column | Ignored by the recommender, reported by `check` |
| Infinity / NaN | Treated as missing, reported |
| Mixed types in one column | Read as text, reported, with a suggestion to clean |
| Very long labels | Shortened with "…" on axes; full text in tooltips |
| Emoji / non-Latin text | Fully supported (UTF-8 everywhere) |
| Duplicate column names | Suffixed and reported |
| Only negative values | Bars grow downward; no donut or treemap |
| Constant column | Flagged as "no variation" and not used for colour or size |

### 4.3 Cleaning modes

| Mode | What it does |
|------|--------------|
| `"off"` (default) | Changes nothing |
| `"safe"` | Applies only fixes that can't change meaning; suggests the rest |
| `"auto"` | Also applies the suggested fixes |

| Area | Safe fix | Suggested (auto only) | Only reported |
|------|----------|-----------------------|---------------|
| Column names | Clean internal key; display name kept | — | Duplicates |
| Text values | Trim spaces | Merge case variants into the most common spelling | Near-duplicates (`Califronia`), with a "did you mean" |
| Dates | Standardise separators; infer day/month from values above 12 | Use the locale when the data can't decide (assumption recorded) | Unparseable values; dates before 1901; future dates (only against an explicit `as_of`, never the clock); ship-before-order |
| Numbers as text | `"$1,234.50"`, `"15%"`, `"(500)"` → numbers, unit remembered | European separators | Values that can't be converted |
| Excel serial dates | — | A date-named column of numbers like `43831` → dates (Excel's day count) | The guess and the date range it produces |
| Missing values | Placeholders (`N/A`, `-`, `null`, `?`, `""`) → missing | — | Measures are never filled; dimensions show "Unknown" |
| Duplicates | — | Removed only with `dedupe=True` | Exact duplicate rows |
| Outliers | — | — | Flagged, never removed |

```python
clean_df, report = ts.clean(df, mode="safe")
report.show()  # applied / suggested / warnings, quality score out of 100
report.apply("Segment")  # apply one suggestion
report.undo("Region")  # restore one column
report.to_dict()  # save the decisions and reuse them on next month's data
```

---

## 5. Aggregation, calculations and correctness

This section exists so that **the numbers are always right**, including after the viewer filters in the browser.

### 5.1 Default aggregation by unit

| Measure type (detected) | Default | Why |
|-------------------------|---------|-----|
| Currency amount (Sales, Revenue, Cost) | sum | Amounts add up |
| Count (Quantity, Orders) | sum | Counts add up |
| Percent / rate (Discount, Rate, Margin) | mean | A total discount of 1,560% is nonsense |
| Price, unit cost, score, rating, temperature, age | mean | Their totals are meaningless |
| ID column | count distinct (if used as a measure) | Never sum IDs |

The chosen aggregation is always shown in the title and tooltip ("Avg Discount"), and can be overridden.

**Plain vs weighted average.** The default for rates is a plain average across rows. Often a weighted average is what people mean, for example discount weighted by sales. `agg="wavg", weight="Sales"` gives it (and stays exact after filtering, section 5.2). When a rate sits next to an amount column, the linter suggests the weighted version, but never switches on its own.

**Missing values in averages:** a mean counts only rows that have a value, so the stored count in section 5.2 is the non-missing count.

### 5.2 Exact re-aggregation in the browser

When a filter changes, the browser re-aggregates the stored rows. Each aggregation is stored so it stays **exact**:

| Aggregation | Stored per row | Recomputed in the browser as | Exact? |
|-------------|----------------|------------------------------|--------|
| sum | sum | sum of sums | Yes |
| count | count | sum of counts | Yes |
| mean | sum + count | Σsum / Σcount | Yes |
| min / max | min / max | min of mins / max of maxes | Yes |
| ratio calc (`SUM(a)/SUM(b)`) | sum(a), sum(b) | Σa / Σb | Yes |
| weighted average | Σ(w·x), Σw | Σ(w·x) / Σw | Yes |
| median, percentiles, count distinct, box plot | values at the needed grain (with a size cap) | computed from the values | Yes, within the cap |
| — above the cap | — | that tile shows "filter not applied to this tile" and links to server mode | Never silently wrong |

The linter warns when a tile cannot be re-aggregated exactly.

### 5.3 Table calculations
Running total, % of total, rank, moving average, difference and % difference.
- They are computed **after** aggregation and **after** filters, as in Tableau.
- `% of total` uses the filtered total by default; `fixed=True` uses the overall total. The tooltip states which base was used.

### 5.4 Calculated fields
- **Row-level:** `Profit / Sales` is computed on each row and then aggregated.
- **Aggregate:** `SUM(Profit) / SUM(Sales)` is computed after grouping. This is the default suggestion for ratios.
- The parser supports:
  - operators: `+ - * /` and comparisons
  - logic: `IF/THEN/ELSE`, `AND`, `OR`
  - aggregates: `SUM`, `AVG`, `MIN`, `MAX`, `COUNT`, `COUNTD`, `MEDIAN`
  - functions: `ROUND`, `ABS`, date parts, `CONTAINS`
- It is our own parser with an allow-list: no `eval`, no attribute access, no imports.
- Parameters (Top N, measure switcher, threshold) appear as dashboard controls.
- **Parameters in offline HTML:** the HTML only holds grouped rows, so a parameter can only change things computed *after* grouping:
  - Work offline: Top N, measure switcher, reference-line and target values, and thresholds used on grouped values (`IF SUM(Profit) < [Target]`).
  - Need server mode: parameters inside row-level formulas (`IF Sales > [Threshold]`), because every row would have to be recomputed. The linter says so and suggests server mode.

### 5.4a Decisions made while building Phase 2
- **Top N never applies to dates.** It applies to the first category dimension, so `[Month, Region]` with `top=5` keeps the top 5 regions across all months (what a multi-line chart needs). If every dimension is a date, top N is skipped with a note.
- **Ranking follows the first requested output**, which may be a calculated field (`top=` by margin works).
- **An all-missing group is missing, not 0** (sums use `min_count=1`), so an empty group never looks like a real zero.
- **"Other" is labelled with its size** (`Other (4)`), which also avoids clashing with a real category called "Other".
- **Calculated fields:** a row-level formula is aggregated with `sum`. Aggregate formulas become hidden exact measures, so they stay exact after filtering. Division by zero, overflow, `LN(0)` and `SQRT(-1)` give a missing value, never an error or infinity. Formula limits: 2,000 characters, 1,000 tokens, 50 levels of nesting, 500-character text values, 100 parameters.
- **`min_group_size` also hides formula results** for small groups.

### 5.5 Hierarchies
Detected or declared hierarchies drive drill-down, treemap and sunburst levels, and "Other" grouping inside each parent.

### 5.6 What a click means (filter semantics)

A filter is always built from what the mark **stands for**, never from its label text.

| Viewer clicks | Filter created |
|---------------|----------------|
| A normal bar, slice or region | `field = value` |
| The **"Other"** bar | `field in [the values inside "Other"]`. The binding stores that list. |
| A histogram bin | `lower <= field < upper` (bin edges stored in the binding) |
| A month, quarter or year | `start <= date < end` for that period |
| A country on a city-level map | `country = value` (all cities in it) |
| A treemap or sunburst parent | `parent_field = value` |
| A drag (brush) on a time or numeric axis | `start <= field <= end` |
| The same mark again | Removes that filter |
| **Ctrl/Shift + click** on another mark | **Adds** that value to the filter (multi-select) |
| A **legend item** | **Highlights** that series and dims the others, as in Tableau. Ctrl + click hides the series. A legend click never filters other tiles. |

**Filter or highlight:** each tile chooses what its clicks do: `action="filter"` (default) filters the other tiles, and `action="highlight"` only highlights matching marks in the other tiles without removing data.

Further rules:
- **Top N after filtering:** the top N is recalculated on the filtered data, so the list of values inside "Other" changes too. The chart note says "Top 10 of 17 (filtered)".
- **Several filters:** values within one field combine with OR; different fields combine with AND, as in Tableau.
- **Tiles with different data:** a tile can use its own DataFrame (`data=`). A filter applies only to tiles whose data has that field. Other tiles show a small "Not affected by Region" note, so nothing looks wrong silently. Joining tables stays in Tier 2.
- **The source tile** highlights the selected mark instead of filtering itself.

---

## 6. Dates, units and formatting

### Units

| Unit | Examples |
|------|----------|
| currency | `$2.3M` (compact), `$2,297,201` (full), `(1,234)` accounting option |
| percent | `15.6%` |
| percentage points | `+3.2 pp` (difference between two percents) |
| count | `5,009`, `5K` |
| number | `12.35` |
| duration | `3.2 days`, `4h 12m` |
| custom | Excel-style format strings: `"#,##0.0"`, `"0.0%"` |

Three styles everywhere: **compact** (axes, KPIs), **full** (tooltips, tables) and **raw** (exports).

### Locales and translation
- Numbers and currency: `en_US`, `en_IE` (`€1,234.5`), `de_DE` (`1.234,5 €`), `en_IN` (`₹1,23,456`), and more.
- **Compact suffixes per locale:** `$2.3M` in English, `2,3 Mio. €` in German, and `₹12.3L` / `₹1.2Cr` (lakh, crore) for `en_IN`.
- **Right-to-left languages** (Arabic, Hebrew) are not supported at first, and the docs say so.
- Dates: day-first or month-first, and translated month names.
- **UI words** ("Other", "No data", "Unknown", "Reset filters", "Estimate", "Top 10 of 17") come from translation files. English ships first, and other languages can be added as simple JSON files.
- Insight sentences use templates per language; English first.

### Dates
- Grains: year, quarter, month, week, day, hour, with automatic choice based on the date range.
- Fiscal years (`fiscal_start=4` → "FY2018 Q1").
- ISO weeks with a configurable week start.
- Missing periods: gaps on lines, zero on bars, configurable.
- Time zones: converted only if the user asks.

### Fonts and colour contrast
- System font stack (Segoe UI, -apple-system, Roboto, Arial), with no font downloads.
- Every theme meets WCAG AA contrast for text, which is checked in tests.

---

## 7. World maps

### 7.1 Levels

| Level | Example | Source | Count | Ships as |
|-------|---------|--------|-------|----------|
| 0. Countries | Ireland, India, Brazil | Natural Earth admin-0 (public domain) | about 250 | Bundled, about 250 KB |
| 1. States / provinces / counties | Irish counties, Indian states, German Länder, US states | Natural Earth admin-1 (public domain) | about 4,600 | Bundled, **one file per country**, about 5–8 MB in total after simplifying (TopoJSON) |
| 2. Districts | Indian districts, UK local authorities | geoBoundaries (CC BY 4.0) | tens of thousands | **Opt-in download**: `ts.geo.download("IND", level=2)`, cached locally |
| Points | Dublin, Mumbai, Austin | Natural Earth populated places (public domain) | about 7,000 cities | Bundled, about 300 KB |

If the level 1 data makes the main package too big (target: wheel under 15 MB), it moves into a companion package `tabsight-geo` that installs automatically.

**Quality varies by country.** Natural Earth's level 1 is not equally detailed or up to date everywhere, and for some countries it is not the level people use day to day. So in Phase 5:
- The **30 most-used countries** are checked one by one (US, Ireland, UK, India, Germany, France, China, Brazil, Canada, Australia and others) against official region lists.
- Where Natural Earth is weak or outdated, the docs point to the opt-in geoBoundaries download for that country.
- A **coverage table** in the docs lists each country, its level 1 unit (state, county, province), the number of regions and any known issues.

### 7.2 Matching names

- Each region is matched on:
  - official name and English name
  - local name (`Bayern` = `Bavaria`)
  - alternate names
  - ISO 3166-1 codes (`IE`, `IRL`)
  - ISO 3166-2 codes (`IE-CO`, `US-CA`, `IN-MH`)
- names in non-Latin scripts: Natural Earth provides names in about 25 languages (Chinese, Arabic, Hindi, Russian, Japanese and others), and all of them are matched. Transliteration (for example pinyin) is not planned.
- Common prefixes and suffixes are normalised: "County", "Co.", "State of", "Province".
- **Display language:** maps show English names by default. `geo_names="local"` shows local names (`Bayern`), and a language code (`"de"`, `"hi"`, `"zh"`) shows that language where available.
- Accents and case are ignored when matching (`Québec` = `Quebec`).
- "Did you mean" suggestions are given for typos.
- Unmatched names are always reported, never dropped.

### 7.3 Automatic map choice
- The values are matched against all levels. If most values are Irish counties, the Ireland level 1 map is used. If they are countries, the world map is used.
- If the values match several countries' regions (for example "Victoria" exists in Australia and elsewhere), a country column is used when there is one; otherwise tabsight warns and picks the best match.
- **Names that exist at two levels or in two countries** (Georgia: country or US state; Luxembourg: country or Belgian province; Punjab: India or Pakistan) are decided in this order:
  1. the other values in the same column (if most are US states, Georgia is the US state)
  2. a country column, if there is one
  3. otherwise a warning naming both options, and `geo_map=` to choose
  These names are part of the geo test set.
- Cities: "Paris" is resolved using a country or state column if there is one; otherwise the most populous match is used, with a warning.

### 7.4 Drawing
- **Projection:** Equal Earth for the world map, so areas are fair; regional maps use a projection fitted to that area. ECharts supports custom projections, and Equal Earth is a short formula we write ourselves, so there is no d3 dependency.
- **Insets** for far-off parts: Alaska, Hawaii and Puerto Rico for the US, and similar for other countries where needed.
- **Tiny countries** (Singapore, Malta and others) are drawn as dots so they can still be seen and clicked.
- **Antarctica** is hidden by default.
- **Auto zoom** to where the data is.
- **No data** regions are grey with the label "No data". Colour scales are sequential, or diverging when there are negative values.
- **Colour scale when filtered:** by default the scale rescales to the filtered data, so contrast stays visible, and the legend shows the new range. `scale="fixed"` keeps the full-data range for like-for-like comparison.
- Map types:
  - choropleth (filled regions)
  - symbol / bubble map (points sized by value)
  - **density map** for many points (heatmap on a map)
  - **flow map** (origin → destination lines), added in the advanced phase

### 7.5 Only what is needed goes into the HTML
A dashboard about Ireland embeds only the Ireland shapes. Shapes are stored as TopoJSON, which is about 80% smaller than GeoJSON, and converted in the browser.

### 7.6 Borders and credits
- Natural Earth's default view is used for disputed borders, and this is stated in the docs. Users can supply their own GeoJSON.
- Credits: Natural Earth needs none. When geoBoundaries data is used, its credit is added to the map footer automatically.
- Geo data is versioned (`tabsight.geo.version`), so updates are tracked.

### 7.7 Street-level background maps
Street or satellite backgrounds (OpenStreetMap tiles) need a network connection, so they are **not** included by default. They are a possible later option, opt-in only.

---

## 8. How people will use it

**Way 1: one line (beginners)**
```python
import pandas as pd, tabsight as ts

df = pd.read_csv("superstore.csv")
ts.auto(df).to_html("sales_dashboard.html")
```
```bash
tabsight auto superstore.csv -o sales_dashboard.html
```

**Way 2: pick your own charts (analysts)**
```python
ts.set_defaults(locale="en_IE", currency="EUR")  # whole program
ts.recommend(df, x="Region", y="Sales")  # ranked, with reasons

fig = ts.chart(df, "map", geo="County", y="Sales")  # Irish county map, detected automatically
fig.lint()
fig.explain()

dash = ts.Dashboard("Sales Performance", data=df, filters=["Region", "Order_Date"])
dash.kpi("Sales", compare="previous_year").kpi("Profit")
dash.add("map", geo="Country", y="Sales", w=6)
dash.add("line", x="Order_Date", y="Sales", freq="M", trend=True, forecast=6, w=6)
dash.add("hbar", x="Sub_Category", y="Profit", calc="pct_of_total")
dash.insights()
dash.save("sales.json")
dash.to_html("my_dashboard.html")

# next month: same dashboard, new data
ts.Dashboard.load("sales.json").bind(new_df).to_html("my_dashboard_nov.html")
```

**Way 3: inside a web app (developers)**
```python
@app.post("/chart")  # FastAPI
def chart(query: Query):
    with ts.config(locale=query.locale):
        return ts.serve_payload(run_sql(query.sql))
```
Helpers are also provided for Flask, Streamlit (`ts.streamlit(fig)`) and Dash.

**What the viewer can do in the dashboard**
- Click a map region or bar to filter all tiles; Ctrl/Shift + click adds more values. A chip appears, and clicking its **x** removes it.
- Click a legend item to highlight that series (Ctrl + click hides it).
- Drag across a time axis or scatter plot to filter a range.
- Click a year or a category to drill down; breadcrumbs lead back up.
- Hover for formatted values (`€457,688 · 19.9% of total`). On phones, tap shows the tooltip and long-press filters.
- Read the Insights panel, which updates with the filters.
- Use each tile's menu to switch chart type (only types that fit), download the tile's data as CSV (raw numbers or formatted, filters applied), save PNG or view as a table.
- Press "Reset all filters", or copy the address to share the exact filtered view. (Sharing a link only works when the HTML file is hosted somewhere; a `file://` address on one computer does not open on another.)
- Use the keyboard and a screen reader.

---

## 9. Architecture

```
DataFrame
  -> read       (internal copy; roles, units, dates, hierarchies)  -> Profile        (always)
  -> clean      (optional, off | safe | auto)                      -> CleanReport
  -> calc       (optional calculated fields, safe parser)
  -> recommend  (rules + scores + reasons)                         -> [Recommendation]
  -> spec       (kind, encodings, agg, sort, top N, table calc)    -> ChartSpec   (versioned JSON)
  -> aggregate  (pandas group-by; exact re-aggregation parts)      -> tidy rows
  -> analytics  (optional trend, forecast, refs, compare)
  -> build      (ECharts option + data binding)                    -> Figure      (JSON)
  -> insights   (optional rule-based sentences)                    -> [Insight]
  -> lint       (quality checks)                                   -> [Warning]
  -> dashboard  (tiles, layout, filters, colours, parameters)      -> Dashboard   (versioned JSON)
  -> render     (HTML / Jupyter / web payload / PNG)
```

### 9.1 One builder plus a small JS "rebinder"
- **Python builders** own chart style and structure: theme, axes, formatters, colours and labels.
- Each figure has a **data binding** that names one of seven **data shapes**:

| Shape | Used by |
|-------|---------|
| `category` | bar, hbar, lollipop, line, area, donut, funnel, waterfall, Pareto, combo bar + line, sparkline |
| `category_series` | stacked, grouped and 100% bars, multi-line, stacked area, heatmap, calendar heatmap, Sankey and flow map (source × target), small multiples |
| `xy` | scatter, bubble |
| `geo` | choropleth, symbol / bubble and density maps |
| `tree` | treemap, sunburst |
| `value` | KPI card, gauge, bullet |
| `rows` | table, box plot, histogram |

A shape can carry more than one measure (for example combo charts and bubble size), so every one of the 33 charts maps to exactly one shape.

- The **JS runtime** does the following and nothing more:
  - filters rows
  - re-aggregates using the exact rules in section 5.2
  - applies table calculations
  - reshapes into one of the seven shapes
  - patches the data into the existing option
  - recomputes simple insights
- **Parity tests** run Python and JS on the same cases using Node, with a small tolerance for floating-point rounding. JS sums use compensated (Kahan) summation so totals match Python.
- **Small JS ports** of the linear trend and Holt-Winters forecast also live in the runtime, so trend lines and forecasts update after filtering. They are covered by the same parity tests.

### 9.1a Using figures outside tabsight's HTML

ECharts formatters are JavaScript functions, which JSON cannot hold.

| Need | How |
|------|-----|
| Your own web page, full features | `fig.to_dict()` uses named formatters such as `"fmt:currency:compact"`. Include `tabsight.js` (get it with `ts.runtime_js()` or from the package's static folder) and call `tabsight.render(el, payload)`. |
| Plain ECharts, no tabsight runtime | `fig.to_dict(pure=True)`: category labels and tooltips are pre-formatted in Python, and value axes use simple ECharts template strings. Cross-filtering, compact axis formatting and insights are lost, and the docs say so. |
| Frontend developers using npm | The runtime ships inside the Python package now. Publishing it to npm as `tabsight-js` comes after 0.1.0. |

### 9.2 Data embedding and size
With cross-filtering, *any* tile's field can filter every other tile, and drill-down needs finer levels. Storing rows separately for each tile would repeat the data many times and still miss fields. So:

- **One shared table per dataset.** tabsight stores a single pre-aggregated table for each dataset, grouped by **every field used anywhere in the dashboard**: tile dimensions, filter fields, cross-filter sources, drill levels and comparison periods. It holds the exact re-aggregation parts from section 5.2. Every tile is built from this table in the browser.
- The raw data is never stored unless the user asks (`embed="raw"`).
- **Date filters default to month grain**, so a day-level date filter cannot blow up the row count.
- **The size is estimated before building**, on that shared table plus the map shapes and the runtime. If it is over the limit (default 5 MB), tabsight acts in this order and reports each step:
  1. use a coarser date grain
  2. turn off cross-filtering from the highest-cardinality fields (those tiles still show data but no longer filter others)
  3. suggest fewer filter fields or excluding some tiles from a filter
  4. suggest server mode
- Charts are drawn only when they scroll into view, so dashboards with many tiles open fast.

### 9.3 Server mode
`ts.serve_payload(...)` returns JSON. The same JS runtime draws it, and filter changes call the API instead of filtering locally. Medians, distinct counts and huge data are always exact in this mode.

### 9.4 Settings
- `ts.set_defaults(...)` changes process-wide defaults (thread-safe, under a lock).
- `with ts.config(...)` scopes settings in `contextvars`, so concurrent web requests (threads or async tasks) never overwrite each other. Both are tested.
- Every setting is validated (locale and currency patterns, ranges, names), and unknown setting names get a "did you mean".

---

## 10. Package layout

```
tabsight/
  pyproject.toml   README.md   LICENSE (MIT)   NOTICE (third-party credits)   CHANGELOG.md
  CONTRIBUTING.md   CODE_OF_CONDUCT.md   SECURITY.md   .github/ (CI, issue and PR templates)
  src/tabsight/
    __init__.py            public API
    __main__.py / cli.py   command line: tabsight auto | check | clean | recommend
    settings.py            Settings, ts.set_defaults, `with ts.config(...)` (contextvars); named settings.py so it is not hidden by the ts.config function
    warnings.py            tabsight warning categories
    io.py                  read CSV / Excel / Parquet, polars and list-of-dicts input
    read.py                internal copy, date and number reading (never changes user data)
    profile.py             roles, units, IDs, geo, date grain, hierarchies, overrides, schema save/load
    check.py               ts.check(df)
    clean.py               ts.clean(df): modes, CleanReport, apply/undo/reuse
    formulas.py            safe parser for calculated fields and parameters (ts.calc); not calc.py, so the ts.calc function does not hide it
    aggregate.py           group-by, exact re-aggregation parts, top-N + Other, date bucketing
    tablecalc.py           running total, % of total, rank, moving average, difference
    recommend.py           rules, scores, reasons, rejections
    spec.py                ChartSpec dataclasses, validation, versioned JSON
    analytics.py           trend, reference lines and bands, forecast, outliers
    compare.py             YoY, MoM, YTD, previous period, fiscal calendars
    insights.py            rule-based insight sentences
    formats.py             number / currency / percent / duration / custom formats, locales
    i18n/                  UI words and insight templates per language (en first)
    colors.py              palettes, ColorRegistry (stable order)
    theme.py               light / dark / print / brand, contrast checks
    lint.py                quality rules, ignore list, strict mode
    explain.py             fig.explain()
    figure.py              Figure: to_dict, to_html, _repr_html_, lint, explain, update, show
    charts/                one module per chart family
    geo/
      names.py             normalising, ISO codes, aliases, accents, "did you mean"
      detect.py            choose map level and country from values
      registry.py          load shapes, custom GeoJSON, insets, projections, tiny-country dots
      download.py          opt-in level-2 downloads with local cache and credits
      data/                world level 0, level 1 per country, cities (TopoJSON), version file
    dashboard/
      model.py             Dashboard, Tile, Filter, Action, Parameter (versioned)
      layout.py            12-column grid, auto placement, responsive
      auto.py              ts.auto(df)
      bind.py              Dashboard.load(...).bind(new_df) with column checks
    render/
      html.py              single-file export, embedding policy, size estimate, safe JSON
      jupyter.py           detect the notebook environment; load once (Lab, classic) or per output (VS Code, Colab)
      server.py            FastAPI / Flask payload helpers
      integrations.py      Streamlit and Dash helpers
      png.py               optional Playwright export
      static/
        tabsight.js        runtime
        tabsight.css       styles
        topojson.min.js    small TopoJSON decoder (inlined)
        echarts.min.js     pinned newest stable 6.x, chosen in Phase 0 (inlined)
        projections.js     Equal Earth projection (about 20 lines, no d3)
  tests/   benchmarks/   docs/   examples/
```

---

## 11. Chart catalogue (33 types + small multiples)

| Family | Charts |
|--------|--------|
| Comparison | bar, horizontal bar, grouped bar, lollipop, bullet |
| Part-to-whole | stacked bar, 100% stacked bar, donut, treemap, sunburst, waterfall, funnel |
| Trend | line, multi-line, area, stacked area, combo bar + line (dual axis), sparkline, calendar heatmap |
| Flow | Sankey |
| Relationship | scatter, bubble, heatmap |
| Distribution | histogram, box plot |
| Maps | choropleth, symbol / bubble map, density map, flow map |
| Single value | KPI card (comparison + sparkline), gauge |
| Detail | table (formatted, sorted, conditional colours, in-cell bars, totals) |
| Ranking | Pareto |

**Small multiples (facets):** `facet="Region"` draws one mini chart per value in a grid, with shared axes and one shared legend, like Tableau's trellis view. It works with bar, line, area, scatter and maps. Above 12 panels it shows the top 12 and notes how many were left out. Clicking a panel title filters the dashboard to that value.

**Tier 2 chart types:** radar, Gantt, slope / dumbbell.

Rules for every chart, all overridable:
- All labels shown, switching to horizontal when labels are long; very long labels are shortened.
- Straight lines, never smoothed.
- Zero baseline for bars.
- One colour for a single series.
- Top N plus "Other".
- Small labels hidden when they do not fit.
- Legend at the top.

**Large data in the browser:**
- Lines with more than 2,000 points are downsampled with LTTB, which keeps the shape.
- Scatter charts with more than 5,000 points use ECharts large mode or sampling.
- Both always show a note such as "showing 2,000 of 50,000 points".

---

## 12. The recommender

1. **Valid set:** a rules table built from field roles, covering all 33 charts and when small multiples help (a second dimension with 3–12 values).
2. **Scoring:** each valid chart gets a score from:
   - the field pattern
   - cardinality
   - label length
   - negative values
   - whether values add up to a whole
   - row count
   - hierarchies
   - geo level
3. **Output:** `Recommendation(kind, score, reason, spec)`, plus `rejected = [(kind, why)]`.
4. **Fixes from the original guide:**
   - time + dimension → multi-line and stacked area
   - long names → hbar first
   - IDs are never used as measures
   - `ts.recommend(df, x=..., y=...)` and `ts.recommend(profile)` both work
5. **Labelled test set:** at least 60 cases ("these fields → this chart"), based on published Show Me guidance and visualization best practice. The agreement rate is reported in the README.
6. **The user always decides.** Any chart can be requested; an unsuitable one gives a lint warning.

---

## 13. Analytics and insights

### Insight rules (facts only, never causes)

| Rule | Example |
|------|---------|
| Peak / low | "Sales peaked in Nov 2017 ($118K, +32% vs Oct)." |
| Biggest contributor | "Copiers give 18% of all profit." |
| Concentration | "The top 3 states make 51% of sales." |
| Negative segments | "Tables lose money in 3 of 4 regions." |
| Trend direction | "Monthly sales rose about 2.1% per month in 2017." |
| Change vs previous period | "Profit is up 14.1% on the previous year." |
| Outliers | "3 orders are unusually large (above $10K)." |
| Seasonality | "Sales are highest every November–December." |

Thresholds can be configured, and each insight links to its tile.

### Insights after the viewer filters

| Insight type | After a filter |
|--------------|----------------|
| Peak / low, biggest contributor, concentration, negative segments, change vs previous period | **Recomputed in the browser** (JS port with parity tests) |
| Trend direction | Recomputed (linear trend is ported to JS) |
| Seasonality, outliers | Kept, but labelled **"based on all data"**, because recomputing them reliably needs more history than a filter may leave |

Every insight shows a small tag: "for current filters" or "based on all data". An insight never silently describes data that is no longer shown.

### Analytics pane
- **Reference lines:** average, median, constant target, percentile band.
- **Trend:** linear least squares, with the method shown in the legend.
- **Forecast:** Holt-Winters (additive), written in numpy, with a JS port so it updates after filtering. Shown dashed with a band and labelled "Estimate". Not offered with less than 2 seasons of history; if a filter leaves too little history, the forecast hides with the note "not enough data for a forecast".
- **Outliers:** IQR or z-score, flagged only.
- **Period comparison:** YoY, MoM, YTD, previous period, fiscal-year aware.
- **Seasonal length for forecasts:** 12 for monthly data, 4 for quarterly, 52 for weekly and 7 for daily, overridable with `season=`.

### Comparisons when the viewer filters dates
- A comparison always uses **the same window shifted back**. Filtering to 2017 compares 2017 with 2016, and filtering to Mar–May 2017 compares it with Mar–May 2016.
- The shared data table (section 9.2) keeps the earlier period, and **date filters do not remove it from comparisons**. It is only used for the comparison numbers.
- If the earlier period has no data, the KPI shows "no data for previous year" instead of a misleading +100%.

### The reference date ("today")
- YTD, "last 12 months" and similar ranges use the **latest date in the data** as "today", never the computer's clock. This keeps the output the same on every run and machine.
- `as_of="2017-12-31"` overrides it. The reference date is shown in the KPI tooltip.

---

## 14. Dashboards

- **Model:** versioned JSON with title, theme, colours, filters, parameters, tiles and actions. `save()` / `load()` round-trip exactly.
- **New data:** `bind(new_df)` checks that every needed column exists, and gives "did you mean" errors for renamed columns.
- **Layout:** 12-column grid, KPIs first, big visuals at width 6, details at width 4, one column on phones. Tiles are drawn lazily.
- **Filters:** multi-select, date range (month grain by default), numeric range and parameters.
- **Actions:**
  - click to filter, Ctrl/Shift + click to add values
  - drag (brush) to filter a range
  - legend click highlights a series, Ctrl + click hides it
  - per tile, `action="filter"` (default) or `action="highlight"`
  - the source tile highlights instead of filtering itself
  - a second click clears
  - chips show active filters, with "Reset all"
- **Drill-down:** dates and detected hierarchies, with breadcrumbs.
- **URL state:** filters are stored in the address (`#f=...`), so a link opens the same view.
- **Tile menu:** switch chart type, CSV, PNG, view as table. The CSV holds that tile's rows with filters applied, either as raw numbers or as formatted text. It is never the original row-level data unless the user embedded it with `embed="raw"`.
- **Printing:** before printing, every tile is drawn (lazy drawing is turned off), so no tile prints blank.
- **Accessibility:**
  - keyboard focus order
  - ARIA labels
  - alt-text from insights
  - pattern fills (ECharts "decal") so colour is not the only cue
  - a table fallback for maps
- **Themes:** light, dark, print (A4 / Letter page layout). The viewer gets a light/dark toggle in the header, which follows the system setting by default (`theme_toggle=False` hides it).
- **Tiles with their own data:** `data=` per tile; filter scope follows section 5.6.
- **Touch:** tap for a tooltip, long-press to filter.

---

## 15. Security, privacy and licences

| Area | Rule |
|------|------|
| XSS | Every data value is escaped before it reaches tooltips, labels, chips, titles or tables. Formatters never insert raw HTML. |
| Embedded JSON | Encoded so that `</script>`, `<!--` and U+2028 cannot break out of the script tag. |
| Calculated fields | Own parser with an allow-list; never `eval` or `exec`. |
| Network | No calls at runtime. The level-2 geo download is the only network feature, and only when the user calls it. |
| Telemetry | None, ever. |
| Data in HTML | Aggregated rows only by default; `exclude_columns=` for sensitive fields. Docs warn that anything embedded can be read by anyone with the file. |
| Licences | tabsight is MIT. ECharts (Apache 2.0) and topojson-client (ISC) are credited in NOTICE. Natural Earth is public domain. geoBoundaries (CC BY 4.0) credits are added to the map automatically. |
| CSV formula injection | In CSV downloads, cells starting with `=`, `+`, `-`, `@`, tab or carriage return are prefixed with `'` so Excel does not run them as formulas. On by default; `csv_safe=False` turns it off. Real negative numbers are exported as numbers and are not affected. |
| Small groups | Grouped data can still reveal one person (for example the salary of a one-person team). `min_group_size=5` hides groups smaller than that, shown as "fewer than 5". Off by default; recommended in the docs for HR, health and survey data. |
| Untrusted dashboard files | A saved spec contains no code: formatters are allow-listed names, formulas go through our parser, raw ECharts options cannot contain functions, and unknown keys are rejected. Loading someone else's spec is therefore safe, and tests use malicious specs to prove it. |
| URL state | Filter values read from the address are treated as data: matched against known values and escaped, never inserted as HTML. |
| Built into every phase | `docs/SECURITY_CHECKLIST.md`. Enforced automatically on every test run: an AST guard (no `eval`/`exec`/`pickle`/`subprocess`, no `.format()` on runtime strings, no network modules, file readers only in `io.py`), ruff bandit rules (`S`), pip-audit and npm audit in CI, Dependabot, hash-locked vendored files, fuzz tests on every parser, and "input unchanged" tests. |
| Trademark | "Tableau" is a trademark of Salesforce. Branding, the PyPI description and the README tagline say "BI-quality" or "dashboard-quality". Tableau is named only in factual comparisons. The `tabsight` name gets a trademark search before 0.1.0. |

Tests use malicious category names (`<img onerror=...>`, `</script>`) to prove the escaping works.

---

## 16. Performance

| Target | Goal |
|--------|------|
| Profile 1M rows × 20 columns | under 3 s |
| `ts.auto()` on 1M rows | under 5 s |
| Dashboard HTML with 12 tiles opens | under 2 s on a normal laptop |
| Filter click → all tiles updated | under 200 ms (Superstore size) |
| Wheel size | under 15 MB, or level-1 geo moves to `tabsight-geo` |

These are measured in `benchmarks/` on every release, not guessed.

---

## 17. Compatibility and engineering

| Area | Plan |
|------|------|
| Python | `requires-python = ">=3.11"`, tested on 3.11, 3.12, 3.13 and 3.14. **3.13 is the main version**: development, local testing and benchmarks run on it first. Why 3.11 as the floor: pandas 3.0 needs Python 3.11 or newer, and Python 3.10 reaches end of life in October 2026. Code avoids syntax newer than 3.11 (for example the 3.12 `type` statement). When 3.11 reaches end of life (October 2027) the floor moves to 3.12, following the deprecation policy. |
| Development environment | A virtual environment on Python 3.13 inside `D:\Experiments` (the machine's default Python is 3.14, which is also tested) |
| pandas | 2.x and 3.x, both tested. pandas 3 changes the default string type and copy behaviour, so the code avoids depending on either. |
| polars | Optional, converted through pyarrow |
| Notebooks | JupyterLab, classic Notebook, VS Code and Colab. The environment is detected: JupyterLab and classic Notebook load the runtime once per notebook. VS Code and Colab isolate each output, so the runtime (about 1 MB) is inlined in each output, or loaded from the CDN if the user sets `cdn=True`. |
| Browsers | Latest Chrome, Edge, Firefox and Safari; phones and tablets |
| OS | Windows, macOS, Linux |
| Code quality | Type hints with `mypy`, `ruff` for linting and formatting, at least 85% test coverage |
| Version control | git from day one, small commits, a CHANGELOG |
| Releases | Semantic versioning, a deprecation policy (warn for one minor release before removing), early 0.0.1 publish to reserve the name on PyPI, and reserve `tabsight` / `tabsight-js` on npm and `tabsight` on GitHub at the same time |
| CI | GitHub Actions on Windows, macOS and Linux × Python 3.11–3.14 × pandas 2/3, plus Node parity tests. Python 3.13 runs the full suite including browser checks; the other versions run the unit and parity tests. pandas 2 is tested only on Python versions it supports. |
| Docs | mkdocs site: tutorial, API reference from docstrings, chart gallery, "how tabsight decides" pages, map coverage table |
| Optional extras | `excel` (openpyxl), `parquet` (pyarrow), `polars` (polars + pyarrow), `png` (playwright, which downloads its own browser on first use, as the docs warn) |
| JS runtime | Ships inside the Python package; npm package `tabsight-js` after 0.1.0 |
| Open source | CONTRIBUTING guide, code of conduct, issue and pull request templates, SECURITY policy (how to report a vulnerability) |

---

## 18. Tests

| Layer | Check |
|-------|-------|
| Unit | read, profile, check, clean (each mode), aggregate, table calcs, calc parser, formats and locales, colours, analytics, insights, recommender, geo matching and detection |
| Never changes data | Every public function is called, and the test checks that the input DataFrame is identical afterwards |
| Correctness | Browser re-aggregation equals pandas for every aggregation type after random filters (property-based tests with `hypothesis`) |
| Click semantics | Every row of the table in 5.6 builds the right filter: "Other", bins, periods, parents, brush, toggle off |
| Reading rules | Units from names, ordered text values, mixed-currency warning, hierarchy false positives, stable tie order, file encodings (UTF-8, BOM, Windows-1252) |
| Comparisons | YoY / MoM / YTD stay correct after date filters (shifted window); `as_of` defaults to the latest data date; missing earlier period shows "no data" |
| Embedding size | The shared data table includes every clickable and drill field; the size estimate matches the real file within 10%; the shrink steps run in order |
| Legend and multi-select | Legend highlights, Ctrl + click hides, Ctrl/Shift + click adds filter values, `action="highlight"` |
| Parameters offline | Grouped-value parameters work offline; row-level ones raise the linter warning |
| Notebooks | Charts render in JupyterLab, classic Notebook, VS Code and Colab |
| Edge cases | Every row of the table in 4.2 |
| Builders | Series count, no smoothing, label interval 0, formatter names valid |
| Parity (Node) | JS formatters, reshapers, re-aggregation, table calcs and insights match Python |
| Round trip | spec, dashboard and clean report save → load; `bind()` with new data |
| Security | XSS and script-breakout cases, parser injection attempts, CSV formula injection, malicious dashboard specs, malicious URL state, `min_group_size` hides small groups |
| Geo | Every bundled region can be matched by name and code; detection picks the right country on test sets for 20+ countries; two-level names (Georgia, Luxembourg, Punjab) resolve correctly from context |
| Visual | Gallery and example dashboards render with no console errors; screenshot comparison with Playwright (optional dependency) |
| Accessibility | Keyboard walk-through, ARIA present, contrast AA |
| Datasets | Superstore plus synthetic finance, HR, world indicators and Ireland retail sets |

---

## 19. Benchmarks

These go in the README to show tabsight is better, with numbers.

| Comparison | Measured against |
|------------|------------------|
| Lines of code to make the same dashboard | Plotly, pyecharts, PyGWalker, Vizro |
| Quality of each tool's default charts, scored against a **published written checklist** (the same rules our linter uses), so anyone can repeat the scoring. Our linter itself is not run on other tools' charts, because that would not be fair or practical. | Same tools |
| Recommender agreement on the labelled set | Expected answers |
| Map coverage (countries and regions matched) | Plotly built-in maps |
| Speed and file size | Section 16 targets |

---

## 20. Build order (each phase is finished and tested before the next)

**Status:** Phase 0 done (27 Oct 2026). Phase 1 done (27 Oct 2026). Phase 2 done (27 Oct 2026). Every phase follows `docs/SECURITY_CHECKLIST.md`, and its automated guards run with every test run.

| Phase | Deliverable | Done when |
|-------|-------------|-----------|
| 0. Setup | Python 3.13 virtual environment, git, pyproject (`requires-python = ">=3.11"`), ruff and mypy set to 3.11 syntax, pytest, CI config, NOTICE, empty package that imports; check ECharts 6.x against our needs and pin the newest stable version | `pip install -e .` and tests run; ECharts version chosen and recorded |
| 1. Foundation | config (contextvars), warnings, io, read, profile (with hierarchies, units from names, ordered text, mixed currencies, edge cases), check, clean, formats + locales + i18n, colours, theme, spec | All unit tests pass on pandas 2 and 3; no function changes input data; same input gives the same output |
| 2. Aggregation and correctness | aggregate with exact re-aggregation parts, unit-based default aggregation, weighted average, table calcs, calc parser (with offline parameter rules) | Property tests prove re-aggregation is exact |
| 3. Core charts | bar family, line family, donut, KPI, table, Figure, **minimal `tabsight.js`** (named formatters and chart drawing) and the Node parity test setup | A single chart opens offline with formatted numbers, passes lint, escapes malicious values, and JS formatters match Python |
| 4. Recommender, linter, explain | rules, scores, reasons, lint rules, explain, labelled test set | Agreement rate published |
| 5. World geo | level 0, level 1 for all countries, cities, matching (all name languages), display language, detection, projections, insets, tiny-country dots, opt-in level 2 download, top-30 country checks, coverage table | 20+ countries detected correctly; unmatched names reported; coverage table written |
| 6. Advanced charts | heatmap, calendar heatmap, treemap, sunburst, Sankey, scatter/bubble, histogram, box, waterfall, funnel, gauge, combo, Pareto, bullet, density and flow maps, small multiples | Gallery shows all 33 types and facets |
| 7. Analytics and insights | reference lines, trend, forecast (with season lengths), outliers, comparisons (shifted window, `as_of`), fiscal years, insight rules | Insights and comparisons correct on all test datasets |
| 8. Dashboard and runtime | model, layout, the rest of the JS runtime on top of the Phase 3 minimal one, shared data table (9.2), comparisons under date filters, click and legend semantics (5.6), filters, brush, cross-filter, drill, chips, reset, URL state, tile menu, per-tile data, insight and forecast updates, theme toggle, lazy draw, accessibility, touch, bind, `to_dict(pure=True)` | Example dashboards cross-filter correctly in the browser, by mouse, keyboard and touch |
| 9. Auto, CLI and integrations | `ts.auto`, CLI, FastAPI/Flask/Streamlit/Dash helpers, Jupyter loading | One line or one command makes a full dashboard for every test dataset |
| 10. Release | docs site, gallery, benchmarks, open-source files (CONTRIBUTING, code of conduct, SECURITY, templates), trademark name check, wheel, 0.1.0 on PyPI | Install from PyPI works in a clean environment |
| Later | Tier 2 items, each as its own phase | — |

---

## 21. Risks

| Risk | Plan |
|------|------|
| Python and JS drift apart | Only reshaping, re-aggregation, table calcs, formatters and simple insights are in JS, all covered by parity tests |
| Wrong numbers after filtering | Exact re-aggregation rules and property-based tests; non-exact tiles say so instead of being silently wrong |
| Large files | Month-grain date filters, size estimate, lazy drawing, server mode |
| Package size from world maps | TopoJSON, simplifying, per-country files, companion `tabsight-geo` if needed |
| Wrong map chosen | Detection reports its choice; `map=` overrides it |
| Disputed borders | Natural Earth default view, documented; custom GeoJSON supported |
| Insights read as advice or causes | Fixed fact-only templates |
| Forecasts taken as certain | Off by default, dashed, banded, labelled "Estimate" |
| Security | Escaping everywhere, safe JSON encoding, own parser, security tests |
| pandas or ECharts changes | Both pandas versions tested; one pinned, inlined ECharts 6.x version |
| Embedded data much bigger than expected | One shared data table per dataset (9.2), size estimated on it, automatic steps to shrink it |
| Comparisons wrong after date filters | Shifted-window rule; earlier period kept for comparisons (section 13) |
| Clicks filter the wrong thing | Filters built from what a mark stands for (section 5.6), with a test for each case |
| Insights describe hidden data | Every insight tagged "for current filters" or "based on all data" |
| Weak region data for some countries | Per-country checks for the top 30, coverage table, geoBoundaries fallback |
| Trademark complaint | No "Tableau" in branding; name search before 0.1.0 |
| Scope | Strict phase order; Tier 2 waits until 0.1.0 is released; section 22 lists what is out |

---

## 22. Out of scope (decided on purpose)

| Item | Why it is out | Possible later? |
|------|---------------|-----------------|
| Street or satellite background maps (OpenStreetMap tiles) | Needs a network connection, which breaks "offline by default" | Yes, as an opt-in |
| Currency conversion | Needs live exchange rates; mixed currencies are warned about instead (section 4.1) | No |
| Live auto-refresh dashboards | Needs a running server | Yes, server mode could poll |
| Drag-and-drop dashboard builder | PyGWalker already does this well; it would double the project | No |
| Joins across tables | Tiles can use separate data (section 5.6), but no joining yet | Yes, Tier 2 (`ts.join`) |
| Logins, sharing, permissions | That is a BI server, not a library | No |
| LLM features | Kept out on purpose: determinism and explainability are the selling points | No |

---

## 23. Needed before building

1. **Downloads into `D:\Experiments`.** All are data or library files, and none are executables.
   - Natural Earth admin-0 countries, admin-1 states/provinces and populated places (public domain)
   - ECharts, newest stable 6.x (Apache 2.0, about 1 MB). 6.0 was released in July 2025 and adds dynamic theme switching, which the light/dark toggle uses. Fall back to 5.6 only if a needed feature breaks.
   - topojson-client (ISC licence, about 10 KB, credited in NOTICE)
2. **Build-time tools**, used only to prepare the data and not shipped: `mapshaper` (via npm) to simplify shapes and convert them to TopoJSON.
3. **Python 3.13** for the development virtual environment (installed with conda or the python.org installer if it is not already on the machine).
4. **Name:** `tabsight`, confirmed and checked free on PyPI, npm and GitHub (27 Oct 2026).
