-- 2026-10-05: spatial crosswalk between boundary vintages.
--
-- GEOIDs are not stable over time: tracts and block groups are renumbered at
-- each decennial census, districts are redrawn, and counties occasionally
-- merge or split (Connecticut's planning regions in 2022). Trends therefore
-- link geographies by shape overlap, not by matching geoid strings.
--
-- One row per overlapping (from, to) pair at a summary level:
--   from_share = overlap / area(from)   share of the old shape inside the new one
--   to_share   = overlap / area(to)     share of the new shape covered by the old one
--   relation   = 'same'  both shares >= 0.98 (same place, geoid may differ)
--                'split' from is divided across several to-shapes
--                'merge' several from-shapes form one to-shape
--                'partial' anything else
-- Areas are measured in EPSG:5070 (CONUS Albers). Only ratios are kept, so the
-- projection's distortion outside CONUS largely cancels.
--
-- Build a pair with warehouse/load/build_crosswalk.sql.
BEGIN;

CREATE TABLE IF NOT EXISTS public.boundary_crosswalk (
    summary_level  VARCHAR(3)   NOT NULL,
    from_year      INTEGER      NOT NULL,
    from_geoid     VARCHAR(64)  NOT NULL,
    to_year        INTEGER      NOT NULL,
    to_geoid       VARCHAR(64)  NOT NULL,
    overlap_m2     DOUBLE PRECISION NOT NULL,
    from_share     REAL         NOT NULL,
    to_share       REAL         NOT NULL,
    relation       VARCHAR(8)   NOT NULL,
    PRIMARY KEY (summary_level, from_year, to_year, from_geoid, to_geoid)
);
CREATE INDEX IF NOT EXISTS idx_crosswalk_to
    ON public.boundary_crosswalk (summary_level, to_year, from_year, to_geoid);

-- Re-express any numeric attribute from year Y on the geographies of target
-- year T. Counts are apportioned by area (value * from_share summed per
-- target); medians, ratios and other non-additive values take the value of the
-- source shape with the largest overlap instead, since they can't be summed.
-- Same-year requests pass straight through.
CREATE OR REPLACE FUNCTION public.attribute_on_geography(
    p_attribute_key VARCHAR, p_summary_level VARCHAR, p_target_year INTEGER,
    p_additive BOOLEAN DEFAULT true)
RETURNS TABLE (geoid VARCHAR, year INTEGER, value NUMERIC, coverage REAL)
LANGUAGE sql STABLE AS $$
    -- data already on the target vintage
    SELECT d.geoid, d.year, d.numeric_value, 1::real
    FROM public.geographic_data d
    WHERE d.attribute_key = p_attribute_key AND d.summary_level = p_summary_level
      AND d.year = p_target_year
    UNION ALL
    -- additive: area-weighted sum of every overlapping source shape
    SELECT x.to_geoid, d.year, sum(d.numeric_value * x.from_share)::numeric,
           sum(x.to_share)::real
    FROM public.geographic_data d
    JOIN public.boundary_crosswalk x
      ON x.summary_level = d.summary_level AND x.from_year = d.year
     AND x.from_geoid = d.geoid AND x.to_year = p_target_year
    WHERE p_additive AND d.attribute_key = p_attribute_key
      AND d.summary_level = p_summary_level AND d.year <> p_target_year
    GROUP BY x.to_geoid, d.year
    UNION ALL
    -- non-additive: value of the dominant source shape
    (SELECT DISTINCT ON (x.to_geoid, d.year) x.to_geoid, d.year, d.numeric_value, x.to_share
    FROM public.geographic_data d
    JOIN public.boundary_crosswalk x
      ON x.summary_level = d.summary_level AND x.from_year = d.year
     AND x.from_geoid = d.geoid AND x.to_year = p_target_year
    WHERE NOT p_additive AND d.attribute_key = p_attribute_key
      AND d.summary_level = p_summary_level AND d.year <> p_target_year
    ORDER BY x.to_geoid, d.year, x.to_share DESC)
$$;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'geoagent') THEN
        GRANT SELECT ON public.boundary_crosswalk TO geoagent;
    END IF;
END $$;

COMMIT;
