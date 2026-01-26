-- Create database user and grant basic permissions
-- This script should run after database creation but before schema setup

DO $$
BEGIN
    -- Create user if not exists
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'geoagent') THEN
        CREATE ROLE geoagent WITH LOGIN PASSWORD 'changeme_to_secure_password_later';
    END IF;
END
$$;

-- Grant connection rights to the database
GRANT CONNECT ON DATABASE geodata TO geoagent;
-- Grant usage of public schema
GRANT USAGE ON SCHEMA public TO geoagent;
-- Grant default privileges for future objects
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO geoagent;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO geoagent;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO geoagent;