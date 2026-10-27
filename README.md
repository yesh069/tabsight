# tabsight

**BI-quality charts, world maps and dashboards from a pandas DataFrame. Rule-based. No LLM. One offline HTML file.**

> Status: early development (Phase 0 of 10). Nothing usable yet. The full roadmap is in `PLAN.md`.

## What it will do

```python
import pandas as pd
import tabsight as ts

df = pd.read_csv("superstore.csv")
ts.auto(df).to_html("sales_dashboard.html")  # a full, offline, cross-filtering dashboard
```

- Picks the right charts with reasons ("Show Me" rules, no LLM)
- Formats numbers properly (`$2.3M`, `15.6%`, `€1.234,5`)
- World maps: countries, states/provinces/counties for every country, and cities
- Click any chart to filter the others, with correct numbers after filtering
- Never changes your data; cleaning is optional and reported

## Development setup

Python 3.11–3.14 is supported; 3.13 is the main development version.

```bash
python -m pip install -e ".[dev]"
python tools/fetch_vendor.py        # pinned third-party files and raw map data, hash-checked
cd tools && npm install --ignore-scripts && cd ..
python -m pytest
python -m ruff check .
python -m mypy
```

## Licence

MIT. Bundled third-party software and data are listed in `NOTICE`.
