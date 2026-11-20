#!/usr/bin/env python3
"""
The Postgres source was retired on 2026-11-13, so `boundaries`, `attributes`
and `verify` no longer have anything to read; new boundary partitions come
from ../../scripts/tiger_to_lake.py. The `sync` command (AWS -> Wasabi mirror)
was removed with the Wasabi bucket on 2026-11-19. Kept for reference only.

Export the public warehouse tables from Postgres to GeoParquet in the lake
(AWS S3, see ../lake_targets.py).

Layout (hive-partitioned so DuckDB/pg_duckdb/Sedona prune by path):

  s3://<bucket>/curated/boundaries/boundary_type=<T>/year=<Y>/part-0.parquet
  s3://<bucket>/curated/attributes/boundary_type=<T>/year=<Y>/part-0.parquet

Boundaries carry scalar spatial keys (h3_r5, h3_r7 of the point-on-surface,
plus bbox xmin/ymin/xmax/ymax) so readers can filter on plain columns before
touching geometry. Rows are sorted by h3_r5 so Parquet row-group stats prune.

Each partition is written once to local staging, row-counted, then uploaded
to the lake. Only public reference data is exported. App-side columns
(layer_id, source_upload_id) are dropped.

Env:
  SOURCE_PG_DSN   libpq DSN of the source DB (read-only use)
  LAKE_TARGETS + LAKE_<NAME>_*   (see ../lake_targets.py)
  LAKE_STAGING    local scratch dir (default: system temp); needs ~1 GB free

Usage:
  python export_geoparquet.py boundaries [--type ZCTA520] [--year 2025] [--force]
  python export_geoparquet.py attributes [--type BG] [--year 2020] [--force]
  python export_geoparquet.py verify                    # source vs lake row counts
"""

import argparse
import logging
import os
import sys
import tempfile
import time

import duckdb

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import lake_targets  # noqa: E402

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
JOIN public.geographic_boundaries b USING (summary_level, geoid, year)
WHERE b.boundary_type = '{t}' AND d.year = {y}
ORDER BY d.geoid, d.attribute_key
"""


def env(name, default=None):
    v = os.getenv(name, default)
    if v is None:
        sys.exit(f"missing env var {name}")
    return v


def connect(targets, with_pg=True):
    con = duckdb.connect()
    for ext in ("httpfs", "spatial") + (("postgres",) if with_pg else ()):
        con.install_extension(ext)
        con.load_extension(ext)
    con.execute("SET preserve_insertion_order = true")
    lake_targets.register_duckdb(con, targets)
    if not with_pg:
        return con
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


def partitions(con, t=None, y=None):
    where = []
    if t:
        where.append(f"boundary_type = '{t}'")
    if y:
        where.append(f"year = {int(y)}")
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    return con.execute(
        "SELECT * FROM postgres_query('pg', ?)",
        [f"SELECT boundary_type, year, count(*)::bigint FROM public.geographic_boundaries "
         f"{clause} GROUP BY 1, 2 ORDER BY 3"],
    ).fetchall()


def key_for(table, t, y):
    return f"{PREFIX}/{table}/boundary_type={t}/year={y}/part-0.parquet"


def export(con, targets, table, t=None, y=None, force=False):
    staging = os.getenv("LAKE_STAGING") or tempfile.gettempdir()
    primary, mirrors = targets[0], targets[1:]
    manifest = {}
    for bt, yr, src_n in partitions(con, t, y):
        key = key_for(table, bt, yr)
        if not force:
            have = {tg.name: tg.head(key) for tg in targets}
            if all(have.values()):
                log.info("skip %s (on all targets)", key)
                continue
            if have[primary.name]:
                # Written before a mirror was added: copy the existing bytes across.
                missing = [tg for tg in mirrors if not have[tg.name]]
                local = os.path.join(staging, key.replace("/", os.sep))
                primary.download(key, local)
                lake_targets.publish(local, key, missing)
                os.remove(local)
                log.info("mirrored %s -> %s", key, ",".join(tg.name for tg in missing))
                continue
        started = time.time()
        if table == "boundaries":
            src = BOUNDARY_SQL.format(t=bt, y=yr)
            select = ("SELECT * EXCLUDE (wkb), ST_GeomFromWKB(wkb) AS geometry "
                      "FROM postgres_query('pg', ?)")
        else:
            src = ATTRIBUTE_SQL.format(t=bt, y=yr)
            select = "SELECT * FROM postgres_query('pg', ?)"
        local = os.path.join(staging, key.replace("/", os.sep))
        os.makedirs(os.path.dirname(local), exist_ok=True)
        tmp = local + ".tmp"
        con.execute(
            f"COPY ({select}) TO '{tmp.replace(chr(39), chr(39) * 2)}' "
            f"(FORMAT parquet, COMPRESSION zstd, ROW_GROUP_SIZE 50000)",
            [src],
        )
        os.replace(tmp, local)
        n = con.execute("SELECT count(*) FROM read_parquet(?)", [local]).fetchone()[0]
        if n != src_n and table == "boundaries":
            sys.exit(f"{key}: wrote {n} rows, source has {src_n}")
        lake_targets.publish(local, key, targets)
        os.remove(local)
        manifest[f"{bt}/{yr}"] = n
        log.info("wrote %s rows=%d in %.1fs", key, n, time.time() - started)
    return manifest


def verify(con, targets):
    """Row counts per partition: source vs lake."""
    primary = targets[0]
    bad = 0
    for table, count_sql in (
        ("boundaries", "SELECT boundary_type, year, count(*)::bigint FROM public.geographic_boundaries GROUP BY 1,2"),
        ("attributes", "SELECT b.boundary_type, d.year, count(*)::bigint FROM public.geographic_data d "
                       "JOIN public.geographic_boundaries b USING (summary_level, geoid, year) GROUP BY 1,2"),
    ):
        src = {(r[0], r[1]): r[2] for r in con.execute("SELECT * FROM postgres_query('pg', ?)", [count_sql]).fetchall()}
        lake = {
            (r[0], int(r[1])): r[2]
            for r in con.execute(
                f"SELECT boundary_type, year, count(*) FROM read_parquet('{primary.url(PREFIX)}/{table}/*/*/*.parquet', "
                f"hive_partitioning = true) GROUP BY 1, 2"
            ).fetchall()
        }
        for k, n in sorted(src.items()):
            if lake.get(k) != n:
                bad += 1
                log.warning("%s %s: source=%s %s=%s", table, k, n, primary.name, lake.get(k))
        log.info("%s: %d partitions, source rows=%d, %s rows=%d",
                 table, len(src), sum(src.values()), primary.name, sum(lake.values()))
    if bad:
        sys.exit(f"{bad} problem(s) found")
    log.info("verify OK")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("table", choices=["boundaries", "attributes", "verify"])
    ap.add_argument("--type", dest="btype")
    ap.add_argument("--year", type=int)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--targets", help="override LAKE_TARGETS")
    a = ap.parse_args()

    targets = lake_targets.load_targets(a.targets)
    log.info("targets: %s", ", ".join(f"{t.name}=s3://{t.bucket}" for t in targets))

    con = connect(targets)
    if a.table == "verify":
        verify(con, targets)
        return
    manifest = export(con, targets, a.table, a.btype, a.year, a.force)
    if manifest:
        log.info("exported %d partitions, %d rows", len(manifest), sum(manifest.values()))


if __name__ == "__main__":
    main()
