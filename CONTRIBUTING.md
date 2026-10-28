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

## Branches and commits

- Never push to `main` directly: it is protected. Work on a branch named after the change,
  for example `fix/kpi-compare-label` or `feat/server-mode`, and open a pull request.
- Write commit messages in the [Conventional Commits](https://www.conventionalcommits.org/)
  style: `type(scope): summary`, in the imperative and under 72 characters. For example:
  `fix(dashboard): keep drill crumbs after a theme switch`.
  Types: `feat`, `fix`, `docs`, `test`, `refactor`, `perf`, `build`, `ci`, `chore`, `security`.
- Explain *why* in the commit body when it isn't obvious. Mark breaking changes with `!`
  (`feat(spec)!: ...`) and a `BREAKING CHANGE:` line.
- Keep each pull request to one change. Pull requests are squash-merged, so the title
  must follow the same commit style.
- CI must be green: tests on Python 3.11–3.14, lint, types and the dependency audit.
- Never commit data files, secrets, `.env` files, built sites (`site/`) or notebooks with outputs.

## Reporting security problems

Don't open a public issue. Follow [SECURITY.md](https://github.com/yesh069/tabsight/blob/main/SECURITY.md) and use GitHub's private
vulnerability reporting.

## Third-party files

Never edit files in `src/tabsight/render/static/` that come from upstream. Change the pinned version in `tools/fetch_vendor.py`, run `python tools/fetch_vendor.py --update`, and update `NOTICE`.

## Releasing (maintainer)

1. In a pull request, set the version in `src/tabsight/_version.py` (for example `0.1.0`) and rename the changelog's "Unreleased" heading to that version and date.
2. Once it is merged and CI is green, tag `main` and push the tag: `git tag v0.1.0 && git push origin v0.1.0`.
3. The **Release** workflow checks that the tag matches the version, builds the sdist and wheel, checks them, and publishes to PyPI with trusted publishing (no token stored anywhere). The first time, add the repository as a trusted publisher on pypi.org: project `tabsight`, workflow `release.yml`, environment `pypi`.

Release tags can't be moved or deleted (a ruleset protects `v*`), so a published version always matches its tag.
