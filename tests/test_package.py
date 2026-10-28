import json
import re
import subprocess
import sys
from pathlib import Path

import tabsight
from tabsight.cli import main
from tabsight.render.assets import ECHARTS_VERSION, TOPOJSON_CLIENT_VERSION, read_static

ROOT = Path(__file__).resolve().parent.parent
LOCK = json.loads((ROOT / "tools" / "vendor.lock.json").read_text(encoding="utf-8"))


def test_version_is_exposed() -> None:
    # A PEP 440 release number: 0.1.0, 0.1.0a1, 0.1.0rc2, 0.2.0.dev0 ...
    assert re.fullmatch(r"\d+\.\d+\.\d+((a|b|rc)\d+)?(\.dev\d+)?", tabsight.__version__)


def test_python_floor_is_311() -> None:
    assert sys.version_info >= (3, 11)


def test_bundled_echarts_matches_pinned_version() -> None:
    js = read_static("echarts.min.js")
    assert ECHARTS_VERSION == "6.1.0"
    assert f'"{ECHARTS_VERSION}"' in js or f"'{ECHARTS_VERSION}'" in js


def test_bundled_topojson_client_is_present() -> None:
    js = read_static("topojson-client.min.js")
    assert TOPOJSON_CLIENT_VERSION in js
    assert "feature" in js


def test_lock_covers_shipped_static_files_with_pinned_urls() -> None:
    echarts = LOCK["src/tabsight/render/static/echarts.min.js"]
    topo = LOCK["src/tabsight/render/static/topojson-client.min.js"]
    assert f"echarts@{ECHARTS_VERSION}/" in echarts["url"]
    assert f"topojson-client@{TOPOJSON_CLIENT_VERSION}/" in topo["url"]
    for entry in LOCK.values():
        assert len(entry["sha256"]) == 64


def test_cli_version_flag() -> None:
    out = subprocess.run(
        [sys.executable, "-m", "tabsight", "--version"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert out.stdout.strip() == f"tabsight {tabsight.__version__}"


def test_cli_without_arguments_prints_help() -> None:
    assert main([]) == 0
