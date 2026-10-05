-- ============================================================================
-- Migration: EAV partitioning + survey namespacing
-- Date:      2026-06-06
-- Target:    LIVE db (in construction, not in use) -- safe to run once.
--
-- What it does, non-destructively:
--   1. geographic_boundaries  -> ADD summary_level + indexes (data preserved).
--   2. geographic_data        -> rebuild as LIST(source_survey)->RANGE(year)
--                                partitioned table. Existing rows are copied
--                                into the new structure (legacy survey unknown
--                                -> 'other', summary_level inferred from geoid).
--   3. Create geographic_data_unmatched + attribute_catalog.
--
-- PostgreSQL cannot ALTER a plain table into a partitioned one, so step 2 does
-- rename -> create -> copy -> drop. Wrapped in one transaction: if anything
-- fails, NOTHING changes. Re-runnable only after a clean rollback (it expects
-- the pre-migration table names on entry).
-- ============================================================================
BEGIN;

-- ---------------------------------------------------------------------------
-- 1. geographic_boundaries: additive only.
-- ---------------------------------------------------------------------------
ALTER TABLE public.geographic_boundaries
    ADD COLUMN IF NOT EXISTS summary_level VARCHAR(3);

-- Backfill summary_level from geoid length where we can infer it.
UPDATE public.geographic_boundaries
SET summary_level = CASE length(geoid)
        WHEN 1  THEN '010'   -- nation
        WHEN 2  THEN '040'   -- state
        WHEN 5  THEN '050'   -- county
        WHEN 7  THEN '160'   -- place
        WHEN 11 THEN '140'   -- tract
        WHEN 12 THEN '150'   -- block group
        ELSE NULL
    END
WHERE summary_level IS NULL;

CREATE INDEX IF NOT EXISTS idx_geoboundaries_geom
    ON public.geographic_boundaries USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_geoboundaries_geoid_prefix
    ON public.geographic_boundaries (summary_level, geoid varchar_pattern_ops);

-- ---------------------------------------------------------------------------
-- 2. geographic_data: rebuild as partitioned. Old table set aside, not dropped
--    until its rows are safely copied.
-- ---------------------------------------------------------------------------
ALTER TABLE IF EXISTS public.geographic_data RENAME TO geographic_data_legacy;

CREATE TABLE public.geographic_data (
    id               BIGINT        GENERATED ALWAYS AS IDENTITY,
    geoid            VARCHAR(64)   NOT NULL,
    year             INTEGER       NOT NULL,
    source_survey    VARCHAR(16)   NOT NULL,
    summary_level    VARCHAR(3)    NOT NULL,
    attribute_key    VARCHAR(128)  NOT NULL,
    attribute_value  TEXT,
    numeric_value    NUMERIC(24,8),
    data_type        VARCHAR(32)   NOT NULL DEFAULT 'text',
    source           VARCHAR(128),
    collection_date  DATE,
    confidence_level VARCHAR(32),
    layer_id         UUID,
    source_upload_id UUID,
    created_at       TIMESTAMPTZ   NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ   NOT NULL DEFAULT now(),
    PRIMARY KEY (source_survey, year, geoid, attribute_key, id),
    CONSTRAINT uq_geo_cell UNIQUE (source_survey, year, geoid, attribute_key)
) PARTITION BY LIST (source_survey);

CREATE TABLE public.geographic_data_acs
    PARTITION OF public.geographic_data FOR VALUES IN ('acs')        PARTITION BY RANGE (year);
CREATE TABLE public.geographic_data_irs
    PARTITION OF public.geographic_data FOR VALUES IN ('irs')        PARTITION BY RANGE (year);
CREATE TABLE public.geographic_data_popest
    PARTITION OF public.geographic_data FOR VALUES IN ('popest')     PARTITION BY RANGE (year);
CREATE TABLE public.geographic_data_decennial
    PARTITION OF public.geographic_data FOR VALUES IN ('decennial')  PARTITION BY RANGE (year);
CREATE TABLE public.geographic_data_brds
    PARTITION OF public.geographic_data FOR VALUES IN ('brds')       PARTITION BY RANGE (year);
CREATE TABLE public.geographic_data_eccen
    PARTITION OF public.geographic_data FOR VALUES IN ('eccen')      PARTITION BY RANGE (year);
CREATE TABLE public.geographic_data_govfin
    PARTITION OF public.geographic_data FOR VALUES IN ('govfin')     PARTITION BY RANGE (year);
CREATE TABLE public.geographic_data_mhs
    PARTITION OF public.geographic_data FOR VALUES IN ('mhs')        PARTITION BY RANGE (year);
CREATE TABLE public.geographic_data_other
    PARTITION OF public.geographic_data DEFAULT                      PARTITION BY RANGE (year);

DO $$
DECLARE
    s TEXT;
    y INTEGER;
    surveys TEXT[] := ARRAY['acs','irs','popest','decennial','brds','eccen','govfin','mhs','other'];
BEGIN
    FOREACH s IN ARRAY surveys LOOP
        FOR y IN 2010..2025 LOOP
            EXECUTE format(
                'CREATE TABLE IF NOT EXISTS public.geographic_data_%1$s_%2$s
                   PARTITION OF public.geographic_data_%1$s
                   FOR VALUES FROM (%2$s) TO (%3$s);', s, y, y + 1);
        END LOOP;
        EXECUTE format(
            'CREATE TABLE IF NOT EXISTS public.geographic_data_%1$s_default
               PARTITION OF public.geographic_data_%1$s DEFAULT;', s);
    END LOOP;
END $$;

CREATE INDEX idx_gd_attr_geo
    ON public.geographic_data (attribute_key, geoid) INCLUDE (numeric_value, attribute_value);
CREATE INDEX idx_gd_geo_attr
    ON public.geographic_data (geoid, attribute_key) INCLUDE (numeric_value);
CREATE INDEX idx_gd_geo_prefix
    ON public.geographic_data (summary_level, geoid varchar_pattern_ops);

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'geoagent') THEN
        GRANT ALL PRIVILEGES ON public.geographic_data TO geoagent;
    END IF;
END $$;

-- Copy legacy rows forward. Legacy data predates survey namespacing, so:
--   source_survey := 'other' (routes to the catch-all partition)
--   summary_level := inferred from geoid length
--   attribute_key := de-duplicated by appending row id when a (geoid,year,key)
--                    collision would otherwise violate uq_geo_cell.
INSERT INTO public.geographic_data
    (geoid, year, source_survey, summary_level, attribute_key,
     attribute_value, numeric_value, data_type, source, collection_date,
     confidence_level, layer_id, source_upload_id)
SELECT
    l.geoid,
    l.year,
    'other' AS source_survey,
    COALESCE(CASE length(l.geoid)
        WHEN 1 THEN '010' WHEN 2 THEN '040' WHEN 5 THEN '050'
        WHEN 7 THEN '160' WHEN 11 THEN '140' WHEN 12 THEN '150' END, '000') AS summary_level,
    -- guarantee uniqueness within (other, year, geoid): keep first key as-is,
    -- suffix any duplicates with #<n>.
    CASE WHEN rn = 1 THEN left(l.attribute_key, 128)
         ELSE left(l.attribute_key, 120) || '#' || rn::text END AS attribute_key,
    l.attribute_value, l.numeric_value, l.data_type, l.source, l.collection_date,
    l.confidence_level, l.layer_id, l.source_upload_id
FROM (
    SELECT *,
           row_number() OVER (PARTITION BY geoid, year, attribute_key ORDER BY id) AS rn
    FROM public.geographic_data_legacy
) l;

DROP TABLE public.geographic_data_legacy;

-- ---------------------------------------------------------------------------
-- 3. Unmatched sink + attribute catalog.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.geographic_data_unmatched (
    geoid            VARCHAR(64)   NOT NULL,
    year             INTEGER       NOT NULL,
    source_survey    VARCHAR(16)   NOT NULL,
    summary_level    VARCHAR(3)    NOT NULL,
    attribute_key    VARCHAR(128)  NOT NULL,
    attribute_value  TEXT,
    numeric_value    NUMERIC(24,8),
    data_type        VARCHAR(32)   NOT NULL DEFAULT 'text',
    source           VARCHAR(128),
    collection_date  DATE,
    logged_at        TIMESTAMPTZ   NOT NULL DEFAULT now(),
    CONSTRAINT uq_unmatched_cell UNIQUE (source_survey, year, geoid, attribute_key)
);
CREATE INDEX IF NOT EXISTS idx_gd_unmatched_geo_year
    ON public.geographic_data_unmatched (geoid, year);

CREATE TABLE IF NOT EXISTS public.attribute_catalog (
    attribute_key   VARCHAR(128) PRIMARY KEY,
    survey          VARCHAR(16)  NOT NULL,
    label           TEXT,
    universe        TEXT,
    unit            VARCHAR(32),
    native_dtype    VARCHAR(16)  NOT NULL DEFAULT 'numeric',
    first_seen_year INTEGER,
    last_seen_year  INTEGER
);

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'geoagent') THEN
        GRANT ALL PRIVILEGES ON public.geographic_data_unmatched TO geoagent;
        GRANT ALL PRIVILEGES ON public.attribute_catalog         TO geoagent;
    END IF;
END $$;

COMMIT;

-- After commit, refresh planner stats on the new partitions:
ANALYZE public.geographic_data;
ANALYZE public.geographic_boundaries;
