# warehouse/

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

## Layout

| Path | What |
|---|---|
| `docker/Dockerfile` | `pgduckdb/pgduckdb:17-v1.1.1` + PostGIS + h3 |
| `docker-compose.yml` | The service (port `5434`, DuckDB memory/threads capped) |
| `init-db/00-05` | Schema: extensions and roles, `borders`/`hexes`, `geographic_boundaries`, partitioned EAV `geographic_data` |
| `init-db/06-pg-duckdb.sh` | Enables pg_duckdb and registers the Wasabi secret from env |
| `init-db/07-lake-views.sh` | `lake.boundaries` / `lake.attributes` views over the curated Parquet |
| `migrations/` | Non-destructive migrations for an existing DB |
| `export/export_geoparquet.py` | Postgres → GeoParquet in S3 exporter (resumable, verifiable) |

## Run it

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

## Lake layout (`s3://<bucket>/curated/`)

```
boundaries/boundary_type=<STATE|COUNTY|TRACT|BG|...>/year=<YYYY>/part-0.parquet   GeoParquet, EPSG:4326
attributes/boundary_type=<...>/year=<YYYY>/part-0.parquet                       EAV facts joined to boundary type
```

Boundary files carry scalar spatial keys next to the geometry: `h3_r5` and
`h3_r7` (the cell of the point-on-surface) and the bbox `xmin/ymin/xmax/ymax`.
Rows are sorted by `h3_r5`, so Parquet row-group statistics prune on them.
**Filter on these first and touch geometry last.** Spatial predicates are not
pushed down to S3.

Raw source files (Census/IRS zips, xlsx and csv) stay under `origin/`, and you
can read them in place too: `SELECT * FROM read_csv('s3://<bucket>/origin/irs/...')`.

## Query patterns

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

## Refreshing the lake

```bash
python3 -m venv .venv && .venv/bin/pip install -r export/requirements.txt
set -a; . ./.env; set +a
export SOURCE_PG_DSN="host=localhost port=5432 dbname=geodata user=... password=..."
.venv/bin/python export/export_geoparquet.py boundaries      # skips partitions already written
.venv/bin/python export/export_geoparquet.py attributes
.venv/bin/python export/export_geoparquet.py verify          # row counts per partition, source vs lake
```

Pass `--type TRACT --year 2024 --force` to rewrite a single partition. Only
public reference columns are exported. App-side columns (`layer_id`,
`source_upload_id`) are dropped.

## Reading the lake without this server

Any DuckDB, GeoPandas, Sedona or QGIS client with a read key can use the same files:

```python
import duckdb
con = duckdb.connect(); con.install_extension("spatial"); con.load_extension("spatial")
con.execute("CREATE SECRET (TYPE s3, KEY_ID '...', SECRET '...', REGION 'us-central-1', "
            "ENDPOINT 's3.us-central-1.wasabisys.com', URL_STYLE 'path')")
con.sql("""SELECT name, ST_Area_Spheroid(geometry)/1e6 AS km2
           FROM read_parquet('s3://<bucket>/curated/boundaries/*/*/*.parquet', hive_partitioning=true)
           WHERE boundary_type='STATE' AND year=2024""").show()
```
