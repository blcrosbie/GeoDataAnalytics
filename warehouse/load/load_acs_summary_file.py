#!/usr/bin/env python3
"""
Load one ACS 5-year table-based Summary File vintage.

  lake : every table -> Parquet at
         <lake>/curated/acs/vintage=<Y>/table=<id>/part-0.parquet
         (all geographies, estimates + MOEs, raw values incl. Census sentinels)
  core : CORE_TABLES estimates at MAP_LEVELS -> public.geographic_data (acs/<Y>)
         keyed 'acs:<table>_e<line>', validate-joined to geographic_boundaries;
         cells with no boundary go to geographic_data_unmatched.

The 5YRData.zip (12 GB, ~48 GB inside) is read in place from the Wasabi mount.
Members are read one at a time and each is streamed in BLOCK-sized record
batches (pyarrow's incremental CSV reader), written to Parquet / COPYed to
Postgres batch by batch, so memory stays at one batch, never one whole table.

core --defer-indexes: detach geographic_data_acs_<Y>, drop every index but the
primary key (the upsert's conflict target), load, then re-attach (Postgres
rebuilds the dropped indexes in one sorted pass). Much faster than maintaining
every index per row.
A run killed while detached resumes on the next run; the year is invisible to
queries until it re-attaches.

Env:   WAREHOUSE_DSN   libpq DSN of the warehouse (core step)
Usage: python load_acs_summary_file.py --year 2024 core [--defer-indexes]
       python load_acs_summary_file.py --year 2024 lake --staging /big/disk/dir [--resume]
"""

import argparse
import csv
import io
import logging
import os
import subprocess
import sys
import tempfile
import time
import zipfile
from collections.abc import Iterator

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.csv as pacsv
import pyarrow.parquet as pq
import psycopg2

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("acs")

HERE = os.path.dirname(os.path.abspath(__file__))
MOUNT = os.path.join(HERE, "..", "..", "data", "geoagent-dev-s3")
SF_DIR = "origin/census_surveys/acs/summary_file/{y}"
LAKE_REMOTE = "wasabi:geoagent-dev-s3/curated/acs/vintage={y}"

# Map layers loaded into Postgres. Everything else stays lake-only.
MAP_LEVELS = {"040", "050", "140", "150", "310", "500", "610", "620"}

# Headline tables for the map (~340 estimate columns). Wide detail tables
# (occupation, industry, language, insurance, disability, veterans, full
# poverty-by-age) are lake-only; query them via pg_duckdb.
CORE_TABLES = [
    "b01001", "b01002", "b01003",            # age/sex, median age, total population
    "b02001", "b03002",                      # race, hispanic origin by race
    "b05012",                                # nativity
    "b07003",                                # mobility (moved in past year)
    "b08301", "b08303",                      # means of transport, travel time
    "b09001", "b11001", "b25010",            # children, household type, household size
    "b15003",                                # educational attainment
    "c16002",                                # limited-English households
    "c17002",                                # income-to-poverty ratio
    "b19001", "b19013", "b19083", "b19301",  # income brackets, median HH, Gini, per capita
    "b22010",                                # SNAP
    "b23025",                                # employment status
    "b25001", "b25002", "b25003", "b25004",  # housing units, occupancy, tenure, vacancy
    "b25024", "b25034", "b25035",            # structure type, year built, median year built
    "b25058", "b25064", "b25070", "b25071",  # rents, rent burden
    "b25075", "b25077", "b25088", "b25105",  # home value, owner costs
    "b28002",                                # internet subscription
]

# Census annotation sentinels in the estimate columns (-666666666 = not
# computable, etc.). Kept raw in the lake; skipped in Postgres.
SENTINEL_BELOW = -100_000_000

BLOCK = 32 << 20  # bytes of CSV text per record batch


def sf_path(year: int, root: str, *candidates: str) -> str:
    """First existing file among layouts: table-based-SF/ (2021+) or prototype/ (2020)."""
    base = os.path.join(root, SF_DIR.format(y=year))
    for c in candidates:
        path = os.path.join(base, c.format(y=year))
        if os.path.exists(path):
            return path
    raise SystemExit(f"ACS {year}: none of {candidates} under {base}")


def open_zip(year: int, root: str) -> zipfile.ZipFile:
    return zipfile.ZipFile(sf_path(year, root, "table-based-SF/data/5YRData/5YRData.zip",
                                   "prototype/5YRData/5YRData.zip"))


def members(zf: zipfile.ZipFile) -> dict[str, zipfile.ZipInfo]:
    return {i.filename.rsplit("-", 1)[1][:-4].lower(): i
            for i in zf.infolist() if i.filename.endswith(".dat")}


def iter_batches(zf: zipfile.ZipFile, info: zipfile.ZipInfo) -> Iterator[pa.RecordBatch]:
    """Pipe-delimited GEO_ID|<T>_E001|<T>_M001|... -> arrow batches, with parsed geo parts."""
    with zf.open(info) as f:
        header = f.readline().decode().strip().split("|")
    types = {c: pa.float64() for c in header if c != "GEO_ID"}
    types["GEO_ID"] = pa.string()
    with zf.open(info) as f:
        reader = pacsv.open_csv(
            f,
            read_options=pacsv.ReadOptions(block_size=BLOCK, use_threads=False),
            parse_options=pacsv.ParseOptions(delimiter="|"),
            convert_options=pacsv.ConvertOptions(column_types=types,
                                                 null_values=["", "null", "NULL"]),
        )
        for b in reader:
            g = b.column("GEO_ID")
            parts = pc.split_pattern(g, "US", max_splits=1)
            yield pa.RecordBatch.from_arrays(
                b.columns + [pc.utf8_slice_codeunits(g, 0, 3),
                             pc.utf8_slice_codeunits(g, 5, 7),
                             pc.list_element(parts, 1)],
                names=b.schema.names + ["sumlev", "component", "geoid"])


def parquet_ok(path: str) -> bool:
    try:
        pq.read_metadata(path)
        return True
    except Exception:
        return False


# ---- lake -------------------------------------------------------------------
def run_lake(zf, year: int, staging: str, tables: list[str] | None, resume: bool) -> None:
    by = members(zf)
    out_root = os.path.join(staging, f"vintage={year}")
    for name in sorted(tables or by):
        d = os.path.join(out_root, f"table={name}")
        out = os.path.join(d, "part-0.parquet")
        if resume and parquet_ok(out):
            continue
        t0 = time.time()
        os.makedirs(d, exist_ok=True)
        rows, writer = 0, None
        # Write to .tmp and rename, so a killed run never leaves a truncated part.
        for b in iter_batches(zf, by[name]):
            if writer is None:
                writer = pq.ParquetWriter(out + ".tmp", b.schema, compression="zstd")
            writer.write_batch(b)
            rows += b.num_rows
        if writer is not None:
            writer.close()
            os.replace(out + ".tmp", out)
        log.info("lake %s %s: %d rows in %.1fs", year, name, rows, time.time() - t0)
    log.info("uploading %s -> %s", out_root, LAKE_REMOTE.format(y=year))
    subprocess.run(["rclone", "move", "--transfers", "16", out_root,
                    LAKE_REMOTE.format(y=year)], check=True)


# ---- core -------------------------------------------------------------------
STAGE_DDL = """
CREATE TEMP TABLE IF NOT EXISTS _stg_acs (
    geoid varchar(64), summary_level varchar(3), attribute_key varchar(128),
    numeric_value numeric(24,8));
TRUNCATE _stg_acs;
"""

MERGE_SQL = """
WITH v AS (
    SELECT s.*, (b.geoid IS NOT NULL) AS has_boundary
    FROM _stg_acs s
    LEFT JOIN public.geographic_boundaries b
           ON b.summary_level = s.summary_level AND b.geoid = s.geoid AND b.year = %(y)s
),
ins AS (
    INSERT INTO {target}
        ({id_col}geoid, year, source_survey, summary_level, attribute_key,
         numeric_value, data_type, source, collection_date)
    SELECT {id_val}geoid, %(y)s, 'acs', summary_level, attribute_key,
           numeric_value, 'numeric', %(src)s, %(cd)s
    FROM v WHERE has_boundary
    ON CONFLICT (source_survey, year, summary_level, geoid, attribute_key) DO UPDATE
        SET numeric_value = EXCLUDED.numeric_value, updated_at = now()
    RETURNING 1
),
unm AS (
    INSERT INTO public.geographic_data_unmatched
        (geoid, year, source_survey, summary_level, attribute_key,
         numeric_value, data_type, source, collection_date)
    SELECT geoid, %(y)s, 'acs', summary_level, attribute_key,
           numeric_value, 'numeric', %(src)s, %(cd)s
    FROM v WHERE NOT has_boundary
    ON CONFLICT (source_survey, year, summary_level, geoid, attribute_key) DO NOTHING
    RETURNING 1
)
SELECT (SELECT count(*) FROM ins), (SELECT count(*) FROM unm);
"""


def load_shells(year: int, root: str) -> dict[str, tuple[str, str, str]]:
    """'B19013_001' -> (label, table title, universe)."""
    path = sf_path(year, root, "table-based-SF/documentation/ACS{y}5YR_Table_Shells.txt",
                   "prototype/ACS{y}_Table_Shells.csv")
    out = {}
    with open(path, encoding="utf-8", errors="replace", newline="") as f:
        if path.endswith(".txt"):
            next(f)
            for line in f:
                p = line.rstrip("\n").split("|")
                if len(p) >= 7 and p[3]:
                    out[p[3].upper()] = (p[4], p[5], p[6])
        else:
            # 2020 prototype CSV: Table ID,Line,Unique ID,Stub. A table's title and
            # "Universe: ..." rows have no Unique ID and precede its lines.
            title = universe = ""
            for row in csv.reader(f):
                if len(row) < 4 or row[0] == "Table ID":
                    continue
                uid, stub = row[2].strip(), row[3].strip()
                if not uid:
                    if stub.lower().startswith("universe:"):
                        universe = stub.split(":", 1)[1].strip()
                    elif stub:
                        title, universe = stub, ""
                    continue
                out[uid.upper()] = (stub, title, universe)
    return out


def catalog_row(col: str, shells: dict, year: int) -> tuple:
    """'B19013_E001' -> attribute_catalog row, labelled from the table shells."""
    label, title, universe = shells.get(col.replace("_E", "_"), ("", "", ""))
    unit = "dollars" if "dollars" in title.lower() else None
    return ("acs:" + col.lower(), f"{title}: {label}".strip(": "), universe or None,
            unit, year, year)


def core_cells(t: pa.RecordBatch) -> io.StringIO:
    """Wide estimates at MAP_LEVELS -> long TSV (geoid, level, key, value)."""
    keep = pc.and_(pc.is_in(t["sumlev"], pa.array(sorted(MAP_LEVELS))),
                   pc.equal(t["component"], "00"))
    t = t.filter(keep)
    est = [c for c in t.column_names if "_E" in c]
    buf = io.StringIO()
    geoid = t["geoid"].to_pylist()
    lvl = t["sumlev"].to_pylist()
    for c in est:
        key = "acs:" + c.lower()
        for g, l, v in zip(geoid, lvl, t[c].to_pylist()):
            if v is None or v <= SENTINEL_BELOW:
                continue
            buf.write(f"{g}\t{l}\t{key}\t{repr(v) if v != int(v) else int(v)}\n")
    buf.seek(0)
    return buf


def detach_partition(conn, year: int) -> str:
    """Detach geographic_data_acs_<year> and drop all indexes but its primary key."""
    part = f"public.geographic_data_acs_{year}"
    with conn.cursor() as cur:
        cur.execute("SELECT EXISTS (SELECT 1 FROM pg_inherits WHERE inhrelid = %s::regclass)",
                    (part,))
        if cur.fetchone()[0]:
            cur.execute(f"ALTER TABLE public.geographic_data_acs DETACH PARTITION {part}")
        cur.execute("SELECT i.indexrelid::regclass::text FROM pg_index i WHERE i.indrelid = "
                    "%s::regclass AND NOT EXISTS (SELECT 1 FROM pg_constraint c "
                    "WHERE c.conindid = i.indexrelid)", (part,))
        for (idx,) in cur.fetchall():
            cur.execute(f"DROP INDEX {idx}")
    conn.commit()
    log.info("core %s: detached %s, deferred its indexes", year, part)
    return part


def attach_partition(conn, year: int, part: str) -> None:
    """Re-attach; Postgres builds the missing parent indexes on the partition."""
    t0 = time.time()
    with conn.cursor() as cur:
        cur.execute("SET maintenance_work_mem = '512MB'")
        cur.execute(f"ALTER TABLE public.geographic_data_acs ATTACH PARTITION {part} "
                    f"FOR VALUES FROM ({year}) TO ({year + 1})")
        cur.execute(f"ANALYZE {part}")
    conn.commit()
    log.info("core %s: re-attached %s, indexes rebuilt in %.0fs", year, part, time.time() - t0)


def run_core(zf, year: int, root: str, tables: list[str] | None, defer_indexes: bool) -> None:
    by = members(zf)
    shells = load_shells(year, root)
    src, cd = f"ACS {year} 5-year", f"{year}-12-31"
    conn = psycopg2.connect(os.environ.get("WAREHOUSE_DSN") or sys.exit("set WAREHOUSE_DSN"))
    if defer_indexes:
        # A detached partition loses the identity default, so draw ids from the parent's sequence.
        part = detach_partition(conn, year)
        merge = MERGE_SQL.format(target=part, id_col="id, ", id_val="nextval(%(seq)s), ")
        with conn.cursor() as cur:
            cur.execute("SELECT pg_get_serial_sequence('public.geographic_data', 'id')")
            seq = cur.fetchone()[0]
    else:
        merge = MERGE_SQL.format(target="public.geographic_data", id_col="", id_val="")
        seq = None
    tot_in = tot_un = 0
    for name in tables or CORE_TABLES:
        t0 = time.time()
        est_cols = None
        with conn.cursor() as cur:
            cur.execute("SET work_mem = '512MB'")
            cur.execute(STAGE_DDL)
            for b in iter_batches(zf, by[name]):
                est_cols = est_cols or [c for c in b.schema.names if "_E" in c]
                cur.copy_expert("COPY _stg_acs FROM STDIN", core_cells(b))
            cur.execute("ANALYZE _stg_acs")
            cur.execute(merge, {"y": year, "src": src, "cd": cd, "seq": seq})
            n_in, n_un = cur.fetchone()
            cur.executemany("""
                INSERT INTO public.attribute_catalog
                    (attribute_key, survey, label, universe, unit, native_dtype,
                     first_seen_year, last_seen_year)
                VALUES (%s, 'acs', %s, %s, %s, 'numeric', %s, %s)
                ON CONFLICT (attribute_key) DO UPDATE
                   SET label = CASE WHEN EXCLUDED.last_seen_year >= attribute_catalog.last_seen_year
                                    THEN EXCLUDED.label ELSE attribute_catalog.label END,
                       universe = CASE WHEN EXCLUDED.last_seen_year >= attribute_catalog.last_seen_year
                                       THEN EXCLUDED.universe ELSE attribute_catalog.universe END,
                       first_seen_year = least(attribute_catalog.first_seen_year, EXCLUDED.first_seen_year),
                       last_seen_year  = greatest(attribute_catalog.last_seen_year, EXCLUDED.last_seen_year)
            """, [catalog_row(c, shells, year) for c in est_cols or []])
        conn.commit()
        tot_in += n_in; tot_un += n_un
        log.info("core %s %s: %d cells loaded, %d unmatched in %.0fs",
                 year, name, n_in, n_un, time.time() - t0)
    if defer_indexes:
        attach_partition(conn, year, part)
    conn.close()
    log.info("core %s done: %d loaded, %d unmatched", year, tot_in, tot_un)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--year", type=int, required=True)
    p.add_argument("--root", default=MOUNT, help="Wasabi mount (or local mirror) root")
    p.add_argument("--tables", help="comma list of table ids (default: core list / all)")
    sub = p.add_subparsers(dest="cmd", required=True)
    co = sub.add_parser("core")
    co.add_argument("--defer-indexes", action="store_true",
                    help="detach the year's partition and rebuild its indexes after the load")
    lk = sub.add_parser("lake")
    lk.add_argument("--staging", default=None, help="local dir for Parquet before upload")
    lk.add_argument("--resume", action="store_true",
                    help="skip tables whose Parquet is already complete in --staging")
    args = p.parse_args(argv)

    tables = [t.strip().lower() for t in args.tables.split(",")] if args.tables else None
    zf = open_zip(args.year, args.root)
    if args.cmd == "core":
        run_core(zf, args.year, args.root, tables, args.defer_indexes)
    else:
        staging = args.staging or tempfile.mkdtemp(prefix=f"acs{args.year}_")
        run_lake(zf, args.year, staging, tables, args.resume)


if __name__ == "__main__":
    main()
