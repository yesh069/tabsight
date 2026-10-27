import contextlib
import json

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from tabsight.colors import (
    PALETTES,
    ColorRegistry,
    contrast_ratio,
    natural_key,
    text_color_on,
    validate_color,
)
from tabsight.spec import CHART_KINDS, ChartSpec
from tabsight.theme import THEMES, contrast_problems, custom_theme
from tabsight.warnings import InvalidSpecError

# ---------------------------------------------------------------- colours


@pytest.mark.parametrize(
    "bad",
    [
        "red",
        "#12345",
        "#ggg",
        "#fff;}</style><script>",
        "url(javascript:alert(1))",
        "rgb(1,2,3)",
        123,
        None,
    ],
)
def test_colour_injection_is_rejected(bad: object) -> None:
    with pytest.raises(InvalidSpecError):
        validate_color(bad)


def test_registry_is_stable_regardless_of_row_order() -> None:
    a, b = ColorRegistry(), ColorRegistry()
    a.assign(["West", "East", "Central"])
    b.assign(["Central", "West", "East"])
    assert a.mapping() == b.mapping()
    assert a.color("Central") == PALETTES["classic10"][0]


def test_registry_pins_and_round_trips() -> None:
    reg = ColorRegistry(pinned={"West": "#E15759"})
    reg.assign(["East", "West"])
    assert reg.color("West") == "#e15759"
    again = ColorRegistry.from_dict(json.loads(json.dumps(reg.to_dict())))
    assert again.mapping() == reg.mapping()
    with pytest.raises(InvalidSpecError):
        ColorRegistry(pinned={"West": "javascript:x"})
    with pytest.raises(InvalidSpecError):
        ColorRegistry.from_dict({"colors": {}, "evil": 1})


def test_natural_sort() -> None:
    assert sorted(["Item 10", "Item 2", "item 1"], key=natural_key) == [
        "item 1",
        "Item 2",
        "Item 10",
    ]


def test_contrast() -> None:
    assert round(contrast_ratio("#000000", "#ffffff"), 1) == 21.0
    assert text_color_on("#4e79a7") == "#ffffff"
    assert text_color_on("#edc948") == "#1f2329"


# ---------------------------------------------------------------- themes


@pytest.mark.parametrize("name", sorted(THEMES))
def test_builtin_themes_pass_wcag_aa(name: str) -> None:
    assert contrast_problems(THEMES[name]) == []


def test_custom_theme_validation() -> None:
    brand = custom_theme(accent="#0b5394", font='"Inter", Arial, sans-serif')
    assert brand.accent == "#0b5394"
    with pytest.raises(InvalidSpecError, match="contrast"):
        custom_theme(text="#cccccc")
    for font in ("Arial; } body { display:none", "</style><script>", 'Arial"'):
        with pytest.raises(InvalidSpecError):
            custom_theme(font=font)
    with pytest.raises(InvalidSpecError):
        custom_theme(page="#fff;background:url(x)")


# ---------------------------------------------------------------- specs


def test_there_are_33_chart_kinds() -> None:
    assert len(CHART_KINDS) == 33 and len(set(CHART_KINDS)) == 33


def test_spec_round_trip_and_aliases() -> None:
    spec = ChartSpec(
        "map", geo="State", y="Sales", top=10, sort="desc", calc="moving_avg:3",
        title="Sales by State", options={"trend": True, "as_of": "2017-12-31"},
    )  # fmt: skip
    assert spec.kind == "choropleth"
    again = ChartSpec.from_json(spec.to_json())
    assert again == spec
    multi = ChartSpec("combo", x="Month", y=["Sales", "Profit"])
    assert ChartSpec.from_dict(multi.to_dict()).y == ("Sales", "Profit")


@pytest.mark.parametrize(
    "bad",
    [
        {"kind": "rm -rf"},
        {"kind": "bar", "x": ""},
        {"kind": "bar", "x": "a" * 500},
        {"kind": "bar", "x": "a\x00b"},
        {"kind": "bar", "agg": "evil"},
        {"kind": "bar", "top": 0},
        {"kind": "bar", "top": True},
        {"kind": "bar", "calc": "moving_avg:9999"},
        {"kind": "bar", "format": "{0.__class__}"},
        {"kind": "bar", "options": {"onclick": "alert(1)"}},
        {"kind": "bar", "options": {"y_min": float("nan")}},
        {"kind": "bar", "title": "x" * 1000},
        {"kind": "bar", "__class__": "x"},
        {"tabsight_spec": 99, "kind": "bar"},
        {"x": "Region"},
        ["kind", "bar"],
    ],
)
def test_malicious_specs_are_rejected(bad: object) -> None:
    with pytest.raises(InvalidSpecError):
        ChartSpec.from_dict(bad)


def test_spec_json_limits() -> None:
    with pytest.raises(InvalidSpecError, match="too large"):
        ChartSpec.from_json(" " * 2_000_000)
    with pytest.raises(InvalidSpecError, match="not valid JSON"):
        ChartSpec.from_json("[" * 100_000)
    with pytest.raises(InvalidSpecError):
        ChartSpec.from_json("{not json")


@settings(max_examples=300, deadline=None)
@given(
    st.dictionaries(
        st.sampled_from(
            ["kind", "x", "y", "agg", "top", "sort", "calc", "title", "options", "evil"]
        ),
        st.none()
        | st.booleans()
        | st.integers()
        | st.text(max_size=20)
        | st.lists(st.text(max_size=5), max_size=3)
        | st.dictionaries(st.text(max_size=8), st.integers(), max_size=2),
        max_size=6,
    )
)
def test_spec_loader_only_raises_invalid_spec(data: dict[str, object]) -> None:
    with contextlib.suppress(InvalidSpecError):
        ChartSpec.from_dict(data)
