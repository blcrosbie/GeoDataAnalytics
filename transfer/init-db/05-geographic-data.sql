BEGIN;

-- ============================================================================
-- geographic_data : EAV fact table for all survey domains.
--   Two-level declarative partitioning: LIST(source_survey) -> RANGE(year).
--   Partition columns (source_survey, year) MUST appear in every unique
--   constraint, hence the wide PK below.
--
--   The boundary relationship to geographic_boundaries(geoid, year) is enforced
--   LOGICALLY by the ingest pipeline (stage -> validate-join -> unmatched sink),
--   NOT by a physical FK, so bulk COPY is not throttled by per-row triggers.
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.geographic_data (
    id               BIGINT        GENERATED ALWAYS AS IDENTITY,
    geoid            VARCHAR(64)   NOT NULL,
    year             INTEGER       NOT NULL,
    source_survey    VARCHAR(16)   NOT NULL,        -- partition key 1: acs/irs/popest/...
    summary_level    VARCHAR(3)    NOT NULL,        -- 040/050/140 ... for cheap level filters
    attribute_key    VARCHAR(128)  NOT NULL,        -- '<survey>:<var>[@dim=val;...]'
    attribute_value  TEXT,
    numeric_value    NUMERIC(20,8),
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

-- ---- Level-1: one LIST partition per survey, each RANGE-partitioned by year --
CREATE TABLE IF NOT EXISTS public.geographic_data_acs
    PARTITION OF public.geographic_data FOR VALUES IN ('acs')        PARTITION BY RANGE (year);
CREATE TABLE IF NOT EXISTS public.geographic_data_irs
    PARTITION OF public.geographic_data FOR VALUES IN ('irs')        PARTITION BY RANGE (year);
CREATE TABLE IF NOT EXISTS public.geographic_data_popest
    PARTITION OF public.geographic_data FOR VALUES IN ('popest')     PARTITION BY RANGE (year);
CREATE TABLE IF NOT EXISTS public.geographic_data_decennial
    PARTITION OF public.geographic_data FOR VALUES IN ('decennial')  PARTITION BY RANGE (year);
CREATE TABLE IF NOT EXISTS public.geographic_data_brds
    PARTITION OF public.geographic_data FOR VALUES IN ('brds')       PARTITION BY RANGE (year);
CREATE TABLE IF NOT EXISTS public.geographic_data_eccen
    PARTITION OF public.geographic_data FOR VALUES IN ('eccen')      PARTITION BY RANGE (year);
CREATE TABLE IF NOT EXISTS public.geographic_data_govfin
    PARTITION OF public.geographic_data FOR VALUES IN ('govfin')     PARTITION BY RANGE (year);
CREATE TABLE IF NOT EXISTS public.geographic_data_mhs
    PARTITION OF public.geographic_data FOR VALUES IN ('mhs')        PARTITION BY RANGE (year);
-- Catch-all so an unknown survey short-code never aborts a COPY.
CREATE TABLE IF NOT EXISTS public.geographic_data_other
    PARTITION OF public.geographic_data DEFAULT                      PARTITION BY RANGE (year);

-- ---- Level-2: yearly leaves 2010..2025 + a DEFAULT leaf per survey ----------
-- The DEFAULT leaf absorbs out-of-span years (e.g. IRS historical 1989, or 2026)
-- so ingest never fails on a year we forgot to provision.
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
                   FOR VALUES FROM (%2$s) TO (%3$s);',
                s, y, y + 1);
        END LOOP;
        EXECUTE format(
            'CREATE TABLE IF NOT EXISTS public.geographic_data_%1$s_default
               PARTITION OF public.geographic_data_%1$s DEFAULT;', s);
    END LOOP;
END $$;

-- ---- Composite / covering indexes (defined on parent -> inherited by leaves) -
-- (A) feeds crosstab MVs: "this attribute across all geoids in a survey/year".
CREATE INDEX IF NOT EXISTS idx_gd_attr_geo
    ON public.geographic_data (attribute_key, geoid)
    INCLUDE (numeric_value, attribute_value);
-- (B) feature inspection: "every attribute for one geoid".
CREATE INDEX IF NOT EXISTS idx_gd_geo_attr
    ON public.geographic_data (geoid, attribute_key)
    INCLUDE (numeric_value);
-- (C) hierarchical rollups: "all tracts within county 06037".
CREATE INDEX IF NOT EXISTS idx_gd_geo_prefix
    ON public.geographic_data (summary_level, geoid varchar_pattern_ops);

-- ============================================================================
-- geographic_data_unmatched : sink for cells whose (geoid, year) has no boundary
--   yet. Replayed into geographic_data once the matching boundary lands.
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.geographic_data_unmatched (
    geoid            VARCHAR(64)   NOT NULL,
    year             INTEGER       NOT NULL,
    source_survey    VARCHAR(16)   NOT NULL,
    summary_level    VARCHAR(3)    NOT NULL,
    attribute_key    VARCHAR(128)  NOT NULL,
    attribute_value  TEXT,
    numeric_value    NUMERIC(20,8),
    data_type        VARCHAR(32)   NOT NULL DEFAULT 'text',
    source           VARCHAR(128),
    collection_date  DATE,
    logged_at        TIMESTAMPTZ   NOT NULL DEFAULT now(),
    CONSTRAINT uq_unmatched_cell UNIQUE (source_survey, year, geoid, attribute_key)
);
CREATE INDEX IF NOT EXISTS idx_gd_unmatched_geo_year
    ON public.geographic_data_unmatched (geoid, year);

-- ============================================================================
-- attribute_catalog : human-readable labels, decoupled from EAV storage.
--   Populated lazily by the ingest pipeline (ON CONFLICT DO NOTHING).
-- ============================================================================
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

-- Grant to geoagent only if that role exists (local dev may run as 'brandon').
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'geoagent') THEN
        GRANT ALL PRIVILEGES ON public.geographic_data           TO geoagent;
        GRANT ALL PRIVILEGES ON public.geographic_data_unmatched TO geoagent;
        GRANT ALL PRIVILEGES ON public.attribute_catalog         TO geoagent;
    END IF;
END $$;

COMMIT;
