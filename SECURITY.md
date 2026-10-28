# Security policy

## Reporting a vulnerability

Please do not open a public issue for security problems. Use GitHub's private vulnerability reporting on the tabsight repository ("Security" tab → "Report a vulnerability"). You should get a reply within 7 days.

## What counts

tabsight writes HTML files that other people open, so these matter most:

- Data values that run as script in the HTML output (XSS, script-tag breakout)
- Formula fields or saved dashboard files that execute code
- CSV downloads that run as formulas in spreadsheet software
- Any network request the user did not ask for
- Server mode (`dash.server`, `ts.web`, `tabsight serve`): requests that read data they shouldn't, or reach a local `tabsight serve` from another website
- Files that `ts.load` should refuse: anything that makes it contact another computer, or exhausts memory (decompression bombs)

## Supported versions

Until version 1.0, only the latest release receives security fixes. Fixes ship as a new release on PyPI and are listed in the changelog.
