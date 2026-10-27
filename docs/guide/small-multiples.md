# Small multiples

`facet="Region"` draws one small chart per region in a grid, the trellis view of BI tools. Comparing four small charts side by side is often clearer than one chart with four colours.

```python
import tabsight as ts

orders = ts.load("examples/superstore_sample.csv")
fig = ts.chart(orders, "stacked_bar", x="Category", y="Sales", color="Segment", facet="Region")
print(fig.title)
print([t["text"] for t in fig.option["title"]])
print({a["max"] for a in fig.option["yAxis"]}, "is the top of every panel's scale")
```

```text title="Output"
Sum of Sales by Category, by Region
['East', 'West', 'Central', 'South']
{40000.0} is the top of every panel's scale
```

The panels share what makes them comparable:

- **One value scale.** A bar of the same height means the same number in every panel. If each panel fitted its own data, a small region would look as big as a large one.
- **One category order**, taken from all the data, so Technology is in the same place in every panel.
- **One colour per series** and a single legend.
- **One map**, for maps: every panel uses the same map and layer, with one shared colour scale.

Facets work with the bar kinds, lollipop, the line and area kinds, scatter, histogram and maps. Histograms share one bar width, so the bars line up across panels.

```python
fig = ts.chart(orders, "map", geo="State", y="Sales", facet="Category")
print(len(fig.option["geo"]), "maps,", fig.option["visualMap"]["min"], "to", fig.option["visualMap"]["max"])
```

```text title="Output"
3 maps, 2395.94 to 14254.84
```

At most 12 panels are drawn: the largest by the measure, or the first 12 in order for dates and ordered columns. A note says how many were left out. With `kind="auto"`, the chart is chosen once on all the data, so every panel is the same kind.
