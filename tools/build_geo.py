"""Build tabsight's bundled map data from Natural Earth (public domain).

Reads the hash-checked GeoJSON in data-raw/naturalearth (see tools/fetch_vendor.py),
simplifies the shapes with mapshaper (tools/node_modules) and writes, into
src/tabsight/geo/data:

- world.topo.json.gz      countries (Antarctica left out), geometry id = ISO 3166-1 alpha-3
- admin1/XXX.topo.json.gz one file per country; one TopoJSON object per layer
                          ("admin1" plus groupings such as UK nations or French regions)
- names.json.gz           every name, code and bounding box used for matching
- cities.json.gz          about 7,300 populated places
- version.json            data version and build settings

Deterministic: the same inputs give byte-identical outputs (no clock, sorted keys).
Usage: python tools/build_geo.py
"""

from __future__ import annotations

import gzip
import json
import math
import shutil
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data-raw" / "naturalearth"
OUT = ROOT / "src" / "tabsight" / "geo" / "data"
MAPSHAPER = ROOT / "tools" / "node_modules" / "mapshaper" / "bin" / "mapshaper"
NATURAL_EARTH = "v5.1.2"
GEO_VERSION = 1

LANGS = ("ar", "bn", "de", "el", "en", "es", "fa", "fr", "he", "hi", "hu", "id", "it", "ja",
         "ko", "nl", "pl", "pt", "ru", "sv", "tr", "uk", "ur", "vi", "zh", "zht")  # fmt: skip
WORLD_RESOLUTION = "2400x1200"
COUNTRY_RESOLUTION = "1400x1400"

# Groupings people use more often than Natural Earth's own level 1 (dissolved at build time).
GROUPS: dict[str, list[tuple[str, str]]] = {
    "GBR": [("nation", "geonunit"), ("region", "region")],
    "FRA": [("region", "region")],
    "ITA": [("region", "region")],
    "ESP": [("region", "region")],
    "PHL": [("region", "region")],
}
# English names for grouped layers whose source names are in the local language.
GROUP_ALIASES: dict[str, list[str]] = {
    "Lombardia": ["Lombardy"], "Piemonte": ["Piedmont"], "Toscana": ["Tuscany"],
    "Sicilia": ["Sicily"], "Sardegna": ["Sardinia"], "Apulia": ["Puglia"],
    "Trentino-Alto Adige": ["Trentino-South Tyrol", "Trentino-Alto Adige/Südtirol"],
    "Valle d'Aosta": ["Aosta Valley"], "Friuli-Venezia Giulia": ["Friuli Venezia Giulia"],
    "Cataluña": ["Catalonia", "Catalunya"], "Andalucía": ["Andalusia"],
    "País Vasco": ["Basque Country", "Euskadi"], "Valenciana": ["Valencia", "Valencian Community", "Comunitat Valenciana"],
    "Castilla y León": ["Castile and León"], "Castilla-La Mancha": ["Castile-La Mancha"],
    "Foral de Navarra": ["Navarre", "Navarra"], "Islas Baleares": ["Balearic Islands", "Illes Balears"],
    "Canary Is.": ["Canary Islands", "Canarias"], "Madrid": ["Community of Madrid", "Comunidad de Madrid"],
    "Bretagne": ["Brittany"], "Normandie": ["Normandy"], "Corse": ["Corsica"],
    "Bourgogne-Franche-Comté": ["Burgundy-Franche-Comté"], "Guyane française": ["French Guiana"],
    "Centre-Val de Loire": ["Centre"],
}  # fmt: skip
# Everyday names Natural Earth doesn't carry. England, Scotland and the other UK nations
# are deliberately not aliases of GBR: they are regions on the UK map.
COUNTRY_ALIASES = {
    "IRL": ["Éire", "Eire"], "GBR": ["UK", "Great Britain", "Britain"], "USA": ["U.S.", "America"],
    "MKD": ["Macedonia"], "COD": ["DRC", "DR Congo", "Congo-Kinshasa"], "COG": ["Congo-Brazzaville"],
    "ARE": ["UAE", "Emirates"], "NLD": ["Holland"], "BIH": ["Bosnia"], "TTO": ["Trinidad"],
    "IND": ["Bharat"], "JPN": ["Nippon", "Nihon"], "CHN": ["Zhongguo", "PRC"], "SAU": ["KSA"],
}  # fmt: skip

# Shown names where Natural Earth's English name is not the everyday one.
DISPLAY_NAMES = {"CHN": "China", "USA": "United States"}

# Canonical names when several Natural Earth units share one ISO 3166-2 code.
# Also fixes Natural Earth's English name where it is misleading (DC's is "Washington").
ISO_NAMES = {"IE-TA": "Tipperary", "IE-D": "Dublin", "IE-LS": "Laois", "AU-NSW": "New South Wales",
             "US-DC": "District of Columbia"}  # fmt: skip
EXTRA_ALIASES = {"IE-LS": ["Laoighis", "Leix"], "IE-OY": ["Offaly"], "US-DC": ["Washington DC", "Washington, D.C.", "D.C."],
                 "RU-SA": ["Yakutia", "Sakha (Yakutia)"]}  # fmt: skip

# US insets: Alaska and Hawaii moved under the lower 48 (lon/lat space; ECharts draws
# country maps in lon/lat). (centre lon, centre lat, scale lon, scale lat, new lon, new lat)
INSETS = {
    "USA": {
        "US-AK": (-152.0, 63.0, 0.17, 0.35, -116.0, 26.0),
        "US-HI": (-157.0, 20.5, 1.0, 1.0, -104.5, 24.5),
    }
}


def main() -> None:
    node = shutil.which("node")
    if node is None:
        raise SystemExit("Node.js is needed (mapshaper simplifies the shapes)")
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "admin1").mkdir(parents=True)
    (OUT / "__init__.py").write_text(
        '"""Bundled map data (built by tools/build_geo.py)."""\n', encoding="utf-8", newline="\n"
    )
    countries = _load("ne_50m_admin_0_countries")
    admin1 = _load("ne_10m_admin_1_states_provinces")
    places = _load("ne_10m_populated_places_simple")

    names: dict[str, Any] = {"countries": {}, "layers": {}, "insets": {}}
    tmp = ROOT / ".geo-build"  # scratch space inside the repo (git-ignored)
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir()
    try:
        _world(node, tmp, countries, names)
        by_country: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for f in admin1:
            by_country[f["properties"]["adm0_a3"]].append(f)
        for iso3 in sorted(by_country):
            _country(node, tmp, iso3, by_country[iso3], names)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    names["insets"] = {c: {k: list(v) for k, v in t.items()} for c, t in INSETS.items()}
    _write_gz(OUT / "names.json.gz", names)
    _write_gz(OUT / "cities.json.gz", _cities(places))
    (OUT / "version.json").write_text(
        json.dumps(
            {"geo_version": GEO_VERSION, "natural_earth": NATURAL_EARTH,
             "world_resolution": WORLD_RESOLUTION, "country_resolution": COUNTRY_RESOLUTION},
            indent=2, sort_keys=True,
        ) + "\n",
        encoding="utf-8", newline="\n",
    )  # fmt: skip
    total = sum(p.stat().st_size for p in OUT.rglob("*") if p.is_file())
    print(
        f"wrote {len(list((OUT / 'admin1').iterdir()))} country files; {total / 1e6:.1f} MB in total"
    )


# ---------------------------------------------------------------- countries


def _country_id(p: dict[str, Any]) -> str:
    # Not ISO_A3_EH: Australia's small territories carry "AUS" there and would overwrite it.
    for key in ("ISO_A3", "ADM0_A3"):
        value = p.get(key)
        if isinstance(value, str) and len(value) == 3 and value != "-99":
            return value
    raise ValueError(p.get("NAME"))


def _world(node: str, tmp: Path, features: list[dict[str, Any]], names: dict[str, Any]) -> None:
    keep = []
    for f in features:
        p = f["properties"]
        cid = _country_id(p)
        if cid == "ATA":
            continue  # Antarctica: hidden by default (PLAN 7.4)
        if cid in names["countries"]:
            raise ValueError(f"two countries share the id {cid}")
        all_names = {lang: p.get(f"NAME_{lang.upper()}") for lang in LANGS}
        alts = [p.get(k) for k in ("NAME", "NAME_LONG", "ADMIN", "FORMAL_EN", "FORMAL_FR", "ABBREV",
                                   "NAME_ALT", "NAME_CIAWF", "GEOUNIT", "SUBUNIT", "BRK_NAME", "NAME_SORT")]  # fmt: skip
        # ISO codes only: FIPS, World Bank and postal codes collide (FIPS "GB" is Gabon)
        codes = [cid, p.get("ISO_A2"), p.get("ISO_A2_EH"), p.get("ADM0_A3"), p.get("ISO_A3_EH")]
        names["countries"][cid] = {
            "n": DISPLAY_NAMES.get(cid) or p.get("NAME_EN") or p["NAME"],
            "iso2": _iso2(p),
            "names": _clean_dict(all_names),
            "alt": _clean_list([*alts, *COUNTRY_ALIASES.get(cid, [])]),
            "codes": _clean_list(codes),
            "tiny": bool(p.get("TINY") not in (None, -99)) or _area(f["geometry"]) < 1.0,
            "label": [round(p["LABEL_X"], 3), round(p["LABEL_Y"], 3)],
            "bbox": _bbox(f["geometry"]),
            "continent": p.get("CONTINENT"),
            "pop": int(p.get("POP_EST") or 0),
        }
        keep.append({"type": "Feature", "id": cid, "properties": {"id": cid},
                     "geometry": f["geometry"]})  # fmt: skip
    src = tmp / "world.geojson"
    src.write_text(json.dumps({"type": "FeatureCollection", "features": keep}), encoding="utf-8")
    topo = _mapshaper(node, src, tmp / "world.topo.json", "countries", WORLD_RESOLUTION, [])
    _write_gz(OUT / "world.topo.json.gz", topo)


def _iso2(p: dict[str, Any]) -> str | None:
    for key in ("ISO_A2", "ISO_A2_EH"):
        value = p.get(key)
        if isinstance(value, str) and len(value) == 2 and value != "-9":
            return value
    return None


# ---------------------------------------------------------------- level 1 regions


def _country(
    node: str, tmp: Path, iso3: str, features: list[dict[str, Any]], names: dict[str, Any]
) -> None:
    insets = INSETS.get(iso3, {})
    regions: dict[str, Any] = {}
    keep = []
    iso_count: dict[str, int] = defaultdict(int)
    for f in features:
        iso_count[f["properties"].get("iso_3166_2") or ""] += 1
    for f in features:
        p = f["properties"]
        rid = p["adm1_code"]
        iso = _valid_iso(p.get("iso_3166_2"))
        geometry = f["geometry"]
        if iso in insets:
            geometry = _transform(geometry, insets[iso])
        all_names = {lang: p.get(f"name_{lang}") for lang in LANGS}
        alts = [p.get("name"), p.get("name_local"), p.get("gn_name"), p.get("woe_name"),
                p.get("woe_label"), p.get("gns_name"), *(p.get("name_alt") or "").split("|"),
                *EXTRA_ALIASES.get(iso or "", [])]  # fmt: skip
        codes = [iso, p.get("postal"), p.get("code_hasc"), p.get("fips"), p.get("abbrev"),
                 p.get("code_local"), p.get("gn_a1_code")]  # fmt: skip
        regions[rid] = {
            "n": ISO_NAMES.get(iso or "") or p.get("name_en") or p.get("name") or rid,
            "local": p.get("name_local") or p.get("name"),
            "names": _clean_dict(all_names),
            "alt": _clean_list(alts),
            "codes": _clean_list(
                [c for c in codes if c and "~" not in str(c) and "-99" not in str(c)]
            ),
            "type": p.get("type_en"),
            "iso": iso,
            "bbox": _bbox(geometry),
            "label": _label_point(p, insets.get(iso or "")),
            "group": {layer: p.get(field) for layer, field in GROUPS.get(iso3, [])},
        }
        props = {"id": rid, "iso": iso or rid}
        for layer, field in GROUPS.get(iso3, []):
            props[layer] = p.get(field) or "?"
        keep.append({"type": "Feature", "properties": props, "geometry": geometry})
    layers: dict[str, Any] = {"admin1": {"type": _layer_type(regions), "features": regions}}
    dissolves: list[list[str]] = []
    if any(n > 1 for code, n in iso_count.items() if code and _valid_iso(code)):
        # Several Natural Earth units share one ISO code (Cork City and County Cork):
        # an "iso" layer merges them, so data by official region still matches.
        dissolves.append(["-dissolve", "iso", "+", "name=iso", "target=admin1", "copy-fields=iso"])
        merged: dict[str, Any] = {}
        for rid, r in regions.items():
            key = r["iso"] or rid
            m = merged.setdefault(key, {"n": ISO_NAMES.get(key, r["n"]), "local": None, "names": {},
                                        "alt": [], "codes": [], "type": r["type"], "iso": r["iso"],
                                        "bbox": r["bbox"], "group": {}})  # fmt: skip
            if key not in ISO_NAMES and len(r["n"]) < len(m["n"]):
                m["n"] = r["n"]
            m["alt"] = _clean_list([*m["alt"], r["n"], *r["alt"]])
            m["codes"] = _clean_list([*m["codes"], *r["codes"]])
            m["bbox"] = _merge_bbox(m["bbox"], r["bbox"])
            m.setdefault("label", r["label"])
        layers["iso"] = {"type": _layer_type(merged), "features": merged}
    for layer, _field in GROUPS.get(iso3, []):
        dissolves.append(
            ["-dissolve", layer, "+", f"name={layer}", "target=admin1", f"copy-fields={layer}"]
        )
        grouped: dict[str, Any] = {}
        for r in regions.values():
            key = r["group"].get(layer) or "?"
            g = grouped.setdefault(key, {"n": key, "local": key, "names": {}, "alt": GROUP_ALIASES.get(key, []),
                                         "codes": [], "type": layer, "iso": None, "bbox": r["bbox"], "group": {}})  # fmt: skip
            g["bbox"] = _merge_bbox(g["bbox"], r["bbox"])
            g["label"] = [
                round((g["bbox"][0] + g["bbox"][2]) / 2, 3),
                round((g["bbox"][1] + g["bbox"][3]) / 2, 3),
            ]
        grouped.pop("?", None)
        layers[layer] = {"type": layer, "features": grouped}
    for r in regions.values():
        r.pop("group")
    names["layers"][iso3] = layers
    src = tmp / f"{iso3}.geojson"
    src.write_text(json.dumps({"type": "FeatureCollection", "features": keep}), encoding="utf-8")
    topo = _mapshaper(node, src, tmp / f"{iso3}.topo.json", "admin1", COUNTRY_RESOLUTION, dissolves)
    _write_gz(OUT / "admin1" / f"{iso3}.topo.json.gz", topo)


def _label_point(p: dict[str, Any], inset: tuple[float, ...] | None) -> list[float]:
    point = [float(p["longitude"]), float(p["latitude"])]
    if inset is not None:
        point = _transform({"type": "Point", "coordinates": point}, inset)["coordinates"]
    return [round(point[0], 3), round(point[1], 3)]


def _layer_type(regions: dict[str, Any]) -> str:
    counts: dict[str, int] = defaultdict(int)
    for r in regions.values():
        counts[r["type"] or "region"] += 1
    return max(sorted(counts), key=lambda k: counts[k]).lower()


def _valid_iso(value: Any) -> str | None:
    if isinstance(value, str) and "-" in value and "~" not in value and "-99" not in value:
        return value
    return None


def _transform(geometry: dict[str, Any], t: tuple[float, ...]) -> dict[str, Any]:
    cx, cy, sx, sy, nx, ny = t

    def move(pt: list[float]) -> list[float]:
        lon, lat = pt[0], pt[1]
        if lon > 0:
            lon -= 360  # the Aleutians cross the antimeridian
        return [round(nx + (lon - cx) * sx, 5), round(ny + (lat - cy) * sy, 5)]

    return {"type": geometry["type"], "coordinates": _map_coords(geometry["coordinates"], move)}


def _map_coords(coords: Any, fn: Any) -> Any:
    if coords and isinstance(coords[0], int | float):
        return fn(coords)
    return [_map_coords(c, fn) for c in coords]


# ---------------------------------------------------------------- cities


def _cities(features: list[dict[str, Any]]) -> list[list[Any]]:
    rows = []
    for f in features:
        p = f["properties"]
        alts = _clean_list([p.get("nameascii"), p.get("namealt"), p.get("meganame"), p.get("ls_name"),
                            p.get("namepar")])  # fmt: skip
        rows.append([
            p["name"], [a for a in alts if a != p["name"]], p.get("adm0_a3"), p.get("adm1name"),
            round(p["latitude"], 4), round(p["longitude"], 4), int(p.get("pop_max") or 0),
            int(p.get("adm0cap") or 0),
        ])  # fmt: skip
    rows.sort(key=lambda r: (-r[6], r[0], r[2] or ""))
    return rows


# ---------------------------------------------------------------- helpers


def _load(name: str) -> list[dict[str, Any]]:
    data = json.loads((RAW / f"{name}.geojson").read_text(encoding="utf-8"))
    return list(data["features"])


def _mapshaper(
    node: str, src: Path, dest: Path, layer: str, resolution: str, extra: list[list[str]]
) -> Any:
    cmd = [node, str(MAPSHAPER), "-i", str(src), f"name={layer}", "-simplify",
           f"resolution={resolution}", "keep-shapes", "-filter-slivers"]  # fmt: skip
    for step in extra:
        cmd += step
    cmd += ["-o", str(dest), "format=topojson", "quantization=20000", "id-field=id,iso,nation,region",
            "target=*" if extra else f"target={layer}"]  # fmt: skip
    done = subprocess.run(cmd, capture_output=True, text=True, check=False)  # noqa: S603 - fixed local tool
    if done.returncode != 0:
        raise SystemExit(f"mapshaper failed on {src.name}: {done.stderr}")
    topo = json.loads(dest.read_text(encoding="utf-8"))
    for obj in topo["objects"].values():  # ids only; names live in names.json
        for geom in obj.get("geometries", []):
            geom.pop("properties", None)
            if obj is topo["objects"].get(layer) and "id" not in geom:
                raise ValueError(f"feature without id in {src.name}")
    return topo


def _bbox(geometry: dict[str, Any]) -> list[float]:
    xs: list[float] = []
    ys: list[float] = []

    def take(pt: list[float]) -> list[float]:
        xs.append(pt[0])
        ys.append(pt[1])
        return pt

    _map_coords(geometry["coordinates"], take)
    return [round(min(xs), 3), round(min(ys), 3), round(max(xs), 3), round(max(ys), 3)]


def _merge_bbox(a: list[float], b: list[float]) -> list[float]:
    return [min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])]


def _area(geometry: dict[str, Any]) -> float:
    x0, y0, x1, y1 = _bbox(geometry)
    return (x1 - x0) * (y1 - y0) * math.cos(math.radians((y0 + y1) / 2))


def _clean_dict(d: dict[str, Any]) -> dict[str, str]:
    return {k: v.strip() for k, v in sorted(d.items()) if isinstance(v, str) and v.strip()}


def _clean_list(items: list[Any]) -> list[str]:
    out: list[str] = []
    for item in items:
        if (
            isinstance(item, str)
            and item.strip()
            and item.strip() != "-99"
            and item.strip() not in out
        ):
            out.append(item.strip())
    return out


def _write_gz(path: Path, data: Any) -> None:
    raw = json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode(
        "utf-8"
    )
    with path.open("wb") as fh, gzip.GzipFile(fileobj=fh, mode="wb", mtime=0, filename="") as gz:
        gz.write(raw)


if __name__ == "__main__":
    sys.exit(main())
