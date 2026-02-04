-- ==========================================
-- Flood Exposure Layer Tests
-- Tests for FEMA NFHL flood zones, water proximity, and flood risk scoring
-- ==========================================

-- Test 1: Flood Zone Data Validation
-- Validates flood zone polygons have correct attributes and valid geometries
WITH flood_zone_validation AS (
    SELECT 
        COUNT(*) as total_zones,
        COUNT(CASE WHEN ST_IsValid(geom) THEN 1 END) as valid_geometries,
        COUNT(CASE WHEN flood_zone IS NOT NULL THEN 1 END) as zones_with_classification,
        COUNT(CASE WHEN ST_Area(geom) > 0 THEN 1 END) as zones_with_area,
        COUNT(CASE WHEN ST_SRID(geom) = 4326 THEN 1 END) as zones_with_correct_crs,
        SUM(ST_Area(geom::geography)) as total_area_sqm
    FROM serving.flood_zone
),
validation_results AS (
    SELECT 
        total_zones,
        valid_geometries,
        zones_with_classification,
        zones_with_area,
        zones_with_correct_crs,
        total_area_sqm,
        CASE 
            WHEN total_zones = 0 THEN 'FAIL: No flood zone data found'
            WHEN valid_geometries < total_zones * 0.95 THEN 'FAIL: Invalid geometries detected'
            WHEN zones_with_classification < total_zones * 0.90 THEN 'FAIL: Missing flood zone classifications'
            WHEN zones_with_correct_crs < total_zones * 0.95 THEN 'FAIL: Incorrect coordinate system'
            ELSE 'PASS: Flood zone data validation successful'
        END as validation_status
    FROM flood_zone_validation
)
SELECT 
    'Flood Zone Validation' as test_name,
    validation_status as status,
    ROUND((valid_geometries::FLOAT / NULLIF(total_zones, 0)) * 100, 2) as geometry_validity_pct,
    ROUND((zones_with_classification::FLOAT / NULLIF(total_zones, 0)) * 100, 2) as classification_completeness_pct,
    ROUND((zones_with_correct_crs::FLOAT / NULLIF(total_zones, 0)) * 100, 2) as crs_compliance_pct,
    total_zones,
    ROUND(total_area_sqm / 1000000.0, 2) as total_area_sqkm
FROM validation_results;

-- Test 2: Water Proximity Distance Calculation
-- Validates distance calculations from flood zones to water features
WITH water_distance_calculation AS (
    SELECT 
        fz.id as zone_id,
        fz.flood_zone,
        ST_Distance(
            fz.geom::geography,
            ST_ClosestPoint(
                (SELECT ST_Collect(w.geom) FROM serving.water_bodies w WHERE ST_IsValid(w.geom)),
                fz.geom
            )::geography
        ) as distance_to_water_m
    FROM serving.flood_zone fz
    WHERE ST_IsValid(fz.geom)
    LIMIT 1000
),
distance_stats AS (
    SELECT 
        COUNT(*) as total_zones_tested,
        COUNT(CASE WHEN distance_to_water_m < 1000 THEN 1 END) as zones_near_water_1km,
        COUNT(CASE WHEN distance_to_water_m < 5000 THEN 1 END) as zones_near_water_5km,
        AVG(distance_to_water_m) as avg_distance_m,
        MAX(distance_to_water_m) as max_distance_m,
        MIN(distance_to_water_m) as min_distance_m,
        STDDEV(distance_to_water_m) as stddev_distance_m
    FROM water_distance_calculation
)
SELECT 
    'Water Proximity Calculation' as test_name,
    CASE 
        WHEN total_zones_tested = 0 THEN 'FAIL: No valid zones for distance calculation'
        WHEN avg_distance_m IS NULL THEN 'FAIL: Distance calculation failed'
        ELSE 'PASS: Water proximity calculations completed'
    END as status,
    total_zones_tested,
    zones_near_water_1km,
    zones_near_water_5km,
    ROUND(avg_distance_m, 2) as avg_distance_meters,
    ROUND(min_distance_m, 2) as min_distance_meters,
    ROUND(max_distance_m, 2) as max_distance_meters,
    ROUND(stddev_distance_m, 2) as stddev_distance_meters
FROM distance_stats;

-- Test 3: Flood Risk Score Computation
-- Validates normalized flood risk scores (0-100) are properly calculated
WITH flood_risk_validation AS (
    SELECT 
        geo_id,
        flood_risk_score,
        flood_zone_count,
        water_proximity_factor,
        elevation_factor,
        CASE 
            WHEN flood_risk_score < 0 OR flood_risk_score > 100 THEN 'OUT_OF_RANGE'
            WHEN flood_risk_score IS NULL THEN 'NULL_VALUE'
            ELSE 'VALID'
        END as score_validity
    FROM serving.flood_risk_scores
    WHERE geo_id IS NOT NULL
),
risk_score_stats AS (
    SELECT 
        COUNT(*) as total_scores,
        COUNT(CASE WHEN score_validity = 'VALID' THEN 1 END) as valid_scores,
        COUNT(CASE WHEN score_validity = 'OUT_OF_RANGE' THEN 1 END) as out_of_range_scores,
        COUNT(CASE WHEN score_validity = 'NULL_VALUE' THEN 1 END) as null_scores,
        AVG(flood_risk_score) as avg_score,
        MAX(flood_risk_score) as max_score,
        MIN(flood_risk_score) as min_score,
        STDDEV(flood_risk_score) as stddev_score
    FROM flood_risk_validation
)
SELECT 
    'Flood Risk Score Computation' as test_name,
    CASE 
        WHEN total_scores = 0 THEN 'FAIL: No flood risk scores found'
        WHEN valid_scores < total_scores * 0.95 THEN 'FAIL: Invalid flood risk scores detected'
        WHEN max_score > 100 OR min_score < 0 THEN 'FAIL: Score range validation failed'
        ELSE 'PASS: Flood risk score computation valid'
    END as status,
    total_scores,
    valid_scores,
    out_of_range_scores,
    null_scores,
    ROUND(avg_score, 2) as average_risk_score,
    max_score,
    min_score,
    ROUND(stddev_score, 2) as score_std_deviation
FROM risk_score_stats;

-- Test 4: Elevation Derivative Integration
-- Validates that elevation derivatives (slope, flow accumulation) are properly integrated
WITH elevation_validation AS (
    SELECT 
        geo_id,
        elevation_m,
        slope_degrees,
        flow_accumulation,
        CASE 
            WHEN elevation_m < -500 OR elevation_m > 9000 THEN 'ELEVATION_OUT_OF_RANGE'
            WHEN slope_degrees < 0 OR slope_degrees > 90 THEN 'SLOPE_OUT_OF_RANGE'
            WHEN flow_accumulation < 0 THEN 'FLOW_NEGATIVE'
            WHEN elevation_m IS NULL OR slope_degrees IS NULL THEN 'MISSING_DERIVATIVE'
            ELSE 'VALID'
        END as derivative_validity
    FROM serving.elevation_derivatives
    WHERE geo_id IS NOT NULL
),
elevation_stats AS (
    SELECT 
        COUNT(*) as total_records,
        COUNT(CASE WHEN derivative_validity = 'VALID' THEN 1 END) as valid_records,
        COUNT(CASE WHEN derivative_validity LIKE 'ELEVATION%' THEN 1 END) as elevation_issues,
        COUNT(CASE WHEN derivative_validity LIKE 'SLOPE%' THEN 1 END) as slope_issues,
        COUNT(CASE WHEN derivative_validity LIKE 'FLOW%' THEN 1 END) as flow_issues,
        AVG(elevation_m) as avg_elevation,
        MAX(elevation_m) as max_elevation,
        MIN(elevation_m) as min_elevation,
        AVG(slope_degrees) as avg_slope
    FROM elevation_validation
)
SELECT 
    'Elevation Derivative Integration' as test_name,
    CASE 
        WHEN total_records = 0 THEN 'FAIL: No elevation derivative data found'
        WHEN valid_records < total_records * 0.95 THEN 'FAIL: Elevation derivative validation failed'
        ELSE 'PASS: Elevation derivatives properly integrated'
    END as status,
    total_records,
    valid_records,
    elevation_issues,
    slope_issues,
    flow_issues,
    ROUND(avg_elevation, 2) as average_elevation_m,
    ROUND(max_elevation, 2) as max_elevation_m,
    ROUND(min_elevation, 2) as min_elevation_m,
    ROUND(avg_slope, 2) as average_slope_degrees
FROM elevation_stats;

-- Test 5: Flood Zone Spatial Join Accuracy
-- Validates spatial joins between flood zones and administrative boundaries
WITH spatial_join_validation AS (
    SELECT 
        fz.id as flood_zone_id,
        fz.flood_zone,
        c.geoid as county_geoid,
        c.name as county_name,
        s.geoid as state_geoid,
        s.name as state_name,
        ST_Intersection(fz.geom, c.geom) as intersection_geom,
        CASE 
            WHEN ST_IsEmpty(ST_Intersection(fz.geom, c.geom)) THEN 'NO_INTERSECTION'
            WHEN NOT ST_IsValid(ST_Intersection(fz.geom, c.geom)) THEN 'INVALID_INTERSECTION'
            ELSE 'VALID_JOIN'
        END as join_validity
    FROM serving.flood_zone fz
    JOIN serving.counties c ON ST_Intersects(fz.geom, c.geom)
    JOIN serving.states s ON ST_Intersects(fz.geom, s.geom)
    WHERE ST_IsValid(fz.geom) AND ST_IsValid(c.geom)
    LIMIT 1000
),
join_stats AS (
    SELECT 
        COUNT(*) as total_joins_tested,
        COUNT(CASE WHEN join_validity = 'VALID_JOIN' THEN 1 END) as valid_joins,
        COUNT(CASE WHEN join_validity = 'NO_INTERSECTION' THEN 1 END) as no_intersection_joins,
        COUNT(CASE WHEN join_validity = 'INVALID_INTERSECTION' THEN 1 END) as invalid_intersection_joins,
        COUNT(DISTINCT state_geoid) as unique_states_covered,
        COUNT(DISTINCT county_geoid) as unique_counties_covered
    FROM spatial_join_validation
)
SELECT 
    'Flood Zone Spatial Join Accuracy' as test_name,
    CASE 
        WHEN total_joins_tested = 0 THEN 'FAIL: No spatial joins to test'
        WHEN valid_joins < total_joins_tested * 0.95 THEN 'FAIL: Spatial join accuracy issues'
        ELSE 'PASS: Spatial joins working correctly'
    END as status,
    total_joins_tested,
    valid_joins,
    no_intersection_joins,
    invalid_intersection_joins,
    unique_states_covered,
    unique_counties_covered,
    ROUND((valid_joins::FLOAT / NULLIF(total_joins_tested, 0)) * 100, 2) as spatial_join_accuracy_pct
FROM join_stats;

-- Test 6: Water Body Classification Accuracy
-- Validates water body features are correctly classified and have valid geometries
WITH water_classification_validation AS (
    SELECT 
        id,
        water_type,
        feature_class,
        CASE 
            WHEN water_type IS NULL THEN 'MISSING_TYPE'
            WHEN feature_class IS NULL THEN 'MISSING_CLASS'
            WHEN ST_IsValid(geom) = FALSE THEN 'INVALID_GEOMETRY'
            WHEN ST_Area(geom) = 0 THEN 'ZERO_AREA'
            ELSE 'VALID'
        END as classification_validity
    FROM serving.water_bodies
),
classification_stats AS (
    SELECT 
        COUNT(*) as total_water_features,
        COUNT(CASE WHEN classification_validity = 'VALID' THEN 1 END) as valid_features,
        COUNT(DISTINCT water_type) as unique_water_types,
        COUNT(DISTINCT feature_class) as unique_feature_classes,
        SUM(ST_Area(geom::geography)) as total_water_area_sqm
    FROM serving.water_bodies wb
    JOIN water_classification_validation wcv ON wb.id = wcv.id
)
SELECT 
    'Water Body Classification Accuracy' as test_name,
    CASE 
        WHEN total_water_features = 0 THEN 'FAIL: No water body features found'
        WHEN valid_features < total_water_features * 0.95 THEN 'FAIL: Water body classification issues'
        ELSE 'PASS: Water body classification accurate'
    END as status,
    total_water_features,
    valid_features,
    unique_water_types,
    unique_feature_classes,
    ROUND(total_water_area_sqm / 1000000.0, 2) as total_water_area_sqkm,
    ROUND((valid_features::FLOAT / NULLIF(total_water_features, 0)) * 100, 2) as classification_accuracy_pct
FROM classification_stats;

-- Test 7: Performance Test: Flood Zone Query Performance
-- Tests performance of spatial queries on flood zone data
EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
SELECT COUNT(*) 
FROM serving.flood_zone fz
WHERE ST_Intersects(
    fz.geom,
    ST_MakeEnvelope(-122.5, 37.7, -122.3, 37.9, 4326)::geography
);

-- Test 8: Comprehensive Flood Risk Integration Test
-- Tests end-to-end integration of all flood risk components
WITH comprehensive_flood_risk AS (
    SELECT 
        h3_id,
        flood_risk_score,
        water_distance_category,
        elevation_risk_factor,
        flood_zone_exposure,
        CASE 
            WHEN flood_risk_score BETWEEN 0 AND 100 THEN 'SCORE_VALID'
            ELSE 'SCORE_INVALID'
        END as score_status,
        CASE 
            WHEN water_distance_category IN ('0-250m', '250-1000m', '1-5km', '5km+') THEN 'DISTANCE_VALID'
            ELSE 'DISTANCE_INVALID'
        END as distance_status,
        CASE 
            WHEN elevation_risk_factor BETWEEN 0 AND 1 THEN 'ELEVATION_VALID'
            ELSE 'ELEVATION_INVALID'
        END as elevation_status
    FROM serving.flood_risk_scores
    JOIN serving.water_proximity wp USING (h3_id)
    JOIN serving.elevation_derivatives ed USING (h3_id)
),
integration_stats AS (
    SELECT 
        COUNT(*) as total_integrated_records,
        COUNT(CASE 
            WHEN score_status = 'SCORE_VALID' 
             AND distance_status = 'DISTANCE_VALID' 
             AND elevation_status = 'ELEVATION_VALID' 
            THEN 1 END) as fully_valid_records,
        AVG(flood_risk_score) as avg_integrated_score,
        MAX(flood_risk_score) as max_integrated_score,
        MIN(flood_risk_score) as min_integrated_score
    FROM comprehensive_flood_risk
)
SELECT 
    'Comprehensive Flood Risk Integration' as test_name,
    CASE 
        WHEN total_integrated_records = 0 THEN 'FAIL: No integrated flood risk data'
        WHEN fully_valid_records < total_integrated_records * 0.90 THEN 'FAIL: Integration validation failed'
        ELSE 'PASS: Comprehensive flood risk integration successful'
    END as status,
    total_integrated_records,
    fully_valid_records,
    ROUND((fully_valid_records::FLOAT / NULLIF(total_integrated_records, 0)) * 100, 2) as integration_completeness_pct,
    ROUND(avg_integrated_score, 2) as average_integrated_risk_score,
    max_integrated_score,
    min_integrated_score
FROM integration_stats;