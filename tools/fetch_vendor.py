"""Download third-party files at pinned versions and record their SHA-256.

Usage:
    python tools/fetch_vendor.py           # download missing files, verify existing ones
    python tools/fetch_vendor.py --update  # re-download everything and rewrite the lock

The lock file (tools/vendor.lock.json) is committed. A later run fails if a file's
hash no longer matches the lock, so a changed upstream file is never picked up silently.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCK = ROOT / "tools" / "vendor.lock.json"

ECHARTS = "6.1.0"
TOPOJSON_CLIENT = "3.1.0"
NATURAL_EARTH = "v5.1.2"

_NE = f"https://raw.githubusercontent.com/nvkelso/natural-earth-vector/{NATURAL_EARTH}/geojson"
_JSD = "https://cdn.jsdelivr.net/npm"

# (destination relative to repo root, source URL)
FILES: list[tuple[str, str]] = [
    ("src/tabsight/render/static/echarts.min.js", f"{_JSD}/echarts@{ECHARTS}/dist/echarts.min.js"),
    ("licenses/echarts-LICENSE.txt", f"{_JSD}/echarts@{ECHARTS}/LICENSE"),
    ("licenses/echarts-NOTICE.txt", f"{_JSD}/echarts@{ECHARTS}/NOTICE"),
    (
        "src/tabsight/render/static/topojson-client.min.js",
        f"{_JSD}/topojson-client@{TOPOJSON_CLIENT}/dist/topojson-client.min.js",
    ),
    ("licenses/topojson-client-LICENSE.txt", f"{_JSD}/topojson-client@{TOPOJSON_CLIENT}/LICENSE"),
    # Raw map data (not committed, not shipped; turned into TopoJSON in Phase 5).
    (
        "data-raw/naturalearth/ne_110m_admin_0_countries.geojson",
        f"{_NE}/ne_110m_admin_0_countries.geojson",
    ),
    (
        "data-raw/naturalearth/ne_50m_admin_0_countries.geojson",
        f"{_NE}/ne_50m_admin_0_countries.geojson",
    ),
    (
        "data-raw/naturalearth/ne_10m_admin_1_states_provinces.geojson",
        f"{_NE}/ne_10m_admin_1_states_provinces.geojson",
    ),
    (
        "data-raw/naturalearth/ne_10m_populated_places_simple.geojson",
        f"{_NE}/ne_10m_populated_places_simple.geojson",
    ),
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "tabsight-fetch-vendor"})
    with urllib.request.urlopen(req, timeout=120) as resp, tmp.open("wb") as out:
        while chunk := resp.read(1 << 20):
            out.write(chunk)
    tmp.replace(dest)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--update", action="store_true", help="re-download and rewrite the lock")
    args = parser.parse_args()

    lock: dict[str, dict[str, str | int]] = (
        json.loads(LOCK.read_text(encoding="utf-8")) if LOCK.exists() and not args.update else {}
    )
    failed = False
    for rel, url in FILES:
        dest = ROOT / rel
        if args.update or not dest.exists():
            print(f"download  {rel}")
            download(url, dest)
        digest = sha256(dest)
        known = lock.get(rel)
        if known and (known["sha256"] != digest or known["url"] != url):
            print(f"MISMATCH  {rel}: lock says {known['sha256'][:12]}, file is {digest[:12]}")
            failed = True
            continue
        lock[rel] = {"url": url, "sha256": digest, "bytes": dest.stat().st_size}
        print(f"ok        {rel}  {dest.stat().st_size:,} bytes  {digest[:12]}")

    LOCK.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
