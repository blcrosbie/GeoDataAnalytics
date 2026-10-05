-- Build boundary_crosswalk rows for one level between two vintages.
-- psql -v level=140 -v from_year=2022 -v to_year=2024 -f build_crosswalk.sql
-- See migrations/2026-10-05-boundary-crosswalk.sql for column meanings.
\set ON_ERROR_STOP 1
BEGIN;
SET LOCAL work_mem = '1GB';

DELETE FROM public.boundary_crosswalk
WHERE summary_level = :'level' AND from_year = :from_year AND to_year = :to_year;

CREATE TEMP TABLE _a ON COMMIT DROP AS
SELECT geoid, ST_Transform(geom, 5070) AS g FROM public.geographic_boundaries
WHERE summary_level = :'level' AND year = :from_year AND geom IS NOT NULL;
CREATE TEMP TABLE _b ON COMMIT DROP AS
SELECT geoid, ST_Transform(geom, 5070) AS g FROM public.geographic_boundaries
WHERE summary_level = :'level' AND year = :to_year AND geom IS NOT NULL;
CREATE INDEX ON _b USING gist (g);
ANALYZE _a; ANALYZE _b;

INSERT INTO public.boundary_crosswalk
    (summary_level, from_year, from_geoid, to_year, to_geoid,
     overlap_m2, from_share, to_share, relation)
SELECT :'level', :from_year, o.a_geoid, :to_year, o.b_geoid, o.overlap,
       o.overlap / o.a_area, o.overlap / o.b_area, ''
FROM (
    SELECT a.geoid AS a_geoid, b.geoid AS b_geoid, ST_Area(a.g) AS a_area, ST_Area(b.g) AS b_area,
           CASE WHEN ST_Equals(a.g, b.g) THEN ST_Area(a.g)
                ELSE ST_Area(ST_Intersection(a.g, b.g)) END AS overlap
    FROM _a a JOIN _b b ON a.g && b.g AND ST_Intersects(a.g, b.g)
) o
WHERE o.a_area > 0 AND o.b_area > 0
  -- drop slivers from boundary realignment: < 1% of both shapes
  AND (o.overlap / o.a_area >= 0.01 OR o.overlap / o.b_area >= 0.01);

-- Classify each pair.
UPDATE public.boundary_crosswalk x SET relation = CASE
    WHEN x.from_share >= 0.98 AND x.to_share >= 0.98 THEN 'same'
    WHEN x.to_share  >= 0.98 THEN 'split'    -- new shape lies inside the old one
    WHEN x.from_share >= 0.98 THEN 'merge'   -- old shape lies inside the new one
    ELSE 'partial' END
WHERE summary_level = :'level' AND from_year = :from_year AND to_year = :to_year;

SELECT relation, count(*) FROM public.boundary_crosswalk
WHERE summary_level = :'level' AND from_year = :from_year AND to_year = :to_year
GROUP BY 1 ORDER BY 1;
COMMIT;
