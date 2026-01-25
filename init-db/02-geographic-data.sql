BEGIN;

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
    metadata                       JSONB,
    created_at                     TIMESTAMPTZ DEFAULT NOW(),
    updated_at                     TIMESTAMPTZ DEFAULT NOW()
);

-- Primary index for lookups by geoid+year
CREATE INDEX IF NOT EXISTS idx_geographic_data_geoid_year
    ON public.geographic_data (geoid, year);

-- GIN index on attribute_key for fast attribute filtering
CREATE INDEX IF NOT EXISTS idx_geographic_data_attribute_key
    ON public.geographic_data USING GIN (attribute_key);

-- B-tree index for exact value lookups (census codes, etc.)
CREATE INDEX IF NOT EXISTS idx_geographic_data_value
    ON public.geographic_data (attribute_value);

-- B-tree index on numeric_value for range queries
CREATE INDEX IF NOT EXISTS idx_geographic_data_numeric_value
    ON public.geographic_data (numeric_value);

-- GIN index on metadata for flexible queries
CREATE INDEX IF NOT EXISTS idx_geographic_data_metadata
    ON public.geographic_data USING GIN (metadata);

-- Composite index for common query patterns
CREATE INDEX IF NOT EXISTS idx_geographic_data_key_year_type
    ON public.geographic_data (attribute_key, year, data_type);

-- Foreign key relationship to boundaries (optional but recommended)
ALTER TABLE public.geographic_data 
ADD CONSTRAINT fk_geographic_data_boundary 
FOREIGN KEY (geoid, year) REFERENCES public.geographic_boundaries(geoid, year) 
ON DELETE CASCADE;

-- GRANT ALL PRIVILEGES ON public.geographic_data TO geoagent;

COMMIT;