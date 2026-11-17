#!/usr/bin/env python3
"""
Roll the block-level LEHD LODES files in the lake up to the levels GeoAgent
uses. Each state contributes its latest published year (Michigan lags; Alaska
stopped publishing after 2016 and is left out).

Reads   curated/reference/lodes/kind=<wac|rac|od>/year=<Y>/state=<st>/part-0.parquet
Writes  curated/derived/lodes/year=<Y>/level=tract/part-0.parquet
          geoid, jobs (workplace, WAC C000), workers (residents, RAC C000),
          jobs_by_earnings (CE01 <= $1,250/mo, CE02, CE03 > $3,333/mo),
          jobs_by_industry (CNS01..CNS20, NAICS sectors), jobs_per_worker,
          lodes_year (the state's year)
        curated/derived/lodes/year=<Y>/level=county/part-0.parquet       same, by county
        curated/derived/lodes/year=<Y>/level=county_flow/part-0.parquet
          home_county, work_county, workers (OD S000); in-state flows only
          (OD "main"), so cross-state commutes are not counted

<Y> is the run's target year (default 2024), the year most states contribute.

Usage:
  python lodes_rollup_to_lake.py [--year 2024] [--out ./lodes_test]
"""

import argparse
import logging
import os
import sys
import tempfile

import duckdb

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "warehouse"))
import lake_targets  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("lodes-rollup")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--year", type=int, default=2024, help="target year; states without it use their latest")
    ap.add_argument("--staging", default=os.getenv("LAKE_STAGING") or tempfile.gettempdir())
    ap.add_argument("--out", help="write locally instead of publishing")
    a = ap.parse_args(argv)

    targets = lake_targets.load_targets()
    con = duckdb.connect()
    con.install_extension("httpfs")
    con.load_extension("httpfs")
    lake_targets.register_duckdb(con, targets)
    src = targets[0].url("curated/reference/lodes")

    def latest(kind):
        """(state, year) to use: the target year when present, else the latest <= target.
        RAC follows the WAC year: a state that did not supply its own UI data
        (Michigan, Alaska) still gets a RAC file, but it only counts residents
        working out of state or federally, so it must not be mixed with jobs."""
        con.execute(f"""
        CREATE OR REPLACE TEMP TABLE pick_{kind} AS
        WITH f AS (
          SELECT regexp_extract(file, 'state=([a-z]+)', 1) AS state,
                 regexp_extract(file, 'year=([0-9]+)', 1)::INT AS year
          FROM glob('{src}/kind={kind}/year=*/state=*/part-0.parquet'))
        SELECT state, max(year) AS year FROM f
        WHERE year <= {a.year}
          {"AND (state, year) IN (SELECT (state, year) FROM pick_wac)" if kind != "wac" else ""}
        GROUP BY state""")
        files = [f"{src}/kind={kind}/year={y}/state={s}/part-0.parquet"
                 for s, y in con.execute(f"SELECT state, year FROM pick_{kind} ORDER BY state").fetchall()]
        old = con.execute(f"SELECT state, year FROM pick_{kind} WHERE year <> {a.year}").fetchall()
        log.info("%s: %d states%s", kind, len(files), f" (older: {old})" if old else "")
        return files

    wac, rac, od = latest("wac"), latest("rac"), latest("od")
    lst = lambda fs: "[" + ", ".join(f"'{f}'" for f in fs) + "]"
    ind = ", ".join(f"sum(CNS{i:02d}::BIGINT) AS cns{i:02d}" for i in range(1, 21))
    con.execute(f"""
    CREATE TEMP TABLE w AS
    SELECT left(w_geocode, 11) AS tract, sum(C000::BIGINT) AS jobs, sum(CE01::BIGINT) AS jobs_earn_low, sum(CE02::BIGINT) AS jobs_earn_mid,
           sum(CE03::BIGINT) AS jobs_earn_high, {ind},
           any_value(regexp_extract(filename, 'year=([0-9]+)', 1)::INT) AS lodes_year
    FROM read_parquet({lst(wac)}, filename = true, union_by_name = true) GROUP BY 1""")
    con.execute(f"""
    CREATE TEMP TABLE r AS
    SELECT left(h_geocode, 11) AS tract, sum(C000::BIGINT) AS workers,
           any_value(regexp_extract(filename, 'year=([0-9]+)', 1)::INT) AS lodes_year
    FROM read_parquet({lst(rac)}, filename = true, union_by_name = true) GROUP BY 1""")
    cols = "jobs, jobs_earn_low, jobs_earn_mid, jobs_earn_high, " + ", ".join(f"cns{i:02d}" for i in range(1, 21))
    con.execute(f"""
    CREATE TEMP TABLE t AS
    SELECT coalesce(w.tract, r.tract) AS geoid, {", ".join(f"coalesce(w.{c}, 0) AS {c}" for c in cols.split(", "))},
           coalesce(r.workers, 0) AS workers,
           coalesce(w.jobs, 0) / nullif(r.workers, 0) AS jobs_per_worker,
           coalesce(w.lodes_year, r.lodes_year) AS lodes_year
    FROM w FULL JOIN r USING (tract)""")
    sums = ", ".join(f"sum({c}) AS {c}" for c in cols.split(", ")) + ", sum(workers) AS workers"
    sqls = {
        "tract": "SELECT * FROM t ORDER BY geoid",
        "county": f"""SELECT left(geoid, 5) AS geoid, {sums}, sum(jobs) / nullif(sum(workers), 0) AS jobs_per_worker,
                             max(lodes_year) AS lodes_year FROM t GROUP BY 1 ORDER BY 1""",
        "county_flow": f"""SELECT left(h_geocode, 5) AS home_county, left(w_geocode, 5) AS work_county,
                                  sum(S000::BIGINT) AS workers, sum(SE03::BIGINT) AS workers_earn_high,
                                  any_value(regexp_extract(filename, 'year=([0-9]+)', 1)::INT) AS lodes_year
                           FROM read_parquet({lst(od)}, filename = true, union_by_name = true)
                           GROUP BY 1, 2 ORDER BY 1, 2""",
    }
    root = os.path.abspath(a.out) if a.out else os.path.join(a.staging, "lodes-rollup")
    for lvl, sql in sqls.items():
        key = f"curated/derived/lodes/year={a.year}/level={lvl}/part-0.parquet"
        local = os.path.join(root, key.replace("/", os.sep))
        os.makedirs(os.path.dirname(local), exist_ok=True)
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
