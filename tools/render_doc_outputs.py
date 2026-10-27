"""Run the Python examples in docs/ and write their real printed output into the pages.

A Python block followed by a text block titled "Output" gets that block replaced with
what the code actually prints. Pages run top to bottom in one namespace, from the
repository root, like a notebook.

Usage:
    python tools/render_doc_outputs.py           # update the pages
    python tools/render_doc_outputs.py --check   # fail if any page is out of date (CI)
"""

from __future__ import annotations

import argparse
import contextlib
import io
import os
import re
import sys
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"

BLOCK = re.compile(
    r"(?P<code>^```python\n(?P<src>.*?)^```\n)"
    r"(?P<gap>\n*)"
    r'(?P<out>^```text title="Output"\n(?P<old>.*?)^```\n)?',
    re.M | re.S,
)


def _setup() -> None:
    import pandas as pd

    pd.set_option("display.width", 88)
    pd.set_option("display.max_columns", 12)
    pd.set_option("display.max_rows", 14)
    pd.set_option("display.max_colwidth", 40)
    pd.set_option("display.precision", 2)


def render(text: str, name: str) -> str:
    """Return ``text`` with every Output block refreshed. Raises if an example fails."""
    namespace: dict[str, object] = {"__name__": "__docs__"}
    pieces: list[str] = []
    pos = 0
    for i, m in enumerate(BLOCK.finditer(text), 1):
        pieces.append(text[pos : m.start()])
        src = m.group("src")
        buffer = io.StringIO()
        if not src.lstrip().startswith("# not run"):
            try:
                with warnings.catch_warnings(), contextlib.redirect_stdout(buffer):
                    warnings.simplefilter("ignore")
                    exec(compile(src, f"{name} example {i}", "exec"), namespace)  # noqa: S102 - our own docs
            except Exception as err:
                raise RuntimeError(
                    f"{name} example {i} failed: {type(err).__name__}: {err}\n{src}"
                ) from err
        pieces.append(m.group("code"))
        if m.group("out") is not None:
            output = "\n".join(
                line.rstrip() for line in buffer.getvalue().rstrip("\n").splitlines()
            )
            pieces.append(
                m.group("gap") + '```text title="Output"\n' + (output + "\n" if output else "")
            )
            pieces.append("```\n")
        else:
            pieces.append(m.group("gap"))
        pos = m.end()
    pieces.append(text[pos:])
    return "".join(pieces)


def pages() -> list[Path]:
    """Documentation pages plus the README, which shows real output too."""
    return [*sorted(DOCS.rglob("*.md")), ROOT / "README.md"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="only report pages whose output is stale"
    )
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT / "src"))
    _setup()
    old_cwd = Path.cwd()
    os.chdir(ROOT)
    stale = []
    try:
        for page in pages():
            text = page.read_text(encoding="utf-8")
            if "```python" not in text:
                continue
            name = page.relative_to(ROOT).as_posix()
            new = render(text, name)
            if new != text:
                stale.append(name)
                if not args.check:
                    page.write_text(new, encoding="utf-8", newline="\n")
            import tabsight.settings

            tabsight.settings.reset_defaults()
    finally:
        os.chdir(old_cwd)
    if stale:
        print(("stale: " if args.check else "updated: ") + ", ".join(stale))
    return 1 if (stale and args.check) else 0


if __name__ == "__main__":
    sys.exit(main())
