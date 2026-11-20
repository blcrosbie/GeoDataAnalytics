#!/usr/bin/env python3
"""
Roll the block-level LEHD LODES files in the lake up to the levels GeoAgent
uses. Each state contributes its latest published year (Michigan lags; Alaska
stopped publishing after 2016 and is left out).

Reads   curated/reference/lodes/kind=<wac|rac|od>/year=<Y>/state=<st>/part-0.parquet
        curated/reference/lodes/kind=xwalk/year=all/state=<st>/part-0.parquet   (block crosswalk)
Writes  curated/derived/lodes/year=<Y>/level=<L>/part-0.parquet, where L is

          tract   11-digit tract GEOID              block GEOID prefix
          county  5-digit county FIPS               sum of the tracts
          bg      12-digit block group GEOID        block GEOID prefix
          place   7-digit state + place FIPS        crosswalk stplc
          zcta    5-digit ZCTA                      crosswalk zcta
          cbsa    5-digit CBSA code                 crosswalk cbsa
          sldu    state upper house district        crosswalk stsldu (2-digit state + 3-char district)
          sldl    state lower house district        crosswalk stsldl

        every one with the columns
          geoid, jobs (workplace, WAC C000), jobs_earn_low|mid|high (CE01 <= $1,250/mo,
          CE02, CE03 > $3,333/mo), cns01..cns20 (jobs by NAICS sector), workers
          (residents, RAC C000), jobs_per_worker (jobs / workers), lodes_year
          (the latest year among the area's blocks)

        curated/derived/lodes/year=<Y>/level=county_flow/part-0.parquet
          home_county, work_county, workers (OD S000), workers_earn_high (SE03),
          lodes_year; in-state flows only (OD "main"), so cross-state commutes
          are not counted

<Y> is the run's target year (default 2024), the year most states contribute.

Jobs are summed by workplace block (w_geocode) and workers by home block
(h_geocode), each to the area the block falls in, then full-joined on the
area GEOID, so an area with only jobs or only residents still gets a row.
Place, ZCTA, CBSA and district membership come from the LODES8 crosswalk
(tabblk2020). Its codes match the TIGER 2025 PLACE, ZCTA520, CBSA, SLDU and
SLDL GEOIDs in curated/boundaries. Blocks outside any such area carry a
placeholder (9999999 / 99999, or ZZZ) and are dropped, so those levels add
up to less than the county totals. Nebraska (unicameral) and DC have no SLDL
rows. ZCTAs and CBSAs can cross state lines and then mix the states' years
(lodes_year is the latest). Some crosswalk IDs were typed as integers when
they were loaded, so codes are zero-padded back to their GEOID width.

Before anything is written, the run checks that block groups add up to tracts
and that no state's places or districts hold more jobs or workers than its
counties, and stops if either check fails.

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

# Crosswalk areas: level -> (crosswalk column, GEOID width, trailing characters
# that are the area's own code and are all 9s or Zs in the placeholder).
XWALK = {
    "place": ("stplc", 7, 5),
    "zcta": ("zcta", 5, 5),
    "cbsa": ("cbsa", 5, 5),
    "sldu": ("stsldu", 5, 3),
    "sldl": ("stsldl", 5, 3),
}
# Every area level: the GEOID of the area a block belongs to.
LEVELS = {"tract": "left(block, 11)", "bg": "left(block, 12)", **{lvl: lvl for lvl in XWALK}}
STATE_PREFIXED = ("place", "sldu", "sldl")  # GEOID starts with the state FIPS
COLS = ["jobs", "jobs_earn_low", "jobs_earn_mid", "jobs_earn_high"] + [f"cns{i:02d}" for i in range(1, 21)]


def xwalk_code(col: str, width: int, own: int) -> str:
    """Crosswalk code as GEOID text, or NULL when blank or a placeholder."""
    v = f"lpad(nullif(trim({col}::VARCHAR), ''), {width}, '0')"
    return f"CASE WHEN NOT regexp_full_match(right({v}, {own}), '9+|Z+') THEN {v} END"


def area_sql(geoid: str) -> str:
    """Jobs by workplace block and workers by home block, each summed to the
    area, then full-joined on the area GEOID (blocks with no area dropped)."""
    sums = ", ".join(f"sum({c}) AS {c}" for c in COLS)
    return f"""
    WITH w AS (SELECT {geoid} AS geoid, {sums}, max(lodes_year) AS lodes_year
               FROM wb WHERE {geoid} IS NOT NULL GROUP BY 1),
         r AS (SELECT {geoid} AS geoid, sum(workers) AS workers, max(lodes_year) AS lodes_year
               FROM rb WHERE {geoid} IS NOT NULL GROUP BY 1)
    SELECT coalesce(w.geoid, r.geoid) AS geoid, {", ".join(f"coalesce(w.{c}, 0) AS {c}" for c in COLS)},
           coalesce(r.workers, 0) AS workers,
           coalesce(w.jobs, 0) / nullif(r.workers, 0) AS jobs_per_worker,
           greatest(w.lodes_year, r.lodes_year) AS lodes_year
    FROM w FULL JOIN r USING (geoid)"""


def check(con) -> None:
    """Log what each level covers; stop if the levels don't add up."""
    for b, what in (("wb", "jobs"), ("rb", "workers")):
        n, v = con.execute(f"SELECT count(*), sum({what}) FROM {b} WHERE NOT in_xwalk").fetchone()
        if n:
            log.warning("%d blocks with %d %s are not in the crosswalk (left out of %s)",
                        n, v, what, ", ".join(XWALK))
    total = con.execute("SELECT sum(jobs), sum(workers) FROM a_tract").fetchone()
    for lvl in LEVELS:
        n, j, w = con.execute(f"SELECT count(*), sum(jobs), sum(workers) FROM a_{lvl}").fetchone()
        log.info("%-5s %7d areas, %5.1f%% of jobs, %5.1f%% of workers", lvl, n,
                 100 * j / total[0], 100 * w / total[1])
    bad = []
    bg = con.execute("SELECT sum(jobs), sum(workers) FROM a_bg").fetchone()
    if bg != total:
        bad.append(f"block groups (jobs, workers) {bg} != tracts {total}")
    for lvl in XWALK:
        st = "left(geoid, 2)" if lvl in STATE_PREFIXED else "'US'"
        bad += [f"{lvl} in state {s}: jobs {j} / workers {w} > county {cj} / {cw}"
                for s, j, w, cj, cw in con.execute(f"""
            WITH c AS (SELECT {st} AS st, sum(jobs) AS jobs, sum(workers) AS workers FROM a_tract GROUP BY 1),
                 a AS (SELECT {st} AS st, sum(jobs) AS jobs, sum(workers) AS workers FROM a_{lvl} GROUP BY 1)
            SELECT a.st, a.jobs, a.workers, c.jobs, c.workers FROM a LEFT JOIN c USING (st)
            WHERE a.jobs > coalesce(c.jobs, 0) OR a.workers > coalesce(c.workers, 0)""").fetchall()]
    if bad:
        for b in bad:
            log.error("check failed: %s", b)
        sys.exit("checks failed, nothing written")
    log.info("checks passed: block groups = tracts; places, districts, ZCTAs, CBSAs <= counties")


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
    year = "regexp_extract(filename, 'year=([0-9]+)', 1)::INT AS lodes_year"
    con.execute(f"""
    CREATE TEMP TABLE xw AS
    SELECT lpad(tabblk2020::VARCHAR, 15, '0') AS block,
           {", ".join(f"{xwalk_code(*spec)} AS {lvl}" for lvl, spec in XWALK.items())}
    FROM read_parquet('{src}/kind=xwalk/year=all/state=*/part-0.parquet', union_by_name = true,
                      hive_partitioning = false)""")
    # One row per block, with the crosswalk areas it falls in.
    xcols = ", ".join(f"xw.{lvl}" for lvl in XWALK) + ", xw.block IS NOT NULL AS in_xwalk"
    con.execute(f"""
    CREATE TEMP TABLE wb AS
    SELECT b.*, {xcols} FROM (
      SELECT w_geocode AS block, C000::BIGINT AS jobs, CE01::BIGINT AS jobs_earn_low, CE02::BIGINT AS jobs_earn_mid,
             CE03::BIGINT AS jobs_earn_high, {", ".join(f"CNS{i:02d}::BIGINT AS cns{i:02d}" for i in range(1, 21))},
             {year}
      FROM read_parquet({lst(wac)}, filename = true, union_by_name = true)) b
    LEFT JOIN xw USING (block)""")
    con.execute(f"""
    CREATE TEMP TABLE rb AS
    SELECT b.*, {xcols} FROM (
      SELECT h_geocode AS block, C000::BIGINT AS workers, {year}
      FROM read_parquet({lst(rac)}, filename = true, union_by_name = true)) b
    LEFT JOIN xw USING (block)""")
    for lvl, geoid in LEVELS.items():
        con.execute(f"CREATE TEMP TABLE a_{lvl} AS {area_sql(geoid)}")
    check(con)

    sums = ", ".join(f"sum({c}) AS {c}" for c in COLS) + ", sum(workers) AS workers"
    sqls = {
        "tract": "SELECT * FROM a_tract ORDER BY geoid",
        "county": f"""SELECT left(geoid, 5) AS geoid, {sums}, sum(jobs) / nullif(sum(workers), 0) AS jobs_per_worker,
                             max(lodes_year) AS lodes_year FROM a_tract GROUP BY 1 ORDER BY 1""",
        "county_flow": f"""SELECT left(h_geocode, 5) AS home_county, left(w_geocode, 5) AS work_county,
                                  sum(S000::BIGINT) AS workers, sum(SE03::BIGINT) AS workers_earn_high,
                                  any_value(regexp_extract(filename, 'year=([0-9]+)', 1)::INT) AS lodes_year
                           FROM read_parquet({lst(od)}, filename = true, union_by_name = true)
                           GROUP BY 1, 2 ORDER BY 1, 2""",
        **{lvl: f"SELECT * FROM a_{lvl} ORDER BY geoid" for lvl in LEVELS if lvl != "tract"},
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
