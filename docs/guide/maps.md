# Maps

Give tabsight a column of place names and it works out which map they belong on: countries, the states, provinces or counties of any country, or cities. Every name is matched against data bundled with tabsight, so it works offline. The page then carries only the shapes that one map needs.

```python
import pandas as pd

import tabsight as ts

sales = pd.DataFrame(
    {
        "County": ["Cork", "Co. Kerry", "Dublin", "Galway", "Tipperary", "Corkk"],
        "Revenue": [500, 200, 1500, 300, 150, 40],
    }
)
fig = ts.chart(sales, "map", geo="County", y="Revenue")
print(fig.maps[0]["name"])
for note in fig.notes:
    print("-", note)
```

```text title="Output"
ts-IRL-iso
- 1 place(s) in 1 row(s) didn't match the map and are left out: 'Corkk' (did you mean 'Cork'?); geo_map= can fix spellings
```

`County` was recognised as Irish counties without being told. "Co. Kerry" matched Kerry, and the misspelt "Corkk" was not dropped silently: the note names it, suggests the fix and shows on the chart. The same message is raised as a `DataWarning`. Pass `geo_map={"Corkk": "Cork"}` to fix it, and Cork's two rows add up to one county.

## How a column is matched

Every country, region and city is matched on:

- its English, local and official names, and the names Natural Earth has in about 25 languages (Hindi, Chinese, Arabic, Russian, Japanese and others)
- alternate names and everyday names (`UK`, `Holland`, `Éire`)
- ISO codes: `IE`, `IRL`, `US-CA`, `IN-MH`, and US postal codes like `TX`

Case, accents and punctuation are ignored, so `Québec` matches `Quebec`. A second pass drops words that only say what kind of place it is: "County", "Province", "State of".

`ts.geo.match` shows the result for any column, without drawing anything:

```python
found = ts.geo.match(sales["County"])
print(found)
```

```text title="Output"
Ireland map (counties): 5 of 6 values matched (83%)
  chosen because 5 of 6 values are counties of Ireland
Not matched:
  'Corkk' (did you mean 'Cork'?)
```

## Choosing the map

The values decide. tabsight scores the world map, every country's region layers and the city list, and the one that matches the most distinct values wins:

```python
for values in (
    ["Ireland", "India", "Brazil", "Germany"],
    ["Bayern", "Hessen", "Sachsen", "Berlin"],
    ["CA", "TX", "NY", "FL", "WA"],
    ["England", "Scotland", "Wales", "Northern Ireland"],
    ["Dublin", "Mumbai", "Tokyo", "Lagos"],
):
    print(f"{values[0]:<10} -> {ts.geo.detect(values).label}")
```

```text title="Output"
Ireland    -> world map (countries)
Bayern     -> Germany map (states)
CA         -> United States of America map (states)
England    -> United Kingdom map (nations)
Dublin     -> cities
```

**Names that exist twice** are settled by the other values. "Georgia" next to Texas and Ohio is the US state; next to Armenia and Azerbaijan it's the country. "Punjab" next to Kerala is in India; next to Sindh it's in Pakistan. When the column alone can't decide, a column named like `Country` is used, and otherwise the detection says so and `map=` decides.

**Words like North, South, East, West and Central** never choose a map on their own. Several countries have regions with exactly those names, and a sales "Region" column almost never means them.

To choose yourself:

```python
# not run
ts.chart(df, "map", geo="State", y="Sales", map="Australia")       # a country's regions
ts.chart(df, "map", geo="Country", y="Sales", map="world")           # the world map
ts.chart(df, "map", geo="Area", y="Sales", map="GBR", layer="region")  # a particular layer
```

## Layers: the regions people actually use

Natural Earth's level 1 isn't always the level people use. The UK's level 1 has 232 local authorities, but most data is by nation. France and Italy have departments and provinces, but data is often by region. So some countries have extra layers, built from the same borders:

```python
for country in ("United Kingdom", "France", "Italy", "Spain", "Ireland"):
    print(f"{country:<15} {ts.geo.layers(country)}")
```

```text title="Output"
United Kingdom  ['admin1', 'nation', 'region']
France          ['admin1', 'region']
Italy           ['admin1', 'region']
Spain           ['admin1', 'region']
Ireland         ['admin1', 'iso']
```

Detection picks the layer your values match best. Ireland's `iso` layer merges the areas Natural Earth splits (Cork city and county, North and South Tipperary) into the 26 official counties.

## Cities and symbol maps

Cities are points, so they're drawn as circles whose area grows with the value:

```python
offices = pd.DataFrame(
    {
        "City": ["Birmingham", "London", "Manchester", "Glasgow"],
        "Country": ["United Kingdom"] * 4,
        "Staff": [120, 900, 210, 75],
    }
)
fig = ts.chart(offices, "symbol_map", geo="City", y="Staff")
print([d["name"] for d in fig.option["series"][0]["data"]])
```

```text title="Output"
['London, United Kingdom', 'Manchester, United Kingdom', 'Birmingham, United Kingdom', 'Glasgow, United Kingdom']
```

"Birmingham" is also a city in Alabama and "London" one in Ontario. The `Country` column settled both. Without it, tabsight picks the largest and adds a note saying so. Points can also come from coordinates: `ts.chart(df, "symbol_map", lat="Latitude", lon="Longitude", y="Sales")`.

## What the map looks like

- **Projection.** The world map uses Equal Earth, so every country keeps its true relative area (Greenland isn't the size of Africa). `projection="mercator"` and `"natural"` are there if you need them.
- **Zoom.** When the data covers only part of the world, the map zooms to it.
- **Colours.** Darker means bigger. When some values are negative, the colours diverge from zero instead. Regions without data are light grey, and their tooltip says "No data".
- **Small places.** Tiny countries such as Singapore and Malta get a dot, so they can be seen and hovered.
- **Insets.** Alaska and Hawaii are moved under the other US states, and cities in them move with them.
- **Antarctica** is left out.
- **Language.** `geo_names="local"` shows local names (`Bayern`), and a language code (`"hi"`, `"zh"`, `"de"`...) shows that language where Natural Earth has it.

`fig.explain()` lists which map was chosen and why, along with everything else tabsight decided.

## Coverage and known gaps

The bundled data is Natural Earth 5.1.2 (public domain): about 240 countries, level-1 regions for every one of them, and about 7,300 cities. It isn't equally good everywhere. The 30 most-used countries were checked against official lists, and the [map coverage](../reference/map-coverage.md) page shows each country's regions and the known differences: for example, Indonesia's 2022 provinces are missing, and Hong Kong and Macau are separate countries rather than parts of China.

Borders follow Natural Earth's default view, including where borders are disputed.

Not in this release:
- districts (level 2), which would need an opt-in download
- your own GeoJSON shapes
- density maps and flow maps, which come in phase 6
