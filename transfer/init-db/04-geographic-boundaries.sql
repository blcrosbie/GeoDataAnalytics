BEGIN;

-- ============================================================================
-- geographic_boundaries : master spatial catalog (entity table)
--   PK (geoid, year) is the join target for the geographic_data EAV facts.
--   Boundary geometry for ArcGIS Pro is served from here (and crosstab MVs).
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.geographic_boundaries (
    geoid               VARCHAR(64)  NOT NULL,
    year                INTEGER      NOT NULL,
    name                VARCHAR(255) NOT NULL,
    geom                geometry(GEOMETRY, 4326),
    boundary_type       VARCHAR(64)  NOT NULL,
    boundary_subtype    VARCHAR(64),
    country             VARCHAR(3),
    summary_level       VARCHAR(3),              -- 010 nation / 040 state / 050 county / 140 tract ...
    source              VARCHAR(255),
    accuracy_meters     NUMERIC(10,2),
    validity_start_date DATE,
    validity_end_date   DATE,
    layer_id            UUID,
    source_upload_id    UUID,
    last_updated        TIMESTAMPTZ  DEFAULT now(),
    created_at          TIMESTAMPTZ  DEFAULT now(),

    PRIMARY KEY (geoid, year)
);

-- Spatial draw index for ArcGIS / PostGIS map queries.
CREATE INDEX IF NOT EXISTS idx_geoboundaries_geom
    ON public.geographic_boundaries USING GIST (geom);

-- Hierarchical prefix lookups: "all tracts in county 06037" -> geoid LIKE '06037%'.
-- varchar_pattern_ops lets a LIKE 'prefix%' use the btree.
CREATE INDEX IF NOT EXISTS idx_geoboundaries_geoid_prefix
    ON public.geographic_boundaries (summary_level, geoid varchar_pattern_ops);

-- Grant to geoagent only if that role exists (local dev may run as 'brandon').
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'geoagent') THEN
        GRANT ALL PRIVILEGES ON public.geographic_boundaries TO geoagent;
    END IF;
END $$;

COMMIT;
