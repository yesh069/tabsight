# Changelog

All notable changes are listed here. The project follows [Semantic Versioning](https://semver.org/).

## Unreleased

### Added
- Phase 0 project setup: package skeleton (`src/` layout), `pyproject.toml` (Python 3.11–3.14), ruff, mypy, pytest, CI workflow, licences and NOTICE.
- Pinned third-party files with a hash lock: ECharts 6.1.0, topojson-client 3.1.0, Natural Earth 5.1.2 raw data (`tools/fetch_vendor.py`).
- ECharts feature check in Node (`tests/js/echarts_features.cjs`), see `docs/decisions/0001-echarts-version.md`.
