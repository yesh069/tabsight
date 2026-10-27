# Contributing to tabsight

Thanks for helping. A few ground rules keep the package predictable.

## Principles every change must keep

1. Never change the user's DataFrame. Work on copies.
2. Every guess has a default and an override.
3. Warn, don't block (unless the user asks for strict mode).
4. Same input gives the same output. No randomness, no clock, no network.
5. Every data value that reaches HTML is escaped.

## Setup

See the "Development setup" section in `README.md`.

## Before opening a pull request

- `python -m pytest` passes (Node tests run when Node.js is installed)
- `python -m ruff check .` and `python -m ruff format --check .` pass
- `python -m mypy` passes
- New behaviour has tests, including the "input DataFrame unchanged" check for public functions
- Code uses Python 3.11 syntax only (no 3.12+ features)
- `CHANGELOG.md` has an entry under "Unreleased"

## Third-party files

Never edit files in `src/tabsight/render/static/` that come from upstream. Change the pinned version in `tools/fetch_vendor.py`, run `python tools/fetch_vendor.py --update`, and update `NOTICE`.
