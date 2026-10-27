# Security policy

## Reporting a vulnerability

Please do not open a public issue for security problems. Use GitHub's private vulnerability reporting on the tabsight repository ("Security" tab → "Report a vulnerability"). You should get a reply within 7 days.

## What counts

tabsight writes HTML files that other people open, so these matter most:

- Data values that run as script in the HTML output (XSS, script-tag breakout)
- Formula fields or saved dashboard files that execute code
- CSV downloads that run as formulas in spreadsheet software
- Any network request the user did not ask for

## Supported versions

Only the latest release receives security fixes until version 1.0.
