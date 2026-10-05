CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;
CREATE EXTENSION IF NOT EXISTS h3;
CREATE EXTENSION IF NOT EXISTS h3_postgis CASCADE;

-- Roles the schema files grant to. NOLOGIN here; give them passwords out of band.
--   geoagent  : read/write (ingest pipelines)
--   geo_reader: read-only (notebooks, other apps/repos that just consume data);
--               also the role allowed to run DuckDB/S3 queries
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'geoagent') THEN
        CREATE ROLE geoagent NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'geo_reader') THEN
        CREATE ROLE geo_reader NOLOGIN;
    END IF;
    -- pg_duckdb only lets members of duckdb.postgres_role (geo_reader) run DuckDB queries.
    GRANT geo_reader TO geoagent;
END
$$;
