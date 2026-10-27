"""Runs the Node-based ECharts feature check (see docs/decisions/0001-echarts-version.md)."""

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
WORLD = ROOT / "data-raw" / "naturalearth" / "ne_110m_admin_0_countries.geojson"


@pytest.mark.node
@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js not installed")
@pytest.mark.skipif(not WORLD.exists(), reason="raw map data missing: run tools/fetch_vendor.py")
def test_bundled_echarts_supports_planned_features() -> None:
    result = subprocess.run(
        ["node", str(ROOT / "tests" / "js" / "echarts_features.cjs"), str(ROOT)],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "19/19 passed" in result.stdout
