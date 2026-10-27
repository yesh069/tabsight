# Security checklist (applied in every phase)

Security is built in as each piece is written, not reviewed afterwards. Most items are **enforced automatically**; the rest are ticked in the phase summary before committing.

## Enforced automatically (CI fails if broken)

| Guard | Where |
|-------|-------|
| No `eval`, `exec`, `compile`, `__import__`, `pickle`, `marshal`, `shelve`, `subprocess`, `os.system`, `os.popen`, `input` in `src/` | `tests/test_security_guards.py` (AST scan) |
| No `.format()` / `.format_map()` called on non-literal strings in `src/` (format-string attacks like `"{0.__class__}"`) | `tests/test_security_guards.py` |
| No network modules (`urllib`, `http`, `socket`, `requests`, `ftplib`, `smtplib`, …) in `src/`, except the future opt-in `geo/download.py` and `localserver.py` (`tabsight serve`, 127.0.0.1 by default) | `tests/test_security_guards.py` |
| pandas file readers called only in `tabsight/io.py`, which rejects URLs | `tests/test_security_guards.py` + `tests/test_io.py` |
| Bandit-style lint rules (ruff `S`) | `pyproject.toml`, CI lint job |
| Known-vulnerable dependencies | `pip-audit` CI job; Dependabot for pip, npm and GitHub Actions |
| Vendored files unchanged | SHA-256 lock checked by `tools/fetch_vendor.py`; byte-exact via `.gitattributes` |
| Public functions never change the input DataFrame | "unchanged input" tests per module (`tests/test_never_mutates.py`) |
| Formula language cannot run code or exhaust resources | `tests/test_formulas.py`: injection attempts, length/token/depth limits, fuzzing, overflow handling |

## Rules for every new piece of code

1. **Validate every user-supplied string at the boundary**: colours (hex only), fonts (safe characters only), format patterns (own parser), locale and currency codes (fixed patterns), column names (must exist; "did you mean"), saved specs and schemas (strict schema, unknown keys rejected, size limits).
2. **Never build code or markup from data.** No string formatting of user text into HTML, JS, CSS or regexes. HTML escaping happens at render time (Phase 3 onwards) and is tested with malicious values.
3. **Untrusted text in messages is truncated and `repr()`-quoted** (`tabsight.warnings.safe_repr`), so huge or control-character values cannot flood or spoof warnings.
4. **No network, no clock, no randomness** in library code. "Today" comes from the data or `as_of=`.
5. **Bounded work on user data**: sampling, caps on distinct values (hierarchies, near-duplicates), anchored linear regexes only (no nested quantifiers).
6. **Safe file reading**: local paths only; XML formats need `defusedxml`; Parquet needs a patched `pyarrow` (>= 15, after CVE-2023-47248).
7. **Every new input gets a malicious-input test in the same change.**

## Phase sign-off

Each phase summary states: new inputs added, how each is validated, and which security tests cover them.
