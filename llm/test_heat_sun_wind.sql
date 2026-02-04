-- ==========================================
-- Heat / Sun / Wind Layer Tests
-- Tests for heat stress index, solar exposure, and wind profile calculations
-- ==========================================

-- Test 1: Heat Stress Index Calculation
-- Validates heat index calculations and temperature data quality
WITH heat_stress_validation AS (
    SELECT 
        geo_id,
        measurement_date,
        temperature_c,
        relative_humidity,
        heat_index_c,
        CASE 
            WHEN temperature_c < -50 OR temperature_c > 60 THEN 'TEMPERATURE_OUT_OF_RANGE'
            WHEN relative_humidity < 0 OR relative_humidity > 100 THEN 'HUMIDITY_OUT_OF_RANGE'
            WHEN heat_index_c < temperature_c THEN 'HEAT_INDEX_LOWER_THAN_TEMP'
            WHEN heat_index_c IS NULL THEN 'NULL_HEAT_INDEX'
            ELSE 'VALID'
        END as heat_stress_validity
    FROM staging.heat_data
),
heat_stats AS (
    SELECT 
        COUNT(*) as total_measurements,
        COUNT(CASE WHEN heat_stress_validity = 'VALID' THEN 1 END) as valid_measurements,
        COUNT(CASE WHEN heat_stress_validity LIKE 'TEMPERATURE%' THEN 1 END) as temperature_issues,
        COUNT(CASE WHEN heat_stress_validity LIKE 'HUMIDITY%' THEN 1 END) as humidity_issues,
        AVG(temperature_c) as avg_temperature,
        MAX(temperature_c) as max_temperature,
        MIN(temperature_c) as min_temperature,
        AVG(heat_index_c) as avg_heat_index,
        MAX(heat_index_c) as max_heat_index
    FROM heat_stress_validation
)
SELECT 
    'Heat Stress Index Calculation' as test_name,
    CASE 
        WHEN total_measurements = 0 THEN 'FAIL: No heat data found'
        WHEN valid_measurements < total_measurements * 0.95 THEN 'FAIL: Heat stress index validation failed'
        ELSE 'PASS: Heat stress index calculation valid'
    END as status,
    total_measurements,
    valid_measurements,
    temperature_issues,
    humidity_issues,
    ROUND(avg_temperature, 2) as average_temperature_c,
    ROUND(max_temperature, 2) as max_temperature_c,
    ROUND(min_temperature, 2) as min_temperature_c,
    ROUND(avg_heat_index, 2) as average_heat_index_c,
    ROUND(max_heat_index, 2) as max_heat_index_c
FROM heat_stats;

-- Test 2: Heat Days Frequency Validation
-- Validates the calculation of extreme heat days and heat waves
WITH heat_days_validation AS (
    SELECT 
        geo_id,
        year,
        month,
        heat_days_count,  -- Days with temp > 32°C (90°F)
        extreme_heat_days, -- Days with temp > 37.8°C (100°F)
        heat_wave_events, -- Consecutive heat days >= 3
        max_consecutive_heat_days,
        CASE 
            WHEN heat_days_count < 0 OR heat_days_count > 31 THEN 'INVALID_HEAT_DAYS'
            WHEN extreme_heat_days < 0 OR extreme_heat_days > 31 THEN 'INVALID_EXTREME_DAYS'
            WHEN max_consecutive_heat_days > 31 THEN 'INVALID_CONSECUTIVE_DAYS'
            WHEN extreme_heat_days > heat_days_count THEN 'EXTREME_EXCEEDS_TOTAL'
            ELSE 'VALID'
        END as days_validity
    FROM serving.heat_frequency
),
heat_days_stats AS (
    SELECT 
        COUNT(*) as total_records,
        COUNT(CASE WHEN days_validity = 'VALID' THEN 1 END) as valid_records,
        COUNT(CASE WHEN days_validity LIKE 'INVALID%' THEN 1 END) as invalid_records,
        AVG(heat_days_count) as avg_heat_days,
        MAX(heat_days_count) as max_heat_days,
        AVG(extreme_heat_days) as avg_extreme_heat_days,
        MAX(extreme_heat_days) as max_extreme_heat_days,
        AVG(heat_wave_events) as avg_heat_waves,
        AVG(max_consecutive_heat_days) as avg_consecutive_days
    FROM heat_days_validation
)
SELECT 
    'Heat Days Frequency Validation' as test_name,
    CASE 
        WHEN total_records = 0 THEN 'FAIL: No heat frequency data found'
        WHEN valid_records < total_records * 0.98 THEN 'FAIL: Heat days frequency validation failed'
        ELSE 'PASS: Heat days frequency calculation valid'
    END as status,
    total_records,
    valid_records,
    invalid_records,
    ROUND(avg_heat_days, 2) as average_heat_days_per_month,
    max_heat_days,
    ROUND(avg_extreme_heat_days, 2) as average_extreme_heat_days,
    max_extreme_heat_days,
    ROUND(avg_heat_waves, 2) as average_heat_waves,
    ROUND(avg_consecutive_days, 2) as average_consecutive_heat_days
FROM heat_days_stats;

-- Test 3: Solar Exposure Index Calculation
-- Validates solar radiance calculations and GHI data processing
WITH solar_exposure_validation AS (
    SELECT 
        geo_id,
        date,
        ghi_wh_m2,  -- Global Horizontal Irradiance
        dni_wh_m2,  -- Direct Normal Irradiance
        dhi_wh_m2,  -- Diffuse Horizontal Irradiance
        solar_exposure_index,
        CASE 
            WHEN ghi_wh_m2 < 0 OR ghi_wh_m2 > 1200 THEN 'GHI_OUT_OF_RANGE'
            WHEN dni_wh_m2 < 0 OR dni_wh_m2 > 1000 THEN 'DNI_OUT_OF_RANGE'
            WHEN dhi_wh_m2 < 0 OR dhi_wh_m2 > 700 THEN 'DHI_OUT_OF_RANGE'
            WHEN solar_exposure_index < 0 OR solar_exposure_index > 100 THEN 'SOLAR_INDEX_OUT_OF_RANGE'
            WHEN ghi_wh_m2 < (dni_wh_m2 * COS(45) + dhi_wh_m2) THEN 'IRRADIANCE_PHYSICS_ERROR'
            ELSE 'VALID'
        END as solar_validity
    FROM staging.solar_irradiance
),
solar_stats AS (
    SELECT 
        COUNT(*) as total_measurements,
        COUNT(CASE WHEN solar_validity = 'VALID' THEN 1 END) as valid_measurements,
        COUNT(CASE WHEN solar_validity LIKE '%OUT_OF_RANGE' THEN 1 END) as out_of_range_measurements,
        COUNT(CASE WHEN solar_validity = 'IRRADIANCE_PHYSICS_ERROR' THEN 1 END) as physics_errors,
        AVG(ghi_wh_m2) as avg_ghi,
        MAX(ghi_wh_m2) as max_ghi,
        MIN(ghi_wh_m2) as min_ghi,
        AVG(solar_exposure_index) as avg_solar_index,
        MAX(solar_exposure_index) as max_solar_index
    FROM solar_exposure_validation
)
SELECT 
    'Solar Exposure Index Calculation' as test_name,
    CASE 
        WHEN total_measurements = 0 THEN 'FAIL: No solar irradiance data found'
        WHEN valid_measurements < total_measurements * 0.95 THEN 'FAIL: Solar exposure validation failed'
        ELSE 'PASS: Solar exposure index calculation valid'
    END as status,
    total_measurements,
    valid_measurements,
    out_of_range_measurements,
    physics_errors,
    ROUND(avg_ghi, 2) as average_ghi_wh_m2,
    ROUND(max_ghi, 2) as max_ghi_wh_m2,
    ROUND(min_ghi, 2) as min_ghi_wh_m2,
    ROUND(avg_solar_index, 2) as average_solar_exposure_index,
    ROUND(max_solar_index, 2) as max_solar_exposure_index
FROM solar_stats;

-- Test 4: Wind Profile Analysis Validation
-- Validates wind speed, direction, and frequency calculations
WITH wind_profile_validation AS (
    SELECT 
        geo_id,
        measurement_date,
        wind_speed_ms,
        wind_direction_deg,
        prevailing_wind_direction,
        wind_speed_category,  -- Calm, Light, Moderate, Strong, Severe
        CASE 
            WHEN wind_speed_ms < 0 OR wind_speed_ms > 100 THEN 'WIND_SPEED_OUT_OF_RANGE'
            WHEN wind_direction_deg < 0 OR wind_direction_deg >= 360 THEN 'WIND_DIRECTION_OUT_OF_RANGE'
            WHEN prevailing_wind_direction < 0 OR prevailing_wind_direction >= 360 THEN 'PREVAILING_DIRECTION_INVALID'
            WHEN wind_speed_category NOT IN ('Calm', 'Light', 'Moderate', 'Strong', 'Severe') THEN 'INVALID_CATEGORY'
            ELSE 'VALID'
        END as wind_validity
    FROM staging.wind_data
),
wind_stats AS (
    SELECT 
        COUNT(*) as total_measurements,
        COUNT(CASE WHEN wind_validity = 'VALID' THEN 1 END) as valid_measurements,
        COUNT(CASE WHEN wind_validity LIKE '%OUT_OF_RANGE' THEN 1 END) as out_of_range_measurements,
        AVG(wind_speed_ms) as avg_wind_speed,
        MAX(wind_speed_ms) as max_wind_speed,
        MIN(wind_speed_ms) as min_wind_speed,
        STDDEV(wind_speed_ms) as stddev_wind_speed,
        COUNT(DISTINCT prevailing_wind_direction) as unique_prevailing_directions,
        AVG(wind_direction_deg) as avg_wind_direction
    FROM wind_profile_validation
)
SELECT 
    'Wind Profile Analysis Validation' as test_name,
    CASE 
        WHEN total_measurements = 0 THEN 'FAIL: No wind data found'
        WHEN valid_measurements < total_measurements * 0.95 THEN 'FAIL: Wind profile validation failed'
        ELSE 'PASS: Wind profile analysis valid'
    END as status,
    total_measurements,
    valid_measurements,
    out_of_range_measurements,
    ROUND(avg_wind_speed, 2) as average_wind_speed_ms,
    ROUND(max_wind_speed, 2) as max_wind_speed_ms,
    ROUND(min_wind_speed, 2) as min_wind_speed_ms,
    ROUND(stddev_wind_speed, 2) as stddev_wind_speed_ms,
    unique_prevailing_directions,
    ROUND(avg_wind_direction, 2) as average_wind_direction_deg
FROM wind_stats;

-- Test 5: Seasonal Temperature Patterns Validation
-- Validates seasonal temperature calculations and anomalies
WITH seasonal_validation AS (
    SELECT 
        geo_id,
        season,  -- Winter, Spring, Summer, Fall
        avg_temperature_c,
        max_temperature_c,
        min_temperature_c,
        temperature_anomaly_c,  -- Difference from long-term average
        CASE 
            WHEN season NOT IN ('Winter', 'Spring', 'Summer', 'Fall') THEN 'INVALID_SEASON'
            WHEN avg_temperature_c < -50 OR avg_temperature_c > 60 THEN 'AVG_TEMP_OUT_OF_RANGE'
            WHEN max_temperature_c < min_temperature_c THEN 'MAX_LESS_THAN_MIN'
            WHEN temperature_anomaly_c < -30 OR temperature_anomaly_c > 30 THEN 'ANOMALY_OUT_OF_RANGE'
            ELSE 'VALID'
        END as seasonal_validity
    FROM serving.seasonal_temperature
),
seasonal_stats AS (
    SELECT 
        COUNT(*) as total_seasonal_records,
        COUNT(CASE WHEN seasonal_validity = 'VALID' THEN 1 END) as valid_records,
        COUNT(CASE WHEN seasonal_validity = 'INVALID_SEASON' THEN 1 END) as invalid_season_records,
        COUNT(DISTINCT season) as unique_seasons,
        AVG(avg_temperature_c) as avg_seasonal_temp,
        MAX(avg_temperature_c) as max_avg_seasonal_temp,
        MIN(avg_temperature_c) as min_avg_seasonal_temp,
        AVG(ABS(temperature_anomaly_c)) as avg_absolute_anomaly,
        MAX(ABS(temperature_anomaly_c)) as max_absolute_anomaly
    FROM seasonal_validation
)
SELECT 
    'Seasonal Temperature Patterns' as test_name,
    CASE 
        WHEN total_seasonal_records = 0 THEN 'FAIL: No seasonal temperature data found'
        WHEN valid_records < total_seasonal_records * 0.98 THEN 'FAIL: Seasonal temperature validation failed'
        WHEN unique_seasons != 4 THEN 'FAIL: Incomplete seasonal coverage'
        ELSE 'PASS: Seasonal temperature patterns valid'
    END as status,
    total_seasonal_records,
    valid_records,
    invalid_season_records,
    unique_seasons,
    ROUND(avg_seasonal_temp, 2) as average_seasonal_temperature_c,
    ROUND(max_avg_seasonal_temp, 2) as max_avg_seasonal_temp_c,
    ROUND(min_avg_seasonal_temp, 2) as min_avg_seasonal_temp_c,
    ROUND(avg_absolute_anomaly, 2) as average_absolute_anomaly_c,
    ROUND(max_absolute_anomaly, 2) as max_absolute_anomaly_c
FROM seasonal_stats;

-- Test 6: UV Index Calculation Validation
-- Validates UV index calculations and risk categorization
WITH uv_validation AS (
    SELECT 
        geo_id,
        date,
        uv_index,
        uv_risk_category,  -- Low, Moderate, High, Very High, Extreme
        CASE 
            WHEN uv_index < 0 OR uv_index > 15 THEN 'UV_INDEX_OUT_OF_RANGE'
            WHEN uv_risk_category NOT IN ('Low', 'Moderate', 'High', 'Very High', 'Extreme') THEN 'INVALID_UV_CATEGORY'
            WHEN uv_index < 3 AND uv_risk_category != 'Low' THEN 'UV_CATEGORY_MISMATCH'
            WHEN uv_index >= 3 AND uv_index < 6 AND uv_risk_category != 'Moderate' THEN 'UV_CATEGORY_MISMATCH'
            WHEN uv_index >= 6 AND uv_index < 8 AND uv_risk_category != 'High' THEN 'UV_CATEGORY_MISMATCH'
            WHEN uv_index >= 8 AND uv_index < 11 AND uv_risk_category != 'Very High' THEN 'UV_CATEGORY_MISMATCH'
            WHEN uv_index >= 11 AND uv_risk_category != 'Extreme' THEN 'UV_CATEGORY_MISMATCH'
            ELSE 'VALID'
        END as uv_validity
    FROM staging.uv_data
),
uv_stats AS (
    SELECT 
        COUNT(*) as total_uv_measurements,
        COUNT(CASE WHEN uv_validity = 'VALID' THEN 1 END) as valid_measurements,
        COUNT(CASE WHEN uv_validity = 'UV_INDEX_OUT_OF_RANGE' THEN 1 END) as out_of_range_measurements,
        COUNT(CASE WHEN uv_validity = 'UV_CATEGORY_MISMATCH' THEN 1 END) as category_mismatches,
        AVG(uv_index) as avg_uv_index,
        MAX(uv_index) as max_uv_index,
        MIN(uv_index) as min_uv_index,
        COUNT(DISTINCT uv_risk_category) as unique_uv_categories
    FROM uv_validation
)
SELECT 
    'UV Index Calculation Validation' as test_name,
    CASE 
        WHEN total_uv_measurements = 0 THEN 'FAIL: No UV index data found'
        WHEN valid_measurements < total_uv_measurements * 0.95 THEN 'FAIL: UV index validation failed'
        WHEN unique_uv_categories != 5 THEN 'FAIL: Incomplete UV risk categories'
        ELSE 'PASS: UV index calculation valid'
    END as status,
    total_uv_measurements,
    valid_measurements,
    out_of_range_measurements,
    category_mismatches,
    ROUND(avg_uv_index, 2) as average_uv_index,
    max_uv_index,
    min_uv_index,
    unique_uv_categories
FROM uv_stats;

-- Test 7: Temperature-Humidity Relationship Validation
-- Validates physical relationships between temperature and humidity
WITH temp_humidity_relationship AS (
    SELECT 
        geo_id,
        measurement_date,
        temperature_c,
        relative_humidity,
        dew_point_c,
        CASE 
            WHEN temperature_c < dew_point_c THEN 'TEMP_BELOW_DEWPOINT'
            WHEN dew_point_c < -40 OR dew_point_c > 50 THEN 'DEWPOINT_OUT_OF_RANGE'
            WHEN relative_humidity = 0 AND temperature_c > dew_point_c + 5 THEN 'HUMIDITY_DEWPOINT_CONFLICT'
            ELSE 'VALID'
        END as relationship_validity
    FROM staging.heat_data
    WHERE dew_point_c IS NOT NULL
),
relationship_stats AS (
    SELECT 
        COUNT(*) as total_relationship_checks,
        COUNT(CASE WHEN relationship_validity = 'VALID' THEN 1 END) as valid_relationships,
        COUNT(CASE WHEN relationship_validity = 'TEMP_BELOW_DEWPOINT' THEN 1 END) as temp_below_dewpoint,
        AVG(temperature_c) as avg_temperature,
        AVG(relative_humidity) as avg_humidity,
        AVG(dew_point_c) as avg_dewpoint,
        AVG(temperature_c - dew_point_c) as avg_temp_dewpoint_spread
    FROM temp_humidity_relationship
)
SELECT 
    'Temperature-Humidity Relationship' as test_name,
    CASE 
        WHEN total_relationship_checks = 0 THEN 'FAIL: No temperature-humidity relationship data'
        WHEN valid_relationships < total_relationship_checks * 0.98 THEN 'FAIL: Temperature-humidity relationship validation failed'
        WHEN temp_below_dewpoint > total_relationship_checks * 0.01 THEN 'FAIL: Temperature below dew point detected'
        ELSE 'PASS: Temperature-humidity relationship valid'
    END as status,
    total_relationship_checks,
    valid_relationships,
    temp_below_dewpoint,
    ROUND(avg_temperature, 2) as average_temperature_c,
    ROUND(avg_humidity, 2) as average_humidity_percent,
    ROUND(avg_dewpoint, 2) as average_dew_point_c,
    ROUND(avg_temp_dewpoint_spread, 2) as average_temp_dewpoint_spread_c
FROM relationship_stats;

-- Test 8: Performance Test: Heat Index Query Performance
-- Tests performance of heat-related spatial queries
EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
SELECT 
    COUNT(*) as high_heat_locations,
    AVG(heat_index_c) as avg_heat_index
FROM staging.heat_data hd
JOIN serving.h3_index h3 ON ST_Contains(h3.geom, ST_MakePoint(hd.longitude, hd.latitude, 4326))
WHERE measurement_date >= CURRENT_DATE - INTERVAL '30 days'
AND heat_index_c > 32  -- Dangerous heat index threshold
AND ST_Intersects(
    h3.geom,
    ST_MakeEnvelope(-125.0, 32.0, -114.0, 42.0, 4326)
);

-- Test 9: Comprehensive Heat/Sun/Wind Integration
-- Tests end-to-end integration of all thermal and solar data
WITH thermal_integration AS (
    SELECT 
        h3_id,
        heat_stress_index,
        solar_exposure_index,
        avg_wind_speed_ms,
        prevailing_wind_direction,
        seasonal_temperature_anomaly,
        CASE 
            WHEN heat_stress_index BETWEEN 0 AND 100 THEN 'HEAT_INDEX_VALID'
            ELSE 'HEAT_INDEX_INVALID'
        END as heat_status,
        CASE 
            WHEN solar_exposure_index BETWEEN 0 AND 100 THEN 'SOLAR_INDEX_VALID'
            ELSE 'SOLAR_INDEX_INVALID'
        END as solar_status,
        CASE 
            WHEN avg_wind_speed_ms >= 0 AND avg_wind_speed_ms <= 50 THEN 'WIND_VALID'
            ELSE 'WIND_INVALID'
        END as wind_status
    FROM serving.thermal_indices
    LEFT JOIN serving.solar_exposure se ON serving.thermal_indices.h3_id = se.geo_id
    LEFT JOIN serving.wind_profiles wp ON serving.thermal_indices.h3_id = wp.geo_id
),
integration_stats AS (
    SELECT 
        COUNT(*) as total_integrated_records,
        COUNT(CASE 
            WHEN heat_status = 'HEAT_INDEX_VALID' 
             AND solar_status = 'SOLAR_INDEX_VALID' 
             AND wind_status = 'WIND_VALID' 
            THEN 1 END) as fully_valid_records,
        AVG(heat_stress_index) as avg_integrated_heat_index,
        AVG(solar_exposure_index) as avg_integrated_solar_index,
        AVG(avg_wind_speed_ms) as avg_integrated_wind_speed,
        COUNT(CASE WHEN prevailing_wind_direction BETWEEN 0 AND 360 THEN 1 END) as valid_wind_directions
    FROM thermal_integration
)
SELECT 
    'Comprehensive Heat/Sun/Wind Integration' as test_name,
    CASE 
        WHEN total_integrated_records = 0 THEN 'FAIL: No integrated thermal data'
        WHEN fully_valid_records < total_integrated_records * 0.90 THEN 'FAIL: Thermal integration validation failed'
        ELSE 'PASS: Comprehensive thermal data integration successful'
    END as status,
    total_integrated_records,
    fully_valid_records,
    ROUND((fully_valid_records::FLOAT / NULLIF(total_integrated_records, 0)) * 100, 2) as integration_completeness_pct,
    ROUND(avg_integrated_heat_index, 2) as average_heat_stress_index,
    ROUND(avg_integrated_solar_index, 2) as average_solar_exposure_index,
    ROUND(avg_integrated_wind_speed, 2) as average_wind_speed_ms,
    valid_wind_directions
FROM integration_stats;