#!/usr/bin/env python3
"""
Urban / suburban / exurban / rural classification, built only from what is
already in the lake (no downloads, no database):

  curated/reference/ruca/vintage=2020/level=tract   USDA ERS RUCA 2020 (commuting-based)
  curated/acs/vintage=<V>/table=b25003, b01003      households, population (ACS 5-year)
  curated/reference/gazetteer/layer=tracts          land area
  curated/reference/rel2020/pair=zcta520_tract20    ZCTA <-> tract overlap
  curated/boundaries TRACT / PLACE / COUNTY / CBSA  for the place and metro rollups

Writes:
  curated/derived/urbanicity/vintage=<V>/level=tract/part-0.parquet
      one row per tract: class, detail, ruca, households, population, densities
  curated/derived/urbanicity/vintage=<V>/level={county,cbsa,zcta,place}/part-0.parquet
      population mix: pop_urban/suburban/exurban/rural, share_*, plurality class

Tract rule (hh_density = ACS households per land sq mi; 2,213 and 102 are
Jed Kolko's urban/suburban/rural household-density cut points; RUCA 1-3 =
metropolitan, 2-3 = commuting-tied fringe outside the urban core):

  class     detail               rule
  urban     urban_core           RUCA 1-3 and hh_density >= 2,213
  suburban  suburban             RUCA 1   and 102 <= hh_density < 2,213
  exurban   exurban_commuter     RUCA 2-3 and hh_density < 2,213
  exurban   exurban_low_density  RUCA 1   and hh_density < 102
  exurban   exurban_metro_town   RUCA 4-6 in a county of a metropolitan CBSA
                                 (small cities inside a metro, e.g. Sonoma CA)
  rural     micropolitan         RUCA 4-6 elsewhere (towns of 10k-50k and their commuters)
  rural     small_town           RUCA 7-9
  rural     remote_rural         RUCA 10
  (none)    unpopulated          no households/population
  by density only (density_only) when a tract has no RUCA code

Rollups are population-weighted:
  county  tracts nest in counties (exact)
  cbsa    counties nest in CBSAs (exact; county point-on-surface in CBSA polygon)
  zcta    tract population split by the share of the tract's land in the ZCTA
          (Census 2020 relationship file; approximate inside split tracts)
  place   tract population split by the share of the tract's area inside the
          place polygon (approximate inside split tracts)

Usage:
  python urbanicity_to_lake.py                    # ACS 2024, all levels, publish
  python urbanicity_to_lake.py --out ./urb_test   # write locally only
"""

import argparse
import logging
import os
import sys
import tempfile
import time

import duckdb

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "warehouse"))
import lake_targets  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("urbanicity")

URBAN_HH_DENSITY = 2213
RURAL_HH_DENSITY = 102
CLASSES = ("urban", "suburban", "exurban", "rural")
LEVELS = ("tract", "county", "cbsa", "zcta", "place")


def connect(targets):
    con = duckdb.connect()
    for ext in ("httpfs", "spatial"):
        con.install_extension(ext)
        con.load_extension(ext)
    lake_targets.register_duckdb(con, targets)
    return con


def build_tracts(con, src, vintage, boundary_year):
    acs = f"{src}curated/acs/vintage={vintage}"
    b = f"{src}curated/boundaries"
    con.execute(f"""
    CREATE TEMP TABLE county_cbsa AS
    SELECT k.geoid AS county, c.geoid AS cbsa, c.boundary_subtype AS cbsa_type
    FROM (SELECT geoid, ST_PointOnSurface(geometry) pt FROM '{b}/boundary_type=COUNTY/year={boundary_year}/part-0.parquet') k
    JOIN (SELECT geoid, boundary_subtype, geometry FROM '{b}/boundary_type=CBSA/year={boundary_year}/part-0.parquet') c
      ON ST_Within(k.pt, c.geometry)""")
    con.execute(f"""
    CREATE TEMP TABLE ruca AS
    SELECT * EXCLUDE (rn) FROM (
      SELECT TractFIPS23 AS geoid, TractFIPS20 AS tract20, PrimaryRUCA AS ruca,
             SecondaryRUCA AS ruca_secondary, PrimaryRUCADescription AS ruca_desc,
             UrbanAreaCode20 AS urban_area_code, UrbanAreaName20 AS urban_area_name,
             row_number() OVER (PARTITION BY TractFIPS23 ORDER BY Population DESC) rn
      FROM '{src}curated/reference/ruca/vintage=2020/level=tract/part-0.parquet') WHERE rn = 1""")
    con.execute(f"""
    CREATE TEMP TABLE tract AS
    WITH pop AS (SELECT geoid, B01003_E001 AS population FROM '{acs}/table=b01003/part-0.parquet' WHERE sumlev = '140'),
         hh  AS (SELECT geoid, B25003_E001 AS households FROM '{acs}/table=b25003/part-0.parquet' WHERE sumlev = '140'),
         gz  AS (SELECT GEOID AS geoid, ALAND_SQMI AS land_sqmi
                 FROM '{src}curated/reference/gazetteer/layer=tracts/year={boundary_year}/part-0.parquet'),
         t AS (
           SELECT pop.geoid, r.tract20, r.ruca, r.ruca_secondary, r.ruca_desc, r.urban_area_code, r.urban_area_name,
                  greatest(pop.population, 0) AS population, greatest(hh.households, 0) AS households, gz.land_sqmi,
                  CASE WHEN gz.land_sqmi > 0 THEN greatest(hh.households, 0) / gz.land_sqmi END AS hh_density,
                  CASE WHEN gz.land_sqmi > 0 THEN greatest(pop.population, 0) / gz.land_sqmi END AS pop_density
           FROM pop LEFT JOIN hh USING (geoid) LEFT JOIN gz USING (geoid) LEFT JOIN ruca r USING (geoid))
    SELECT t.geoid, left(t.geoid, 2) AS state, left(t.geoid, 5) AS county, cc.cbsa, cc.cbsa_type, t.* EXCLUDE (geoid),
      CASE
        WHEN coalesce(households, 0) = 0 AND coalesce(population, 0) = 0 THEN 'unpopulated'
        WHEN ruca IS NULL OR ruca = 99 THEN
             CASE WHEN hh_density >= {URBAN_HH_DENSITY} THEN 'density_only_urban'
                  WHEN hh_density >= {RURAL_HH_DENSITY} THEN 'density_only_suburban'
                  ELSE 'density_only_rural' END
        WHEN ruca BETWEEN 1 AND 3 AND hh_density >= {URBAN_HH_DENSITY} THEN 'urban_core'
        WHEN ruca = 1 AND hh_density >= {RURAL_HH_DENSITY} THEN 'suburban'
        WHEN ruca IN (2, 3) THEN 'exurban_commuter'
        WHEN ruca = 1 THEN 'exurban_low_density'
        WHEN ruca BETWEEN 4 AND 6 AND cc.cbsa_type = 'metro_area' THEN 'exurban_metro_town'
        WHEN ruca BETWEEN 4 AND 6 THEN 'micropolitan'
        WHEN ruca BETWEEN 7 AND 9 THEN 'small_town'
        ELSE 'remote_rural' END AS detail
    FROM t LEFT JOIN county_cbsa cc ON cc.county = left(t.geoid, 5)""")
    con.execute("""
    ALTER TABLE tract ADD COLUMN class VARCHAR;
    UPDATE tract SET class = CASE
        WHEN detail = 'unpopulated' THEN NULL
        WHEN detail IN ('urban_core', 'density_only_urban') THEN 'urban'
        WHEN detail IN ('suburban', 'density_only_suburban') THEN 'suburban'
        WHEN detail LIKE 'exurban%' THEN 'exurban'
        ELSE 'rural' END""")
    n, nr, ng = con.execute("SELECT count(*), count(ruca), count(land_sqmi) FROM tract").fetchone()
    log.info("tracts: %d (with RUCA %d, with land area %d)", n, nr, ng)


def build_weights(con, src, boundary_year):
    """level, geoid, tract, w: the share of each tract's population credited to each area."""
    con.execute("CREATE TEMP TABLE w (level VARCHAR, geoid VARCHAR, tract VARCHAR, w DOUBLE, method VARCHAR)")
    con.execute("INSERT INTO w SELECT 'county', county, geoid, 1.0, 'nested' FROM tract")

    b = f"{src}curated/boundaries"
    con.execute("INSERT INTO w SELECT 'cbsa', cbsa, geoid, 1.0, 'nested' FROM tract WHERE cbsa IS NOT NULL")

    # ZCTA: Census relationship file is on 2020 tract codes; RUCA maps 2020 -> current (CT).
    con.execute(f"""
    INSERT INTO w
    SELECT 'zcta', r.GEOID_ZCTA5_20, t.geoid,
           r.AREALAND_PART::DOUBLE / sum(r.AREALAND_PART) OVER (PARTITION BY r.GEOID_TRACT_20), 'land_area_share'
    FROM '{src}curated/reference/rel2020/pair=zcta520_tract20/part-0.parquet' r
    JOIN tract t ON t.tract20 = r.GEOID_TRACT_20
    WHERE r.GEOID_ZCTA5_20 IS NOT NULL AND r.AREALAND_PART > 0""")

    log.info("place overlay (tract x place polygons)...")
    t0 = time.time()
    con.execute(f"""
    CREATE TEMP TABLE tg AS
    SELECT geoid, geometry, ST_Area(geometry) a FROM '{b}/boundary_type=TRACT/year={boundary_year}/part-0.parquet'
    WHERE geoid IN (SELECT geoid FROM tract)""")
    con.execute(f"""
    CREATE TEMP TABLE pg AS
    SELECT geoid, geometry FROM '{b}/boundary_type=PLACE/year={boundary_year}/part-0.parquet'""")
    con.execute("""
    INSERT INTO w
    SELECT 'place', p.geoid, t.geoid,
           CASE WHEN ST_Within(t.geometry, p.geometry) THEN 1.0
                ELSE ST_Area(ST_Intersection(t.geometry, p.geometry)) / nullif(t.a, 0) END, 'area_share'
    FROM tg t JOIN pg p ON ST_Intersects(t.geometry, p.geometry)""")
    con.execute("DELETE FROM w WHERE level = 'place' AND (w IS NULL OR w < 1e-4)")
    log.info("place overlay done in %.0fs; tracts with geometry: %d", time.time() - t0,
             con.execute("SELECT count(*) FROM tg").fetchone()[0])
    for lvl, n, k in con.execute("SELECT level, count(*), count(DISTINCT geoid) FROM w GROUP BY 1 ORDER BY 1").fetchall():
        log.info("  weights %-6s %7d rows, %6d areas", lvl, n, k)


def rollup_sql(level, vintage):
    pops = ",\n".join(f"  sum(CASE WHEN t.class = '{c}' THEN t.population * w.w ELSE 0 END) AS pop_{c}" for c in CLASSES)
    return f"""
    WITH agg AS (
      SELECT w.geoid, any_value(w.method) AS method,
             sum(t.population * w.w) AS population, sum(t.households * w.w) AS households,
             sum(t.land_sqmi * w.w) AS land_sqmi,
             {pops},
             count(*) AS tracts
      FROM w JOIN tract t ON t.geoid = w.tract
      WHERE w.level = '{level}'
      GROUP BY w.geoid)
    SELECT geoid, '{level}' AS level,
           round(population) AS population, round(households) AS households, land_sqmi,
           households / nullif(land_sqmi, 0) AS hh_density,
           {", ".join(f"round(pop_{c}) AS pop_{c}" for c in CLASSES)},
           {", ".join(f"pop_{c} / nullif({' + '.join('pop_' + k for k in CLASSES)}, 0) AS share_{c}" for c in CLASSES)},
           CASE greatest({", ".join('pop_' + c for c in CLASSES)})
             {" ".join(f"WHEN pop_{c} THEN '{c}'" for c in CLASSES)} END AS class,
           tracts, method, {vintage} AS vintage, 2020 AS ruca_vintage
    FROM agg ORDER BY geoid"""


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--vintage", type=int, default=2024, help="ACS 5-year release for population/households")
    ap.add_argument("--boundary-year", type=int, default=2025,
                    help="TIGER/Gazetteer year for tract land area and polygons (must be 2020-census tracts)")
    ap.add_argument("--levels", default=",".join(LEVELS))
    ap.add_argument("--staging", default=os.getenv("LAKE_STAGING") or tempfile.gettempdir())
    ap.add_argument("--out", help="write parquet under this local dir instead of publishing")
    a = ap.parse_args(argv)

    levels = [l.strip() for l in a.levels.split(",") if l.strip()]
    targets = lake_targets.load_targets()
    src = targets[0].url("")
    con = connect(targets)
    build_tracts(con, src, a.vintage, a.boundary_year)
    if any(l != "tract" for l in levels):
        build_weights(con, src, a.boundary_year)

    for cls, n, p in con.execute("""SELECT class, count(*), round(sum(population)) FROM tract
                                    GROUP BY 1 ORDER BY 3 DESC""").fetchall():
        log.info("  %-9s %6d tracts  %12s people", cls, n, f"{int(p or 0):,}")

    root = os.path.abspath(a.out) if a.out else os.path.join(a.staging, "urbanicity")
    for lvl in levels:
        key = f"curated/derived/urbanicity/vintage={a.vintage}/level={lvl}/part-0.parquet"
        local = os.path.join(root, key.replace("/", os.sep))
        os.makedirs(os.path.dirname(local), exist_ok=True)
        if lvl == "tract":
            sql = f"""SELECT geoid, tract20, state, county, cbsa, cbsa_type, class, detail, ruca, ruca_secondary, ruca_desc,
                             urban_area_code, urban_area_name, population, households, land_sqmi,
                             hh_density, pop_density, {a.vintage} AS vintage, 2020 AS ruca_vintage
                      FROM tract ORDER BY geoid"""
        else:
            sql = rollup_sql(lvl, a.vintage)
        con.execute(f"COPY ({sql}) TO '{local}' (FORMAT parquet, COMPRESSION zstd)")
        n = con.execute(f"SELECT count(*) FROM '{local}'").fetchone()[0]
        if a.out:
            log.info("wrote %s (%d rows)", local, n)
        else:
            lake_targets.publish(local, key, targets)
            os.remove(local)
            log.info("published %s (%d rows)", key, n)


if __name__ == "__main__":
    main()
