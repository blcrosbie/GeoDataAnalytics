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
    metadata                       JSONB,
    last_updated                   TIMESTAMPTZ DEFAULT NOW(),
    created_at                     TIMESTAMPTZ DEFAULT NOW(),
    
    PRIMARY KEY (geoid, year)
);

-- GIST index for spatial queries
CREATE INDEX IF NOT EXISTS idx_geographic_boundaries_geom
    ON public.geographic_boundaries USING GIST (geom);

-- GIN index on boundary_type for fast filtering
CREATE INDEX IF NOT EXISTS idx_geographic_boundaries_type
    ON public.geographic_boundaries USING GIN (boundary_type);

-- Composite index on country and type for common queries
CREATE INDEX IF NOT EXISTS idx_geographic_boundaries_country_type
    ON public.geographic_boundaries (country, boundary_type);

-- GIN index on JSONB metadata for flexible queries
CREATE INDEX IF NOT EXISTS idx_geographic_boundaries_metadata
    ON public.geographic_boundaries USING GIN (metadata);

-- GRANT ALL PRIVILEGES ON public.geographic_boundaries TO geoagent;

COMMIT;