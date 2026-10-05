#!/bin/bash
# Enable pg_duckdb + DuckDB extensions and register the Wasabi S3 secret.
# Credentials come from the container env (warehouse/.env), never from git.
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-'SQL'
    CREATE EXTENSION IF NOT EXISTS pg_duckdb;
    SELECT duckdb.install_extension('httpfs');
    SELECT duckdb.install_extension('spatial');
    SELECT duckdb.install_extension('iceberg');
    CREATE SCHEMA IF NOT EXISTS lake;
SQL

if [[ -n "${LAKE_S3_KEY_ID:-}" && -n "${LAKE_S3_SECRET:-}" ]]; then
    psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
         -v key_id="$LAKE_S3_KEY_ID" -v secret="$LAKE_S3_SECRET" \
         -v region="${LAKE_S3_REGION:-us-east-1}" \
         -v endpoint="${LAKE_S3_ENDPOINT:-s3.us-east-1.wasabisys.com}" <<-'SQL'
        SELECT duckdb.create_simple_secret(
            type      := 'S3',
            key_id    := :'key_id',
            secret    := :'secret',
            region    := :'region',
            endpoint  := :'endpoint',
            url_style := 'path'
        );
        -- create_simple_secret maps the key to the calling user only. Add a PUBLIC
        -- mapping so geo_reader members (the duckdb.postgres_role) can read the
        -- lake too. Anyone with USAGE can see these options, so use a READ-ONLY key.
        CREATE USER MAPPING FOR PUBLIC SERVER simple_s3_secret
            OPTIONS (key_id :'key_id', secret :'secret');
        GRANT USAGE ON FOREIGN SERVER simple_s3_secret TO geo_reader;
SQL
else
    echo "06-pg-duckdb: LAKE_S3_KEY_ID/LAKE_S3_SECRET not set; skipping S3 secret" >&2
fi
