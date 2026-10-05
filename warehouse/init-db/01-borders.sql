BEGIN;

CREATE TABLE IF NOT EXISTS public.borders (
    geoid                          VARCHAR(64) NOT NULL,
    year                           INTEGER NOT NULL,
    name                           VARCHAR(255) NOT NULL,
    geom                           geometry(MULTIPOLYGON, 4326),
    border_type                    VARCHAR(64),
    border_subtype                 VARCHAR(64),
    country_alpha_3                VARCHAR(8),
    last_updated                   TIMESTAMPTZ DEFAULT NOW(),
    
    PRIMARY KEY (geoid, year)
);

CREATE INDEX IF NOT EXISTS idx_borders_geom
    ON public.borders USING GIST (geom);

GRANT ALL PRIVILEGES ON public.borders TO geoagent;

COMMIT;
