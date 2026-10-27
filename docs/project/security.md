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
