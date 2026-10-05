-- 2026-10-05: boundary attributes become columns; layer joins the key.
--
-- 1. The legacy PG16 import put TIGER/Line shapefile columns (ALAND, AWATER,
--    INTPTLAT/LON, MTFCC, FUNCSTAT, ...) into geographic_data as EAV "facts".
--    They describe the shape, not a survey measure, so they move onto
--    geographic_boundaries and the geographic_data_other_* rows are removed.
--    Survey data (acs/decennial/irs/...) is untouched (there was none).
--
-- 2. geoid alone does not identify a geography: county 01001, SLDU 01001,
--    SLDL 01001 and ZCTA 01001 all share the string. summary_level joins the
--    boundary PK and the fact-table cell key so layers stop overwriting each other.
--
-- Run: docker compose exec -T warehouse psql -U geoadmin -d geodata -v ON_ERROR_STOP=1 -f - < this.sql
BEGIN;

-- ---- 1. TIGER attributes -> boundary columns --------------------------------
ALTER TABLE public.geographic_boundaries
    ADD COLUMN IF NOT EXISTS aland          BIGINT,                 -- land area, m²
    ADD COLUMN IF NOT EXISTS awater         BIGINT,                 -- water area, m²
    ADD COLUMN IF NOT EXISTS internal_point geometry(POINT, 4326),  -- TIGER INTPTLAT/INTPTLON
    ADD COLUMN IF NOT EXISTS mtfcc          VARCHAR(5),
    ADD COLUMN IF NOT EXISTS funcstat       VARCHAR(1);

SET LOCAL work_mem = '1GB';
CREATE TEMP TABLE _tiger_attrs ON COMMIT DROP AS
SELECT geoid, year, summary_level,
       max(numeric_value) FILTER (WHERE attribute_key = 'aland')::bigint    AS aland,
       max(numeric_value) FILTER (WHERE attribute_key = 'awater')::bigint   AS awater,
       max(numeric_value) FILTER (WHERE attribute_key = 'intptlat')         AS lat,
       max(numeric_value) FILTER (WHERE attribute_key = 'intptlon')         AS lon,
       max(attribute_value) FILTER (WHERE attribute_key = 'mtfcc')          AS mtfcc,
       max(attribute_value) FILTER (WHERE attribute_key = 'funcstat')       AS funcstat
FROM public.geographic_data_other
WHERE attribute_key IN ('aland', 'awater', 'intptlat', 'intptlon', 'mtfcc', 'funcstat')
GROUP BY 1, 2, 3;

UPDATE public.geographic_boundaries b
SET aland          = t.aland,
    awater         = t.awater,
    internal_point = CASE WHEN t.lat IS NOT NULL AND t.lon IS NOT NULL
                          THEN ST_SetSRID(ST_MakePoint(t.lon, t.lat), 4326) END,
    mtfcc          = left(t.mtfcc, 5),
    funcstat       = left(t.funcstat, 1)
FROM _tiger_attrs t
WHERE b.geoid = t.geoid AND b.year = t.year AND b.summary_level = t.summary_level;

-- Every row in the 'other' partitions is one of those TIGER columns.
TRUNCATE public.geographic_data_other;

-- ---- 2. layer-aware keys ----------------------------------------------------
ALTER TABLE public.geographic_boundaries ALTER COLUMN summary_level SET NOT NULL;
ALTER TABLE public.geographic_boundaries DROP CONSTRAINT geographic_boundaries_pkey;
ALTER TABLE public.geographic_boundaries
    ADD CONSTRAINT geographic_boundaries_pkey PRIMARY KEY (summary_level, geoid, year);

ALTER TABLE public.geographic_data DROP CONSTRAINT uq_geo_cell;
ALTER TABLE public.geographic_data DROP CONSTRAINT geographic_data_pkey;
ALTER TABLE public.geographic_data
    ADD CONSTRAINT geographic_data_pkey
        PRIMARY KEY (source_survey, year, summary_level, geoid, attribute_key, id),
    ADD CONSTRAINT uq_geo_cell
        UNIQUE (source_survey, year, summary_level, geoid, attribute_key);

ALTER TABLE public.geographic_data_unmatched DROP CONSTRAINT uq_unmatched_cell;
ALTER TABLE public.geographic_data_unmatched
    ADD CONSTRAINT uq_unmatched_cell
        UNIQUE (source_survey, year, summary_level, geoid, attribute_key);

COMMIT;

ANALYZE public.geographic_boundaries;
