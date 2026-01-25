BEGIN;

CREATE TABLE IF NOT EXISTS public.hexes (
    hex_id                         TEXT PRIMARY KEY,
    resolution                     INTEGER,
    country                        VARCHAR(64),
    country_alpha_3                VARCHAR(8),
    geom                           geometry(POLYGON, 4326),
    lng                            DOUBLE PRECISION,
    lat                            DOUBLE PRECISION,
    h3_cell_area                   DOUBLE PRECISION,
    name                           VARCHAR(255),
    region                         VARCHAR(255),
    state_alpha_2                  VARCHAR(8),
    pop_total_h5                   DOUBLE PRECISION,
    housing_total_h5               DOUBLE PRECISION,
    housing_occupied_h5            DOUBLE PRECISION,
    pop_density_h5                 DOUBLE PRECISION,
    last_updated                   TIMESTAMPTZ,
    number_of_agents               INTEGER DEFAULT 0,
    buy_now_price                  DOUBLE PRECISION,

    -- New building morphology / classification fields
    buildings_total                          INTEGER,
    density_buildings_per_km2                DOUBLE PRECISION,
    density_buildings_residential_per_km2    DOUBLE PRECISION,
    buildings_height_avg_m                   DOUBLE PRECISION,
    buildings_height_max_m                   DOUBLE PRECISION,
    buildings_tall_gte_50_m                  INTEGER,
    buildings_residential                    INTEGER,
    buildings_commercial                     INTEGER,
    buildings_industrial                     INTEGER,
    buildings_institutional                  INTEGER,
    buildings_other                          INTEGER,
    urban_class                              VARCHAR(32),

    -- RAN coverage / capacity metrics
    pathloss_model                           VARCHAR(32),
    airnode_portal_180_coverage_radius_km    DOUBLE PRECISION,
    airnode_portal_180_sector_area_km2       DOUBLE PRECISION,
    number_of_airnode_portal_360_required    INTEGER,

    -- Economics
    starting_bid                             DOUBLE PRECISION,
    ran_planning_constraint                  VARCHAR(255),

    -- Politics / Water
    is_inhibited                             BOOLEAN NOT NULL DEFAULT false,
    reason_inhibited                         TEXT DEFAULT NULL,
    number_of_watchers                       INTEGER DEFAULT 0,
    view_count                               INTEGER NOT NULL DEFAULT 0,
    number_of_hosts                          INTEGER DEFAULT 0
);


CREATE INDEX IF NOT EXISTS hexes_geom_gix ON public.hexes USING GIST (geom);

CREATE INDEX IF NOT EXISTS hexes_center_geog_gix
    ON public.hexes
    USING GIST ((CAST(ST_SetSRID(ST_MakePoint(lng, lat), 4326) AS geography)));

GRANT ALL PRIVILEGES ON public.hexes TO geoagent;

COMMIT;
