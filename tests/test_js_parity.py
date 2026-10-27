"""tabsight.js must format numbers exactly like Python (one recipe, two languages)."""

from __future__ import annotations

import itertools
import json
import math
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from tabsight.formats import LOCALES, format_number, js_spec, locale_payload

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = ROOT / "src" / "tabsight" / "render" / "static" / "tabsight.js"
SCRIPT = ROOT / "tests" / "js" / "parity.cjs"

EDGE_VALUES = [
    0.0, -0.0, 0.5, 1.5, 2.5, -2.5, 0.125, 0.0001, 1e-7, 9.995, 99.95, 999.5, 999.95,
    999_950.0, 999_999.0, 1_000_000.0, 1234.5, -1234.5, 12345.678, 123456.789,
    2_297_200.8574, 99_999.0, 99_960.0, 9_999_999.0, 12_345_678.9, 1e12, 1e15, 3.2e17,
    0.156, 0.155, 0.1549999, 0.032, -0.082, 1.797693134862316e306,
    math.nan, math.inf, -math.inf,
]  # fmt: skip
CURRENCIES = {
    "en_US": "USD",
    "en_IE": "EUR",
    "en_IN": "INR",
    "de_DE": "EUR",
    "fr_FR": "EUR",
    "pt_BR": "BRL",
}


def _cases() -> list[dict[str, object]]:
    rng = np.random.default_rng(42)
    randoms = list(rng.normal(0, 1, 120) * 10.0 ** rng.integers(-3, 10, 120))
    values = EDGE_VALUES + [float(v) for v in randoms]
    variants: list[dict[str, object]] = []
    for unit, style in itertools.product(
        ["currency", "percent", "pp", "count", "number", "duration"], ["compact", "full"]
    ):
        variants.append({"unit": unit, "style": style})
    variants += [
        {"unit": "currency", "style": "full", "decimals": 2},
        {"unit": "currency", "style": "full", "negative": "parens"},
        {"unit": "percent", "style": "full", "sign": True, "decimals": 2},
        {"unit": "percent", "style": "full", "percent_scale": "whole"},
        {"unit": "number", "style": "full", "decimals": 3},
        {"unit": "duration", "style": "full", "duration_unit": "hours"},
        {"unit": "duration", "style": "full", "duration_unit": "days"},
        {"unit": "number", "style": "full", "pattern": "#,##0.0"},
        {"unit": "number", "style": "full", "pattern": "0.0%"},
        {"unit": "number", "style": "full", "pattern": '"€"#,##0.00'},
        {"unit": "number", "style": "full", "pattern": '0" kg"'},
        {"unit": "currency", "style": "full", "currency": "JPY"},
        {"unit": "currency", "style": "full", "currency": "XYZ"},
    ]
    cases = []
    for locale in sorted(LOCALES):
        for variant in variants:
            kwargs = dict(variant)
            kwargs.setdefault("currency", CURRENCIES.get(locale, "EUR"))
            unit, style = kwargs.pop("unit"), kwargs.pop("style")
            spec = js_spec(unit, style, locale=locale, **kwargs)  # type: ignore[arg-type]
            for value in values:
                expected = format_number(value, unit, style, locale=locale, **kwargs)  # type: ignore[arg-type]
                cases.append(
                    {
                        "value": None if not math.isfinite(value) else value,
                        "spec": spec,
                        "expected": expected,
                    }
                )
    return cases


@pytest.mark.node
@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js not installed")
def test_javascript_formatting_matches_python(tmp_path: Path) -> None:
    cases = _cases()
    payload = {"locales": locale_payload(LOCALES), "cases": cases}
    data = tmp_path / "cases.json"
    data.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    result = subprocess.run(
        ["node", str(SCRIPT), str(RUNTIME), str(data)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=300,
    )
    assert result.returncode == 0, result.stdout[-4000:] + result.stderr[-2000:]
    assert f"{len(cases)}/{len(cases)} match" in result.stdout
    assert len(cases) > 30_000
