# Security

tabsight produces HTML files that other people open, reads files from many sources, and accepts formulas and saved settings that may come from someone else. Security is built in from the first line of code, and most of it is **enforced by automated tests**, not by review.

## What tabsight guarantees

| Area | Guarantee |
|------|-----------|
| Network | The library never makes a network request. URLs passed as data are refused. |
| Code execution | No `eval`, `exec`, `pickle` or `subprocess` anywhere in the library. Formulas use tabsight's own parser. |
| Your data | Never modified; every function works on a copy. |
| Saved files | Specs, schemas, cleaning decisions and colour registries are validated against allow-lists; unknown keys are rejected; sizes are limited. |
| HTML output (from Phase 3) | Every data value is escaped; embedded JSON cannot break out of its script tag; CSV downloads are protected from spreadsheet formula injection. |
| Chart advice (from Phase 4) | Recommendations, `explain()` and lint reports are plain text and are never written into the HTML page. Column names in them are checked against the data first, and unknown names or lint codes are refused with shortened, quoted messages. |
| Maps (from Phase 5) | Map shapes and names come only from data bundled with tabsight; country file names are checked before any file is opened. Place names from your data are matched against that list and shown as escaped text. The one extra script on a map page (topojson-client, which turns the shapes into drawable form) is pinned by hash like the others. Nothing is downloaded. |
| New chart kinds (from Phase 6) | Every chart kind is tested with hostile names and titles. Where a chart needs drawing code (waterfall bars, projections), the data names a built-in function such as `{"$render": "range"}` and the page looks it up; no code ever travels in the data. `df.plot` and `df.ts` go through the same validated `ts.chart`. |
| Analytics and insights (from Phase 7) | Forecasts, trends and insights are plain numpy with no randomness and no clock: "today" comes from the data or `as_of=`. Insight sentences are filled from fixed templates by a placeholder regex (never `str.format`) and escaped wherever they are shown. Every series is capped before fitting. |
| Still pictures (from Phase 7) | `to_svg()` runs only tabsight's own bundled scripts inside dukpy; the figure goes in as a JSON string read with `JSON.parse`, never pasted into code. The SVG is refused if it contains scripts, event handlers, foreign objects or links. In notebooks it is a base64 image, and browsers never run scripts in an image. |
| Dashboards (from Phase 8) | The page holds pre-aggregated parts, never raw rows. Filters read from the address bar are kept only when their column and values exist in the dashboard's table. The runtime builds every label with `textContent`; CSV downloads guard against spreadsheet formulas. Dashboard files are checked key by key and hold only plain JSON. |
| Styling | Colours must be hex codes; fonts may only contain safe characters, so CSS cannot be injected. |
| File formats | Excel only with `defusedxml` (blocks XML bombs); Parquet only with pyarrow 15+ (after CVE-2023-47248); no pickle. |
| Privacy | `min_group_size` hides small groups; no telemetry; no clock. |

## How it is enforced

- **Code scanner** (`tests/test_security_guards.py`) fails the build if library code calls `eval`/`exec`/`compile`, imports `pickle`/`subprocess`/network modules, calls `.format()` on runtime strings, or reads files outside `io.py`. It is itself tested against known-bad code.
- **Bandit security lint rules** run on every change.
- **pip-audit and npm audit** check dependencies for known vulnerabilities in CI; Dependabot keeps them up to date.
- **Fuzz tests** throw random input at the number formatter, the format-pattern parser, the formula parser and the spec loader.
- **Malicious-input tests** for every input: CSS and script injection, `{0.__class__}` format attacks, `__import__` in formulas, oversized and deeply nested input.
- **Pinned, hash-checked third-party files**: ECharts and topojson-client are verified against SHA-256 hashes.

The full list is the [security checklist](../SECURITY_CHECKLIST.md), which every phase follows.

## Reporting a vulnerability

Please do not open a public issue. Use GitHub's private vulnerability reporting on the repository ("Security" tab → "Report a vulnerability").
