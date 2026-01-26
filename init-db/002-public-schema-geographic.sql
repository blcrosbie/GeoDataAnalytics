BEGIN;

CREATE TABLE IF NOT EXISTS public.geographic_boundaries (
    geoid                          VARCHAR(64) NOT NULL,
    year                           INTEGER NOT NULL,
    name                           VARCHAR(255) NOT NULL,
    geom                           geometry(GEOMETRY, 4326),
    boundary_type                  VARCHAR(64) NOT NULL,
    boundary_subtype               VARCHAR(64),
    country                        VARCHAR(3),
    source                         VARCHAR(255),
    accuracy_meters                DECIMAL(10,2),
    validity_start_date            DATE,
    validity_end_date              DATE,
    layer_id                       UUID,
    source_upload_id               UUID,
    attributes                     JSONB,
    last_updated                   TIMESTAMPTZ DEFAULT NOW(),
    created_at                     TIMESTAMPTZ DEFAULT NOW(),
    
    PRIMARY KEY (geoid, year)
);

-- GIST index for spatial queries
CREATE INDEX IF NOT EXISTS idx_geographic_boundaries_geom
    ON public.geographic_boundaries USING GIST (geom);

-- B-tree index on boundary_type for fast filtering
CREATE INDEX IF NOT EXISTS idx_geographic_boundaries_type
    ON public.geographic_boundaries (boundary_type);

-- Composite index on country and type for common queries
CREATE INDEX IF NOT EXISTS idx_geographic_boundaries_country_type
    ON public.geographic_boundaries (country, boundary_type);

-- GIN index on JSONB metadata for flexible queries
CREATE INDEX IF NOT EXISTS idx_geographic_boundaries_metadata
    ON public.geographic_boundaries USING GIN (attributes);

CREATE INDEX IF NOT EXISTS idx_geographic_boundaries_layer_id
    ON public.geographic_boundaries (layer_id);

CREATE INDEX IF NOT EXISTS idx_geographic_boundaries_source_upload_id
    ON public.geographic_boundaries (source_upload_id);

CREATE TABLE IF NOT EXISTS public.geographic_data (
    id                             BIGSERIAL PRIMARY KEY,
    geoid                          VARCHAR(64) NOT NULL,
    year                           INTEGER NOT NULL,
    attribute_key                  VARCHAR(128) NOT NULL,
    attribute_value                TEXT,
    numeric_value                  DECIMAL(20,8),
    data_type                      VARCHAR(32) NOT NULL DEFAULT 'text',
    source                         VARCHAR(128),
    collection_date                DATE,
    confidence_level               VARCHAR(32),
    layer_id                       UUID,
    source_upload_id               UUID,
    attributes                     JSONB,
    created_at                     TIMESTAMPTZ DEFAULT NOW(),
    updated_at                     TIMESTAMPTZ DEFAULT NOW()
);

-- Primary index for lookups by geoid+year
CREATE INDEX IF NOT EXISTS idx_geographic_data_geoid_year
    ON public.geographic_data (geoid, year);

-- B-tree index on attribute_key for fast attribute filtering
CREATE INDEX IF NOT EXISTS idx_geographic_data_attribute_key
    ON public.geographic_data (attribute_key);

-- B-tree index for exact value lookups (census codes, etc.)
CREATE INDEX IF NOT EXISTS idx_geographic_data_value
    ON public.geographic_data (attribute_value);

-- B-tree index on numeric_value for range queries
CREATE INDEX IF NOT EXISTS idx_geographic_data_numeric_value
    ON public.geographic_data (numeric_value);

-- GIN index on metadata for flexible queries
CREATE INDEX IF NOT EXISTS idx_geographic_data_metadata
    ON public.geographic_data USING GIN (attributes);

CREATE INDEX IF NOT EXISTS idx_geographic_data_layer_id
    ON public.geographic_data (layer_id);

CREATE INDEX IF NOT EXISTS idx_geographic_data_source_upload_id
    ON public.geographic_data (source_upload_id);

-- Composite index for common query patterns
CREATE INDEX IF NOT EXISTS idx_geographic_data_key_year_type
    ON public.geographic_data (attribute_key, year, data_type);

-- Foreign key relationship to boundaries (optional but recommended)
ALTER TABLE public.geographic_data 
ADD CONSTRAINT fk_geographic_data_boundary 
FOREIGN KEY (geoid, year) REFERENCES public.geographic_boundaries(geoid, year) 
ON DELETE CASCADE;

-- Grant permissions to geoagent user
GRANT USAGE ON SCHEMA public TO geoagent;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO geoagent;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO geoagent;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO geoagent;

COMMIT;
