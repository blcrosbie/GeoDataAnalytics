#!/usr/bin/env python3
"""
RETIRED (2026-11-13): the Postgres warehouse is gone. Build boundary
partitions straight into the lake with ../../scripts/tiger_to_lake.py, which
uses the same layer table and GEOID20 handling. Kept for reference.

Load TIGER/Line boundaries for one vintage into public.geographic_boundaries,
one (year, summary_level) at a time.

Each layer is replaced wholesale inside one transaction (delete that year+level,
COPY the fresh shapes), so a rerun is idempotent and a killed run leaves the
previous rows in place.

Memory: files are read one at a time, in CHUNK-feature slices, and each slice is
COPYed into a server-side temp table before the next is read, so RAM holds one
slice of one state, never a whole national layer. Keys are (summary_level, geoid, year), so county 01001
and SLDU 01001 no longer overwrite each other.

Source zips are read in place from the Wasabi mount (or any directory laid out
as <root>/<year>/tl_<year>_<st|us>_<layer>.zip) via GDAL /vsizip/.

Env:   WAREHOUSE_DSN   libpq DSN, e.g. "host=localhost port=5434 dbname=geodata user=geoadmin"
Usage: python load_tiger_boundaries.py --year 2025 [--layers zcta,place,uac]
       python load_tiger_boundaries.py --year 2025 --list      # what's on disk for that vintage

Vintage-suffixed layers (ZCTA520, UAC20, PUMA20, CD119) take the highest suffix
present and carry it in boundary_type, and their columns (GEOID20, NAME20,
ALAND20, ...) are read with the suffix stripped. Before this, ZCTA files (no
plain GEOID column) collapsed onto one empty-geoid row.
"""

import argparse
import glob
import io
import logging
import os
import re
import sys
import time
from collections.abc import Iterator

import geopandas as gpd
import pandas as pd
import psycopg2
import pyogrio

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("tiger")

DEFAULT_ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "data",
                            "geoagent-dev-s3", "origin", "census")

# layer -> (summary_level, file stem, national?, versioned?)
#   national:  tl_<Y>_us_<stem>.zip            per-state: tl_<Y>_<SS>_<stem>.zip
#   versioned: stem is followed by a vintage suffix (cd119, zcta520, uac20, puma20);
#              the highest one present wins and becomes part of boundary_type.
LAYERS = {
    "state":  ("040", "state",  True,  False),
    "county": ("050", "county", True,  False),
    "cousub": ("060", "cousub", False, False),
    "tract":  ("140", "tract",  False, False),
    "bg":     ("150", "bg",     False, False),
    "place":  ("160", "place",  False, False),
    "aiannh": ("250", "aiannh", True,  False),
    "cbsa":   ("310", "cbsa",   True,  False),
    "metdiv": ("314", "metdiv", True,  False),
    "csa":    ("330", "csa",    True,  False),
    "uac":    ("400", "uac",    True,  True),
    "cd":     ("500", "cd",     False, True),
    "sldu":   ("610", "sldu",   False, False),
    "sldl":   ("620", "sldl",   False, False),
    "puma":   ("795", "puma",   False, True),
    "zcta":   ("860", "zcta5",  True,  True),
}

# TIGER ID column, after stripping a vintage suffix (GEOID20 -> GEOID).
GEOID_FIELDS = ("GEOID", "GEOIDFQ", "ZCTA5CE")

CHUNK = 5_000  # features per read; bounds RAM to one slice of one file

COLS = ("geoid", "year", "name", "geom", "boundary_type", "country", "summary_level",
        "source", "validity_start_date", "aland", "awater", "internal_point",
        "mtfcc", "funcstat")


def layer_files(root: str, year: int, layer: str) -> tuple[list[str], str]:
    """Return the zips for a layer and its boundary_type label."""
    _lvl, stem, national, versioned = LAYERS[layer]
    ydir = os.path.join(root, str(year))
    if not versioned:
        pattern = f"tl_{year}_us_{stem}.zip" if national else f"tl_{year}_[0-9][0-9]_{stem}.zip"
        return sorted(glob.glob(os.path.join(ydir, pattern))), layer.upper()
    # Per-state files first (cd), else national (zcta520, uac20); highest vintage wins.
    per_state = glob.glob(os.path.join(ydir, f"tl_{year}_[0-9][0-9]_{stem}[0-9]*.zip"))
    files = per_state or glob.glob(os.path.join(ydir, f"tl_{year}_us_{stem}[0-9]*.zip"))
    if not files:
        return [], ""
    rx = re.compile(rf"_{stem}(\d+)\.zip$")
    files = [f for f in files if rx.search(f)]
    if not files:
        return [], ""
    ver = max((rx.search(f).group(1) for f in files), key=int)
    files = [f for f in files if rx.search(f).group(1) == ver]
    return sorted(files), f"{stem.upper()}{ver}"


def iter_chunks(files: list[str]) -> Iterator[gpd.GeoDataFrame]:
    """Yield each file in CHUNK-feature slices, one slice in memory at a time."""
    for f in files:
        path = f"/vsizip/{f}"
        n = pyogrio.read_info(path)["features"]
        for skip in range(0, n, CHUNK):
            yield gpd.read_file(path, engine="pyogrio", skip_features=skip, max_features=CHUNK)


def column_map(columns) -> dict[str, str]:
    """UPPER name -> real column, plus each vintage-suffixed column under its
    bare name (GEOID20 -> GEOID, ALAND20 -> ALAND) unless the bare one exists."""
    up = {c.upper(): c for c in columns}
    for c in columns:
        bare = re.sub(r"(10|20)$", "", c.upper())
        if bare != c.upper():
            up.setdefault(bare, c)
    return up


def to_rows(g: gpd.GeoDataFrame, year: int, lvl: str, btype: str, source: str) -> pd.DataFrame:
    g = g.to_crs(4326)
    up = column_map(g.columns)
    col = lambda name: g[up[name]] if name in up else None
    geoid = next((col(f) for f in GEOID_FIELDS if f in up), None)
    if geoid is None:
        raise SystemExit(f"{btype} {year}: no GEOID column in {list(g.columns)}")
    name = col("NAMELSAD") if "NAMELSAD" in up else col("NAME")
    lat = pd.to_numeric(col("INTPTLAT"), errors="coerce") if "INTPTLAT" in up else None
    lon = pd.to_numeric(col("INTPTLON"), errors="coerce") if "INTPTLON" in up else None
    ipt = (gpd.GeoSeries(gpd.points_from_xy(lon, lat), crs=4326).to_wkb(hex=True)
           if lat is not None else None)
    return pd.DataFrame({
        "geoid": geoid.astype(str).str.strip(),
        "year": year,
        "name": (name if name is not None else geoid).fillna("").astype(str).str.slice(0, 255),
        "geom": g.geometry.to_wkb(hex=True),
        "boundary_type": btype,
        "country": "USA",
        "summary_level": lvl,
        "source": source,
        "validity_start_date": f"{year}-01-01",
        "aland": col("ALAND").astype("Int64") if "ALAND" in up else None,
        "awater": col("AWATER").astype("Int64") if "AWATER" in up else None,
        "internal_point": ipt,
        "mtfcc": col("MTFCC"),
        "funcstat": col("FUNCSTAT"),
    })


def load(conn, chunks: Iterator[pd.DataFrame], year: int, lvl: str, btype: str) -> int:
    with conn.cursor() as cur:
        cur.execute("CREATE TEMP TABLE _b (LIKE public.geographic_boundaries INCLUDING DEFAULTS) "
                    "ON COMMIT DROP")
        for df in chunks:
            buf = io.StringIO()
            df.to_csv(buf, sep="\t", header=False, index=False, na_rep="\\N")
            buf.seek(0)
            cur.copy_expert(f"COPY _b ({', '.join(COLS)}) FROM STDIN WITH (FORMAT text)", buf)
            del buf, df
        # Duplicates can span files (states), so check after all slices are in.
        cur.execute("SELECT geoid FROM _b GROUP BY geoid HAVING count(*) > 1 LIMIT 5")
        dupes = [r[0] for r in cur.fetchall()]
        if dupes:
            conn.rollback()
            raise SystemExit(f"level {lvl} {year}: duplicate GEOIDs in source: {dupes}")
        cur.execute("UPDATE _b SET geom = ST_Multi(ST_MakeValid(geom)) WHERE NOT ST_IsValid(geom)")
        # Also clear rows of this layer filed under another summary_level by the
        # legacy import (e.g. PLACE), or the new rows would sit beside them.
        cur.execute("DELETE FROM public.geographic_boundaries "
                    "WHERE year = %s AND (summary_level = %s OR boundary_type = %s)",
                    (year, lvl, btype))
        cur.execute(f"INSERT INTO public.geographic_boundaries ({', '.join(COLS)}) "
                    f"SELECT {', '.join(COLS)} FROM _b")
        n = cur.rowcount
    conn.commit()
    return n


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--year", type=int, required=True)
    p.add_argument("--layers", default=",".join(LAYERS))
    p.add_argument("--root", default=DEFAULT_ROOT)
    p.add_argument("--list", action="store_true", help="show the files each layer would load, then exit")
    args = p.parse_args(argv)
    unknown = set(args.layers.split(",")) - set(LAYERS)
    if unknown:
        p.error(f"unknown layer(s) {sorted(unknown)}; choose from {','.join(LAYERS)}")

    if args.list:
        for layer in args.layers.split(","):
            files, btype = layer_files(args.root, args.year, layer)
            print(f"{layer:7} {LAYERS[layer][0]} {btype or '-':8} {len(files):3} file(s)"
                  + (f"  e.g. {os.path.basename(files[0])}" if files else ""))
        return

    dsn = os.environ.get("WAREHOUSE_DSN") or sys.exit("set WAREHOUSE_DSN")
    conn = psycopg2.connect(dsn)
    for layer in args.layers.split(","):
        lvl = LAYERS[layer][0]
        files, btype = layer_files(args.root, args.year, layer)
        if not files:
            log.warning("%s %s: no files under %s, skipped", layer, args.year, args.root)
            continue
        t = time.time()
        src = f"Census TIGER/Line {args.year}"
        rows = (to_rows(g, args.year, lvl, btype, src) for g in iter_chunks(files))
        n = load(conn, rows, args.year, lvl, btype)
        log.info("%s %s (%s, %d files): %d shapes in %.0fs",
                 btype, args.year, lvl, len(files), n, time.time() - t)
    conn.close()


if __name__ == "__main__":
    main()
