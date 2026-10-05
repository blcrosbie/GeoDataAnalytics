#!/bin/bash
# lake.* views over the curated GeoParquet in S3 (written by export/export_geoparquet.py).
#
# Each session that reads geometry must first run:
#   SELECT duckdb.raw_query($$ SET enable_geoparquet_conversion = false $$);
# so DuckDB hands back plain WKB (bytea) instead of its internal geometry
# encoding; then ST_GeomFromWKB(geometry_wkb, 4326) works in PostGIS.
set -euo pipefail

if [[ -z "${LAKE_BUCKET:-}" ]]; then
    echo "07-lake-views: LAKE_BUCKET not set; skipping lake views" >&2
    exit 0
fi

run_sql() {
    psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
         -v boundaries="s3://${LAKE_BUCKET}/curated/boundaries/*/*/*.parquet" \
         -v attributes="s3://${LAKE_BUCKET}/curated/attributes/*/*/*.parquet"
}

# DuckDB binds the Parquet schema when the view is created, so a view can only
# be made once its files exist. Don't fail init over it; rerun this script later.
run_sql <<-'SQL' || echo "07-lake-views: lake.boundaries not created (no files yet?)" >&2
    CREATE OR REPLACE VIEW lake.boundaries AS
    SELECT r['boundary_type']::text   AS boundary_type,
           r['year']::int             AS year,
           r['geoid']::text           AS geoid,
           r['name']::text            AS name,
           r['boundary_subtype']::text AS boundary_subtype,
           r['country']::text         AS country,
           r['source']::text          AS source,
           r['h3_r5']::text           AS h3_r5,
           r['h3_r7']::text           AS h3_r7,
           r['xmin']::float8          AS xmin,
           r['ymin']::float8          AS ymin,
           r['xmax']::float8          AS xmax,
           r['ymax']::float8          AS ymax,
           r['geometry']::bytea       AS geometry_wkb
    FROM read_parquet(:'boundaries', hive_partitioning := true) r;
SQL

run_sql <<-'SQL' || echo "07-lake-views: lake.attributes not created (no files yet?)" >&2
    CREATE OR REPLACE VIEW lake.attributes AS
    SELECT r['boundary_type']::text   AS boundary_type,
           r['year']::int             AS year,
           r['geoid']::text           AS geoid,
           r['attribute_key']::text   AS attribute_key,
           r['attribute_value']::text AS attribute_value,
           r['numeric_value']::float8 AS numeric_value,
           r['data_type']::text       AS data_type,
           r['source']::text          AS source
    FROM read_parquet(:'attributes', hive_partitioning := true) r;
SQL

run_sql <<-'SQL'
    GRANT USAGE ON SCHEMA lake TO geo_reader;
    GRANT SELECT ON ALL TABLES IN SCHEMA lake TO geo_reader;
    GRANT SELECT ON ALL TABLES IN SCHEMA public TO geo_reader;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO geo_reader;
    ALTER DEFAULT PRIVILEGES IN SCHEMA lake GRANT SELECT ON TABLES TO geo_reader;
SQL
