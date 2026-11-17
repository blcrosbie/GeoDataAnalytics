#!/usr/bin/env python3
"""
Fetch the non-TIGER reference datasets a national geographic layer needs, keep
the raw files in the archive, and publish typed Parquet to the lake.

  gazetteer  Census Gazetteer: one row per geography with land/water area and
             internal point (zcta, place, county, tract, ua, cbsa, cousub)
  rel        2020 ZCTA relationship files: ZCTA x tract / county / place / cousub
             with the land area of each part, for apportioning ZIP data
  ruca       USDA ERS 2020 Rural-Urban Commuting Area codes, tract and ZIP level
  lodes      LEHD LODES8 workplace (WAC) and residence (RAC) job counts by block,
             plus the block crosswalk; OD (commute flows) with --od

Lake layout (every lake target, see warehouse/lake_targets.py):

  curated/reference/gazetteer/layer=<zcta|place|...>/year=<Y>/part-0.parquet
  curated/reference/rel2020/pair=<zcta520_tract20|...>/part-0.parquet
  curated/reference/ruca/vintage=2020/level=<tract|zip>/part-0.parquet
  curated/reference/lodes/kind=<wac|rac|od|xwalk>/year=<Y>/state=<st>/part-0.parquet

Raw downloads go to origin/reference/<dataset>/... on ORIGIN_TARGET (default
"wasabi", the archive), when that target is configured.

ID columns (anything named like FIPS / GEOID / CODE / ZIP / geocode) are always
read as text, so leading zeros survive. FCC stations and broadcast contours
are built by fcc_to_lake.py (FCC query lists + the geo.fcc.gov contour API;
the bulk contour zips on fcc.gov refuse scripted clients).

Usage:
  python get_reference_data.py gazetteer --year 2025
  python get_reference_data.py rel ruca
  python get_reference_data.py lodes --lodes-year 2022 [--states ca,co] [--od]
  python get_reference_data.py all --year 2025 --dry-run
"""

import argparse
import csv
import gzip
import logging
import os
import re
import shutil
import sys
import tempfile
import time
import zipfile

import duckdb
import requests

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "warehouse"))
import lake_targets  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("reference")

UA = {"User-Agent": "GeoDataAnalytics-reference-fetch/1.0"}
GAZ = "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/{y}_Gazetteer/{y}_Gaz_{layer}_national.zip"
GAZ_LAYERS = ["zcta", "place", "counties", "tracts", "ua", "cbsa", "cousubs"]
REL = "https://www2.census.gov/geo/docs/maps-data/data/rel2020/zcta520/tab20_{pair}_natl.txt"
REL_PAIRS = ["zcta520_tract20", "zcta520_county20", "zcta520_place20", "zcta520_cousub20"]
RUCA = {
    "tract": "https://www.ers.usda.gov/media/5443/2020-rural-urban-commuting-area-codes-census-tracts.csv",
    "zip": "https://www.ers.usda.gov/media/5444/2020-rural-urban-commuting-area-codes-zip-codes.csv",
}
LODES = "https://lehd.ces.census.gov/data/lodes/LODES8/{st}/{path}"
STATES = ("al ak az ar ca co ct de dc fl ga hi id il in ia ks ky la me md ma mi mn ms mo mt ne "
          "nv nh nj nm ny nc nd oh ok or pa ri sc sd tn tx ut vt va wa wv wi wy").split()

ID_COL = re.compile(r"(fips|geoid|code|zip|geocode|^oid|ce\d*$|_ce|cbsafp|statefp|countyfp)", re.I)


class Publisher:
    def __init__(self, staging: str, dry_run: bool):
        self.staging, self.dry = staging, dry_run
        self.lake = [] if dry_run else lake_targets.load_targets()
        self.origin = []
        name = os.getenv("ORIGIN_TARGET", "wasabi")
        if not dry_run and os.getenv(f"LAKE_{name.upper()}_BUCKET"):
            self.origin = lake_targets.load_targets(name)
        self.con = duckdb.connect()

    def fetch(self, url: str, origin_key: str) -> str | None:
        local = os.path.join(self.staging, "raw", origin_key.replace("/", os.sep))
        if self.dry:
            log.info("would fetch %s -> origin/%s", url, origin_key)
            return None
        if not os.path.exists(local):
            os.makedirs(os.path.dirname(local), exist_ok=True)
            for attempt in range(4):
                try:
                    with requests.get(url, headers=UA, stream=True, timeout=120) as r:
                        if r.status_code == 404:
                            log.warning("404 %s (not published?), skipped", url)
                            return None
                        r.raise_for_status()
                        # census.gov serves some .txt with Content-Encoding: gzip;
                        # r.raw skips that decoding unless asked.
                        r.raw.decode_content = True
                        with open(local + ".tmp", "wb") as f:
                            shutil.copyfileobj(r.raw, f, 8 << 20)
                    os.replace(local + ".tmp", local)
                    break
                except requests.RequestException as e:
                    if attempt == 3:
                        raise
                    log.warning("retry %s (%s)", url, e)
                    time.sleep(10 * (attempt + 1))
        if self.origin:
            lake_targets.publish(local, f"origin/reference/{origin_key}", self.origin)
        return local

    def to_lake(self, text_path: str, key: str) -> None:
        """Delimited text -> zstd Parquet with ID-like columns forced to VARCHAR.
        The delimiter is read off the header: the Gazetteer moved from tab to
        pipe in 2025, the relationship files are pipe, RUCA and LODES comma."""
        with open(text_path, encoding="utf-8-sig", errors="replace") as f:
            first = f.readline()
        delim = max(("|", "\t", ","), key=first.count)
        header = next(csv.reader([first], delimiter=delim))
        names = [h.strip() for h in header]
        q = lambda v: "'" + v.replace("'", "''") + "'"
        # A struct literal: the Python binding turns a dict parameter into a MAP or
        # STRUCT depending on its shape, and read_csv only accepts the struct.
        types = ", ".join(f"{q(n)}: 'VARCHAR'" for n in names if ID_COL.search(n))
        out = os.path.join(self.staging, "lake", key.replace("/", os.sep))
        os.makedirs(os.path.dirname(out), exist_ok=True)
        try:  # USDA ships Latin-1 ("Doña Ana"); Census ships UTF-8 with a BOM
            with open(text_path, encoding="utf-8-sig") as f:
                for _ in f:
                    pass
            enc = "utf-8"
        except UnicodeDecodeError:
            enc = "latin-1"
        self.con.execute(
            "COPY (SELECT * FROM read_csv(?, delim = ?, header = true, names = ?, "
            + (f"types = {{{types}}}, " if types else "")
            + f"encoding = '{enc}', "
            + "      quote = '\"', sample_size = -1, strict_mode = false)) "
            f"TO {q(out)} (FORMAT parquet, COMPRESSION zstd)",
            [text_path, delim, names],
        )
        n = self.con.execute("SELECT count(*) FROM read_parquet(?)", [out]).fetchone()[0]
        lake_targets.publish(out, key, self.lake)
        log.info("%s: %d rows", key, n)
        os.remove(out)


def unzip_one(path: str) -> str:
    with zipfile.ZipFile(path) as z:
        member = next(m for m in z.namelist() if m.lower().endswith((".txt", ".csv")))
        out = os.path.join(os.path.dirname(path), os.path.basename(member))
        with z.open(member) as src, open(out, "wb") as dst:
            shutil.copyfileobj(src, dst)
    return out


def gunzip(path: str) -> str:
    out = path[:-3]
    with gzip.open(path, "rb") as src, open(out, "wb") as dst:
        shutil.copyfileobj(src, dst)
    return out


def run_gazetteer(pub: Publisher, year: int) -> None:
    for layer in GAZ_LAYERS:
        z = pub.fetch(GAZ.format(y=year, layer=layer), f"gazetteer/{year}/{year}_Gaz_{layer}_national.zip")
        if z:
            pub.to_lake(unzip_one(z), f"curated/reference/gazetteer/layer={layer}/year={year}/part-0.parquet")


def run_rel(pub: Publisher) -> None:
    for pair in REL_PAIRS:
        t = pub.fetch(REL.format(pair=pair), f"rel2020/tab20_{pair}_natl.txt")
        if t:
            pub.to_lake(t, f"curated/reference/rel2020/pair={pair}/part-0.parquet")


def run_ruca(pub: Publisher) -> None:
    for level, url in RUCA.items():
        t = pub.fetch(url, f"ruca/2020/{os.path.basename(url)}")
        if t:
            pub.to_lake(t, f"curated/reference/ruca/vintage=2020/level={level}/part-0.parquet")


def run_lodes(pub: Publisher, year: int, states: list[str], od: bool) -> None:
    for st in states:
        paths = {
            "wac": f"wac/{st}_wac_S000_JT00_{year}.csv.gz",
            "rac": f"rac/{st}_rac_S000_JT00_{year}.csv.gz",
            "xwalk": f"{st}_xwalk.csv.gz",
        }
        if od:
            paths["od"] = f"od/{st}_od_main_JT00_{year}.csv.gz"
        for kind, path in paths.items():
            gz = pub.fetch(LODES.format(st=st, path=path), f"lodes/LODES8/{st}/{path}")
            if gz:
                yr = "all" if kind == "xwalk" else year
                pub.to_lake(gunzip(gz), f"curated/reference/lodes/kind={kind}/year={yr}/state={st}/part-0.parquet")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("datasets", nargs="+", choices=["gazetteer", "rel", "ruca", "lodes", "all"])
    ap.add_argument("--year", type=int, default=2025, help="Gazetteer vintage")
    ap.add_argument("--lodes-year", type=int, default=2022, help="LODES job year (lags ~3 years)")
    ap.add_argument("--states", default=",".join(STATES), help="LODES states, e.g. ca,co")
    ap.add_argument("--od", action="store_true", help="LODES: also fetch origin-destination flows (large)")
    ap.add_argument("--staging", default=os.getenv("LAKE_STAGING") or tempfile.gettempdir())
    ap.add_argument("--keep", action="store_true", help="keep raw downloads in staging")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)

    want = set(a.datasets)
    if "all" in want:
        want = {"gazetteer", "rel", "ruca", "lodes"}
    staging = os.path.join(a.staging, "reference")
    pub = Publisher(staging, a.dry_run)
    if "gazetteer" in want:
        run_gazetteer(pub, a.year)
    if "rel" in want:
        run_rel(pub)
    if "ruca" in want:
        run_ruca(pub)
    if "lodes" in want:
        run_lodes(pub, a.lodes_year, [s.strip().lower() for s in a.states.split(",") if s.strip()], a.od)
    if not a.keep and not a.dry_run:
        shutil.rmtree(os.path.join(staging, "raw"), ignore_errors=True)


if __name__ == "__main__":
    main()
