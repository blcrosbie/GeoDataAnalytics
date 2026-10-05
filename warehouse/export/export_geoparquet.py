#!/usr/bin/env python3
"""
Export the public warehouse tables from Postgres to GeoParquet in S3 (Wasabi).

Layout (hive-partitioned so DuckDB/pg_duckdb/Sedona prune by path):

  s3://<bucket>/curated/boundaries/boundary_type=<T>/year=<Y>/part-0.parquet
  s3://<bucket>/curated/attributes/boundary_type=<T>/year=<Y>/part-0.parquet

Boundaries carry scalar spatial keys (h3_r5, h3_r7 of the point-on-surface,
plus bbox xmin/ymin/xmax/ymax) so readers can filter on plain columns before
touching geometry. Rows are sorted by h3_r5 so Parquet row-group stats prune.

Only public reference data is exported. App-side columns (layer_id,
source_upload_id) are dropped.

Env:
  SOURCE_PG_DSN   libpq DSN of the source DB (read-only use)
  LAKE_S3_KEY_ID / LAKE_S3_SECRET / LAKE_S3_REGION / LAKE_S3_ENDPOINT / LAKE_BUCKET

Usage:
  python export_geoparquet.py boundaries [--type BG] [--year 2020] [--force]
  python export_geoparquet.py attributes [--type BG] [--year 2020] [--force]
  python export_geoparquet.py verify
"""

import argparse
import json
import logging
import os
import sys
import time

import duckdb

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("export")

PREFIX = "curated"

BOUNDARY_SQL = """
SELECT geoid, year, name, boundary_type, boundary_subtype, country, source,
       accuracy_meters::float8 AS accuracy_meters,
       validity_start_date, validity_end_date, last_updated,
       h3_lat_lng_to_cell(p::point, 5)::text AS h3_r5,
       h3_lat_lng_to_cell(p::point, 7)::text AS h3_r7,
       ST_XMin(geom) AS xmin, ST_YMin(geom) AS ymin,
       ST_XMax(geom) AS xmax, ST_YMax(geom) AS ymax,
       ST_AsBinary(geom) AS wkb
FROM (
    SELECT b.*, CASE WHEN geom IS NULL OR ST_IsEmpty(geom) THEN NULL
                     ELSE ST_PointOnSurface(ST_MakeValid(geom)) END AS p
    FROM public.geographic_boundaries b
    WHERE boundary_type = '{t}' AND year = {y}
) s
ORDER BY h3_r5, geoid
"""

ATTRIBUTE_SQL = """
SELECT d.geoid, d.year, b.boundary_type, d.attribute_key, d.attribute_value,
       d.numeric_value, d.data_type, d.source, d.collection_date, d.confidence_level
FROM public.geographic_data d
JOIN public.geographic_boundaries b USING (geoid, year)
WHERE b.boundary_type = '{t}' AND d.year = {y}
ORDER BY d.geoid, d.attribute_key
"""


def env(name, default=None):
    v = os.getenv(name, default)
    if v is None:
        sys.exit(f"missing env var {name}")
    return v


def connect():
    con = duckdb.connect()
    for ext in ("httpfs", "spatial", "postgres"):
        con.install_extension(ext)
        con.load_extension(ext)
    con.execute("SET preserve_insertion_order = true")
    con.execute(
        "CREATE SECRET lake (TYPE s3, KEY_ID ?, SECRET ?, REGION ?, ENDPOINT ?, URL_STYLE 'path')",
        [env("LAKE_S3_KEY_ID"), env("LAKE_S3_SECRET"),
         env("LAKE_S3_REGION", "us-east-1"), env("LAKE_S3_ENDPOINT", "s3.us-east-1.wasabisys.com")],
    )
    dsn = env("SOURCE_PG_DSN")
    if "options=" not in dsn:
        # Session-only: some postgis images ship a JIT built against a newer LLVM
        # than they load, and the first query expensive enough to JIT kills the
        # backend ("SSL connection has been closed unexpectedly").
        dsn += " options=-cjit=off"
    try:
        con.execute(f"ATTACH '{dsn.replace(chr(39), chr(39) * 2)}' AS pg (TYPE postgres, READ_ONLY)")
    except duckdb.Error as e:
        # DuckDB errors echo the statement, i.e. the DSN and its password.
        sys.exit(f"could not attach source DB ({type(e).__name__}); check SOURCE_PG_DSN")
    return con


def pg_scalar(con, sql):
    return con.execute("SELECT * FROM postgres_query('pg', ?)", [sql]).fetchone()


def partitions(con, t=None, y=None):
    where = []
    if t:
        where.append(f"boundary_type = '{t}'")
    if y:
        where.append(f"year = {int(y)}")
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    rows = con.execute(
        "SELECT * FROM postgres_query('pg', ?)",
        [f"SELECT boundary_type, year, count(*)::bigint FROM public.geographic_boundaries "
         f"{clause} GROUP BY 1, 2 ORDER BY 3"],
    ).fetchall()
    return rows


def target(bucket, table, t, y):
    return f"s3://{bucket}/{PREFIX}/{table}/boundary_type={t}/year={y}/part-0.parquet"


def exists(con, path):
    # glob() echoes a literal (non-wildcard) path back even when it's missing,
    # so list the partition directory with a wildcard instead.
    pattern = path.rsplit("/", 1)[0] + "/*.parquet"
    try:
        return con.execute("SELECT count(*) FROM glob(?)", [pattern]).fetchone()[0] > 0
    except duckdb.Error:
        return False


def export(con, table, t=None, y=None, force=False):
    bucket = env("LAKE_BUCKET")
    manifest = {}
    for bt, yr, _n in partitions(con, t, y):
        path = target(bucket, table, bt, yr)
        if not force and exists(con, path):
            log.info("skip %s (exists)", path)
            continue
        started = time.time()
        if table == "boundaries":
            src = BOUNDARY_SQL.format(t=bt, y=yr)
            select = ("SELECT * EXCLUDE (wkb), ST_GeomFromWKB(wkb) AS geometry "
                      "FROM postgres_query('pg', ?)")
        else:
            src = ATTRIBUTE_SQL.format(t=bt, y=yr)
            select = "SELECT * FROM postgres_query('pg', ?)"
        con.execute(
            f"COPY ({select}) TO '{path}' (FORMAT parquet, COMPRESSION zstd, ROW_GROUP_SIZE 50000)",
            [src],
        )
        n = con.execute("SELECT count(*) FROM read_parquet(?)", [path]).fetchone()[0]
        manifest[f"{bt}/{yr}"] = n
        log.info("wrote %s rows=%d in %.1fs", path, n, time.time() - started)
    return manifest


def verify(con):
    """Compare Parquet row counts to the source, per partition."""
    bucket = env("LAKE_BUCKET")
    bad = 0
    for table, count_sql in (
        ("boundaries", "SELECT boundary_type, year, count(*)::bigint FROM public.geographic_boundaries GROUP BY 1,2"),
        ("attributes", "SELECT b.boundary_type, d.year, count(*)::bigint FROM public.geographic_data d "
                       "JOIN public.geographic_boundaries b USING (geoid, year) GROUP BY 1,2"),
    ):
        src = {(r[0], r[1]): r[2] for r in con.execute("SELECT * FROM postgres_query('pg', ?)", [count_sql]).fetchall()}
        lake = {
            (r[0], int(r[1])): r[2]
            for r in con.execute(
                f"SELECT boundary_type, year, count(*) FROM read_parquet('s3://{bucket}/{PREFIX}/{table}/*/*/*.parquet', "
                f"hive_partitioning = true) GROUP BY 1, 2"
            ).fetchall()
        }
        for k, n in sorted(src.items()):
            if lake.get(k) != n:
                bad += 1
                log.warning("%s %s: source=%s lake=%s", table, k, n, lake.get(k))
        log.info("%s: %d partitions, source rows=%d, lake rows=%d",
                 table, len(src), sum(src.values()), sum(lake.values()))
    if bad:
        sys.exit(f"{bad} partition(s) mismatched")
    log.info("verify OK")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("table", choices=["boundaries", "attributes", "verify"])
    ap.add_argument("--type", dest="btype")
    ap.add_argument("--year", type=int)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()

    con = connect()
    if a.table == "verify":
        verify(con)
        return
    manifest = export(con, a.table, a.btype, a.year, a.force)
    if manifest:
        log.info("exported %d partitions, %d rows", len(manifest), sum(manifest.values()))


if __name__ == "__main__":
    main()
