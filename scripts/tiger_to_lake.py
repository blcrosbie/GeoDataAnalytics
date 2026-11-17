#!/usr/bin/env python3
"""
Build TIGER/Line boundary GeoParquet straight from the Census zips into the
lake. No database: DuckDB (spatial + h3) reads the shapefiles through GDAL,
computes the spatial keys and writes one partition per (layer, year):

  curated/boundaries/boundary_type=<T>/year=<Y>/part-0.parquet

The schema matches what the retired Postgres exporter wrote, so readers (the
GeoAgent tile build, geo-llm-lab/evals) see no difference:

  geoid, year, name, boundary_type, boundary_subtype, country, source,
  accuracy_meters, validity_start_date, validity_end_date, last_updated,
  h3_r5, h3_r7 (of ST_PointOnSurface), xmin, ymin, xmax, ymax,
  geometry (WKB, OGC:CRS84)

Rows are sorted by h3_r5, geoid; invalid shapes are repaired with ST_MakeValid;
duplicate GEOIDs abort the build. Each partition is written once to local
staging and uploaded byte-for-byte to every lake target (warehouse/lake_targets.py).

Source zips, first hit wins:
  --root DIR          local tree laid out as DIR/<Y>/tl_<Y>_<us|SS>_<stem>.zip
  origin archive      origin/census/<Y>/ on ORIGIN_TARGET (default "wasabi")
  census.gov          https://www2.census.gov/geo/tiger/TIGER<Y>/<DIR>/ (directory listing)
With --archive-raw, zips fetched from census.gov are also copied to the origin archive.

Vintage-suffixed layers (zcta520, uac20, puma20, cd119) take the highest suffix
available and carry it in boundary_type (ZCTA520, UAC20, PUMA20, CD119).

Usage:
  python tiger_to_lake.py --year 2025 --layers zcta
  python tiger_to_lake.py --year 2020,2022,2023,2024,2025 --layers zcta --force
  python tiger_to_lake.py --year 2025 --layers sldu,sldl --dry-run
"""

import argparse
import logging
import os
import re
import shutil
import sys
import tempfile
import time

import duckdb
import requests

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "warehouse"))
import lake_targets  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("tiger")

UA = {"User-Agent": "GeoDataAnalytics-tiger-fetch/1.0"}
CENSUS = "https://www2.census.gov/geo/tiger/TIGER{y}/"
ACCURACY_M = 7.62  # TIGER/Line stated positional accuracy

# layer -> (file stem, national?, versioned?)
LAYERS = {
    "state":  ("state",  True,  False),
    "county": ("county", True,  False),
    "cousub": ("cousub", False, False),
    "tract":  ("tract",  False, False),
    "bg":     ("bg",     False, False),
    "place":  ("place",  False, False),
    "aiannh": ("aiannh", True,  False),
    "cbsa":   ("cbsa",   True,  False),
    "metdiv": ("metdiv", True,  False),
    "csa":    ("csa",    True,  False),
    "uac":    ("uac",    True,  True),
    "cd":     ("cd",     True,  True),
    "sldu":   ("sldu",   False, False),
    "sldl":   ("sldl",   False, False),
    "puma":   ("puma",   False, True),
    "zcta":   ("zcta5",  True,  True),
}


def pick(names: list[str], year: int, layer: str) -> tuple[list[str], str]:
    """From a list of zip basenames, the files for one layer and its boundary_type."""
    stem, national, versioned = LAYERS[layer]
    scope = r"us" if national else r"\d\d"
    suffix = r"(\d+)" if versioned else r"()"
    rx = re.compile(rf"^tl_{year}_({scope})_{stem}{suffix}\.zip$")
    hits = [(n, rx.match(n)) for n in names]
    hits = [(n, m) for n, m in hits if m]
    if not hits and national and versioned:  # cd119 also ships per state in some years
        return pick_states(names, year, layer)
    if not hits:
        return [], ""
    ver = max((m.group(2) for _, m in hits), key=lambda v: int(v or 0))
    files = sorted(n for n, m in hits if m.group(2) == ver)
    return files, (stem.upper() + ver) if versioned else layer.upper()


def pick_states(names, year, layer):
    stem = LAYERS[layer][0]
    rx = re.compile(rf"^tl_{year}_\d\d_{stem}(\d+)\.zip$")
    hits = [(n, rx.match(n)) for n in names if rx.match(n)]
    if not hits:
        return [], ""
    ver = max((m.group(1) for _, m in hits), key=int)
    return sorted(n for n, m in hits if m.group(1) == ver), stem.upper() + ver


class Source:
    """Finds and fetches raw zips: local root, then origin archive, then census.gov."""

    def __init__(self, root, origin, raw_dir, archive_raw):
        self.root, self.origin, self.raw, self.archive = root, origin, raw_dir, archive_raw
        self._census_dirs = {}

    def candidates(self, year):
        if self.root:
            d = os.path.join(self.root, str(year))
            if os.path.isdir(d):
                yield "local", {n: os.path.join(d, n) for n in os.listdir(d) if n.endswith(".zip")}
        if self.origin:
            keys = self.origin.list(f"origin/census/{year}/")
            yield "origin", {k.rsplit("/", 1)[-1]: k for k in keys if k.endswith(".zip")}
        yield "census", None  # resolved lazily per layer (one listing per directory)

    def census_listing(self, year, layer):
        stem = LAYERS[layer][0]
        base = CENSUS.format(y=year)
        if year not in self._census_dirs:
            r = requests.get(base, headers=UA, timeout=60)
            r.raise_for_status()
            self._census_dirs[year] = sorted(set(re.findall(r'href="([A-Z0-9_]+)/"', r.text)))
        out = {}
        for d in self._census_dirs[year]:
            if not d.lower().startswith(stem.lower()[:4]):
                continue
            r = requests.get(base + d + "/", headers=UA, timeout=60)
            if r.ok:
                for n in set(re.findall(r'href="(tl_[^"]+\.zip)"', r.text)):
                    out[n] = base + d + "/" + n
        return out

    def resolve(self, year, layer):
        for kind, listing in self.candidates(year):
            if kind == "census":
                listing = self.census_listing(year, layer)
            files, btype = pick(sorted(listing), year, layer)
            if files:
                return kind, [listing[f] for f in files], btype
        return None, [], ""

    def fetch(self, kind, ref):
        if kind == "local":
            return ref
        local = os.path.join(self.raw, os.path.basename(ref))
        if os.path.exists(local):
            return local
        os.makedirs(self.raw, exist_ok=True)
        if kind == "origin":
            self.origin.download(ref, local)
            return local
        for attempt in range(4):
            try:
                with requests.get(ref, headers=UA, stream=True, timeout=300) as r:
                    r.raise_for_status()
                    with open(local + ".tmp", "wb") as f:
                        shutil.copyfileobj(r.raw, f, 8 << 20)
                os.replace(local + ".tmp", local)
                break
            except requests.RequestException as e:
                if attempt == 3:
                    raise
                log.warning("retry %s (%s)", ref, e)
                time.sleep(10 * (attempt + 1))
        if self.archive and self.origin:
            year = re.search(r"tl_(\d{4})_", local).group(1)
            lake_targets.publish(local, f"origin/census/{year}/{os.path.basename(local)}", [self.origin])
        return local


def connect(targets):
    con = duckdb.connect()
    for ext in ("httpfs", "spatial"):
        con.install_extension(ext)
        con.load_extension(ext)
    con.execute("INSTALL h3 FROM community")
    con.execute("LOAD h3")
    con.execute("SET preserve_insertion_order = true")
    if targets:
        lake_targets.register_duckdb(con, targets)
    return con


def sql_str(v):
    return "'" + str(v).replace("'", "''") + "'"


def stage(con, zips):
    """All files of one layer into a temp table, columns normalized:
    vintage suffixes stripped (GEOID20 -> GEOID), upper-cased."""
    con.execute("DROP TABLE IF EXISTS _src")
    for i, z in enumerate(zips):
        path = "/vsizip/" + z.replace("\\", "/")
        cols = [r[0] for r in con.execute(f"DESCRIBE SELECT * FROM ST_Read({sql_str(path)})").fetchall()]
        up = {}
        for c in cols:
            if c == "geom":
                continue
            bare = re.sub(r"(10|20)$", "", c.upper())
            up.setdefault(c.upper(), c)
            up.setdefault(bare, c)
        geoid = next((up[f] for f in ("GEOID", "ZCTA5CE") if f in up), None)
        if geoid is None:
            sys.exit(f"{os.path.basename(z)}: no GEOID column in {cols}")
        pick_ = lambda n: f'"{up[n]}"::VARCHAR' if n in up else "NULL::VARCHAR"
        select = (f'SELECT trim("{geoid}") AS geoid, {pick_("NAME")} AS name, '
                  f'{pick_("NAMELSAD")} AS namelsad, geom FROM ST_Read({sql_str(path)})')
        con.execute(("CREATE TEMP TABLE _src AS " if i == 0 else "INSERT INTO _src ") + select)
    return con.execute("SELECT count(*) FROM _src").fetchone()[0]


def subtype_sql():
    # LSAD text as NAMELSAD minus NAME ("Nome Census Area" - "Nome" -> census_area),
    # matching the labels already in the lake ("city", "census_area", ...).
    return """CASE
      WHEN namelsad IS NULL OR name IS NULL OR namelsad = name THEN NULL
      WHEN starts_with(namelsad, name || ' ') THEN
        CASE lower(trim(substr(namelsad, length(name) + 2)))
          WHEN 'cdp' THEN 'census_designated_place'
          ELSE nullif(regexp_replace(lower(trim(substr(namelsad, length(name) + 2))), '[^a-z0-9]+', '_', 'g'), '')
        END
      END"""


def build(con, year, btype, out):
    dupes = con.execute("SELECT geoid FROM _src GROUP BY 1 HAVING count(*) > 1 LIMIT 5").fetchall()
    if dupes:
        sys.exit(f"{btype} {year}: duplicate GEOIDs in source: {[d[0] for d in dupes]}")
    con.execute(f"""
    COPY (
      WITH g AS (
        SELECT geoid, name, namelsad,
               CASE WHEN ST_IsValid(geom) THEN geom ELSE ST_MakeValid(geom) END AS geom
        FROM _src
      ), p AS (
        SELECT *, CASE WHEN geom IS NULL OR ST_IsEmpty(geom) THEN NULL ELSE ST_PointOnSurface(geom) END AS pt
        FROM g
      )
      SELECT geoid,
             {int(year)}::BIGINT AS year,
             -- no NAME field: BG keeps the Postgres-era '' (2011-2025 partitions);
             -- SLDU/SLDL use NAMELSAD ("State Senate District 38"); others the GEOID
             coalesce(name, {"''" if btype == "BG" else "namelsad, geoid" if btype in ("SLDU", "SLDL") else "geoid"}) AS name,
             {sql_str(btype)} AS boundary_type,
             {subtype_sql()} AS boundary_subtype,
             'US' AS country,
             {sql_str(f"Census TIGER/Line {year}")} AS source,
             {ACCURACY_M}::DOUBLE AS accuracy_meters,
             DATE '{int(year)}-01-01' AS validity_start_date,
             DATE '{int(year)}-12-31' AS validity_end_date,
             now() AS last_updated,
             h3_latlng_to_cell_string(ST_Y(pt), ST_X(pt), 5) AS h3_r5,
             h3_latlng_to_cell_string(ST_Y(pt), ST_X(pt), 7) AS h3_r7,
             ST_XMin(geom) AS xmin, ST_YMin(geom) AS ymin,
             ST_XMax(geom) AS xmax, ST_YMax(geom) AS ymax,
             ST_SetCRS(geom, 'OGC:CRS84') AS geometry
      FROM p
      ORDER BY h3_r5, geoid
    ) TO {sql_str(out)} (FORMAT parquet, COMPRESSION zstd, ROW_GROUP_SIZE 50000)""")
    return con.execute("SELECT count(*) FROM read_parquet(?)", [out]).fetchone()[0]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--year", required=True, help="one year or a comma list")
    ap.add_argument("--layers", required=True, help=f"comma list of {','.join(LAYERS)}")
    ap.add_argument("--root", help="local TIGER tree (<root>/<Y>/tl_*.zip), tried first")
    ap.add_argument("--staging", default=os.getenv("LAKE_STAGING") or tempfile.gettempdir())
    ap.add_argument("--force", action="store_true", help="rebuild even if the partition is on every target")
    ap.add_argument("--archive-raw", action="store_true", help="copy zips fetched from census.gov to the origin archive")
    ap.add_argument("--keep-raw", action="store_true", help="keep downloaded zips in staging")
    ap.add_argument("--dry-run", action="store_true", help="resolve sources and keys, write nothing")
    ap.add_argument("--out", help="write the parquet here and stop (no upload); for testing")
    a = ap.parse_args(argv)

    layers = [s.strip() for s in a.layers.split(",") if s.strip()]
    unknown = set(layers) - set(LAYERS)
    if unknown:
        ap.error(f"unknown layer(s) {sorted(unknown)}; choose from {','.join(LAYERS)}")
    years = [int(y) for y in a.year.split(",")]

    local_only = bool(a.out)
    targets = [] if local_only else lake_targets.load_targets()
    origin_name = os.getenv("ORIGIN_TARGET", "wasabi")
    origin = None
    if os.getenv(f"LAKE_{origin_name.upper()}_BUCKET"):
        origin = lake_targets.load_targets(origin_name)[0]
    staging = os.path.join(a.staging, "tiger")
    src = Source(a.root, origin, os.path.join(staging, "raw"), a.archive_raw)
    con = connect(targets)

    for year in years:
        for layer in layers:
            kind, refs, btype = src.resolve(year, layer)
            if not refs:
                log.warning("%s %s: no source zips found, skipped", layer, year)
                continue
            key = f"curated/boundaries/boundary_type={btype}/year={year}/part-0.parquet"
            if targets and not a.force and all(t.head(key) for t in targets):
                log.info("skip %s (on all targets; --force to rebuild)", key)
                continue
            log.info("%s %s: %d file(s) from %s -> %s", btype, year, len(refs), kind, key)
            if a.dry_run:
                continue
            t0 = time.time()
            zips = [src.fetch(kind, r) for r in refs]
            n_src = stage(con, zips)
            out = os.path.abspath(a.out) if a.out else os.path.join(staging, "lake", key.replace("/", os.sep))
            os.makedirs(os.path.dirname(out), exist_ok=True)
            n = build(con, year, btype, out + ".tmp")
            os.replace(out + ".tmp", out)
            if n != n_src:
                sys.exit(f"{key}: wrote {n} rows, source has {n_src}")
            if local_only:
                log.info("wrote %s rows=%d in %.0fs (local only)", out, n, time.time() - t0)
                return
            lake_targets.publish(out, key, targets)
            os.remove(out)
            if not a.keep_raw and kind != "local":
                for z in zips:
                    os.remove(z)
            log.info("published %s rows=%d to %s in %.0fs", key, n,
                     ",".join(t.name for t in targets), time.time() - t0)


if __name__ == "__main__":
    main()
