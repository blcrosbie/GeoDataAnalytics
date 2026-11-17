-- geographic_data: make the cell key the primary key; drop the near-duplicate.
--
-- The old primary key (source_survey, year, summary_level, geoid, attribute_key, id)
-- duplicated uq_geo_cell (the same five columns without id): two ~7-10 GB indexes
-- per ACS year holding the same rows. The five-column cell key already identifies a
-- row, so it becomes the primary key and both old indexes go. ON CONFLICT targets
-- name columns, not constraints, so loaders need no change.
--
-- Takes an ACCESS EXCLUSIVE lock on geographic_data while the new index builds
-- (~15 min for 5 x 106M ACS rows); run with no loaders or readers active.

SET maintenance_work_mem = '1GB';

BEGIN;
ALTER TABLE public.geographic_data DROP CONSTRAINT geographic_data_pkey;
ALTER TABLE public.geographic_data
    ADD CONSTRAINT geographic_data_pkey
        PRIMARY KEY (source_survey, year, summary_level, geoid, attribute_key);
ALTER TABLE public.geographic_data DROP CONSTRAINT uq_geo_cell;
COMMIT;
