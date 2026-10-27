# Changelog

All notable changes are listed here. The project follows [Semantic Versioning](https://semver.org/).

## Unreleased

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
