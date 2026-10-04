#!/usr/bin/env python3
"""
census_ingest_pipeline.py
Streaming EAV ingest for multi-domain Census / IRS survey archives.

Reads zipped or bare CSV/TXT members (from local disk OR a Wasabi S3 key),
normalizes GEOIDs to the geographic_boundaries key space, builds namespaced
'<survey>:<var>[@dim=val]' attribute keys, and bulk-loads cells into the
partitioned public.geographic_data table via:

    stream -> COPY into UNLOGGED staging -> set-based UPSERT (validate-join)

Cells whose (geoid, year) has no boundary yet are diverted to
public.geographic_data_unmatched and replayed later by `replay-unmatched`.

Usage
-----
  # local file already on disk (uses confirmed IRS county layout):
  python census_ingest_pipeline.py ingest \
      --survey irs_county --year 2018 \
      --path ../data/irs/county/2018/18incyallagi.csv

  # straight from S3 (zip or csv):
  python census_ingest_pipeline.py ingest \
      --survey irs_county --year 2018 \
      --s3-key origin/irs/county/2018/2018countydata.zip

  # parse-only, no DB writes:
  python census_ingest_pipeline.py ingest --survey irs_county \
      --path ../data/irs/county/2018/18incyallagi.csv --dry-run

  # promote previously-unmatched cells once their boundaries exist:
  python census_ingest_pipeline.py replay-unmatched
"""

import argparse
import csv
import io
import os
import re
import sys
import zipfile
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Iterator

import psycopg2
from psycopg2 import sql

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


# ===========================================================================
# GEOID + value normalization
# ===========================================================================
SUMMARY_BY_LEN = {1: "010", 2: "040", 5: "050", 7: "160", 11: "140", 12: "150"}
_NUM_RE = re.compile(r"[,$%\s]")
# Census / IRS null sentinels that must NOT be coerced to 0.
_NULL_TOKENS = {"", "-", ".", "(d)", "(x)", "(s)", "n", "*", "na", "n/a", "null"}


@dataclass(frozen=True)
class NormalizedGeo:
    geoid: str
    summary_level: str


def normalize_geoid(raw: str = "", *, statefips: str = "", countyfips: str = "",
                    placefips: str = "") -> NormalizedGeo | None:
    """Collapse the many incoming GEOID dialects to the bare FIPS key.

    Returns None for shapes we cannot resolve; the caller routes those rows
    to the unmatched sink rather than crashing the batch.
    """
    raw = (raw or "").strip()
    if statefips:
        sf = statefips.strip().zfill(2)
        if countyfips:
            return NormalizedGeo(sf + countyfips.strip().zfill(3), "050")
        if placefips:
            return NormalizedGeo(sf + placefips.strip().zfill(5), "160")
        return NormalizedGeo(sf, "040")
    # Prefixed Census API form: '0500000US01001'
    if "US" in raw and raw[:7].isdigit():
        return NormalizedGeo(raw.split("US", 1)[1], raw[:3])
    if raw.isdigit():
        lvl = SUMMARY_BY_LEN.get(len(raw))
        if lvl:
            return NormalizedGeo(raw, lvl)
    return None


def coerce_numeric(value: str) -> Decimal | None:
    if value.strip().lower() in _NULL_TOKENS:
        return None
    try:
        cleaned = _NUM_RE.sub("", value)
        if cleaned.lower() in _NULL_TOKENS:
            return None
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None


def year_from_name(name: str) -> int | None:
    m = re.search(r"(19|20)\d{2}", name)
    return int(m.group()) if m else None


# ===========================================================================
# Survey layout registry
#   Specs are DATA, not code: the explode loop is generic and driven entirely
#   by these. Add a survey by adding an entry, no loop changes required.
#   `irs_county` is confirmed against the on-disk 20xxincyallagi.csv headers.
#   `acs` / `popest` are templates -- confirm column names against real headers
#   before trusting them in production.
# ===========================================================================
@dataclass
class SurveySpec:
    survey: str                       # short code -> partition value (acs/irs/...)
    delimiter: str = ","
    geoid_cols: dict = field(default_factory=dict)  # how to build the geoid
    skip_cols: set = field(default_factory=set)     # non-measure columns
    dim_cols: tuple = ()              # columns folded into attribute_key as @dim=val
    encoding: str = "utf-8"
    member_suffixes: tuple = (".csv", ".txt")


SPECS: dict[str, SurveySpec] = {
    # IRS SOI county income -- STATEFIPS+COUNTYFIPS -> 5-digit; agi_stub is a
    # within-(geoid,year) income bracket dimension folded into the key.
    "irs_county": SurveySpec(
        survey="irs",
        geoid_cols={"statefips": "STATEFIPS", "countyfips": "COUNTYFIPS"},
        skip_cols={"STATEFIPS", "STATE", "COUNTYFIPS", "COUNTYNAME", "agi_stub"},
        dim_cols=("agi_stub",),
    ),
    # ACS wide data profile -- prefixed GEO_ID, estimate/MOE columns are measures.
    "acs": SurveySpec(
        survey="acs",
        geoid_cols={"raw": "GEO_ID"},
        skip_cols={"GEO_ID", "NAME", "Geographic Area Name"},
    ),
    # Population estimates -- STATE+COUNTY component columns.
    "popest": SurveySpec(
        survey="popest",
        geoid_cols={"statefips": "STATE", "countyfips": "COUNTY"},
        skip_cols={"SUMLEV", "REGION", "DIVISION", "STATE", "COUNTY",
                   "STNAME", "CTYNAME"},
    ),
}

COPY_COLS = ("geoid", "year", "source_survey", "summary_level",
             "attribute_key", "attribute_value", "numeric_value",
             "data_type", "source", "collection_date")


# ===========================================================================
# Pipeline
# ===========================================================================
class CensusIngestPipeline:
    def __init__(self, dsn: str | None = None, batch_rows: int = 200_000):
        self.dsn = dsn or self._dsn_from_env()
        self.batch_rows = batch_rows
        self._s3 = None  # lazily created only if an --s3-key is used

    @staticmethod
    def _dsn_from_env() -> str:
        return (
            f"postgresql://{os.getenv('POSTGRES_USER', 'postgres')}:"
            f"{os.getenv('POSTGRES_PASSWORD', '')}@"
            f"{os.getenv('POSTGRES_HOST', 'localhost')}:"
            f"{os.getenv('POSTGRES_PORT', '5432')}/"
            f"{os.getenv('POSTGRES_DB', 'postgres')}"
        )

    @property
    def s3(self):
        if self._s3 is None:
            import boto3
            from botocore.config import Config
            self._s3 = boto3.client(
                "s3",
                endpoint_url=os.getenv("S3_ENDPOINT_URL", "https://s3.us-east-1.wasabisys.com"),
                aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
                aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
                region_name=os.getenv("AWS_DEFAULT_REGION", "us-east-1"),
                config=Config(signature_version="s3v4"),
            )
        return self._s3

    # ---- streaming readers: never extract gigabytes to disk -----------------
    def _rows_from_bytes(self, blob: bytes, name: str, spec: SurveySpec) -> Iterator[dict]:
        """Yield dict rows from a blob that is either a zip archive or a bare
        CSV/TXT. Zip members are streamed via ZipFile.open (no extractall)."""
        if blob[:2] == b"PK":  # zip magic
            with zipfile.ZipFile(io.BytesIO(blob)) as zf:
                for info in zf.infolist():
                    if info.is_dir() or not info.filename.lower().endswith(spec.member_suffixes):
                        continue
                    with zf.open(info, "r") as member:
                        text = io.TextIOWrapper(member, encoding=spec.encoding,
                                                errors="replace", newline="")
                        yield from csv.DictReader(text, delimiter=spec.delimiter)
        else:
            text = io.StringIO(blob.decode(spec.encoding, errors="replace"))
            yield from csv.DictReader(text, delimiter=spec.delimiter)

    def iter_rows(self, *, path: str | None, s3_key: str | None,
                  spec: SurveySpec) -> Iterator[dict]:
        if path:
            with open(path, "rb") as fh:
                yield from self._rows_from_bytes(fh.read(), os.path.basename(path), spec)
        else:
            blob = self.s3.get_object(
                Bucket=os.getenv("S3_BUCKET_NAME", "geoagent-dev-s3"), Key=s3_key
            )["Body"].read()
            yield from self._rows_from_bytes(blob, os.path.basename(s3_key), spec)

    # ---- row -> EAV cell tuples --------------------------------------------
    def explode_row(self, row: dict, spec: SurveySpec, year: int,
                    source_label: str) -> Iterator[tuple]:
        gargs = {k: (row.get(col, "") or "") for k, col in spec.geoid_cols.items()}
        ng = normalize_geoid(**gargs)
        if ng is None:
            return
        dims = {d: (row.get(d, "") or "").strip() for d in spec.dim_cols if row.get(d)}
        dim_suffix = ("@" + ";".join(f"{k}={v}" for k, v in sorted(dims.items()))) if dims else ""
        coll = date(year, 1, 1)
        for col, val in row.items():
            if col is None or col in spec.skip_cols or col in spec.dim_cols:
                continue
            if val is None:
                continue
            val = val.strip()
            if val == "":
                continue
            key = f"{spec.survey}:{col.lower().strip()}{dim_suffix}"[:128]
            num = coerce_numeric(val)
            yield (ng.geoid, year, spec.survey, ng.summary_level, key, val[:65535],
                   num, "numeric" if num is not None else "text",
                   source_label[:128], coll)

    # ---- staging + merge SQL ------------------------------------------------
    _STAGING_DDL = """
        CREATE UNLOGGED TABLE IF NOT EXISTS _stg_geographic_data (
            geoid varchar(64), year integer, source_survey varchar(16),
            summary_level varchar(3), attribute_key varchar(128),
            attribute_value text, numeric_value numeric(20,8),
            data_type varchar(32), source varchar(128), collection_date date);
        TRUNCATE _stg_geographic_data;
    """

    _MERGE_SQL = """
        WITH deduped AS (
            -- collapse duplicate cells within this batch (last write wins)
            SELECT DISTINCT ON (source_survey, year, geoid, attribute_key) *
            FROM _stg_geographic_data
            ORDER BY source_survey, year, geoid, attribute_key, ctid DESC
        ),
        validated AS (
            SELECT d.*, (b.geoid IS NOT NULL) AS has_boundary
            FROM   deduped d
            LEFT   JOIN public.geographic_boundaries b
                   ON b.geoid = d.geoid AND b.year = d.year
        ),
        ins_main AS (
            INSERT INTO public.geographic_data
                (geoid, year, source_survey, summary_level, attribute_key,
                 attribute_value, numeric_value, data_type, source, collection_date)
            SELECT geoid, year, source_survey, summary_level, attribute_key,
                   attribute_value, numeric_value, data_type, source, collection_date
            FROM   validated WHERE has_boundary
            ON CONFLICT (source_survey, year, geoid, attribute_key) DO UPDATE
                SET attribute_value = EXCLUDED.attribute_value,
                    numeric_value   = EXCLUDED.numeric_value,
                    data_type       = EXCLUDED.data_type,
                    updated_at      = now()
            RETURNING 1
        ),
        ins_unmatched AS (
            INSERT INTO public.geographic_data_unmatched
                (geoid, year, source_survey, summary_level, attribute_key,
                 attribute_value, numeric_value, data_type, source, collection_date)
            SELECT geoid, year, source_survey, summary_level, attribute_key,
                   attribute_value, numeric_value, data_type, source, collection_date
            FROM   validated WHERE NOT has_boundary
            ON CONFLICT (source_survey, year, geoid, attribute_key) DO NOTHING
            RETURNING 1
        )
        SELECT (SELECT count(*) FROM ins_main),
               (SELECT count(*) FROM ins_unmatched);
    """

    _CATALOG_SQL = """
        INSERT INTO public.attribute_catalog
            (attribute_key, survey, native_dtype, first_seen_year, last_seen_year)
        SELECT attribute_key, source_survey,
               max(data_type), min(year), max(year)
        FROM _stg_geographic_data
        GROUP BY attribute_key, source_survey
        ON CONFLICT (attribute_key) DO UPDATE
            SET first_seen_year = least(attribute_catalog.first_seen_year, EXCLUDED.first_seen_year),
                last_seen_year  = greatest(attribute_catalog.last_seen_year, EXCLUDED.last_seen_year);
    """

    def _copy_batch(self, cur, rows: list[tuple]) -> None:
        buf = io.StringIO()
        w = csv.writer(buf, delimiter="\t", lineterminator="\n")
        for r in rows:
            w.writerow(["\\N" if c is None else c for c in r])
        buf.seek(0)
        cur.copy_expert(
            sql.SQL("COPY _stg_geographic_data ({}) FROM STDIN WITH "
                    "(FORMAT text, DELIMITER E'\\t', NULL '\\N')")
               .format(sql.SQL(", ").join(map(sql.Identifier, COPY_COLS))),
            buf,
        )

    # ---- public entry points ------------------------------------------------
    def ingest(self, *, survey: str, year: int | None, path: str | None = None,
               s3_key: str | None = None, dry_run: bool = False) -> dict:
        if survey not in SPECS:
            raise SystemExit(f"unknown survey '{survey}'. known: {sorted(SPECS)}")
        spec = SPECS[survey]
        src_name = os.path.basename(path or s3_key or "")
        year = year or year_from_name(src_name)
        if year is None:
            raise SystemExit("could not determine year; pass --year")
        source_label = f"{spec.survey} {year} ({src_name})"

        if dry_run:
            cells = geos = bad_geo = 0
            for row in self.iter_rows(path=path, s3_key=s3_key, spec=spec):
                tuples = list(self.explode_row(row, spec, year, source_label))
                if tuples:
                    cells += len(tuples)
                    geos += 1
                else:
                    bad_geo += 1
            return {"mode": "dry-run", "rows_with_geoid": geos,
                    "rows_skipped_no_geoid": bad_geo, "cells": cells}

        conn = psycopg2.connect(self.dsn)
        staged = merged = unmatched = 0
        try:
            conn.autocommit = False
            with conn.cursor() as cur:
                cur.execute(self._STAGING_DDL)
                batch: list[tuple] = []
                for row in self.iter_rows(path=path, s3_key=s3_key, spec=spec):
                    batch.extend(self.explode_row(row, spec, year, source_label))
                    if len(batch) >= self.batch_rows:
                        self._copy_batch(cur, batch); staged += len(batch); batch.clear()
                if batch:
                    self._copy_batch(cur, batch); staged += len(batch)
                cur.execute("ANALYZE _stg_geographic_data;")
                cur.execute(self._CATALOG_SQL)
                cur.execute(self._MERGE_SQL)
                merged, unmatched = cur.fetchone()
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        return {"mode": "ingest", "source": source_label, "staged_cells": staged,
                "merged": merged, "unmatched": unmatched}

    def replay_unmatched(self) -> dict:
        replay = """
            WITH promotable AS (
                DELETE FROM public.geographic_data_unmatched u
                USING public.geographic_boundaries b
                WHERE b.geoid = u.geoid AND b.year = u.year
                RETURNING u.geoid, u.year, u.source_survey, u.summary_level,
                          u.attribute_key, u.attribute_value, u.numeric_value,
                          u.data_type, u.source, u.collection_date
            )
            INSERT INTO public.geographic_data
                (geoid, year, source_survey, summary_level, attribute_key,
                 attribute_value, numeric_value, data_type, source, collection_date)
            SELECT * FROM promotable
            ON CONFLICT (source_survey, year, geoid, attribute_key) DO NOTHING;
        """
        conn = psycopg2.connect(self.dsn)
        try:
            conn.autocommit = False
            with conn.cursor() as cur:
                cur.execute(replay)
                promoted = cur.rowcount
            conn.commit()
        finally:
            conn.close()
        return {"promoted": promoted}


# ===========================================================================
# CLI
# ===========================================================================
def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    ing = sub.add_parser("ingest", help="ingest one survey file (local or S3)")
    ing.add_argument("--survey", required=True, choices=sorted(SPECS))
    ing.add_argument("--year", type=int, default=None)
    src = ing.add_mutually_exclusive_group(required=True)
    src.add_argument("--path", help="local path to .csv/.txt/.zip")
    src.add_argument("--s3-key", help="S3 object key")
    ing.add_argument("--dry-run", action="store_true")
    ing.add_argument("--batch-rows", type=int, default=200_000)

    sub.add_parser("replay-unmatched", help="promote unmatched cells now matchable")

    args = p.parse_args(argv)

    if args.cmd == "ingest":
        pipe = CensusIngestPipeline(batch_rows=args.batch_rows)
        result = pipe.ingest(survey=args.survey, year=args.year, path=args.path,
                             s3_key=args.s3_key, dry_run=args.dry_run)
    else:
        result = CensusIngestPipeline().replay_unmatched()

    for k, v in result.items():
        print(f"{k:>22}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
