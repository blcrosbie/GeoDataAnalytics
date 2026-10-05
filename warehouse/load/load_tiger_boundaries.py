#!/usr/bin/env python3
"""
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
Usage: python load_tiger_boundaries.py --year 2024 [--layers state,county,tract,bg,cbsa,cd,sldu,sldl]
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

# layer -> (summary_level, file glob suffix, national?)
LAYERS = {
    "state":  ("040", "us_state", True),
    "county": ("050", "us_county", True),
    "cbsa":   ("310", "us_cbsa", True),
    "tract":  ("140", "tract", False),
    "bg":     ("150", "bg", False),
    "cd":     ("500", "cd", False),
    "sldu":   ("610", "sldu", False),
    "sldl":   ("620", "sldl", False),
}

CHUNK = 5_000  # features per read; bounds RAM to one slice of one file

COLS = ("geoid", "year", "name", "geom", "boundary_type", "country", "summary_level",
        "source", "validity_start_date", "aland", "awater", "internal_point",
        "mtfcc", "funcstat")


def layer_files(root: str, year: int, layer: str) -> tuple[list[str], str]:
    """Return the zips for a layer and its boundary_type label."""
    lvl, suffix, national = LAYERS[layer]
    ydir = os.path.join(root, str(year))
    if layer == "cd":
        # Per-state files carry the current congress (cd118, cd119); fall back
        # to a national file. Pick the highest congress number present.
        per_state = glob.glob(os.path.join(ydir, f"tl_{year}_[0-9][0-9]_cd[0-9]*.zip"))
        files = per_state or glob.glob(os.path.join(ydir, f"tl_{year}_us_cd[0-9]*.zip"))
        if not files:
            return [], ""
        congress = max(re.search(r"_cd(\d+)\.zip$", f).group(1) for f in files)
        files = [f for f in files if f.endswith(f"_cd{congress}.zip")]
        return sorted(files), f"CD{congress}"
    pattern = f"tl_{year}_{suffix}.zip" if national else f"tl_{year}_[0-9][0-9]_{suffix}.zip"
    return sorted(glob.glob(os.path.join(ydir, pattern))), layer.upper()


def iter_chunks(files: list[str]) -> Iterator[gpd.GeoDataFrame]:
    """Yield each file in CHUNK-feature slices, one slice in memory at a time."""
    for f in files:
        path = f"/vsizip/{f}"
        n = pyogrio.read_info(path)["features"]
        for skip in range(0, n, CHUNK):
            yield gpd.read_file(path, engine="pyogrio", skip_features=skip, max_features=CHUNK)


def to_rows(g: gpd.GeoDataFrame, year: int, lvl: str, btype: str, source: str) -> pd.DataFrame:
    g = g.to_crs(4326)
    up = {c.upper(): c for c in g.columns}
    col = lambda name: g[up[name]] if name in up else None
    geoid = col("GEOID")
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


def load(conn, chunks: Iterator[pd.DataFrame], year: int, lvl: str) -> int:
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
        cur.execute("DELETE FROM public.geographic_boundaries WHERE year = %s AND summary_level = %s",
                    (year, lvl))
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
    args = p.parse_args(argv)

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
        n = load(conn, rows, args.year, lvl)
        log.info("%s %s (%s, %d files): %d shapes in %.0fs",
                 btype, args.year, lvl, len(files), n, time.time() - t)
    conn.close()


if __name__ == "__main__":
    main()
