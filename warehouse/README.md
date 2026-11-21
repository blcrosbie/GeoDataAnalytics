# warehouse/

**Status (2026-11-13): there is no database server any more.** The Hetzner
node and its PostgreSQL 17 + PostGIS + pg_duckdb service were shut down to cut
cost. The GeoParquet lake on **AWS S3** (us-east-2, read by GeoAgent) is the
system of record and the only copy; the Wasabi mirror and its raw `origin/`
archive were dropped on 2026-11-19. Scripts download each source from its
publisher into local staging, clean and transform it there, and upload only
the curated result. Raw files are never uploaded, since they are free to
fetch again. Everything is queried in place with DuckDB.

```
 census.gov / USDA / LEHD / FCC ──► local staging (raw files, deleted after)
                                   │
   scripts/tiger_to_lake.py ───────┤  DuckDB spatial + h3, no database
   scripts/get_reference_data.py ──┤
   load/load_acs_summary_file.py ──┘  (lake step)
                                   ▼
                          AWS S3 curated/
                                   │
   DuckDB (notebooks, scripts, LLM agent) · GeoAgent PMTiles build · Sedona
```

## What's live in this folder

| Path | What |
|---|---|
| `lake_targets.py` | The lake target (AWS S3) from env: upload with sha256, list, DuckDB secrets. Every writer goes through it. |
| `load/load_acs_summary_file.py` | ACS 5-year table-based Summary File → `curated/acs/` Parquet (the `lake` step). |
| `.env.example` | The `LAKE_*` variables every writer reads. |

Boundary partitions are built by [`../scripts/tiger_to_lake.py`](../scripts/tiger_to_lake.py).
Everything else here (`docker/`, `init-db/`, `migrations/`, `load/load_tiger_boundaries.py`,
`load/build_crosswalk.sql`, the exporter's `boundaries`/`attributes`/`verify`) belongs
to the retired Postgres service and is kept for reference only. See
[Retired: the Postgres warehouse](#retired-the-postgres-warehouse).

## Building the lake

```bash
python3 -m venv .venv && .venv/bin/pip install -r export/requirements.txt requests
set -a; . ./.env; set +a          # LAKE_TARGETS=aws, LAKE_AWS_* (see .env.example)

# boundaries: TIGER zips -> curated/boundaries/boundary_type=<T>/year=<Y>/ on every target
.venv/bin/python ../scripts/tiger_to_lake.py --year 2025 --layers zcta --dry-run   # where the zips come from
.venv/bin/python ../scripts/tiger_to_lake.py --year 2025 --layers zcta,uac,csa,metdiv,cousub
.venv/bin/python ../scripts/tiger_to_lake.py --year 2020,2021,2022,2023,2024 --layers zcta

# reference tables and ACS
.venv/bin/python ../scripts/get_reference_data.py gazetteer rel ruca --year 2025
.venv/bin/python ../scripts/get_reference_data.py lodes --lodes-year 2024 --od
.venv/bin/python ../scripts/get_reference_data.py lodes --lodes-year 2021 --states mi --od   # MI lags
.venv/bin/python ../scripts/lodes_rollup_to_lake.py                    # jobs by tract/bg/county/place/zcta/cbsa/sld + county flows
.venv/bin/python load/load_acs_summary_file.py --year 2024 --root /big/disk/acs-sf lake --staging /big/disk/tmp   # 2020+ (downloads 12 GB once)
.venv/bin/python ../scripts/acs_api_to_lake.py --years 2014-2019                         # older releases (CENSUS_API_KEY)

# derived layers and media
.venv/bin/python ../scripts/urbanicity_to_lake.py                      # urban/suburban/exurban/rural
.venv/bin/python ../scripts/fcc_to_lake.py all --services core         # stations, contours, coverage (~2.5 h)
```

`tiger_to_lake.py` downloads the raw zips from census.gov (or reads them
from a local `--root` tree) and deletes them once their partition is
published. It skips partitions already in the lake unless `--force` is
passed. `load_acs_summary_file.py` downloads the 12 GB Summary File zip from
census.gov into `--root` once and keeps it there for reruns. Each partition is checked before it is published: no duplicate
GEOIDs, and the row count must match the source feature count. Vintage-suffixed
layers (`zcta520`, `uac20`, `puma20`, `cd119`) take the highest suffix, carry
it in `boundary_type` (`ZCTA520`, `UAC20`), and read `GEOID20`/`NAME20` as
`GEOID`/`NAME`. The output schema is identical to what the Postgres exporter
wrote. That was checked against STATE 2025: same columns, names, subtypes
and `h3_r5`, with bboxes within 1 m.

GEOIDs are only unique within one layer and vintage: county `01001`, SLDU
`01001` and ZCTA `01001` are different places. Always key on
`(boundary_type, year, geoid)`, which the partition path gives you.

## Lake layout (`s3://<bucket>/curated/`)

```
boundaries/boundary_type=<STATE|COUNTY|TRACT|BG|...>/year=<YYYY>/part-0.parquet   GeoParquet, EPSG:4326
attributes/boundary_type=<...>/year=<YYYY>/part-0.parquet                       EAV facts joined to boundary type
acs/vintage=<YYYY>/table=<b19013|...>/part-0.parquet                             ACS 5-year, one wide file per table
reference/gazetteer|rel2020|ruca|lodes/...                                       see ../scripts/get_reference_data.py
derived/urbanicity/vintage=<YYYY>/level=<tract|county|cbsa|zcta|place>/          class + population mix
derived/lodes/year=<YYYY>/level=<tract|bg|county|place|zcta|cbsa|sldu|sldl>/     jobs, resident workers
derived/lodes/year=<YYYY>/level=county_flow/                                     county-to-county commute flows
media/fcc/stations/snapshot=<DATE>/                                              every US FM/TV/AM record, licensee
media/fcc/contours/snapshot=<DATE>/band=<fm|tv|am>/                              service contour polygons (GeoParquet)
media/fcc/coverage/snapshot=<DATE>/level=<station|county|cbsa|zcta|tract>/       population covered per station
```

`attributes/` was exported from the retired Postgres EAV tables and is frozen;
use `acs/` for anything new.

ACS vintages 2020+ come from the table-based Summary File and hold every
summary level. 2014-2019 were backfilled from the Census API
(`acs_api_to_lake.py`) for GeoAgent's 12 tables and 8 levels (us, state,
county, tract, block group, place, CBSA, ZCTA), in the same wide layout.
Up to 2019, tracts, block groups and ZCTAs are **2010-census geographies**:
same-looking GEOIDs, different shapes. Compare them across 2019 -> 2020 only
through a crosswalk. Non-overlapping windows give the clean trend comparisons:
2019 vs 2024 (5-year) and 2014 vs 2024 (10-year).

Urbanicity (`urbanicity_to_lake.py`) classifies each 2020 tract from USDA
RUCA 2020 plus ACS household density, with Kolko's 2,213 and 102 households
per square mile as the cut points: urban, suburban, exurban (metro
commuting fringe, low-density metro, small cities inside a metro) and rural.
Other levels carry the population mix and the plurality class. Rules are in
the script's docstring.

FCC contours (`fcc_to_lake.py`) are the protected service areas computed by
the FCC contour API: FM 60/54 dBu, TV noise-limited, AM 2 mV/m. Coverage
counts a tract as covered when its interior point is inside the contour.

Boundary files carry scalar spatial keys next to the geometry: `h3_r5` and
`h3_r7` (the cell of the point-on-surface) and the bbox `xmin/ymin/xmax/ymax`.
Rows are sorted by `h3_r5`, so Parquet row-group statistics prune on them.
**Filter on these first and touch geometry last.** Spatial predicates are not
pushed down to S3.

Raw source files are not in the lake. Read them from the publisher
(DuckDB's `read_csv` takes an `https://www2.census.gov/...` URL) or rerun the
script that builds the curated table.

## Reading the lake

Any DuckDB, GeoPandas, Sedona or QGIS client with a read key can use the files:

```python
import duckdb
con = duckdb.connect(); con.install_extension("spatial"); con.load_extension("spatial")
con.execute("CREATE SECRET (TYPE s3, PROVIDER credential_chain, REGION 'us-east-2')")
con.sql("""SELECT name, ST_Area_Spheroid(geometry)/1e6 AS km2
           FROM read_parquet('s3://<bucket>/curated/boundaries/*/*/*.parquet', hive_partitioning=true)
           WHERE boundary_type='STATE' AND year=2025""").show()
```

## Retired: the Postgres warehouse

What follows describes the PG17 + PostGIS + h3 + pg_duckdb service that ran
on Hetzner until 2026-11-13. It is kept so the setup can be rebuilt if a
low-latency serving database is ever needed again
(see `../docs/GEO_FOUNDATION_ARCHITECTURE.md`).

The central geo database. It's PostgreSQL 17 with PostGIS, h3 and
[pg_duckdb](https://github.com/duckdb/pg_duckdb), running on the Hetzner box. It
holds hot data as native PostGIS tables. Everything else lives as GeoParquet in
the Wasabi bucket and is queried in place through DuckDB embedded in Postgres.

This is the self-hosted equivalent of Aurora PostgreSQL's `aurora_analytics`
extension (also DuckDB inside Postgres). Aurora only reads AWS S3/Glue with an
IAM role, so it can't sit in front of a Wasabi bucket from Hetzner. pg_duckdb
can, because Wasabi speaks the S3 API and charges no egress.

```
            ┌──────────────── Hetzner ────────────────┐
 notebooks ─┤  Postgres 17 :5434                       │
 scripts   ─┤   ├─ public.*  native PostGIS (hot)      │
 other apps─┤   └─ lake.*    views ─► pg_duckdb ───────┼──► s3://<bucket>/curated/*.parquet  (Wasabi)
            └──────────────────────────────────────────┘
 laptops / Sedona / GeoPandas ───── read the same Parquet directly, no server needed
```

### Layout

| Path | What |
|---|---|
| `docker/Dockerfile` | `pgduckdb/pgduckdb:17-v1.1.1` + PostGIS + h3 |
| `docker-compose.yml` | The service (port `5434`, DuckDB memory/threads capped) |
| `init-db/00-05b` | Schema: extensions and roles, `borders`/`hexes`, `geographic_boundaries`, partitioned EAV `geographic_data`, `boundary_crosswalk` |
| `init-db/06-pg-duckdb.sh` | Enables pg_duckdb and registers the Wasabi secret from env |
| `init-db/07-lake-views.sh` | `lake.boundaries` / `lake.attributes` views over the curated Parquet |
| `migrations/` | Non-destructive migrations for an existing DB |
| `export/export_geoparquet.py` | Postgres → GeoParquet exporter to the lake (resumable, verifiable) |
| `lake_targets.py` | The lake target (AWS S3) from env: upload, list, DuckDB secrets |
| `load/load_tiger_boundaries.py` | TIGER/Line zips → `geographic_boundaries`, one vintage, layer by layer |
| `load/load_acs_summary_file.py` | ACS 5-year table-based Summary File → lake Parquet (all tables) and `geographic_data` (core tables) |
| `load/build_crosswalk.sql` | Shape-overlap crosswalk between two boundary vintages |

### Run it

```bash
cp .env.example .env        # set POSTGRES_PASSWORD, a read-only Wasabi key, LAKE_BUCKET
docker compose up -d --build
psql "host=localhost port=5434 dbname=geodata user=geoadmin"
```

The port binds to `127.0.0.1` by default. To serve other machines, set
`WAREHOUSE_BIND=0.0.0.0` and put it behind TLS and the Hetzner Cloud Firewall.
Docker-published ports bypass `ufw`.

Roles: `geo_reader` is read-only and is the role pg_duckdb lets run DuckDB/S3
queries (`duckdb.postgres_role`). `geoagent` is read/write and a member of
`geo_reader`. Both are created `NOLOGIN`. Create a login per consumer:

```sql
CREATE ROLE notebook_ro LOGIN PASSWORD '...' IN ROLE geo_reader;
```

The Wasabi key is exposed to every `geo_reader` member through a PUBLIC user
mapping (that's how pg_duckdb shares one secret), so it **must be a read-only key**.

### Loading Census data

Geographies are keyed `(summary_level, geoid, year)`. A geoid alone is
ambiguous: county `01001`, SLDU `01001` and ZCTA `01001` are different places.

```bash
export WAREHOUSE_DSN="host=localhost port=5434 dbname=geodata user=geoadmin password=..."
# 1. boundaries for the vintage (--list shows which layers have files)
python load/load_tiger_boundaries.py --year 2024          # all layers on disk, incl. zcta, place, uac
# 2. ACS 5-year: core tables into Postgres, every table into the lake
#    --defer-indexes: detach the year's partition, keep only the upsert key,
#    rebuild the other indexes on re-attach (~2x faster for a full year)
python load/load_acs_summary_file.py --year 2024 core --defer-indexes
python load/load_acs_summary_file.py --year 2024 lake --staging /big/disk/tmp --resume
# 3. crosswalk each older vintage onto the newest one, per level
psql "$WAREHOUSE_DSN" -v level=140 -v from_year=2022 -v to_year=2024 -f load/build_crosswalk.sql
```

Sources are read in place from the Wasabi rclone mount at
`data/geoagent-dev-s3/origin/` (pass `--root` for another mirror).

ACS values are keyed `acs:<table>_e<line>` (estimates only in Postgres) and
labelled in `attribute_catalog`. Postgres holds the core tables (`CORE_TABLES`
in the loader) at state, county, tract, block group, CBSA, congressional and
state-legislative levels. Every table, every geography, with MOEs and
Census annotation sentinels kept raw (-666666666 etc.), is in
`curated/acs/vintage=<Y>/table=<id>/part-0.parquet`.

#### Trends across changing boundaries

GEOIDs change: tracts and block groups are renumbered every decennial census,
districts are redrawn, and Connecticut swapped counties for planning regions
in 2022. `boundary_crosswalk` links two vintages by shape overlap
(`from_share`, `to_share`, and `relation` = same / split / merge / partial).
`attribute_on_geography()` re-expresses any year onto a target year's shapes:

```sql
-- total population (additive) for every year, on 2024 tracts
SELECT * FROM attribute_on_geography('acs:b01003_e001', '140', 2024);
-- median household income (not additive): dominant overlapping tract's value
SELECT * FROM attribute_on_geography('acs:b19013_e001', '140', 2024, false);
```

Counts are apportioned by area, which assumes people are spread evenly within
a shape. ACS dollar values are in each vintage's own inflation-adjusted
dollars, so adjust by CPI before comparing them across years.

### Query patterns

```sql
-- once per session that reads geometry: hand back WKB instead of DuckDB's internal encoding
SELECT duckdb.raw_query($$ SET enable_geoparquet_conversion = false $$);

-- scalar-only query straight off S3 (partition + column pruning)
SELECT boundary_type, year, count(*) FROM lake.boundaries GROUP BY 1, 2;

-- hydrate an area of interest into native PostGIS, index it, then do spatial work
CREATE TABLE aoi AS
SELECT geoid, name, geometry_wkb
FROM lake.boundaries
WHERE boundary_type = 'TRACT' AND year = 2024
  AND xmin > -105.3 AND xmax < -104.6 AND ymin > 39.5 AND ymax < 40.1;   -- bbox pushdown

ALTER TABLE aoi ADD COLUMN geom geometry(Geometry, 4326);
UPDATE aoi SET geom = ST_GeomFromWKB(geometry_wkb, 4326);
CREATE INDEX ON aoi USING gist (geom);
```

Gotchas found while building this:

- Inside a pg_duckdb query, `::geometry` casts and other PostGIS calls on S3
  columns fail, because the whole query runs in DuckDB. Materialize first (or
  wrap the S3 read in a subquery that only selects columns), then call PostGIS
  on the result.
- Without the `enable_geoparquet_conversion = false` setting, geometry arrives
  as `bytea` in DuckDB's internal format and `ST_GeomFromWKB` fails with
  "Invalid endian flag".
- A view over `read_parquet` must list its columns explicitly
  (`r['col']::type AS col`). Otherwise it collapses to one `duckdb.row` column.
  DuckDB binds the schema when the view is created, so the files have to exist
  by then. Rerun the views after the first export (or after adding a column):
  `docker compose exec warehouse bash /docker-entrypoint-initdb.d/07-lake-views.sh`.
