-- ==========================================
-- Air Quality & GHG Signal Tests
-- Tests for Sentinel-5P satellite data, AQI calculations, and pollutant processing
-- ==========================================

-- Test 1: Sentinel-5P Data Quality Validation
-- Validates satellite-derived pollutant measurements have realistic values
WITH sentinel5p_quality AS (
    SELECT 
        COUNT(*) as total_measurements,
        COUNT(CASE WHEN no2_mol_m2 IS NOT NULL AND no2_mol_m2 >= 0 THEN 1 END) as valid_no2_measurements,
        COUNT(CASE WHEN so2_mol_m2 IS NOT NULL AND so2_mol_m2 >= 0 THEN 1 END) as valid_so2_measurements,
        COUNT(CASE WHEN co_mol_m2 IS NOT NULL AND co_mol_m2 >= 0 THEN 1 END) as valid_co_measurements,
        COUNT(CASE WHEN o3_mol_m2 IS NOT NULL AND o3_mol_m2 >= 0 THEN 1 END) as valid_o3_measurements,
        COUNT(CASE WHEN ch4_mol_m2 IS NOT NULL AND ch4_mol_m2 >= 0 THEN 1 END) as valid_ch4_measurements,
        COUNT(CASE WHEN measurement_date IS NOT NULL THEN 1 END) as measurements_with_date,
        AVG(no2_mol_m2) as avg_no2,
        MAX(no2_mol_m2) as max_no2,
        AVG(co_mol_m2) as avg_co,
        MAX(co_mol_m2) as max_co
    FROM staging.sentinel5p_data
),
quality_assessment AS (
    SELECT 
        total_measurements,
        valid_no2_measurements,
        valid_so2_measurements,
        valid_co_measurements,
        valid_o3_measurements,
        valid_ch4_measurements,
        measurements_with_date,
        CASE 
            WHEN total_measurements = 0 THEN 'FAIL: No Sentinel-5P data found'
            WHEN valid_no2_measurements < total_measurements * 0.50 THEN 'FAIL: Insufficient NO2 data'
            WHEN measurements_with_date < total_measurements * 0.95 THEN 'FAIL: Missing temporal data'
            ELSE 'PASS: Sentinel-5P data quality acceptable'
        END as quality_status
    FROM sentinel5p_quality
)
SELECT 
    'Sentinel-5P Data Quality' as test_name,
    quality_status as status,
    total_measurements,
    valid_no2_measurements,
    valid_so2_measurements,
    valid_co_measurements,
    valid_o3_measurements,
    valid_ch4_measurements,
    measurements_with_date,
    ROUND((valid_no2_measurements::FLOAT / NULLIF(total_measurements, 0)) * 100, 2) as no2_data_completeness_pct,
    ROUND(avg_no2, 6) as avg_no2_mol_m2,
    ROUND(max_no2, 6) as max_no2_mol_m2
FROM quality_assessment;

-- Test 2: Air Quality Index Calculation
-- Validates multi-pollutant AQI calculation against EPA standards
WITH aqi_validation AS (
    SELECT 
        geo_id,
        measurement_date,
        aqi_value,
        aqi_category,  -- Good, Moderate, Unhealthy for Sensitive, Unhealthy, Very Unhealthy, Hazardous
        no2_concentration_ug_m3,
        pm25_concentration_ug_m3,
        o3_concentration_ug_m3,
        CASE 
            WHEN aqi_value < 0 OR aqi_value > 500 THEN 'AQI_OUT_OF_RANGE'
            WHEN aqi_category NOT IN ('Good', 'Moderate', 'Unhealthy for Sensitive', 'Unhealthy', 'Very Unhealthy', 'Hazardous') THEN 'INVALID_AQI_CATEGORY'
            WHEN aqi_value <= 50 AND aqi_category != 'Good' THEN 'AQI_CATEGORY_MISMATCH'
            WHEN aqi_value > 50 AND aqi_value <= 100 AND aqi_category != 'Moderate' THEN 'AQI_CATEGORY_MISMATCH'
            WHEN aqi_value > 100 AND aqi_value <= 150 AND aqi_category != 'Unhealthy for Sensitive' THEN 'AQI_CATEGORY_MISMATCH'
            WHEN aqi_value > 150 AND aqi_value <= 200 AND aqi_category != 'Unhealthy' THEN 'AQI_CATEGORY_MISMATCH'
            WHEN aqi_value > 200 AND aqi_value <= 300 AND aqi_category != 'Very Unhealthy' THEN 'AQI_CATEGORY_MISMATCH'
            WHEN aqi_value > 300 AND aqi_category != 'Hazardous' THEN 'AQI_CATEGORY_MISMATCH'
            ELSE 'VALID'
        END as aqi_validity
    FROM serving.air_quality_index
),
aqi_stats AS (
    SELECT 
        COUNT(*) as total_aqi_records,
        COUNT(CASE WHEN aqi_validity = 'VALID' THEN 1 END) as valid_aqi_records,
        COUNT(CASE WHEN aqi_validity = 'AQI_OUT_OF_RANGE' THEN 1 END) as out_of_range_records,
        COUNT(CASE WHEN aqi_validity = 'AQI_CATEGORY_MISMATCH' THEN 1 END) as category_mismatches,
        AVG(aqi_value) as avg_aqi,
        MAX(aqi_value) as max_aqi,
        MIN(aqi_value) as min_aqi,
        COUNT(DISTINCT aqi_category) as unique_aqi_categories
    FROM aqi_validation
)
SELECT 
    'Air Quality Index Calculation' as test_name,
    CASE 
        WHEN total_aqi_records = 0 THEN 'FAIL: No AQI data found'
        WHEN valid_aqi_records < total_aqi_records * 0.95 THEN 'FAIL: AQI calculation validation failed'
        WHEN unique_aqi_categories != 6 THEN 'FAIL: Incomplete AQI categories'
        ELSE 'PASS: AQI calculation valid'
    END as status,
    total_aqi_records,
    valid_aqi_records,
    out_of_range_records,
    category_mismatches,
    unique_aqi_categories,
    ROUND(avg_aqi, 1) as average_aqi_value,
    max_aqi,
    min_aqi,
    ROUND((valid_aqi_records::FLOAT / NULLIF(total_aqi_records, 0)) * 100, 2) as aqi_calculation_accuracy_pct
FROM aqi_stats;

-- Test 3: Pollutant Concentration Validation
-- Validates individual pollutant concentration calculations and units
WITH pollutant_validation AS (
    SELECT 
        geo_id,
        measurement_date,
        no2_ug_m3,
        so2_ug_m3,
        co_mg_m3,
        o3_ug_m3,
        pm25_ug_m3,
        pm10_ug_m3,
        CASE 
            WHEN no2_ug_m3 < 0 OR no2_ug_m3 > 500 THEN 'NO2_OUT_OF_RANGE'
            WHEN so2_ug_m3 < 0 OR so2_ug_m3 > 1000 THEN 'SO2_OUT_OF_RANGE'
            WHEN co_mg_m3 < 0 OR co_mg_m3 > 50 THEN 'CO_OUT_OF_RANGE'
            WHEN o3_ug_m3 < 0 OR o3_ug_m3 > 300 THEN 'O3_OUT_OF_RANGE'
            WHEN pm25_ug_m3 < 0 OR pm25_ug_m3 > 500 THEN 'PM25_OUT_OF_RANGE'
            WHEN pm10_ug_m3 < 0 OR pm10_ug_m3 > 600 THEN 'PM10_OUT_OF_RANGE'
            ELSE 'VALID'
        END as concentration_validity
    FROM serving.pollutant_concentrations
),
concentration_stats AS (
    SELECT 
        COUNT(*) as total_concentration_records,
        COUNT(CASE WHEN concentration_validity = 'VALID' THEN 1 END) as valid_records,
        COUNT(CASE WHEN concentration_validity LIKE '%OUT_OF_RANGE' THEN 1 END) as out_of_range_records,
        AVG(no2_ug_m3) as avg_no2,
        AVG(so2_ug_m3) as avg_so2,
        AVG(co_mg_m3) as avg_co,
        AVG(o3_ug_m3) as avg_o3,
        AVG(pm25_ug_m3) as avg_pm25,
        AVG(pm10_ug_m3) as avg_pm10,
        MAX(pm25_ug_m3) as max_pm25
    FROM pollutant_validation
)
SELECT 
    'Pollutant Concentration Validation' as test_name,
    CASE 
        WHEN total_concentration_records = 0 THEN 'FAIL: No pollutant concentration data found'
        WHEN valid_records < total_concentration_records * 0.95 THEN 'FAIL: Pollutant concentration validation failed'
        ELSE 'PASS: Pollutant concentrations valid'
    END as status,
    total_concentration_records,
    valid_records,
    out_of_range_records,
    ROUND(avg_no2, 2) as average_no2_ug_m3,
    ROUND(avg_so2, 2) as average_so2_ug_m3,
    ROUND(avg_co, 3) as average_co_mg_m3,
    ROUND(avg_o3, 2) as average_o3_ug_m3,
    ROUND(avg_pm25, 2) as average_pm25_ug_m3,
    ROUND(avg_pm10, 2) as average_pm10_ug_m3,
    max_pm25 as max_pm25_ug_m3
FROM concentration_stats;

-- Test 4: Ground Station vs Satellite Data Comparison
-- Validates consistency between ground-based stations and satellite measurements
WITH ground_satellite_comparison AS (
    SELECT 
        gs.geo_id,
        gs.measurement_date,
        gs.no2_ug_m3 as ground_no2,
        s5p.no2_ug_m3 as satellite_no2,
        ABS(gs.no2_ug_m3 - s5p.no2_ug_m3) as absolute_difference,
        CASE 
            WHEN s5p.no2_ug_m3 IS NULL THEN 'MISSING_SATELLITE_DATA'
            WHEN gs.no2_ug_m3 IS NULL THEN 'MISSING_GROUND_DATA'
            WHEN ABS(gs.no2_ug_m3 - s5p.no2_ug_m5) > 50 THEN 'LARGE_DISCREPANCY'
            ELSE 'VALID'
        END as comparison_status
    FROM serving.ground_stations gs
    LEFT JOIN staging.sentinel5p_aggregated s5p ON 
        gs.geo_id = s5p.geo_id AND 
        DATE_TRUNC('day', gs.measurement_date) = DATE_TRUNC('day', s5p.measurement_date)
    WHERE gs.no2_ug_m3 IS NOT NULL
),
comparison_stats AS (
    SELECT 
        COUNT(*) as total_comparisons,
        COUNT(CASE WHEN comparison_status = 'VALID' THEN 1 END) as valid_comparisons,
        COUNT(CASE WHEN comparison_status = 'MISSING_SATELLITE_DATA' THEN 1 END) as missing_satellite,
        COUNT(CASE WHEN comparison_status = 'MISSING_GROUND_DATA' THEN 1 END) as missing_ground,
        COUNT(CASE WHEN comparison_status = 'LARGE_DISCREPANCY' THEN 1 END) as large_discrepancies,
        AVG(ground_no2) as avg_ground_no2,
        AVG(satellite_no2) as avg_satellite_no2,
        AVG(absolute_difference) as avg_difference
    FROM ground_satellite_comparison
)
SELECT 
    'Ground Station vs Satellite Comparison' as test_name,
    CASE 
        WHEN total_comparisons = 0 THEN 'FAIL: No ground-satellite comparison data'
        WHEN valid_comparisons < total_comparisons * 0.70 THEN 'FAIL: Ground-satellite comparison validation failed'
        WHEN large_discrepancies > total_comparisons * 0.20 THEN 'FAIL: Too large ground-satellite discrepancies'
        ELSE 'PASS: Ground-satellite comparison acceptable'
    END as status,
    total_comparisons,
    valid_comparisons,
    missing_satellite,
    missing_ground,
    large_discrepancies,
    ROUND(avg_ground_no2, 2) as average_ground_no2_ug_m3,
    ROUND(avg_satellite_no2, 2) as average_satellite_no2_ug_m3,
    ROUND(avg_difference, 2) as average_difference_ug_m3,
    ROUND((valid_comparisons::FLOAT / NULLIF(total_comparisons, 0)) * 100, 2) as comparison_accuracy_pct
FROM comparison_stats;

-- Test 5: Air Quality Trend Analysis
-- Validates air quality trend calculations and change detection
WITH aqi_trend_validation AS (
    SELECT 
        geo_id,
        trend_period,  -- 1_year, 3_year, 5_year
        aqi_trend_direction,  -- improving, worsening, stable
        aqi_change_percent,
        statistical_significance,  -- significant, not_significant
        sample_size,
        CASE 
            WHEN trend_period NOT IN ('1_year', '3_year', '5_year') THEN 'INVALID_PERIOD'
            WHEN aqi_trend_direction NOT IN ('improving', 'worsening', 'stable') THEN 'INVALID_DIRECTION'
            WHEN aqi_change_percent < -100 OR aqi_change_percent > 100 THEN 'INVALID_PERCENTAGE'
            WHEN statistical_significance NOT IN ('significant', 'not_significant') THEN 'INVALID_SIGNIFICANCE'
            WHEN sample_size < 30 THEN 'INSUFFICIENT_SAMPLE_SIZE'
            ELSE 'VALID'
        END as trend_validity
    FROM serving.aqi_trends
),
trend_stats AS (
    SELECT 
        COUNT(*) as total_trend_records,
        COUNT(CASE WHEN trend_validity = 'VALID' THEN 1 END) as valid_trends,
        COUNT(CASE WHEN trend_validity LIKE 'INVALID%' THEN 1 END) as invalid_trends,
        COUNT(DISTINCT trend_period) as unique_periods,
        COUNT(CASE WHEN aqi_trend_direction = 'improving' THEN 1 END) as improving_trends,
        COUNT(CASE WHEN aqi_trend_direction = 'worsening' THEN 1 END) as worsening_trends,
        COUNT(CASE WHEN aqi_trend_direction = 'stable' THEN 1 END) as stable_trends,
        AVG(ABS(aqi_change_percent)) as avg_absolute_change_percent
    FROM aqi_trend_validation
)
SELECT 
    'Air Quality Trend Analysis' as test_name,
    CASE 
        WHEN total_trend_records = 0 THEN 'FAIL: No AQI trend data found'
        WHEN valid_trends < total_trend_records * 0.95 THEN 'FAIL: AQI trend validation failed'
        WHEN unique_periods != 3 THEN 'FAIL: Incomplete trend period coverage'
        ELSE 'PASS: AQI trend analysis valid'
    END as status,
    total_trend_records,
    valid_trends,
    invalid_trends,
    unique_periods,
    improving_trends,
    worsening_trends,
    stable_trends,
    ROUND(avg_absolute_change_percent, 2) as average_absolute_change_percent
FROM trend_stats;

-- Test 6: PM2.5 Spatial Interpolation Validation
-- Validates PM2.5 spatial interpolation and surface generation
WITH pm25_interpolation_validation AS (
    SELECT 
        geo_id,
        pm25_value,
        interpolation_method,
        confidence_score,
        distance_to_nearest_station_km,
        CASE 
            WHEN pm25_value < 0 OR pm25_value > 500 THEN 'PM25_OUT_OF_RANGE'
            WHEN interpolation_method NOT IN ('kriging', 'idw', 'splines') THEN 'INVALID_METHOD'
            WHEN confidence_score < 0 OR confidence_score > 1 THEN 'INVALID_CONFIDENCE'
            WHEN distance_to_nearest_station_km > 100 THEN 'TOO_FAR_FROM_STATION'
            ELSE 'VALID'
        END as interpolation_validity
    FROM serving.pm25_surface
),
interpolation_stats AS (
    SELECT 
        COUNT(*) as total_interpolated_points,
        COUNT(CASE WHEN interpolation_validity = 'VALID' THEN 1 END) as valid_interpolations,
        COUNT(CASE WHEN interpolation_validity = 'PM25_OUT_OF_RANGE' THEN 1 END) as out_of_range_points,
        COUNT(DISTINCT interpolation_method) as unique_methods,
        AVG(pm25_value) as avg_pm25,
        MAX(pm25_value) as max_pm25,
        MIN(pm25_value) as min_pm25,
        AVG(confidence_score) as avg_confidence,
        AVG(distance_to_nearest_station_km) as avg_distance_to_station
    FROM pm25_interpolation_validation
)
SELECT 
    'PM2.5 Spatial Interpolation Validation' as test_name,
    CASE 
        WHEN total_interpolated_points = 0 THEN 'FAIL: No PM2.5 interpolated data found'
        WHEN valid_interpolations < total_interpolated_points * 0.90 THEN 'FAIL: PM2.5 interpolation validation failed'
        ELSE 'PASS: PM2.5 spatial interpolation valid'
    END as status,
    total_interpolated_points,
    valid_interpolations,
    out_of_range_points,
    unique_methods,
    ROUND(avg_pm25, 2) as average_pm25_ug_m3,
    max_pm25,
    min_pm25,
    ROUND(avg_confidence, 3) as average_confidence_score,
    ROUND(avg_distance_to_station, 2) as average_distance_to_station_km
FROM interpolation_stats;

-- Test 7: Methane Emission Hotspot Detection
-- Validates CH4 hotspot detection algorithms and thresholds
WITH ch4_hotspot_validation AS (
    SELECT 
        hotspot_id,
        ch4_concentration_ppb,
        background_concentration_ppb,
        concentration_anomaly_ppb,
        hotspot_confidence,
        CASE 
            WHEN ch4_concentration_ppb < 1800 OR ch4_concentration_ppb > 3000 THEN 'CH4_OUT_OF_RANGE'
            WHEN background_concentration_ppb < 1800 OR background_concentration_ppb > 2000 THEN 'BACKGROUND_OUT_OF_RANGE'
            WHEN concentration_anomaly_ppb < 0 THEN 'NEGATIVE_ANOMALY'
            WHEN hotspot_confidence < 0 OR hotspot_confidence > 1 THEN 'INVALID_CONFIDENCE'
            WHEN concentration_anomaly_ppb < 50 THEN 'LOW_ANOMALY_THRESHOLD'
            ELSE 'VALID'
        END as hotspot_validity
    FROM serving.ch4_hotspots
),
hotspot_stats AS (
    SELECT 
        COUNT(*) as total_hotspots,
        COUNT(CASE WHEN hotspot_validity = 'VALID' THEN 1 END) as valid_hotspots,
        COUNT(CASE WHEN hotspot_validity = 'CH4_OUT_OF_RANGE' THEN 1 END) as out_of_range_hotspots,
        COUNT(CASE WHEN hotspot_validity = 'LOW_ANOMALY_THRESHOLD' THEN 1 END) as low_anomaly_hotspots,
        AVG(ch4_concentration_ppb) as avg_ch4_concentration,
        MAX(ch4_concentration_ppb) as max_ch4_concentration,
        AVG(concentration_anomaly_ppb) as avg_anomaly_ppb,
        MAX(concentration_anomaly_ppb) as max_anomaly_ppb,
        AVG(hotspot_confidence) as avg_confidence
    FROM ch4_hotspot_validation
)
SELECT 
    'Methane Emission Hotspot Detection' as test_name,
    CASE 
        WHEN total_hotspots = 0 THEN 'FAIL: No CH4 hotspot data found'
        WHEN valid_hotspots < total_hotspots * 0.80 THEN 'FAIL: CH4 hotspot validation failed'
        ELSE 'PASS: CH4 hotspot detection valid'
    END as status,
    total_hotspots,
    valid_hotspots,
    out_of_range_hotspots,
    low_anomaly_hotspots,
    ROUND(avg_ch4_concentration, 1) as average_ch4_ppb,
    ROUND(max_ch4_concentration, 1) as max_ch4_ppb,
    ROUND(avg_anomaly_ppb, 1) as average_anomaly_ppb,
    ROUND(max_anomaly_ppb, 1) as max_anomaly_ppb,
    ROUND(avg_confidence, 3) as average_hotspot_confidence
FROM hotspot_stats;

-- Test 8: Performance Test: Air Quality Spatial Query
-- Tests performance of air quality spatial queries with different pollutants
EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
SELECT 
    COUNT(*) as high_pollution_locations,
    AVG(aqi_value) as avg_aqi,
    AVG(no2_ug_m3) as avg_no2,
    AVG(pm25_ug_m3) as avg_pm25
FROM serving.air_quality_index aqi
JOIN serving.pollutant_concentrations pc ON aqi.geo_id = pc.geo_id AND aqi.measurement_date = pc.measurement_date
JOIN serving.h3_index h3 ON aqi.geo_id = h3.h3_id
WHERE aqi.measurement_date >= CURRENT_DATE - INTERVAL '7 days'
AND aqi.aqi_value > 100  -- Unhealthy for Sensitive Groups threshold
AND ST_Intersects(
    h3.geom,
    ST_MakeEnvelope(-125.0, 32.0, -114.0, 42.0, 4326)
);

-- Test 9: Comprehensive Air Quality Integration
-- Tests end-to-end integration of satellite, ground station, and AQI data
WITH air_quality_integration AS (
    SELECT 
        h3_id,
        aqi_value,
        aqi_category,
        no2_ug_m3,
        pm25_ug_m3,
        o3_ug_m3,
        satellite_data_quality,
        ground_station_distance_km,
        CASE 
            WHEN aqi_value BETWEEN 0 AND 500 THEN 'AQI_VALID'
            ELSE 'AQI_INVALID'
        END as aqi_status,
        CASE 
            WHEN no2_ug_m3 >= 0 AND no2_ug_m3 <= 500 THEN 'NO2_VALID'
            ELSE 'NO2_INVALID'
        END as no2_status,
        CASE 
            WHEN pm25_ug_m3 >= 0 AND pm25_ug_m3 <= 500 THEN 'PM25_VALID'
            ELSE 'PM25_INVALID'
        END as pm25_status,
        CASE 
            WHEN ground_station_distance_km <= 50 THEN 'STATION_PROXIMATE'
            ELSE 'STATION_DISTANT'
        END as station_proximity
    FROM serving.air_quality_index aqi
    LEFT JOIN serving.pollutant_concentrations pc ON aqi.geo_id = pc.geo_id AND aqi.measurement_date = pc.measurement_date
    LEFT JOIN (
        SELECT geo_id, AVG(quality_score) as satellite_data_quality
        FROM staging.sentinel5p_quality_metrics
        WHERE measurement_date >= CURRENT_DATE - INTERVAL '7 days'
        GROUP BY geo_id
    ) s5p_quality ON aqi.geo_id = s5p_quality.geo_id
    LEFT JOIN (
        SELECT geo_id, AVG(ST_Distance(station_geom::geography, centroid_geom::geography)/1000.0) as ground_station_distance_km
        FROM serving.station_proximity
        GROUP BY geo_id
    ) station_dist ON aqi.geo_id = station_dist.geo_id
    WHERE aqi.measurement_date >= CURRENT_DATE - INTERVAL '7 days'
),
integration_stats AS (
    SELECT 
        COUNT(*) as total_integrated_records,
        COUNT(CASE 
            WHEN aqi_status = 'AQI_VALID' 
             AND no2_status = 'NO2_VALID' 
             AND pm25_status = 'PM25_VALID' 
            THEN 1 END) as fully_valid_records,
        AVG(aqi_value) as avg_integrated_aqi,
        AVG(no2_ug_m3) as avg_integrated_no2,
        AVG(pm25_ug_m3) as avg_integrated_pm25,
        COUNT(CASE WHEN station_proximity = 'STATION_PROXIMATE' THEN 1 END) as station_proximate_records,
        AVG(satellite_data_quality) as avg_satellite_quality
    FROM air_quality_integration
)
SELECT 
    'Comprehensive Air Quality Integration' as test_name,
    CASE 
        WHEN total_integrated_records = 0 THEN 'FAIL: No integrated air quality data'
        WHEN fully_valid_records < total_integrated_records * 0.85 THEN 'FAIL: Air quality integration validation failed'
        ELSE 'PASS: Comprehensive air quality integration successful'
    END as status,
    total_integrated_records,
    fully_valid_records,
    ROUND((fully_valid_records::FLOAT / NULLIF(total_integrated_records, 0)) * 100, 2) as integration_completeness_pct,
    ROUND(avg_integrated_aqi, 1) as average_integrated_aqi,
    ROUND(avg_integrated_no2, 2) as average_integrated_no2_ug_m3,
    ROUND(avg_integrated_pm25, 2) as average_integrated_pm25_ug_m3,
    station_proximate_records,
    ROUND(avg_satellite_quality, 3) as average_satellite_quality
FROM integration_stats;