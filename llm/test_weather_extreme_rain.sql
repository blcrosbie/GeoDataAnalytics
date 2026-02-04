-- ==========================================
-- Weather & Extreme Rain Signal Tests
-- Tests for NOAA precipitation data, extreme rain events, and weather patterns
-- ==========================================

-- Test 1: Precipitation Data Quality Validation
-- Validates precipitation measurements have realistic values and proper temporal coverage
WITH precipitation_quality AS (
    SELECT 
        COUNT(*) as total_measurements,
        COUNT(CASE WHEN precipitation_mm >= 0 AND precipitation_mm <= 1000 THEN 1 END) as valid_measurements,
        COUNT(CASE WHEN precipitation_mm < 0 THEN 1 END) as negative_measurements,
        COUNT(CASE WHEN precipitation_mm > 1000 THEN 1 END) as extreme_measurements,
        COUNT(CASE WHEN measurement_date IS NOT NULL THEN 1 END) as measurements_with_date,
        COUNT(CASE WHEN station_id IS NOT NULL THEN 1 END) as measurements_with_station,
        AVG(precipitation_mm) as avg_precipitation,
        MAX(precipitation_mm) as max_precipitation,
        MIN(precipitation_mm) as min_precipitation,
        STDDEV(precipitation_mm) as stddev_precipitation
    FROM staging.precipitation_data
),
quality_assessment AS (
    SELECT 
        total_measurements,
        valid_measurements,
        negative_measurements,
        extreme_measurements,
        measurements_with_date,
        measurements_with_station,
        avg_precipitation,
        max_precipitation,
        min_precipitation,
        CASE 
            WHEN total_measurements = 0 THEN 'FAIL: No precipitation data found'
            WHEN valid_measurements < total_measurements * 0.95 THEN 'FAIL: Invalid precipitation values detected'
            WHEN negative_measurements > 0 THEN 'FAIL: Negative precipitation values'
            WHEN measurements_with_date < total_measurements * 0.99 THEN 'FAIL: Missing temporal data'
            ELSE 'PASS: Precipitation data quality acceptable'
        END as quality_status
    FROM precipitation_quality
)
SELECT 
    'Precipitation Data Quality' as test_name,
    quality_status as status,
    total_measurements,
    valid_measurements,
    negative_measurements,
    extreme_measurements,
    ROUND((valid_measurements::FLOAT / NULLIF(total_measurements, 0)) * 100, 2) as data_quality_pct,
    ROUND(avg_precipitation, 2) as avg_precipitation_mm,
    ROUND(max_precipitation, 2) as max_precipitation_mm,
    ROUND(min_precipitation, 2) as min_precipitation_mm
FROM quality_assessment;

-- Test 2: Extreme Rain Event Detection
-- Validates the identification of extreme precipitation events based on statistical thresholds
WITH extreme_rain_detection AS (
    SELECT 
        station_id,
        measurement_date,
        precipitation_mm,
        daily_normal_mm,
        CASE 
            WHEN precipitation_mm > daily_normal_mm * 5 THEN 'EXTREME_5X'
            WHEN precipitation_mm > daily_normal_mm * 3 THEN 'EXTREME_3X'
            WHEN precipitation_mm > daily_normal_mm * 2 THEN 'EXTREME_2X'
            WHEN precipitation_mm > daily_normal_mm * 1.5 THEN 'HEAVY_RAIN'
            ELSE 'NORMAL'
        END as event_classification,
        CASE 
            WHEN daily_normal_mm IS NULL OR daily_normal_mm = 0 THEN 'MISSING_BASELINE'
            WHEN precipitation_mm < 0 THEN 'INVALID_PRECIPITATION'
            ELSE 'VALID'
        END as detection_validity
    FROM staging.precipitation_data pd
    LEFT JOIN staging.precipitation_normals pn ON 
        pd.station_id = pn.station_id AND 
        EXTRACT(DOY FROM pd.measurement_date) = pn.day_of_year
),
extreme_event_stats AS (
    SELECT 
        COUNT(*) as total_events,
        COUNT(CASE WHEN event_classification LIKE 'EXTREME%' THEN 1 END) as extreme_events,
        COUNT(CASE WHEN event_classification = 'HEAVY_RAIN' THEN 1 END) as heavy_rain_events,
        COUNT(CASE WHEN event_classification = 'NORMAL' THEN 1 END) as normal_events,
        COUNT(CASE WHEN detection_validity = 'VALID' THEN 1 END) as valid_detections,
        COUNT(DISTINCT station_id) as stations_with_events,
        COUNT(DISTINCT measurement_date) as unique_dates
    FROM extreme_rain_detection
)
SELECT 
    'Extreme Rain Event Detection' as test_name,
    CASE 
        WHEN total_events = 0 THEN 'FAIL: No precipitation events for analysis'
        WHEN valid_detections < total_events * 0.95 THEN 'FAIL: Extreme event detection validation failed'
        ELSE 'PASS: Extreme rain event detection working'
    END as status,
    total_events,
    extreme_events,
    heavy_rain_events,
    normal_events,
    valid_detections,
    stations_with_events,
    unique_dates,
    ROUND((extreme_events::FLOAT / NULLIF(total_events, 0)) * 100, 2) as extreme_event_percentage
FROM extreme_event_stats;

-- Test 3: Precipitation Temporal Aggregation Validation
-- Tests monthly and yearly precipitation aggregations against daily data
WITH daily_aggregates AS (
    SELECT 
        station_id,
        DATE_TRUNC('month', measurement_date) as month,
        SUM(precipitation_mm) as daily_monthly_total,
        COUNT(*) as daily_days_count
    FROM staging.precipitation_data
    WHERE precipitation_mm >= 0
    GROUP BY station_id, DATE_TRUNC('month', measurement_date)
),
monthly_aggregates AS (
    SELECT 
        station_id,
        month,
        monthly_precipitation_mm,
        days_with_data
    FROM serving.monthly_precipitation
),
aggregation_validation AS (
    SELECT 
        da.station_id,
        da.month,
        da.daily_monthly_total,
        ma.monthly_precipitation_mm,
        da.daily_days_count,
        ma.days_with_data,
        ABS(da.daily_monthly_total - ma.monthly_precipitation_mm) as absolute_difference,
        CASE 
            WHEN ma.monthly_precipitation_mm IS NULL THEN 'MISSING_MONTHLY'
            WHEN ABS(da.daily_monthly_total - ma.monthly_precipitation_mm) > 0.1 THEN 'AGGREGATION_MISMATCH'
            WHEN da.daily_days_count != ma.days_with_data THEN 'DAY_COUNT_MISMATCH'
            ELSE 'VALID'
        END as aggregation_status
    FROM daily_aggregates da
    JOIN monthly_aggregates ma ON da.station_id = ma.station_id AND da.month = ma.month
),
validation_stats AS (
    SELECT 
        COUNT(*) as total_comparisons,
        COUNT(CASE WHEN aggregation_status = 'VALID' THEN 1 END) as valid_aggregations,
        COUNT(CASE WHEN aggregation_status = 'AGGREGATION_MISMATCH' THEN 1 END) as aggregation_mismatches,
        COUNT(CASE WHEN aggregation_status = 'DAY_COUNT_MISMATCH' THEN 1 END) as day_count_mismatches,
        AVG(absolute_difference) as avg_difference_mm,
        MAX(absolute_difference) as max_difference_mm
    FROM aggregation_validation
)
SELECT 
    'Precipitation Temporal Aggregation' as test_name,
    CASE 
        WHEN total_comparisons = 0 THEN 'FAIL: No aggregation data to validate'
        WHEN valid_aggregations < total_comparisons * 0.98 THEN 'FAIL: Precipitation aggregation validation failed'
        ELSE 'PASS: Precipitation temporal aggregation accurate'
    END as status,
    total_comparisons,
    valid_aggregations,
    aggregation_mismatches,
    day_count_mismatches,
    ROUND(avg_difference_mm, 3) as avg_difference_mm,
    ROUND(max_difference_mm, 3) as max_difference_mm,
    ROUND((valid_aggregations::FLOAT / NULLIF(total_comparisons, 0)) * 100, 2) as aggregation_accuracy_pct
FROM validation_stats;

-- Test 4: Rain Intensity Index Calculation
-- Validates rain intensity index computation based on frequency and intensity metrics
WITH rain_intensity_validation AS (
    SELECT 
        geo_id,
        month,
        rain_intensity_index,
        extreme_rain_days,
        heavy_rain_days,
        total_rain_days,
        avg_rain_intensity,
        max_daily_precipitation,
        CASE 
            WHEN rain_intensity_index < 0 OR rain_intensity_index > 100 THEN 'INDEX_OUT_OF_RANGE'
            WHEN rain_intensity_index IS NULL THEN 'NULL_INDEX'
            WHEN total_rain_days = 0 AND rain_intensity_index > 0 THEN 'INCONSISTENT_RAIN_DAYS'
            ELSE 'VALID'
        END as intensity_validity
    FROM serving.rain_intensity_index
),
intensity_stats AS (
    SELECT 
        COUNT(*) as total_records,
        COUNT(CASE WHEN intensity_validity = 'VALID' THEN 1 END) as valid_records,
        COUNT(CASE WHEN intensity_validity = 'INDEX_OUT_OF_RANGE' THEN 1 END) as out_of_range_records,
        COUNT(CASE WHEN intensity_validity = 'NULL_INDEX' THEN 1 END) as null_index_records,
        COUNT(CASE WHEN intensity_validity = 'INCONSISTENT_RAIN_DAYS' THEN 1 END) as inconsistent_records,
        AVG(rain_intensity_index) as avg_intensity_index,
        MAX(rain_intensity_index) as max_intensity_index,
        MIN(rain_intensity_index) as min_intensity_index,
        AVG(extreme_rain_days) as avg_extreme_days
    FROM rain_intensity_validation
)
SELECT 
    'Rain Intensity Index Calculation' as test_name,
    CASE 
        WHEN total_records = 0 THEN 'FAIL: No rain intensity index data found'
        WHEN valid_records < total_records * 0.95 THEN 'FAIL: Rain intensity index validation failed'
        WHEN max_intensity_index > 100 OR min_intensity_index < 0 THEN 'FAIL: Index range validation failed'
        ELSE 'PASS: Rain intensity index calculation valid'
    END as status,
    total_records,
    valid_records,
    out_of_range_records,
    null_index_records,
    inconsistent_records,
    ROUND(avg_intensity_index, 2) as average_intensity_index,
    max_intensity_index,
    min_intensity_index,
    ROUND(avg_extreme_days, 2) as average_extreme_rain_days
FROM intensity_stats;

-- Test 5: Storm Event Spatial Validation
-- Validates storm event polygons and point features have correct spatial properties
WITH storm_event_validation AS (
    SELECT 
        event_id,
        event_type,
        ST_GeometryType(geom) as geometry_type,
        CASE 
            WHEN NOT ST_IsValid(geom) THEN 'INVALID_GEOMETRY'
            WHEN ST_Area(geom) = 0 AND event_type = 'POLYGON' THEN 'ZERO_AREA_POLYGON'
            WHEN ST_SRID(geom) != 4326 THEN 'INVALID_CRS'
            WHEN event_type = 'POINT' AND ST_GeometryType(geom) != 'ST_Point' THEN 'MISMATCHED_POINT_TYPE'
            WHEN event_type = 'POLYGON' AND ST_GeometryType(geom) NOT IN ('ST_Polygon', 'ST_MultiPolygon') THEN 'MISMATCHED_POLYGON_TYPE'
            ELSE 'VALID'
        END as spatial_validity
    FROM serving.storm_events
    WHERE geom IS NOT NULL
),
spatial_stats AS (
    SELECT 
        COUNT(*) as total_events,
        COUNT(CASE WHEN spatial_validity = 'VALID' THEN 1 END) as valid_events,
        COUNT(DISTINCT event_type) as unique_event_types,
        COUNT(CASE WHEN geometry_type = 'ST_Point' THEN 1 END) as point_events,
        COUNT(CASE WHEN geometry_type IN ('ST_Polygon', 'ST_MultiPolygon') THEN 1 END) as polygon_events,
        COUNT(CASE WHEN spatial_validity = 'INVALID_GEOMETRY' THEN 1 END) as invalid_geometries
    FROM storm_event_validation
)
SELECT 
    'Storm Event Spatial Validation' as test_name,
    CASE 
        WHEN total_events = 0 THEN 'FAIL: No storm event data found'
        WHEN valid_events < total_events * 0.95 THEN 'FAIL: Storm event spatial validation failed'
        ELSE 'PASS: Storm event spatial data valid'
    END as status,
    total_events,
    valid_events,
    unique_event_types,
    point_events,
    polygon_events,
    invalid_geometries,
    ROUND((valid_events::FLOAT / NULLIF(total_events, 0)) * 100, 2) as spatial_validity_pct
FROM spatial_stats;

-- Test 6: Precipitation Climatology Comparison
-- Validates recent precipitation patterns against long-term normals
WITH climatology_comparison AS (
    SELECT 
        station_id,
        EXTRACT(MONTH FROM measurement_date) as month,
        AVG(precipitation_mm) as recent_avg_precipitation,
        normal.monthly_normal_mm,
        AVG(precipitation_mm) - normal.monthly_normal_mm as deviation_from_normal,
        CASE 
            WHEN normal.monthly_normal_mm IS NULL THEN 'MISSING_NORMAL'
            WHEN ABS(AVG(precipitation_mm) - normal.monthly_normal_mm) > normal.monthly_normal_mm * 2 THEN 'EXTREME_DEVIATION'
            ELSE 'VALID'
        END as comparison_status
    FROM staging.precipitation_data pd
    LEFT JOIN staging.precipitation_normals normal ON 
        pd.station_id = normal.station_id AND 
        EXTRACT(MONTH FROM pd.measurement_date) = normal.month
    WHERE measurement_date >= CURRENT_DATE - INTERVAL '3 years'
    AND precipitation_mm >= 0
    GROUP BY station_id, EXTRACT(MONTH FROM measurement_date), normal.monthly_normal_mm
),
climatology_stats AS (
    SELECT 
        COUNT(*) as total_comparisons,
        COUNT(CASE WHEN comparison_status = 'VALID' THEN 1 END) as valid_comparisons,
        COUNT(CASE WHEN comparison_status = 'EXTREME_DEVIATION' THEN 1 END) as extreme_deviations,
        AVG(deviation_from_normal) as avg_deviation_mm,
        STDDEV(deviation_from_normal) as stddev_deviation_mm,
        MAX(deviation_from_normal) as max_positive_deviation,
        MIN(deviation_from_normal) as max_negative_deviation
    FROM climatology_comparison
)
SELECT 
    'Precipitation Climatology Comparison' as test_name,
    CASE 
        WHEN total_comparisons = 0 THEN 'FAIL: No climatology data to compare'
        WHEN valid_comparisons < total_comparisons * 0.90 THEN 'FAIL: Climatology comparison validation failed'
        ELSE 'PASS: Precipitation climatology comparison valid'
    END as status,
    total_comparisons,
    valid_comparisons,
    extreme_deviations,
    ROUND(avg_deviation_mm, 2) as average_deviation_mm,
    ROUND(stddev_deviation_mm, 2) as stddev_deviation_mm,
    ROUND(max_positive_deviation, 2) as max_positive_deviation,
    ROUND(max_negative_deviation, 2) as max_negative_deviation
FROM climatology_stats;

-- Test 7: Performance Test: Precipitation Query Performance
-- Tests performance of temporal and spatial precipitation queries
EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
SELECT 
    DATE_TRUNC('month', measurement_date) as month,
    AVG(precipitation_mm) as avg_monthly_precip,
    COUNT(*) as measurement_count
FROM staging.precipitation_data
WHERE measurement_date >= CURRENT_DATE - INTERVAL '1 year'
AND ST_Within(
    ST_MakePoint(longitude, latitude, 4326),
    ST_MakeEnvelope(-125.0, 32.0, -114.0, 42.0, 4326)
)
GROUP BY DATE_TRUNC('month', measurement_date)
ORDER BY month;

-- Test 8: Comprehensive Weather Data Integration
-- Tests end-to-end integration of precipitation, storm events, and intensity indices
WITH weather_integration AS (
    SELECT 
        h3_id,
        rain_intensity_index,
        monthly_precipitation_mm,
        storm_event_count,
        extreme_rain_frequency,
        CASE 
            WHEN rain_intensity_index BETWEEN 0 AND 100 THEN 'INDEX_VALID'
            ELSE 'INDEX_INVALID'
        END as index_status,
        CASE 
            WHEN monthly_precipitation_mm >= 0 THEN 'PRECIPITATION_VALID'
            ELSE 'PRECIPITATION_INVALID'
        END as precipitation_status,
        CASE 
            WHEN storm_event_count >= 0 THEN 'STORM_COUNT_VALID'
            ELSE 'STORM_COUNT_INVALID'
        END as storm_status
    FROM serving.rain_intensity_index rii
    LEFT JOIN serving.monthly_precipitation mp ON rii.geo_id = mp.geo_id
    LEFT JOIN (
        SELECT geo_id, COUNT(*) as storm_event_count
        FROM serving.storm_events se
        JOIN serving.h3_index h3 ON ST_Contains(h3.geom, se.geom)
        WHERE se.event_date >= CURRENT_DATE - INTERVAL '1 year'
        GROUP BY geo_id
    ) storms ON rii.geo_id = storms.geo_id
),
integration_stats AS (
    SELECT 
        COUNT(*) as total_integrated_records,
        COUNT(CASE 
            WHEN index_status = 'INDEX_VALID' 
             AND precipitation_status = 'PRECIPITATION_VALID' 
             AND storm_status = 'STORM_COUNT_VALID' 
            THEN 1 END) as fully_valid_records,
        AVG(rain_intensity_index) as avg_integrated_intensity,
        AVG(monthly_precipitation_mm) as avg_integrated_precipitation,
        AVG(storm_event_count) as avg_storm_events
    FROM weather_integration
)
SELECT 
    'Comprehensive Weather Data Integration' as test_name,
    CASE 
        WHEN total_integrated_records = 0 THEN 'FAIL: No integrated weather data'
        WHEN fully_valid_records < total_integrated_records * 0.90 THEN 'FAIL: Weather integration validation failed'
        ELSE 'PASS: Comprehensive weather data integration successful'
    END as status,
    total_integrated_records,
    fully_valid_records,
    ROUND((fully_valid_records::FLOAT / NULLIF(total_integrated_records, 0)) * 100, 2) as integration_completeness_pct,
    ROUND(avg_integrated_intensity, 2) as average_intensity_index,
    ROUND(avg_integrated_precipitation, 2) as average_monthly_precipitation,
    ROUND(avg_storm_events, 2) as average_storm_events_per_location
FROM integration_stats;