# Central geo warehouse: PostgreSQL 17 + PostGIS 3.6 + h3 + pg_duckdb.
#
# pg_duckdb embeds DuckDB inside Postgres (the same approach Aurora's
# aurora_analytics extension uses), so Parquet/GeoParquet/Iceberg in any
# S3-compatible bucket (Wasabi here) can be queried and joined with native
# PostGIS tables from one connection.
ARG PG_DUCKDB_TAG=17-v1.1.1
FROM pgduckdb/pgduckdb:${PG_DUCKDB_TAG}

USER root
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      postgresql-17-postgis-3 \
      postgresql-17-postgis-3-scripts \
      postgresql-17-h3 \
 && rm -rf /var/lib/apt/lists/*
USER postgres
