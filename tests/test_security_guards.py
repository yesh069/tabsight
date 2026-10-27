"""Static guards: forbid dangerous calls and network access anywhere in the library source.

These run on every test run, so a risky pattern can never be merged unnoticed.
See docs/SECURITY_CHECKLIST.md.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent / "src" / "tabsight"
PY_FILES = sorted(p for p in SRC.rglob("*.py"))

BANNED_CALLS = {"eval", "exec", "compile", "__import__", "input", "breakpoint"}
BANNED_MODULES = {"pickle", "marshal", "shelve", "subprocess", "dill", "cloudpickle"}
BANNED_ATTR_CALLS = {
    ("os", "system"),
    ("os", "popen"),
    ("os", "execv"),
    ("os", "execl"),
    ("yaml", "load"),
}
NETWORK_MODULES = {
    "urllib",
    "http",
    "socket",
    "requests",
    "httpx",
    "aiohttp",
    "ftplib",
    "smtplib",
    "telnetlib",
    "xmlrpc",
    "webbrowser",
}
# The only module allowed to touch the network (opt-in level-2 map download).
# geo/download.py: the future opt-in map download. localserver.py: `tabsight serve`, which
# listens on 127.0.0.1 only when the user runs that command.
NETWORK_ALLOWED = {SRC / "geo" / "download.py", SRC / "localserver.py"}
# pandas readers that open files or URLs: only tabsight/io.py may call them.
PANDAS_READERS = {
    "read_csv",
    "read_table",
    "read_excel",
    "read_parquet",
    "read_json",
    "read_html",
    "read_xml",
    "read_pickle",
    "read_feather",
    "read_orc",
    "read_sas",
    "read_spss",
    "read_stata",
    "read_hdf",
    "read_sql",
    "read_fwf",
    "read_clipboard",
}
NEVER_ALLOWED_READERS = {"read_pickle", "read_html", "read_xml", "read_clipboard", "read_hdf"}
IO_MODULE = SRC / "io.py"


def _tree(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _imported_roots(tree: ast.AST) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    return roots


@pytest.mark.parametrize("path", PY_FILES, ids=lambda p: str(p.relative_to(SRC)))
def test_no_dangerous_builtins_or_modules(path: Path) -> None:
    tree = _tree(path)
    problems: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in BANNED_CALLS:
                problems.append(f"line {node.lineno}: call to {func.id}()")
            if (
                isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Name)
                and (func.value.id, func.attr) in BANNED_ATTR_CALLS
            ):
                problems.append(f"line {node.lineno}: call to {func.value.id}.{func.attr}()")
    for name in _imported_roots(tree) & BANNED_MODULES:
        problems.append(f"imports banned module {name}")
    assert not problems, f"{path.name}: " + "; ".join(problems)


@pytest.mark.parametrize("path", PY_FILES, ids=lambda p: str(p.relative_to(SRC)))
def test_no_format_on_non_literal_strings(path: Path) -> None:
    """str.format / format_map on runtime strings allow '{0.__class__}' style attacks."""
    problems = []
    for node in ast.walk(_tree(path)):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in {"format", "format_map"}
        ):
            target = node.func.value
            if not (isinstance(target, ast.Constant) and isinstance(target.value, str)):
                problems.append(f"line {node.lineno}")
    assert not problems, f"{path.name}: .format() on a non-literal string at " + ", ".join(problems)


@pytest.mark.parametrize("path", PY_FILES, ids=lambda p: str(p.relative_to(SRC)))
def test_no_network_modules(path: Path) -> None:
    if path in NETWORK_ALLOWED:
        return
    found = _imported_roots(_tree(path)) & NETWORK_MODULES
    assert not found, f"{path.name} imports network modules {sorted(found)}"


@pytest.mark.parametrize("path", PY_FILES, ids=lambda p: str(p.relative_to(SRC)))
def test_pandas_readers_only_in_io_module(path: Path) -> None:
    calls = {
        node.func.attr
        for node in ast.walk(_tree(path))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in PANDAS_READERS
    }
    assert not (calls & NEVER_ALLOWED_READERS), f"{path.name} uses {calls & NEVER_ALLOWED_READERS}"
    if path != IO_MODULE:
        assert not calls, f"{path.name} reads files directly ({sorted(calls)}); use tabsight.io"


def test_guard_catches_known_bad_code(tmp_path: Path) -> None:
    """The guard itself must work: feed it code that should fail."""
    bad = tmp_path / "bad.py"
    bad.write_text(
        "import pickle\nimport urllib.request\nx = eval('1')\nfmt = 'a'\nfmt.format(1)\n",
        encoding="utf-8",
    )
    tree = _tree(bad)
    assert "pickle" in _imported_roots(tree)
    assert "urllib" in _imported_roots(tree)
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)]
    assert any(isinstance(c.func, ast.Name) and c.func.id == "eval" for c in calls)
    assert any(isinstance(c.func, ast.Attribute) and c.func.attr == "format" for c in calls)
