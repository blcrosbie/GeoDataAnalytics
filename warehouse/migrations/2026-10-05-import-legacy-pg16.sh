#!/bin/bash
# One-time import of the pre-partitioning geo DB (PG16, flat geographic_* tables)
# into the warehouse's partitioned schema.
#
# Usage: ./2026-10-05-import-legacy-pg16.sh [--resume]
#   --resume: staging/classification already done; load only years not yet in
#             public.geographic_data (each year is one transaction, so a killed
#             year rolls back cleanly).
#
#   SRC_PSQL / DST_PSQL : commands that run psql against source / warehouse, e.g.
#     SRC_PSQL="docker exec -i old-db psql -U admin -d geodata"
#     DST_PSQL="docker compose exec -T warehouse psql -U geoadmin -d geodata"
#
# What happens to every source row:
#   boundaries  geoid <> ''                       -> public.geographic_boundaries
#               geoid  = ''                       -> legacy.boundaries_quarantine
#   data        clean cell (1 row, or N identical) -> public.geographic_data (1 row)
#               geoid = '' or conflicting values  -> legacy.data_quarantine (all rows, with reason)
#
# Why quarantine: the old loader read only TIGER's GEOID column, so ZCTA (GEOID20)
# and area landmarks (AREAID) collapsed onto geoid ''. Its PK (geoid, year) also
# lets different layers that share an id string (county 01001 / SLDU 01001 /
# SLDL 01001) overwrite each other, which mixes their attributes. Neither can be
# repaired from the DB; reload those layers from TIGER with the fixed loader.
set -euo pipefail
: "${SRC_PSQL:?}" "${DST_PSQL:?}"

src() { $SRC_PSQL -v ON_ERROR_STOP=1 -X -q "$@"; }
dst() { $DST_PSQL -v ON_ERROR_STOP=1 -X -q "$@"; }
log() { echo "$(date -u +%H:%M:%S) $*"; }

if [[ "${1:-}" != "--resume" ]]; then

dst <<'SQL'
CREATE SCHEMA IF NOT EXISTS legacy;
DROP TABLE IF EXISTS legacy._stage_data;
CREATE UNLOGGED TABLE legacy._stage_data (
    id bigint, geoid varchar(64), year int, attribute_key varchar(128),
    attribute_value text, numeric_value double precision, data_type varchar(32),
    source varchar(128), collection_date date, confidence_level varchar(32),
    created_at timestamptz, updated_at timestamptz);
CREATE TABLE IF NOT EXISTS legacy.boundaries_quarantine (LIKE public.geographic_boundaries);
CREATE TABLE IF NOT EXISTS legacy.data_quarantine (
    LIKE legacy._stage_data, reason text NOT NULL);
-- TIGER layer -> census summary level
CREATE OR REPLACE FUNCTION legacy.summary_level(boundary_type text) RETURNS varchar(3)
LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE
        WHEN boundary_type = 'STATE'   THEN '040'
        WHEN boundary_type = 'COUNTY'  THEN '050'
        WHEN boundary_type = 'TRACT'   THEN '140'
        WHEN boundary_type = 'BG'      THEN '150'
        WHEN boundary_type = 'PLACE'   THEN '160'
        WHEN boundary_type = 'CBSA'    THEN '310'
        WHEN boundary_type LIKE 'CD%'  THEN '500'
        WHEN boundary_type = 'SLDU'    THEN '610'
        WHEN boundary_type = 'SLDL'    THEN '620'
        WHEN boundary_type LIKE 'ZCTA%' THEN '860'
        ELSE '000' END
$$;
SQL

BCOLS="geoid, year, name, geom, boundary_type, boundary_subtype, country, source,
       accuracy_meters, validity_start_date, validity_end_date, layer_id, source_upload_id,
       last_updated, created_at"

log "boundaries -> public"
src -c "COPY (SELECT $BCOLS FROM public.geographic_boundaries WHERE geoid <> '') TO STDOUT" \
  | dst -c "COPY public.geographic_boundaries ($BCOLS) FROM STDIN"
log "boundaries (empty geoid) -> legacy"
src -c "COPY (SELECT $BCOLS FROM public.geographic_boundaries WHERE geoid = '') TO STDOUT" \
  | dst -c "COPY legacy.boundaries_quarantine ($BCOLS) FROM STDIN"
dst -c "UPDATE public.geographic_boundaries SET summary_level = legacy.summary_level(boundary_type)"

log "data -> staging"
src -c "SET jit = off" -c "COPY (SELECT id, geoid, year, attribute_key, attribute_value, numeric_value,
        data_type, source, collection_date, confidence_level, created_at, updated_at
        FROM public.geographic_data) TO STDOUT" \
  | dst -c "COPY legacy._stage_data FROM STDIN"

log "classify + load"
dst <<'SQL'
SET work_mem = '512MB';
SET maintenance_work_mem = '2GB';
CREATE INDEX IF NOT EXISTS _stage_year_cell ON legacy._stage_data (year, geoid, attribute_key, id);
ANALYZE legacy._stage_data;

INSERT INTO legacy.data_quarantine
SELECT s.*, 'empty geoid (ZCTA/AREALM GEOID-column bug)' FROM legacy._stage_data s WHERE s.geoid = '';

DROP TABLE IF EXISTS legacy._conflicts;
CREATE TABLE legacy._conflicts AS
SELECT geoid, year, attribute_key
FROM legacy._stage_data
WHERE geoid <> ''
GROUP BY 1, 2, 3
HAVING count(DISTINCT (attribute_value, numeric_value, data_type)) > 1;
CREATE UNIQUE INDEX ON legacy._conflicts (geoid, year, attribute_key);
ANALYZE legacy._conflicts;

INSERT INTO legacy.data_quarantine
SELECT s.*, 'conflicting values for one (geoid, year, key): layers sharing a geoid'
FROM legacy._stage_data s
JOIN legacy._conflicts c USING (geoid, year, attribute_key);
SQL

fi

# Load year by year so each transaction stays bounded.
for y in $(dst -At -c "SELECT DISTINCT year FROM legacy._stage_data ORDER BY 1"); do
  if [[ "$(dst -At -c "SELECT EXISTS (SELECT 1 FROM public.geographic_data WHERE year = $y)")" == t ]]; then
    log "data year $y already loaded, skipping"; continue
  fi
  log "data year $y -> public"
  dst <<SQL
SET work_mem = '512MB';
INSERT INTO public.geographic_data
    (geoid, year, source_survey, summary_level, attribute_key, attribute_value, numeric_value,
     data_type, source, collection_date, confidence_level, created_at, updated_at)
SELECT DISTINCT ON (s.geoid, s.attribute_key)
       s.geoid, s.year, 'other', legacy.summary_level(b.boundary_type), s.attribute_key,
       s.attribute_value, s.numeric_value::numeric(24,8), s.data_type, s.source,
       s.collection_date, s.confidence_level, s.created_at, s.updated_at
FROM legacy._stage_data s
JOIN public.geographic_boundaries b ON b.geoid = s.geoid AND b.year = s.year
WHERE s.year = $y AND s.geoid <> ''
  AND NOT EXISTS (SELECT 1 FROM legacy._conflicts c
                  WHERE c.geoid = s.geoid AND c.year = s.year AND c.attribute_key = s.attribute_key)
ORDER BY s.geoid, s.attribute_key, s.id;
SQL
done

log "reconcile"
dst <<'SQL'
SELECT
  (SELECT count(*) FROM legacy._stage_data)                             AS source_rows,
  (SELECT count(*) FROM public.geographic_data)                         AS loaded,
  (SELECT count(*) FROM legacy.data_quarantine)                         AS quarantined,
  (SELECT count(*) FROM legacy._stage_data s WHERE s.geoid <> ''
     AND NOT EXISTS (SELECT 1 FROM legacy._conflicts c
                     WHERE c.geoid = s.geoid AND c.year = s.year AND c.attribute_key = s.attribute_key))
    - (SELECT count(*) FROM public.geographic_data)                     AS identical_dups_collapsed;
SQL
log "done (legacy._stage_data / legacy._conflicts kept for checks; drop them when satisfied)"
