-- ==========================================
-- Test Data Fixtures and Sample Data
-- Sample data generation for testing PostGIS ETL pipeline
-- ==========================================

-- Insert sample test configuration records
INSERT INTO test_framework.test_config (test_name, test_category, description, expected_result_count) VALUES
('Flood Zone Validation', 'FLOOD', 'Validates flood zone polygons and attributes', 100),
('Water Proximity Calculation', 'FLOOD', 'Tests distance calculations to water features', 50),
('Flood Risk Score Computation', 'FLOOD', 'Validates normalized flood risk scoring', 200),
('Precipitation Data Processing', 'WEATHER', 'Tests precipitation data aggregation', 1000),
('Extreme Rain Event Detection', 'WEATHER', 'Validates extreme rain identification', 500),
('Heat Index Calculation', 'HEAT', 'Tests heat stress index computation', 365),
('Solar Exposure Analysis', 'HEAT', 'Validates solar radiance calculations', 365),
('Wind Profile Analysis', 'HEAT', 'Tests wind speed/direction processing', 365),
('Air Quality Index', 'AIR_QUALITY', 'Tests multi-pollutant AQI calculation', 365),
('NO2 Layer Validation', 'AIR_QUALITY', 'Validates NO2 satellite data processing', 365),
('ACS Data Integration', 'CENSUS', 'Tests ACS demographic data joins', 3219),
('IRS Migration Processing', 'CENSUS', 'Validates IRS migration data', 3120),
('Geographic Identifier Validation', 'VALIDATION', 'Tests GEOID and FIPS validation', 50000),
('Coordinate System Accuracy', 'VALIDATION', 'Validates CRS transformations', 10000),
('Geometry Quality Check', 'VALIDATION', 'Tests geometry validity and cleanliness', 3500),
('MVT Vector Generation', 'PERFORMANCE', 'Tests Mapbox Vector Tile generation', 100),
('Spatial Query Performance', 'PERFORMANCE', 'Validates spatial index performance', 50)
ON CONFLICT (test_name) DO NOTHING;

-- Sample administrative boundary data (simplified)
CREATE TABLE IF NOT EXISTS test_data.sample_states AS
SELECT 
    '06'::VARCHAR as geoid,
    'California'::VARCHAR as name,
    'CA'::VARCHAR as statefp,
    ST_MakeEnvelope(-124.5, 32.5, -114.1, 42.0, 4326)::GEOMETRY as geom
UNION ALL
SELECT 
    '53'::VARCHAR as geoid,
    'Washington'::VARCHAR as name,
    'WA'::VARCHAR as statefp,
    ST_MakeEnvelope(-124.8, 45.5, -116.9, 49.0, 4326)::GEOMETRY as geom
UNION ALL
SELECT 
    '41'::VARCHAR as geoid,
    'Oregon'::VARCHAR as name,
    'OR'::VARCHAR as statefp,
    ST_MakeEnvelope(-124.6, 42.0, -116.5, 46.3, 4326)::GEOMETRY as geom;

-- Sample county data
CREATE TABLE IF NOT EXISTS test_data.sample_counties AS
SELECT 
    '06001'::VARCHAR as geoid,
    'Alameda County'::VARCHAR as name,
    '06'::VARCHAR as statefp,
    '001'::VARCHAR as countyfp,
    ST_MakeEnvelope(-122.3, 37.4, -121.5, 37.9, 4326)::GEOMETRY as geom
UNION ALL
SELECT 
    '06075'::VARCHAR as geoid,
    'San Francisco County'::VARCHAR as name,
    '06'::VARCHAR as statefp,
    '075'::VARCHAR as countyfp,
    ST_MakeEnvelope(-122.5, 37.7, -122.4, 37.8, 4326)::GEOMETRY as geom
UNION ALL
SELECT 
    '53033'::VARCHAR as geoid,
    'King County'::VARCHAR as name,
    '53'::VARCHAR as statefp,
    '033'::VARCHAR as countyfp,
    ST_MakeEnvelope(-122.4, 47.2, -121.2, 47.8, 4326)::GEOMETRY as geom;

-- Sample flood zone data
CREATE TABLE IF NOT EXISTS test_data.sample_flood_zones AS
SELECT 
    generate_series(1, 100) as id,
    CASE WHEN random() < 0.7 THEN 'AE' WHEN random() < 0.9 THEN 'X' ELSE 'VE' END as flood_zone,
    ST_MakePoint(
        -122.0 + (random() * 2.0), 
        37.5 + (random() * 1.0), 
        4326
    )::GEOMETRY as geom;

-- Sample precipitation data
CREATE TABLE IF NOT EXISTS test_data.sample_precipitation AS
SELECT 
    generate_series(1, 1000) as measurement_id,
    CASE WHEN random() < 0.3 THEN 'STATION_A' WHEN random() < 0.6 THEN 'STATION_B' ELSE 'STATION_C' END as station_id,
    CURRENT_DATE - (random() * 365)::INTEGER as measurement_date,
    ROUND((random() * 50)::NUMERIC, 2) as precipitation_mm,
    -122.0 + (random() * 2.0) as longitude,
    37.5 + (random() * 1.0) as latitude;

-- Sample temperature and humidity data
CREATE TABLE IF NOT EXISTS test_data.sample_heat_data AS
SELECT 
    generate_series(1, 365) as measurement_id,
    CURRENT_DATE - (generate_series(1, 365) - 1) as measurement_date,
    ROUND((15 + (random() * 20))::NUMERIC, 1) as temperature_c,
    ROUND((30 + (random() * 60))::NUMERIC, 1) as relative_humidity,
    -122.0 + (random() * 2.0) as longitude,
    37.5 + (random() * 1.0) as latitude;

-- Sample ACS demographic data
CREATE TABLE IF NOT EXISTS test_data.sample_acs_data AS
SELECT 
    CASE 
        WHEN random() < 0.5 THEN '06001' 
        WHEN random() < 0.75 THEN '06075' 
        ELSE '53033' 
    END as geoid,
    2022 as year,
    ROUND((50000 + (random() * 100000))::INTEGER) as total_population,
    ROUND((50000 + (random() * 100000))::INTEGER) as median_household_income,
    ROUND((25 + (random() * 25))::NUMERIC, 1) as median_age,
    ROUND((20 + (random() * 60))::NUMERIC, 1) as education_bachelors_or_higher_pct;

-- Sample air quality data
CREATE TABLE IF NOT EXISTS test_data.sample_air_quality AS
SELECT 
    generate_series(1, 365) as measurement_id,
    CASE 
        WHEN random() < 0.5 THEN '06001' 
        WHEN random() < 0.75 THEN '06075' 
        ELSE '53033' 
    END as geo_id,
    CURRENT_DATE - (generate_series(1, 365) - 1) as measurement_date,
    ROUND((random() * 200)::INTEGER) as aqi_value,
    CASE 
        WHEN random() < 0.6 THEN 'Good'
        WHEN random() < 0.8 THEN 'Moderate'
        WHEN random() < 0.95 THEN 'Unhealthy for Sensitive'
        ELSE 'Unhealthy'
    END as aqi_category,
    ROUND((random() * 50)::NUMERIC, 2) as no2_ug_m3,
    ROUND((random() * 30)::NUMERIC, 2) as pm25_ug_m3,
    ROUND((random() * 60)::NUMERIC, 2) as o3_ug_m3;

-- Sample H3 hexagon grid data
CREATE TABLE IF NOT EXISTS test_data.sample_h3_index AS
SELECT 
    h3_latlng_to_cell(37.5 + (random() * 1.0), -122.0 + (random() * 2.0), 7) as h3_id,
    7 as resolution,
    h3_cell_to_boundary(h3_latlng_to_cell(37.5 + (random() * 1.0), -122.0 + (random() * 2.0), 7))::GEOMETRY as geom
FROM generate_series(1, 200);

-- Sample wind data
CREATE TABLE IF NOT EXISTS test_data.sample_wind_data AS
SELECT 
    generate_series(1, 365) as measurement_id,
    CURRENT_DATE - (generate_series(1, 365) - 1) as measurement_date,
    ROUND((random() * 15)::NUMERIC, 2) as wind_speed_ms,
    ROUND((random() * 360)::INTEGER) as wind_direction_deg,
    CASE 
        WHEN random() < 0.4 THEN 'Calm'
        WHEN random() < 0.7 THEN 'Light'
        WHEN random() < 0.9 THEN 'Moderate'
        ELSE 'Strong'
    END as wind_speed_category,
    CASE WHEN random() < 0.5 THEN '06001' WHEN random() < 0.75 THEN '06075' ELSE '53033' END as geo_id;

-- Sample solar irradiance data
CREATE TABLE IF NOT EXISTS test_data.sample_solar_data AS
SELECT 
    generate_series(1, 365) as measurement_id,
    CURRENT_DATE - (generate_series(1, 365) - 1) as measurement_date,
    ROUND((100 + (random() * 600))::NUMERIC, 2) as ghi_wh_m2,
    ROUND((50 + (random() * 400))::NUMERIC, 2) as dni_wh_m2,
    ROUND((30 + (random() * 200))::NUMERIC, 2) as dhi_wh_m2,
    ROUND((random() * 100)::NUMERIC, 2) as solar_exposure_index,
    CASE WHEN random() < 0.5 THEN '06001' WHEN random() < 0.75 THEN '06075' ELSE '53033' END as geo_id;

-- Sample water bodies data
CREATE TABLE IF NOT EXISTS test_data.sample_water_bodies AS
SELECT 
    generate_series(1, 50) as id,
    CASE 
        WHEN random() < 0.4 THEN 'River'
        WHEN random() < 0.7 THEN 'Lake'
        WHEN random() < 0.9 THEN 'Stream'
        ELSE 'Wetland'
    END as water_type,
    'HYDROGRAPHY' as feature_class,
    ST_Buffer(
        ST_MakePoint(
            -122.0 + (random() * 2.0), 
            37.5 + (random() * 1.0), 
            4326
        )::GEOMETRY,
        (random() * 0.01)
    ) as geom;

-- Sample test data registry entries
INSERT INTO test_framework.test_data_registry (dataset_name, dataset_type, geometry_type, coordinate_system, row_count) VALUES
('sample_states', 'BOUNDARIES', 'MULTIPOLYGON', 'EPSG:4326', 3),
('sample_counties', 'BOUNDARIES', 'MULTIPOLYGON', 'EPSG:4326', 3),
('sample_flood_zones', 'FLOOD', 'POINT', 'EPSG:4326', 100),
('sample_precipitation', 'WEATHER', 'POINT', 'EPSG:4326', 1000),
('sample_heat_data', 'WEATHER', 'POINT', 'EPSG:4326', 365),
('sample_acs_data', 'CENSUS', 'NONE', 'NONE', 3),
('sample_air_quality', 'AIR_QUALITY', 'NONE', 'NONE', 365),
('sample_h3_index', 'GRID', 'POLYGON', 'EPSG:4326', 200),
('sample_wind_data', 'WEATHER', 'NONE', 'NONE', 365),
('sample_solar_data', 'WEATHER', 'NONE', 'NONE', 365),
('sample_water_bodies', 'HYDROGRAPHY', 'POLYGON', 'EPSG:4326', 50)
ON CONFLICT (dataset_name) DO NOTHING;

-- Create sample validation rules
INSERT INTO test_framework.validation_rules (test_config_id, rule_name, rule_type, rule_definition, is_critical) VALUES
(
    (SELECT id FROM test_framework.test_config WHERE test_name = 'Flood Zone Validation'),
    'geometry_validity_check',
    'GEOMETRY_VALID',
    '{"require_valid": true, "allow_empty": false}',
    true
),
(
    (SELECT id FROM test_framework.test_config WHERE test_name = 'Precipitation Data Processing'),
    'data_range_validation',
    'DATA_RANGE',
    '{"min_value": 0, "max_value": 1000, "column": "precipitation_mm"}',
    true
),
(
    (SELECT id FROM test_framework.test_config WHERE test_name = 'ACS Data Integration'),
    'geoid_format_check',
    'ROW_COUNT',
    '{"min_rows": 1, "geoid_pattern": "^[0-9]{5}$"}',
    true
)
ON CONFLICT DO NOTHING;

-- Create sample performance benchmarks
INSERT INTO test_framework.performance_benchmarks (test_config_id, baseline_time_ms, max_acceptable_time_ms, memory_usage_mb) VALUES
(
    (SELECT id FROM test_framework.test_config WHERE test_name = 'Spatial Query Performance'),
    500,  -- 500ms baseline
    2000, -- 2 second max
    50.0   -- 50MB memory
),
(
    (SELECT id FROM test_framework.test_config WHERE test_name = 'MVT Vector Generation'),
    100,  -- 100ms baseline
    1000, -- 1 second max
    25.0   -- 25MB memory
),
(
    (SELECT id FROM test_framework.test_config WHERE test_name = 'Air Quality Index'),
    200,  -- 200ms baseline
    1000, -- 1 second max
    30.0   -- 30MB memory
)
ON CONFLICT DO NOTHING;

-- Create sample flood risk scores table for testing
CREATE TABLE IF NOT EXISTS test_data.sample_flood_risk_scores AS
SELECT 
    h3_id,
    ROUND((random() * 100)::NUMERIC, 2) as flood_risk_score,
    ROUND((random() * 5)::INTEGER) as flood_zone_count,
    ROUND((random() * 1000)::NUMERIC, 2) as water_distance_m,
    ROUND((random() * 1.0)::NUMERIC, 3) as water_proximity_factor,
    ROUND((random() * 1.0)::NUMERIC, 3) as elevation_factor
FROM test_data.sample_h3_index;

-- Create sample census tracts
CREATE TABLE IF NOT EXISTS test_data.sample_census_tracts AS
SELECT 
    CASE 
        WHEN random() < 0.3 THEN '06075010100'
        WHEN random() < 0.6 THEN '06075010200'
        WHEN random() < 0.8 THEN '06001010100'
        ELSE '06001010200'
    END as geoid,
    'Sample Tract ' || generate_series(1, 20) as name,
    ST_MakePoint(
        -122.0 + (random() * 2.0), 
        37.5 + (random() * 1.0), 
        4326
    )::GEOMETRY as geom
FROM generate_series(1, 20);

-- Create sample places (cities/towns)
CREATE TABLE IF NOT EXISTS test_data.sample_places AS
SELECT 
    CASE 
        WHEN random() < 0.3 THEN '0600000'
        WHEN random() < 0.6 THEN '5300000'
        ELSE '4100000'
    END as geoid,
    CASE 
        WHEN random() < 0.3 THEN 'Sample City CA'
        WHEN random() < 0.6 THEN 'Sample City WA'
        ELSE 'Sample City OR'
    END as name,
    ST_Buffer(
        ST_MakePoint(
            -122.0 + (random() * 2.0), 
            37.5 + (random() * 1.0), 
            4326
        )::GEOMETRY,
        (random() * 0.05)
    ) as geom
FROM generate_series(1, 10);

-- Create sample elevation derivatives
CREATE TABLE IF NOT EXISTS test_data.sample_elevation_derivatives AS
SELECT 
    h3_id,
    ROUND((100 + (random() * 1000))::NUMERIC, 2) as elevation_m,
    ROUND((random() * 45)::NUMERIC, 2) as slope_degrees,
    ROUND((random() * 10000)::INTEGER) as flow_accumulation
FROM test_data.sample_h3_index;

-- Create sample storm events
CREATE TABLE IF NOT EXISTS test_data.sample_storm_events AS
SELECT 
    generate_series(1, 50) as event_id,
    CASE 
        WHEN random() < 0.4 THEN 'THUNDERSTORM'
        WHEN random() < 0.7 THEN 'HEAVY_RAIN'
        WHEN random() < 0.9 THEN 'FLOOD'
        ELSE 'EXTREME_PRECIPITATION'
    END as event_type,
    CURRENT_DATE - (random() * 365)::INTEGER as event_date,
    CASE 
        WHEN random() < 0.5 THEN 'POINT'
        ELSE 'POLYGON'
    END as geometry_type,
    CASE 
        WHEN random() < 0.5 THEN 
            ST_MakePoint(-122.0 + (random() * 2.0), 37.5 + (random() * 1.0), 4326)::GEOMETRY
        ELSE 
            ST_Buffer(
                ST_MakePoint(-122.0 + (random() * 2.0), 37.5 + (random() * 1.0), 4326)::GEOMETRY,
                (random() * 0.02)
            )
    END as geom;

-- Create sample UV data
CREATE TABLE IF NOT EXISTS test_data.sample_uv_data AS
SELECT 
    generate_series(1, 365) as measurement_id,
    CURRENT_DATE - (generate_series(1, 365) - 1) as measurement_date,
    ROUND((random() * 12)::INTEGER) as uv_index,
    CASE 
        WHEN random() < 0.4 THEN 'Low'
        WHEN random() < 0.6 THEN 'Moderate'
        WHEN random() < 0.8 THEN 'High'
        WHEN random() < 0.95 THEN 'Very High'
        ELSE 'Extreme'
    END as uv_risk_category,
    CASE WHEN random() < 0.5 THEN '06001' WHEN random() < 0.75 THEN '06075' ELSE '53033' END as geo_id;

-- Create sample population estimates
CREATE TABLE IF NOT EXISTS test_data.sample_population_estimates AS
SELECT 
    CASE 
        WHEN random() < 0.5 THEN '06001' 
        WHEN random() < 0.75 THEN '06075' 
        ELSE '53033' 
    END as geoid,
    2022 as year,
    ROUND((50000 + (random() * 100000))::INTEGER) as total_population,
    ROUND((total_population * 0.49)::INTEGER) as male_population,
    ROUND((total_population * 0.51)::INTEGER) as female_population,
    ROUND((total_population * 0.35)::INTEGER) as housing_units
FROM test_data.sample_acs_data;

-- Add spatial indexes for performance testing
CREATE INDEX IF NOT EXISTS idx_sample_states_geom ON test_data.sample_states USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_sample_counties_geom ON test_data.sample_counties USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_sample_flood_zones_geom ON test_data.sample_flood_zones USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_sample_water_bodies_geom ON test_data.sample_water_bodies USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_sample_h3_index_geom ON test_data.sample_h3_index USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_sample_census_tracts_geom ON test_data.sample_census_tracts USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_sample_places_geom ON test_data.sample_places USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_sample_storm_events_geom ON test_data.sample_storm_events USING GIST (geom);

-- Add data quality indexes
CREATE INDEX IF NOT EXISTS idx_sample_precipitation_date ON test_data.sample_precipitation (measurement_date);
CREATE INDEX IF NOT EXISTS idx_sample_heat_data_date ON test_data.sample_heat_data (measurement_date);
CREATE INDEX IF NOT EXISTS idx_sample_air_quality_date ON test_data.sample_air_quality (measurement_date);
CREATE INDEX IF NOT EXISTS idx_sample_acs_geoid_year ON test_data.sample_acs_data (geoid, year);
CREATE INDEX IF NOT EXISTS idx_sample_flood_risk_h3_id ON test_data.sample_flood_risk_scores (h3_id);

-- Create views for common test scenarios
CREATE OR REPLACE VIEW test_data.test_flood_scenario AS
SELECT 
    c.geoid,
    c.name as county_name,
    COUNT(fz.id) as flood_zone_count,
    AVG(frs.flood_risk_score) as avg_flood_risk_score,
    COUNT(wb.id) as nearby_water_bodies
FROM test_data.sample_counties c
LEFT JOIN test_data.sample_flood_zones fz ON ST_Intersects(c.geom, fz.geom)
LEFT JOIN test_data.sample_flood_risk_scores frs ON ST_Intersects(c.geom, (SELECT ST_Union(geom) FROM test_data.sample_h3_index))
LEFT JOIN test_data.sample_water_bodies wb ON ST_DWithin(c.geom, wb.geom, 0.01)
GROUP BY c.geoid, c.name;

CREATE OR REPLACE VIEW test_data.test_weather_scenario AS
SELECT 
    hd.measurement_date,
    AVG(hd.temperature_c) as avg_temperature,
    AVG(hd.relative_humidity) as avg_humidity,
    AVG(prec.precipitation_mm) as total_precipitation,
    AVG(wd.wind_speed_ms) as avg_wind_speed,
    AVG(sd.solar_exposure_index) as avg_solar_exposure
FROM test_data.sample_heat_data hd
LEFT JOIN test_data.sample_precipitation prec ON hd.measurement_date = prec.measurement_date
LEFT JOIN test_data.sample_wind_data wd ON hd.measurement_date = wd.measurement_date
LEFT JOIN test_data.sample_solar_data sd ON hd.measurement_date = sd.measurement_date
GROUP BY hd.measurement_date;

-- Commit all test data creation
COMMIT;