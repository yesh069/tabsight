# Colours and themes

## The same value always gets the same colour

A `ColorRegistry` gives each value a palette colour and remembers it, so `West` is the same colour on every chart. Values are **sorted before colours are assigned**, so the same data always gets the same colours, whatever order the rows are in.

```python
import tabsight as ts

colors = ts.ColorRegistry()  # default palette: classic10
colors.assign(["West", "East", "Central", "South"])
print(colors.mapping())
```

Pin colours you care about:

```python
brand = ts.ColorRegistry(pinned={"West": "#e15759"})
brand.assign(["East", "West"])
print(brand.color("West"), brand.color("East"))
saved = brand.to_dict()  # save with a dashboard; ts.ColorRegistry.from_dict(saved) restores it
```

## Palettes

| Name | Colours | Notes |
|------|---------|-------|
| `classic10` | 10 | The default; same colours as d3's widely used `schemeTableau10` |
| `okabe_ito` | 8 | Designed to be distinguishable with colour-vision deficiency |
| `muted` | 8 | Softer tones |

Sequential (`blues`, `greens`) and diverging (`red_blue`) scales are in `tabsight.colors`.

> [!IMPORTANT]
> Colours must be hex codes such as `#4e79a7`. Anything else (colour names, `rgb()`, CSS) is rejected, so a colour value can never inject CSS or markup into HTML output.

## Themes

| Theme | Use |
|-------|-----|
| `light` | Default: white tiles on a light grey page |
| `dark` | Dark tiles and page |
| `print` | White, black text, colour-blind-safe palette, square corners |

Every built-in theme passes **WCAG AA contrast** (4.5:1) for its text, and a test checks this.

```python
brand_theme = ts.custom_theme("light", accent="#0b5394", font='"Inter", Arial, sans-serif')
print(brand_theme.accent)
```

`custom_theme` checks contrast and refuses themes whose text would be hard to read. Fonts may only contain letters, digits, spaces, commas, quotes and hyphens. tabsight never downloads fonts; the default is the system font stack.

```python
from tabsight.colors import contrast_ratio

print(round(contrast_ratio("#1f2329", "#ffffff"), 1))
```
