BEGIN;

CREATE TABLE IF NOT EXISTS public.hexes_borders (
    hex_id                        TEXT NOT NULL REFERENCES public.hexes(hex_id) ON DELETE CASCADE,
    geoid                         VARCHAR(64) NOT NULL,
    year                          INTEGER NOT NULL,
    overlap_ratio_hex_to_border   DOUBLE PRECISION,
    overlap_ratio_border_to_hex   DOUBLE PRECISION,
    geom                          geometry(MULTIPOLYGON, 4326), 
    
    -- Link to the composite PK in borders
    CONSTRAINT fk_hexes_borders_to_borders 
        FOREIGN KEY (geoid, year) 
        REFERENCES public.borders(geoid, year) 
        ON DELETE CASCADE,

    -- The new PK for this table ensures a hex/border link is unique per year
    PRIMARY KEY (hex_id, geoid, year)
);

-- Index for the reverse lookup (finding hexes for a border in a specific year)
CREATE INDEX IF NOT EXISTS idx_hexes_borders_geoid_year 
    ON public.hexes_borders(geoid, year);

GRANT ALL PRIVILEGES ON public.hexes_borders TO geoagent;

COMMIT;
