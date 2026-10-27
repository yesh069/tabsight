# Colours and themes

## The same region is the same colour everywhere

A dashboard where West is blue in one chart and orange in the next makes people work harder than they should. tabsight gives each value one colour and keeps it:

```python
import tabsight as ts

colors = ts.ColorRegistry()
colors.assign(["West", "East", "Central", "South"])
print(colors.mapping())
```

```text title="Output"
{'Central': '#4e79a7', 'East': '#f28e2b', 'South': '#e15759', 'West': '#76b7b2'}
```

The values are sorted before colours are handed out, so you get the same colours however the rows happen to be ordered. If a colour matters to you, such as your company's red for its home region, pin it:

```python
brand = ts.ColorRegistry(pinned={"West": "#e15759"})
brand.assign(["East", "West", "South"])
print(brand.mapping())
```

```text title="Output"
{'West': '#e15759', 'East': '#4e79a7', 'South': '#f28e2b'}
```

A registry saves with `to_dict()` and comes back with `ts.ColorRegistry.from_dict(...)`, so next month's dashboard uses the same colours.

## Palettes

The default, `classic10`, uses the same ten colours as d3's widely used `schemeTableau10`. `okabe_ito` is designed to stay distinguishable for people with colour-vision deficiency, and the print theme uses it. `muted` is a softer set for dense charts. Pick one with `ts.ColorRegistry("okabe_ito")`, or for everything with `ts.set_defaults(palette="okabe_ito")`.

Colours have to be hex codes such as `#4e79a7`. Names like `red`, `rgb()` and anything else are rejected. That keeps a colour value from smuggling CSS into an HTML file.

## Themes

There are three built-in themes: `light` (white tiles on a pale grey page), `dark`, and `print` (pure white, black text, the colour-blind-safe palette and square corners). Each one meets the WCAG AA contrast standard for text, and a test makes sure it stays that way.

To match a brand, start from a built-in theme and change what you need:

```python
from tabsight.warnings import InvalidSpecError

brand_theme = ts.custom_theme("light", accent="#0b5394", font='"Inter", Arial, sans-serif')
print(brand_theme.accent, "|", brand_theme.font)

try:
    ts.custom_theme("light", text="#c8c8c8")
except InvalidSpecError as err:
    print(err)
```

```text title="Output"
#0b5394 | "Inter", Arial, sans-serif
theme fails WCAG AA contrast: text on tile is 1.67:1; text on page is 1.55:1; text on header is 1.50:1
```

The second theme was refused because light grey text on white is hard to read. Font names can only contain letters, digits, spaces, commas, quotes and hyphens, and tabsight never downloads fonts: the default is whatever sans-serif your system already has.
