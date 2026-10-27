"""ts.geo: bundled names, matching, detection and coverage."""

from __future__ import annotations

import pandas as pd
import pytest

import tabsight as ts
from tabsight.geo import names as gn
from tabsight.geo.detection import GeoTarget, detect, display_name, match
from tabsight.warnings import InvalidSpecError

# ---------------------------------------------------------------- every bundled place


def test_every_country_and_region_matches_its_own_name_and_codes() -> None:
    data = gn.geo_data()
    countries = gn.country_index()
    for code, entry in data["countries"].items():
        assert code in (gn.lookup(entry["n"], countries) or ()), entry["n"]
        assert code in (gn.lookup(code, countries) or ()), code
    regions = gn.region_index()
    checked = 0
    for country, layers in data["layers"].items():
        for layer, info in layers.items():
            for rid, entry in info["features"].items():
                assert (country, layer, rid) in (gn.lookup(entry["n"], regions) or ()), entry["n"]
                if entry.get("iso"):
                    assert (country, layer, rid) in (gn.lookup(entry["iso"], regions) or ()), entry[
                        "iso"
                    ]
                checked += 1
    assert len(data["countries"]) >= 240 and checked >= 4600


def test_matching_ignores_case_accents_punctuation_and_place_words() -> None:
    idx = gn.region_index()

    def county(text: str) -> set[tuple[str, str, str]]:
        return {hit for hit in gn.lookup(text, idx) or () if hit[:2] == ("IRL", "iso")}

    assert county("Cork") == {("IRL", "iso", "IE-CO")}
    for spelling in ["CORK", "co. cork", "County Cork", "Cork County", " cork "]:
        assert county(spelling) == county("Cork"), spelling
    assert gn.lookup("Quebec", idx) == gn.lookup("Québec", idx)
    assert gn.key("St. Louis") == gn.key("Saint Louis")
    assert gn.key("west.") == "west"  # "st." only as a word
    assert gn.lookup("Bavaria", idx) == gn.lookup("Bayern", idx)  # English and local names


# ---------------------------------------------------------------- detection: 30 countries

REGION_CASES: dict[str, list[str]] = {
    "USA": ["California", "Texas", "New York", "Florida", "Illinois"],
    "IND": ["Maharashtra", "Tamil Nadu", "Karnataka", "Kerala", "Uttar Pradesh"],
    "IRL": ["Cork", "Kerry", "Dublin", "Galway", "Tipperary"],
    "GBR": ["Kent", "Cornwall", "Glasgow", "Cardiff", "Manchester"],
    "DEU": ["Bayern", "Nordrhein-Westfalen", "Hessen", "Sachsen", "Berlin"],
    "FRA": ["Gironde", "Finistère", "Bouches-du-Rhône", "Nord", "Haute-Garonne"],
    "CHN": ["Guangdong", "Sichuan", "Zhejiang", "Yunnan", "Shandong"],
    "BRA": ["São Paulo", "Bahia", "Minas Gerais", "Paraná", "Amazonas"],
    "CAN": ["Ontario", "Quebec", "Alberta", "Manitoba", "Nova Scotia"],
    "AUS": ["New South Wales", "Queensland", "Victoria", "Tasmania", "Western Australia"],
    "ESP": ["Madrid", "Barcelona", "Sevilla", "Valencia", "Málaga"],
    "ITA": ["Roma", "Milano", "Torino", "Napoli", "Firenze"],
    "MEX": ["Jalisco", "Oaxaca", "Yucatán", "Sonora", "Chiapas"],
    "JPN": ["Hokkaido", "Osaka", "Okinawa", "Kyoto", "Aichi"],
    "NLD": ["Noord-Holland", "Utrecht", "Groningen", "Friesland", "Zeeland"],
    "ZAF": ["Gauteng", "Limpopo", "KwaZulu-Natal", "Western Cape", "Free State"],
    "NGA": ["Lagos", "Kano", "Kaduna", "Rivers", "Oyo"],
    "RUS": ["Tatarstan", "Bashkortostan", "Dagestan", "Chechnya", "Yakutia"],
    "IDN": ["Bali", "Aceh", "Papua", "Jawa Barat", "Riau"],
    "PAK": ["Punjab", "Sindh", "Balochistan", "Khyber Pakhtunkhwa"],
    "BEL": ["Antwerpen", "Limburg", "Hainaut", "Namur", "Liège"],
    "CHE": ["Zürich", "Bern", "Vaud", "Ticino", "Valais"],
    "SWE": ["Stockholm", "Skåne", "Uppsala", "Norrbotten", "Gotland"],
    "POL": ["Mazowieckie", "Malopolskie", "Slaskie", "Pomorskie", "Lubelskie"],
    "ARG": ["Mendoza", "Salta", "Chubut", "Tucumán", "Santa Fe"],
    "KOR": ["Seoul", "Busan", "Jeju", "Gyeonggi", "Incheon"],
    "TUR": ["Istanbul", "Ankara", "Izmir", "Antalya", "Konya"],
    "PHL": ["Cebu", "Palawan", "Bohol", "Batangas", "Pampanga"],
    "NZL": ["Auckland", "Canterbury", "Otago", "Waikato", "Northland"],
    "EGY": ["Cairo", "Alexandria", "Giza", "Aswan", "Luxor"],
}


@pytest.mark.parametrize("country", list(REGION_CASES))
def test_detects_regions_for_top_30_countries(country: str) -> None:
    values = pd.Series(REGION_CASES[country], name="Region name")
    target = detect(values, name="Province")
    assert target is not None and target.level == "region" and target.country == country, target
    found = match(values, target)
    assert not found.unmatched, found.show()


def test_detects_countries_codes_and_other_languages() -> None:
    assert (
        detect(["Ireland", "India", "Côte d'Ivoire", "South Korea", "Czechia", "UK"]).level
        == "country"
    )  # type: ignore[union-attr]
    assert detect(["IE", "IN", "BR", "DE", "US", "GB"]).level == "country"  # type: ignore[union-attr]
    assert detect(["IRL", "IND", "BRA", "DEU"]).level == "country"  # type: ignore[union-attr]
    assert detect(["भारत", "जर्मनी", "ब्राज़ील"]).level == "country"  # type: ignore[union-attr]
    found = match(["Éire", "Holland", "UAE", "DR Congo", "U.S."], GeoTarget("country"))
    assert dict(found.ids) == {
        "Éire": "IRL",
        "Holland": "NLD",
        "UAE": "ARE",
        "DR Congo": "COD",
        "U.S.": "USA",
    }


def test_layers_people_actually_use() -> None:
    uk = detect(["England", "Scotland", "Wales", "Northern Ireland"])
    assert uk is not None and (uk.country, uk.layer) == ("GBR", "nation")
    fr = detect(["Île-de-France", "Bretagne", "Normandy", "Occitanie"])
    assert fr is not None and (fr.country, fr.layer) == ("FRA", "region")
    it = detect(["Lombardy", "Tuscany", "Sicily", "Piemonte"])
    assert it is not None and (it.country, it.layer) == ("ITA", "region")
    ie = detect(
        ["Cork", "Tipperary", "Dublin"]
    )  # Natural Earth splits these; the iso layer doesn't
    assert ie is not None and (ie.country, ie.layer) == ("IRL", "iso")
    assert ts.geo.layers("United Kingdom") == ["admin1", "nation", "region"]


def test_us_postal_codes() -> None:
    target = detect(["CA", "TX", "NY", "FL", "WA", "OH", "IL", "GA"])
    assert target is not None and target.country == "USA"
    assert match(["CA", "TX"], target).ids["CA"] == match(["California"], target).ids["California"]


def test_names_at_two_levels_or_in_two_countries() -> None:
    us = detect(["Georgia", "Texas", "Ohio", "Florida"])
    assert us is not None and us.country == "USA"
    world = detect(["Georgia", "Armenia", "Azerbaijan", "Turkey"])
    assert world is not None and world.level == "country"
    lux_be = detect(["Luxembourg", "Namur", "Liège", "Hainaut"])
    assert lux_be is not None and lux_be.country == "BEL"
    lux_world = detect(["Luxembourg", "Belgium", "Netherlands"])
    assert lux_world is not None and lux_world.level == "country"
    assert detect(["Punjab", "Kerala", "Goa"]).country == "IND"  # type: ignore[union-attr]
    assert detect(["Punjab", "Sindh", "Balochistan"]).country == "PAK"  # type: ignore[union-attr]
    india = detect(["Punjab"], context=["India"])
    pakistan = detect(["Punjab"], context=["Pakistan"])
    assert india is not None and pakistan is not None
    assert (india.country, pakistan.country) == ("IND", "PAK")
    assert "pass country=" in detect(["Punjab"]).reason  # type: ignore[union-attr]


def test_cities_and_the_country_column() -> None:
    target = detect(["Dublin", "Mumbai", "Tokyo", "Lagos", "Sydney"], name="City")
    assert target is not None and target.level == "city"
    values = ["Birmingham", "Birmingham", "London"]
    found = match(values, GeoTarget("city"), context=["United States", "United States", "Canada"])
    rows = gn.cities_data()
    assert rows[int(found.ids["Birmingham"])][2] == "USA"
    assert rows[int(found.ids["London"])][2] == "CAN"
    largest = match(["Birmingham"], GeoTarget("city"))
    assert rows[int(largest.ids["Birmingham"])][2] == "GBR"
    assert "add a country column" in largest.notes[0]


def test_not_places() -> None:
    for values in (["Chairs", "Tables", "Phones"], ["North", "South", "East", "West"],
                   ["Central", "East", "South", "West"], ["A", "B", "C"], ["1", "2", "3"],
                   ["Consumer", "Corporate", "Home Office"], []):  # fmt: skip
        assert detect(values) is None, values


def test_unmatched_values_are_reported_with_suggestions() -> None:
    target = detect(["Cork", "Kerry", "Galway"])
    assert target is not None
    found = match(["Cork", "Kery", "Atlantis", None, "Galway"], target)
    assert dict(found.unmatched) == {"Kery": "Kerry", "Atlantis": None}
    assert found.share == pytest.approx(2 / 4)
    text = found.show()
    assert "'Kery' (did you mean 'Kerry'?)" in text and "'Atlantis'" in text
    fixed = match(["Kery"], target, overrides={"Kery": "Kerry"})
    assert not fixed.unmatched
    with pytest.raises(InvalidSpecError, match="geo_map"):
        match(["Kery"], target, overrides={"Kery": 5})  # type: ignore[dict-item]


def test_display_names_in_other_languages() -> None:
    target = GeoTarget("country")
    assert display_name(target, "DEU") == "Germany"
    assert display_name(target, "DEU", "local") in ("Germany", "Deutschland")
    assert display_name(target, "DEU", "hi") == "जर्मनी"
    bavaria = match(["Bavaria"], detect(["Bavaria", "Hessen", "Sachsen"]))  # type: ignore[arg-type]
    rid = bavaria.ids["Bavaria"]
    assert display_name(bavaria.target, rid, "local") == "Bayern"


def test_public_api() -> None:
    assert ts.geo.country_code("Ireland") == ts.geo.country_code("IE") == "IRL"
    with pytest.raises(InvalidSpecError, match="did you mean 'Ireland'"):
        ts.geo.country_code("Irelnd")
    found = ts.geo.match(pd.Series(["Cork", "Kerry"], name="County"))
    assert len(found.ids) == 2 and found.to_dict()["target"]["country"] == "IRL"
    assert ts.geo.match(["England", "Scotland"], layer="nation").target.layer == "nation"
    with pytest.raises(InvalidSpecError, match="layer"):
        ts.geo.match(["England", "Scotland"], layer="nope")
    assert ts.geo.version()["natural_earth"] == "v5.1.2"
    assert ts.geo.detect(pd.Series(["Chairs"], name="Product")) is None


# ---------------------------------------------------------------- coverage against official lists

# Official level-1 counts (ISO 3166-2 and national sources, 2026) next to what is bundled.
# Where they differ, the reason is shown in the coverage table in the docs.
OFFICIAL = {
    ("USA", "admin1"): (51, 51, "50 states + DC"),
    ("IND", "admin1"): (36, 36, "28 states + 8 union territories"),
    ("IRL", "iso"): (26, 26, "26 counties"),
    ("GBR", "nation"): (4, 4, "4 nations"),
    ("DEU", "admin1"): (16, 16, "16 states"),
    ("FRA", "region"): (18, 18, "13 metropolitan + 5 overseas regions"),
    ("BRA", "admin1"): (27, 27, "26 states + federal district"),
    ("CAN", "admin1"): (13, 13, "10 provinces + 3 territories"),
    ("ESP", "region"): (19, 19, "17 communities + 2 cities"),
    ("ITA", "region"): (20, 20, "20 regions"),
    ("JPN", "admin1"): (47, 47, "47 prefectures"),
    ("ZAF", "admin1"): (9, 9, "9 provinces"),
    ("NGA", "admin1"): (37, 37, "36 states + FCT"),
    ("CHE", "admin1"): (26, 26, "26 cantons"),
    ("SWE", "admin1"): (21, 21, "21 counties"),
    ("POL", "admin1"): (16, 16, "16 voivodeships"),
    ("ARG", "admin1"): (24, 24, "23 provinces + Buenos Aires city"),
    ("KOR", "admin1"): (17, 17, "17 first-level divisions"),
    ("TUR", "admin1"): (81, 81, "81 provinces"),
    ("EGY", "admin1"): (27, 27, "27 governorates"),
    ("CHN", "admin1"): (34, 32, "Hong Kong and Macau are separate countries in Natural Earth"),
    ("AUS", "iso"): (8, 10, "plus Jervis Bay Territory and Macquarie Island"),
    ("MEX", "admin1"): (32, 33, "plus one small island group without a code"),
    ("NLD", "admin1"): (12, 15, "plus the 3 Caribbean special municipalities"),
    ("IDN", "admin1"): (38, 33, "Natural Earth predates the 2022 Papua splits"),
    ("RUS", "admin1"): (
        83,
        86,
        "includes Crimea and Sevastopol (Natural Earth's de facto view) and one small unnamed area",
    ),
    ("PAK", "admin1"): (7, 8, "still has the Tribal Areas, merged into Khyber Pakhtunkhwa in 2018"),
    ("PHL", "iso"): (82, 83, "82 provinces + Metro Manila"),
    ("NZL", "admin1"): (16, 24, "plus outlying islands"),
    ("BEL", "admin1"): (11, 11, "10 provinces + Brussels"),
}


@pytest.mark.parametrize(("key", "expected"), list(OFFICIAL.items()), ids=lambda k: str(k))
def test_region_counts_for_top_30_countries(
    key: tuple[str, str], expected: tuple[int, int, str]
) -> None:
    country, layer = key
    _official, bundled, _why = expected
    assert len(gn.geo_data()["layers"][country][layer]["features"]) == bundled


def test_coverage_table() -> None:
    table = ts.geo.coverage()
    assert len(table) >= 240 and set(table.columns) == {
        "country",
        "code",
        "regions",
        "region_type",
        "layers",
    }
    gb = table[table["code"] == "GBR"].iloc[0]
    assert gb["layers"] == "admin1, nation, region"
