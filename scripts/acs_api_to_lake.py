#!/usr/bin/env python3
"""
Backfill ACS 5-year releases that predate the table-based Summary File
(2009-2019 releases; Census only publishes the table-based SF from 2021, and
this lake's 2020-2024 came from it) by pulling whole tables from the Census
Data API, and write them in the SAME wide layout as the 2020+ lake files:

  curated/acs/vintage=<Y>/table=<t>/part-0.parquet
    GEO_ID ('1400000US06037101110'), <T>_E001, <T>_M001, <T>_E002, ... (DOUBLE),
    sumlev ('140'), component ('00'), geoid ('06037101110'), table ('b19013'), vintage

Values are kept raw, Census sentinels included (-666666666 etc.), exactly like
the Summary File loads. Only these summary levels are fetched (the ones GeoAgent
maps): 010 us, 040 state, 050 county, 140 tract, 150 block group, 160 place,
310 CBSA, 860 ZCTA. A 2020+ file has every summary level; a backfilled one has
these eight.

Geography caveat: releases up to 2019 are tabulated on 2010-census tracts,
block groups and ZCTAs. Their GEOIDs look like 2020 ones but are different
shapes; compare across 2019 -> 2020 at those levels only through a crosswalk.
States, counties, places and CBSAs compare directly (watch Connecticut 2022).

Non-overlapping windows are the clean comparisons: 2019 vs 2024 (5Y),
2014 vs 2024 (10Y).

Needs a free key: https://api.census.gov/data/key_signup.html -> CENSUS_API_KEY.

Usage:
  python acs_api_to_lake.py --years 2014-2019                      # GeoAgent's 12 tables
  python acs_api_to_lake.py --years 2019 --tables b01003,b19013 --levels county,tract
  python acs_api_to_lake.py --years 2014-2019 --dry-run            # plan the calls, no key needed
"""

import argparse
import concurrent.futures as cf
import json
import logging
import os
import sys
import tempfile
import time

import pyarrow as pa
import pyarrow.parquet as pq
import requests

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "warehouse"))
import lake_targets  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("acs-api")

API = "https://api.census.gov/data/{y}/acs/acs5"
UA = {"User-Agent": "GeoDataAnalytics-acs-backfill/1.0"}

# The tables GeoAgent turns into curated/facts/acs (build-attrs).
DEFAULT_TABLES = ["b01002", "b01003", "b11001", "b15003", "b17001", "b19013",
                  "b19301", "b23025", "b25001", "b25003", "b25064", "b25077"]

# level name -> (sumlev, API geography name)
LEVELS = {
    "us":     ("010", "us"),
    "state":  ("040", "state"),
    "county": ("050", "county"),
    "tract":  ("140", "tract"),
    "bg":     ("150", "block group"),
    "place":  ("160", "place"),
    "cbsa":   ("310", "metropolitan statistical area/micropolitan statistical area"),
    "zcta":   ("860", "zip code tabulation area"),
}

STATES = ("01 02 04 05 06 08 09 10 11 12 13 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30 "
          "31 32 33 34 35 36 37 38 39 40 41 42 44 45 46 47 48 49 50 51 53 54 55 56 72").split()


def env_key() -> str | None:
    """CENSUS_API_KEY from the environment, else from warehouse/.env or ./.env (gitignored)."""
    if os.getenv("CENSUS_API_KEY"):
        return os.environ["CENSUS_API_KEY"]
    here = os.path.dirname(os.path.abspath(__file__))
    for p in (os.path.join(here, "..", "warehouse", ".env"), os.path.join(here, "..", ".env")):
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                for line in f:
                    k, _, v = line.strip().partition("=")
                    if k.strip() == "CENSUS_API_KEY" and v.strip():
                        return v.strip().strip('"').strip("'")
    return None


class Api:
    def __init__(self, key: str | None):
        self.key = key
        self.s = requests.Session()
        self.s.headers.update(UA)
        self.calls = 0

    def get(self, url, params, meta=False):
        p = dict(params)
        if self.key and not meta:
            p["key"] = self.key
        for attempt in range(6):
            try:
                r = self.s.get(url, params=p, timeout=300, allow_redirects=False)
            except requests.RequestException as e:  # dropped connection, timeout
                log.warning("retry %s (%s)", url, type(e).__name__)
                time.sleep(5 * (attempt + 1))
                continue
            if r.status_code == 302 and "missing_key" in r.headers.get("Location", ""):
                sys.exit("Census API wants a key: set CENSUS_API_KEY "
                         "(free, https://api.census.gov/data/key_signup.html)")
            if r.status_code == 302 and "invalid_key" in r.headers.get("Location", ""):
                sys.exit("CENSUS_API_KEY was rejected (activate it from the signup email first)")
            if r.status_code == 204:  # valid request, no rows (e.g. no ZCTAs in a state)
                return []
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(5 * (attempt + 1))
                continue
            if r.status_code != 200:
                raise RuntimeError(f"{r.status_code} {r.url.split('&key=')[0]}: {r.text[:300]}")
            self.calls += 1
            return r.json()
        raise RuntimeError(f"gave up on {url} {params}")


def geo_rules(api: Api, year: int) -> dict:
    """API geography name -> (requires, wildcard) for one release, from geography.json."""
    d = api.get(API.format(y=year) + "/geography.json", {}, meta=True)
    out = {}
    for g in d["fips"]:
        lvl = g.get("geoLevelDisplay") or g.get("geoLevelId")
        if lvl in {v[0] for v in LEVELS.values()}:
            out.setdefault(g["name"], (g.get("requires") or [], g.get("wildcard") or []))
    return out


def requests_for(level: str, rules: dict) -> list[dict]:
    """The `for`/`in` parameter sets that cover a level nationally. Required
    parents that accept a wildcard get '*'; any other (in practice: state) is
    enumerated."""
    _, name = LEVELS[level]
    if name not in rules:
        return []
    requires, wildcard = rules[name]
    fixed = [r for r in requires if r not in wildcard]
    if not fixed:
        ins = [f"{r}:*" for r in requires]
        return [{"for": f"{name}:*", **({"in": " ".join(ins)} if ins else {})}]
    if fixed != ["state"]:
        raise SystemExit(f"{name}: don't know how to enumerate {fixed}")
    return [{"for": f"{name}:*", "in": " ".join([f"state:{st}"] + [f"{r}:*" for r in requires if r != "state"])}
            for st in STATES]


def table_columns(api: Api, year: int, table: str) -> list[str]:
    """API variable names (B19013_001E, B19013_001M, ...) in line order."""
    d = api.get(API.format(y=year) + f"/groups/{table.upper()}.json", {}, meta=True)
    names = [v for v in d["variables"] if v.endswith(("E", "M")) and v[-4:-1].isdigit()]
    return sorted(names, key=lambda v: (int(v.split("_")[1][:-1]), v[-1]))


def lake_name(api_var: str) -> str:
    t, rest = api_var.split("_")           # B19013, 001E
    return f"{t}_{rest[-1]}{rest[:-1]}"    # B19013_E001


def fetch_table(api: Api, year: int, table: str, levels: list[str], rules: dict, workers: int) -> pa.Table:
    cols = table_columns(api, year, table)
    want = ["GEO_ID"] + cols
    jobs = [(lvl, q) for lvl in levels for q in requests_for(lvl, rules)]
    rows: list[list] = []

    def one(job):
        _, q = job
        data = api.get(API.format(y=year), {"get": f"group({table.upper()})", **q})
        if not data:
            return []
        head = data[0]
        idx = [head.index(c) for c in want]
        return [[r[i] for i in idx] for r in data[1:]]

    with cf.ThreadPoolExecutor(workers) as ex:
        for part in ex.map(one, jobs):
            rows.extend(part)
    seen, uniq = set(), []
    for r in rows:                         # ZCTAs come back once per state they touch
        if r[0] not in seen:
            seen.add(r[0])
            uniq.append(r)
    geo = [r[0] for r in uniq]
    arrays = {"GEO_ID": pa.array(geo, pa.string())}
    for j, c in enumerate(cols, start=1):
        arrays[lake_name(c)] = pa.array([None if r[j] in (None, "") else float(r[j]) for r in uniq], pa.float64())
    arrays["sumlev"] = pa.array([g[:3] for g in geo], pa.string())
    arrays["component"] = pa.array([g[3:5] for g in geo], pa.string())
    arrays["geoid"] = pa.array([g.split("US", 1)[1] if "US" in g else "" for g in geo], pa.string())
    arrays["table"] = pa.array([table.lower()] * len(geo), pa.string())
    arrays["vintage"] = pa.array([year] * len(geo), pa.int64())
    return pa.table(arrays), len(jobs)


def parse_years(s: str) -> list[int]:
    out = []
    for part in s.split(","):
        if "-" in part:
            a, b = part.split("-")
            out += range(int(a), int(b) + 1)
        else:
            out.append(int(part))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--years", default="2014-2019", help="e.g. 2014-2019 or 2015,2019")
    ap.add_argument("--tables", default=",".join(DEFAULT_TABLES))
    ap.add_argument("--levels", default=",".join(LEVELS))
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--staging", default=os.getenv("LAKE_STAGING") or tempfile.gettempdir())
    ap.add_argument("--force", action="store_true", help="rewrite partitions already on every target")
    ap.add_argument("--dry-run", action="store_true", help="show the calls per table/year, write nothing")
    ap.add_argument("--out", help="write parquet under this local dir instead of publishing (for testing)")
    a = ap.parse_args(argv)

    years = parse_years(a.years)
    if max(years) >= 2020 and not a.force:
        ap.error("2020+ comes from the table-based Summary File (warehouse/load/load_acs_summary_file.py); "
                 "pass --force to overwrite it from the API anyway")
    tables = [t.strip().lower() for t in a.tables.split(",") if t.strip()]
    levels = [l.strip() for l in a.levels.split(",") if l.strip()]
    bad = set(levels) - set(LEVELS)
    if bad:
        ap.error(f"unknown levels {sorted(bad)}; choose from {','.join(LEVELS)}")

    api = Api(env_key())
    targets = [] if (a.dry_run or a.out) else lake_targets.load_targets()
    staging = os.path.join(a.staging, "acs-api")

    for year in years:
        rules = geo_rules(api, year)
        if a.dry_run:
            n = sum(len(requests_for(l, rules)) for l in levels)
            missing = [l for l in levels if not requests_for(l, rules)]
            log.info("%s: %d calls per table x %d tables = %d%s", year, n, len(tables), n * len(tables),
                     f" (no API geography for {missing})" if missing else "")
            for l in levels:
                q = requests_for(l, rules)
                if q:
                    log.info("    %-6s %3d call(s), e.g. %s", l, len(q), json.dumps(q[0]))
            continue
        for table in tables:
            key = f"curated/acs/vintage={year}/table={table}/part-0.parquet"
            if targets and not a.force and all(t.head(key) for t in targets):
                log.info("skip %s (on all targets)", key)
                continue
            t0, c0 = time.time(), api.calls
            tbl, njobs = fetch_table(api, year, table, levels, rules, a.workers)
            by_lvl = {}
            for s in tbl.column("sumlev").to_pylist():
                by_lvl[s] = by_lvl.get(s, 0) + 1
            local = os.path.join(os.path.abspath(a.out) if a.out else staging, key.replace("/", os.sep))
            os.makedirs(os.path.dirname(local), exist_ok=True)
            pq.write_table(tbl, local + ".tmp", compression="zstd")
            os.replace(local + ".tmp", local)
            if not a.out:
                lake_targets.publish(local, key, targets)
                os.remove(local)
            log.info("%s: %d rows %s, %d calls, %.0fs", key, tbl.num_rows,
                     dict(sorted(by_lvl.items())), api.calls - c0, time.time() - t0)


if __name__ == "__main__":
    main()
