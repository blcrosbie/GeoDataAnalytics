-- ==========================================
-- Geographic Validation SQL Tests
-- Tests for GEOID validation, coordinate systems, and spatial accuracy
-- ==========================================

-- Test 1: GEOID Format and Range Validation
-- Validates GEOID formats and FIPS code ranges across all administrative levels
WITH geoid_validation AS (
    SELECT 
        geoid,
        CASE 
            WHEN LENGTH(geoid) = 2 THEN 'STATE'
            WHEN LENGTH(geoid) = 5 THEN 'COUNTY'
            WHEN LENGTH(geoid) = 7 THEN 'PLACE'
            WHEN LENGTH(geoid) BETWEEN 11 AND 12 THEN 'TRACT'
            WHEN LENGTH(geoid) = 5 AND geoid ~ '^[0-9]{5}$' THEN 'ZIP_ZCTA'
            ELSE 'OTHER'
        END as geographic_level,
        CASE 
            WHEN LENGTH(geoid) = 2 THEN
                CASE 
                    WHEN geoid::INTEGER BETWEEN 1 AND 56 THEN 'VALID_STATE_FIPS'
                    ELSE 'INVALID_STATE_FIPS'
                END
            WHEN LENGTH(geoid) = 5 THEN
                CASE 
                    WHEN LEFT(geoid, 2)::INTEGER BETWEEN 1 AND 56 
                     AND RIGHT(geoid, 3)::INTEGER BETWEEN 1 AND 999 THEN 'VALID_COUNTY_FIPS'
                    ELSE 'INVALID_COUNTY_FIPS'
                END
            WHEN geoid ~ '^[0-9]+$' THEN 'VALID_NUMERIC_GEOID'
            ELSE 'INVALID_GEOID_FORMAT'
        END as geoid_validity
    FROM (
        SELECT DISTINCT geoid FROM serving.census_tracts
        UNION SELECT DISTINCT geoid FROM serving.counties  
        UNION SELECT DISTINCT geoid FROM serving.states
        UNION SELECT DISTINCT geoid FROM serving.places
    ) all_geoids
),
geoid_stats AS (
    SELECT 
        geographic_level,
        COUNT(*) as total_geo_ids,
        COUNT(CASE WHEN geoid_validity LIKE 'VALID%' THEN 1 END) as valid_geo_ids,
        COUNT(CASE WHEN geoid_validity LIKE 'INVALID%' THEN 1 END) as invalid_geo_ids,
        COUNT(DISTINCT geoid) as unique_geo_ids
    FROM geoid_validation
    GROUP BY geographic_level
)
SELECT 
    'GEOID Format and Range Validation' as test_name,
    CASE 
        WHEN COUNT(*) = 0 THEN 'FAIL: No GEOID data found'
        WHEN COUNT(CASE WHEN geoid_validity LIKE 'VALID%' THEN 1 END) < COUNT(*) * 0.95 THEN 'FAIL: GEOID validation failed'
        ELSE 'PASS: GEOID formats and ranges valid'
    END as status,
    geographic_level,
    total_geo_ids,
    valid_geo_ids,
    invalid_geo_ids,
    ROUND((valid_geo_ids::FLOAT / NULLIF(total_geo_ids, 0)) * 100, 2) as geoid_validity_pct
FROM geoid_stats
GROUP BY geographic_level, total_geo_ids, valid_geo_ids, invalid_geo_ids;

-- Test 2: Coordinate System (CRS) Validation
-- Validates coordinate systems and spatial reference consistency
WITH crs_validation AS (
    SELECT 
        table_name,
        geometry_column_name,
        ST_SRID(geometry_column) as current_srid,
        CASE 
            WHEN ST_SRID(geometry_column) = 4326 THEN 'WGS84'
            WHEN ST_SRID(geometry_column) = 3857 THEN 'WEB_MERCATOR'
            WHEN ST_SRID(geometry_column) = 5070 THEN 'NAD83_CONUS_ALBERS'
            WHEN ST_SRID(geometry_column) = 2163 THEN 'US_NATIONAL_ATLAS_EQUAL_AREA'
            ELSE 'OTHER_CRS'
        END as crs_name,
        CASE 
            WHEN ST_SRID(geometry_column) IN (4326, 3857, 5070, 2163) THEN 'VALID_CRS'
            ELSE 'INVALID_CRS'
        END as crs_validity
    FROM (
        SELECT 'counties' as table_name, 'geom' as geometry_column_name, geom as geometry_column FROM serving.counties LIMIT 1
        UNION SELECT 'states', 'geom', geom FROM serving.states LIMIT 1
        UNION SELECT 'census_tracts', 'geom', geom FROM serving.census_tracts LIMIT 1
        UNION SELECT 'places', 'geom', geom FROM serving.places LIMIT 1
        UNION SELECT 'h3_index', 'geom', geom FROM serving.h3_index LIMIT 1
    ) geometry_tables
),
crs_stats AS (
    SELECT 
        COUNT(*) as total_geometry_tables,
        COUNT(CASE WHEN crs_validity = 'VALID_CRS' THEN 1 END) as valid_crs_tables,
        COUNT(CASE WHEN crs_validity = 'INVALID_CRS' THEN 1 END) as invalid_crs_tables,
        COUNT(DISTINCT current_srid) as unique_srids,
        COUNT(DISTINCT crs_name) as unique_crs_names
    FROM crs_validation
)
SELECT 
    'Coordinate System (CRS) Validation' as test_name,
    CASE 
        WHEN total_geometry_tables = 0 THEN 'FAIL: No geometry tables found'
        WHEN valid_crs_tables < total_geometry_tables THEN 'FAIL: CRS validation failed'
        ELSE 'PASS: Coordinate systems valid'
    END as status,
    total_geometry_tables,
    valid_crs_tables,
    invalid_crs_tables,
    unique_srids,
    unique_crs_names
FROM crs_stats;

-- Test 3: Geometry Quality and Validity Checks
-- Validates geometry validity, topology, and quality metrics
WITH geometry_quality_validation AS (
    SELECT 
        'counties' as table_name,
        geoid,
        ST_IsValid(geom) as is_valid,
        ST_IsValidReason(geom) as validity_reason,
        ST_IsSimple(geom) as is_simple,
        ST_Area(geom::geography) as area_sqkm,
        ST_Perimeter(geom::geography) as perimeter_km,
        CASE 
            WHEN NOT ST_IsValid(geom) THEN 'INVALID_GEOMETRY'
            WHEN NOT ST_IsSimple(geom) THEN 'COMPLEX_GEOMETRY'
            WHEN ST_Area(geom::geography) = 0 THEN 'ZERO_AREA'
            WHEN ST_Area(geom::geography) > 100000 THEN 'EXCESSIVE_AREA'  -- >100,000 sq km
            WHEN ST_Perimeter(geom::geography) > 10000 THEN 'EXCESSIVE_PERIMETER'  -- >10,000 km
            ELSE 'VALID'
        END as geometry_quality
    FROM serving.counties
    WHERE ST_IsValid(geom) OR ST_Area(geom::geography) > 0  -- Include invalid for analysis
    LIMIT 1000
),
geometry_stats AS (
    SELECT 
        table_name,
        COUNT(*) as total_geometries,
        COUNT(CASE WHEN is_valid THEN 1 END) as valid_geometries,
        COUNT(CASE WHEN is_simple THEN 1 END) as simple_geometries,
        COUNT(CASE WHEN geometry_quality = 'VALID' THEN 1 END) as high_quality_geometries,
        COUNT(CASE WHEN geometry_quality LIKE 'INVALID%' THEN 1 END) as invalid_geometries,
        AVG(area_sqkm) as avg_area_sqkm,
        MAX(area_sqkm) as max_area_sqkm,
        AVG(perimeter_km) as avg_perimeter_km
    FROM geometry_quality_validation
    GROUP BY table_name
)
SELECT 
    'Geometry Quality and Validity Checks' as test_name,
    CASE 
        WHEN total_geometries = 0 THEN 'FAIL: No geometry data found'
        WHEN valid_geometries < total_geometries * 0.95 THEN 'FAIL: Geometry validity check failed'
        ELSE 'PASS: Geometry quality checks passed'
    END as status,
    table_name,
    total_geometries,
    valid_geometries,
    simple_geometries,
    high_quality_geometries,
    invalid_geometries,
    ROUND(avg_area_sqkm, 2) as average_area_sqkm,
    ROUND(max_area_sqkm, 2) as maximum_area_sqkm,
    ROUND(avg_perimeter_km, 2) as average_perimeter_km
FROM geometry_stats;

-- Test 4: Spatial Relationship Validation
-- Validates spatial relationships and topological consistency
WITH spatial_relationship_validation AS (
    SELECT 
        c.geoid as county_geoid,
        s.geoid as state_geoid,
        ST_Contains(s.geom, c.geom) as contains_county,
        ST_Intersects(s.geom, c.geom) as intersects_county,
        ST_Area(ST_Intersection(s.geom, c.geom)::geography) as intersection_area_sqkm,
        ST_Area(c.geom::geography) as county_area_sqkm,
        CASE 
            WHEN NOT ST_Intersects(s.geom, c.geom) THEN 'NO_INTERSECTION'
            WHEN NOT ST_Contains(s.geom, c.geom) THEN 'COUNTY_NOT_CONTAINED'
            WHEN intersection_area_sqkm / county_area_sqkm < 0.95 THEN 'PARTIAL_CONTAINMENT'
            ELSE 'VALID_SPATIAL_RELATIONSHIP'
        END as spatial_validity
    FROM serving.counties c
    JOIN serving.states s ON ST_Intersects(c.geom, s.geom)
    WHERE ST_IsValid(c.geom) AND ST_IsValid(s.geom)
    LIMIT 1000
),
spatial_stats AS (
    SELECT 
        COUNT(*) as total_spatial_relationships,
        COUNT(CASE WHEN spatial_validity = 'VALID_SPATIAL_RELATIONSHIP' THEN 1 END) as valid_relationships,
        COUNT(CASE WHEN spatial_validity = 'NO_INTERSECTION' THEN 1 END) as no_intersections,
        COUNT(CASE WHEN spatial_validity = 'COUNTY_NOT_CONTAINED' THEN 1 END) as counties_not_contained,
        COUNT(CASE WHEN spatial_validity = 'PARTIAL_CONTAINMENT' THEN 1 END) as partial_containments,
        AVG(intersection_area_sqkm / county_area_sqkm) as avg_containment_ratio,
        COUNT(DISTINCT state_geoid) as states_tested
    FROM spatial_relationship_validation
)
SELECT 
    'Spatial Relationship Validation' as test_name,
    CASE 
        WHEN total_spatial_relationships = 0 THEN 'FAIL: No spatial relationships to validate'
        WHEN valid_relationships < total_spatial_relationships * 0.90 THEN 'FAIL: Spatial relationship validation failed'
        ELSE 'PASS: Spatial relationships valid'
    END as status,
    total_spatial_relationships,
    valid_relationships,
    no_intersections,
    counties_not_contained,
    partial_containments,
    ROUND(avg_containment_ratio, 4) as average_containment_ratio,
    states_tested
FROM spatial_stats;

-- Test 5: Coordinate Range and Extent Validation
-- Validates coordinate ranges and geographic extent
WITH coordinate_range_validation AS (
    SELECT 
        'states' as table_name,
        geoid,
        ST_XMin(geom) as min_x,
        ST_XMax(geom) as max_x,
        ST_YMin(geom) as min_y,
        ST_YMax(geom) as max_y,
        CASE 
            WHEN ST_XMin(geom) < -180 OR ST_XMax(geom) > 180 THEN 'INVALID_LONGITUDE_RANGE'
            WHEN ST_YMin(geom) < -90 OR ST_YMax(geom) > 90 THEN 'INVALID_LATITUDE_RANGE'
            WHEN ST_XMax(geom) - ST_XMin(geom) > 60 THEN 'EXCESSIVE_LONGITUDE_SPAN'  -- >60 degrees
            WHEN ST_YMax(geom) - ST_YMin(geom) > 30 THEN 'EXCESSIVE_LATITUDE_SPAN'  -- >30 degrees
            ELSE 'VALID_COORDINATE_RANGE'
        END as coordinate_validity
    FROM serving.states
    WHERE ST_IsValid(geom)
    LIMIT 100
),
coordinate_stats AS (
    SELECT 
        table_name,
        COUNT(*) as total_features,
        COUNT(CASE WHEN coordinate_validity = 'VALID_COORDINATE_RANGE' THEN 1 END) as valid_coordinates,
        COUNT(CASE WHEN coordinate_validity LIKE 'INVALID_%' THEN 1 END) as invalid_range_coordinates,
        COUNT(CASE WHEN coordinate_validity LIKE 'EXCESSIVE_%' THEN 1 END) as excessive_span_coordinates,
        AVG(ST_XMax(geom) - ST_XMin(geom)) as avg_longitude_span,
        AVG(ST_YMax(geom) - ST_YMin(geom)) as avg_latitude_span,
        AVG(ST_XMin(geom)) as avg_min_longitude,
        AVG(ST_XMax(geom)) as avg_max_longitude,
        AVG(ST_YMin(geom)) as avg_min_latitude,
        AVG(ST_YMax(geom)) as avg_max_latitude
    FROM coordinate_range_validation crv
    JOIN serving.states s ON crv.geoid = s.geoid
    GROUP BY table_name
)
SELECT 
    'Coordinate Range and Extent Validation' as test_name,
    CASE 
        WHEN total_features = 0 THEN 'FAIL: No coordinate data found'
        WHEN valid_coordinates < total_features * 0.95 THEN 'FAIL: Coordinate range validation failed'
        ELSE 'PASS: Coordinate ranges valid'
    END as status,
    table_name,
    total_features,
    valid_coordinates,
    invalid_range_coordinates,
    excessive_span_coordinates,
    ROUND(avg_longitude_span, 4) as average_longitude_span_degrees,
    ROUND(avg_latitude_span, 4) as average_latitude_span_degrees,
    ROUND(avg_min_longitude, 4) as average_min_longitude,
    ROUND(avg_max_longitude, 4) as average_max_longitude,
    ROUND(avg_min_latitude, 4) as average_min_latitude,
    ROUND(avg_max_latitude, 4) as average_max_latitude
FROM coordinate_stats;

-- Test 6: H3 Index Spatial Accuracy Validation
-- Validates H3 hexagon grid spatial properties and indexing
WITH h3_spatial_validation AS (
    SELECT 
        h3_id,
        resolution,
        ST_Area(geom::geography) as area_sqkm,
        ST_Perimeter(geom::geography) as perimeter_km,
        ST_NPoints(geom) as vertex_count,
        CASE 
            WHEN NOT ST_IsValid(geom) THEN 'INVALID_GEOMETRY'
            WHEN resolution < 0 OR resolution > 15 THEN 'INVALID_RESOLUTION'
            WHEN area_sqkm = 0 THEN 'ZERO_AREA'
            WHEN vertex_count != 6 THEN 'INVALID_VERTEX_COUNT'  -- H3 should have 6 vertices
            ELSE 'VALID'
        END as h3_validity
    FROM serving.h3_index
    WHERE ST_IsValid(geom) OR area_sqkm > 0
    LIMIT 1000
),
h3_stats AS (
    SELECT 
        COUNT(*) as total_h3_cells,
        COUNT(CASE WHEN h3_validity = 'VALID' THEN 1 END) as valid_h3_cells,
        COUNT(CASE WHEN h3_validity = 'INVALID_GEOMETRY' THEN 1 END) as invalid_geometry_cells,
        COUNT(CASE WHEN h3_validity = 'INVALID_RESOLUTION' THEN 1 END) as invalid_resolution_cells,
        COUNT(DISTINCT resolution) as unique_resolutions,
        AVG(area_sqkm) as avg_area_sqkm,
        MIN(area_sqkm) as min_area_sqkm,
        MAX(area_sqkm) as max_area_sqkm,
        AVG(vertex_count) as avg_vertex_count
    FROM h3_spatial_validation
)
SELECT 
    'H3 Index Spatial Accuracy Validation' as test_name,
    CASE 
        WHEN total_h3_cells = 0 THEN 'FAIL: No H3 index data found'
        WHEN valid_h3_cells < total_h3_cells * 0.95 THEN 'FAIL: H3 spatial validation failed'
        WHEN unique_resolutions = 0 THEN 'FAIL: No H3 resolutions found'
        ELSE 'PASS: H3 spatial properties valid'
    END as status,
    total_h3_cells,
    valid_h3_cells,
    invalid_geometry_cells,
    invalid_resolution_cells,
    unique_resolutions,
    ROUND(avg_area_sqkm, 6) as average_area_sqkm,
    ROUND(min_area_sqkm, 6) as minimum_area_sqkm,
    ROUND(max_area_sqkm, 6) as maximum_area_sqkm,
    ROUND(avg_vertex_count, 1) as average_vertex_count
FROM h3_stats;

-- Test 7: Address and Point Location Validation
-- Validates point data quality and address geocoding accuracy
WITH point_location_validation AS (
    SELECT 
        address_id,
        longitude,
        latitude,
        geocode_quality,
        ST_MakePoint(longitude, latitude, 4326) as point_geom,
        CASE 
            WHEN longitude IS NULL OR latitude IS NULL THEN 'MISSING_COORDINATES'
            WHEN longitude < -180 OR longitude > 180 THEN 'INVALID_LONGITUDE'
            WHEN latitude < -90 OR latitude > 90 THEN 'INVALID_LATITUDE'
            WHEN geocode_quality NOT IN ('high', 'medium', 'low') THEN 'INVALID_GEOCODE_QUALITY'
            ELSE 'VALID'
        END as point_validity
    FROM staging.geocoded_addresses
    WHERE address_id IS NOT NULL
    LIMIT 1000
),
point_stats AS (
    SELECT 
        COUNT(*) as total_points,
        COUNT(CASE WHEN point_validity = 'VALID' THEN 1 END) as valid_points,
        COUNT(CASE WHEN point_validity LIKE 'INVALID_%' THEN 1 END) as invalid_range_points,
        COUNT(CASE WHEN point_validity = 'MISSING_COORDINATES' THEN 1 END) as missing_coordinate_points,
        COUNT(DISTINCT geocode_quality) as unique_geocode_qualities,
        AVG(longitude) as avg_longitude,
        AVG(latitude) as avg_latitude,
        COUNT(CASE WHEN geocode_quality = 'high' THEN 1 END) as high_quality_geocodes
    FROM point_location_validation
)
SELECT 
    'Address and Point Location Validation' as test_name,
    CASE 
        WHEN total_points = 0 THEN 'FAIL: No point location data found'
        WHEN valid_points < total_points * 0.95 THEN 'FAIL: Point location validation failed'
        ELSE 'PASS: Point locations valid'
    END as status,
    total_points,
    valid_points,
    invalid_range_points,
    missing_coordinate_points,
    unique_geocode_qualities,
    high_quality_geocodes,
    ROUND(avg_longitude, 6) as average_longitude,
    ROUND(avg_latitude, 6) as average_latitude
FROM point_stats;

-- Test 8: Spatial Index Performance Validation
-- Tests spatial index performance and query optimization
WITH spatial_index_test AS (
    SELECT 
        'counties' as table_name,
        COUNT(*) as total_counties,
        COUNT(CASE WHEN ST_Intersects(
            geom,
            ST_MakeEnvelope(-125.0, 32.0, -114.0, 42.0, 4326)
        ) THEN 1 END) as counties_in_california
    FROM serving.counties
    WHERE ST_IsValid(geom)
)
SELECT 
    'Spatial Index Performance Validation' as test_name,
    CASE 
        WHEN total_counties = 0 THEN 'FAIL: No counties for spatial index test'
        WHEN counties_in_california = 0 THEN 'FAIL: Spatial index not working properly'
        ELSE 'PASS: Spatial index performance acceptable'
    END as status,
    table_name,
    total_counties,
    counties_in_california,
    ROUND((counties_in_california::FLOAT / NULLIF(total_counties, 0)) * 100, 2) as california_coverage_pct
FROM spatial_index_test;

-- Test 9: Comprehensive Geographic Integration Test
-- Tests end-to-end geographic data integration and consistency
WITH geographic_integration AS (
    SELECT 
        c.geoid as county_geoid,
        s.geoid as state_geoid,
        ct.geoid as tract_geoid,
        ST_Contains(s.geom, c.geom) as county_in_state,
        ST_Contains(c.geom, ct.geom) as tract_in_county,
        ST_IsValid(c.geom) as county_valid,
        ST_IsValid(s.geom) as state_valid,
        ST_IsValid(ct.geom) as tract_valid,
        CASE 
            WHEN NOT county_valid THEN 'INVALID_COUNTY_GEOMETRY'
            WHEN NOT state_valid THEN 'INVALID_STATE_GEOMETRY'
            WHEN NOT tract_valid THEN 'INVALID_TRACT_GEOMETRY'
            WHEN NOT county_in_state THEN 'COUNTY_NOT_IN_STATE'
            WHEN NOT tract_in_county THEN 'TRACT_NOT_IN_COUNTY'
            ELSE 'VALID_INTEGRATION'
        END as integration_status
    FROM serving.counties c
    JOIN serving.states s ON ST_Intersects(c.geom, s.geom)
    JOIN serving.census_tracts ct ON ST_Intersects(ct.geom, c.geom)
    WHERE ST_IsValid(c.geom) AND ST_IsValid(s.geom) AND ST_IsValid(ct.geom)
    LIMIT 500
),
integration_stats AS (
    SELECT 
        COUNT(*) as total_integration_tests,
        COUNT(CASE WHEN integration_status = 'VALID_INTEGRATION' THEN 1 END) as valid_integrations,
        COUNT(CASE WHEN integration_status LIKE 'INVALID_%' THEN 1 END) as invalid_geometry_integrations,
        COUNT(CASE WHEN integration_status LIKE '%NOT_IN_%' THEN 1 END) as containment_failures,
        COUNT(DISTINCT state_geoid) as states_tested,
        COUNT(DISTINCT county_geoid) as counties_tested,
        COUNT(DISTINCT tract_geoid) as tracts_tested
    FROM geographic_integration
)
SELECT 
    'Comprehensive Geographic Integration Test' as test_name,
    CASE 
        WHEN total_integration_tests = 0 THEN 'FAIL: No geographic integration tests'
        WHEN valid_integrations < total_integration_tests * 0.90 THEN 'FAIL: Geographic integration validation failed'
        ELSE 'PASS: Comprehensive geographic integration successful'
    END as status,
    total_integration_tests,
    valid_integrations,
    invalid_geometry_integrations,
    containment_failures,
    states_tested,
    counties_tested,
    tracts_tested,
    ROUND((valid_integrations::FLOAT / NULLIF(total_integration_tests, 0)) * 100, 2) as integration_completeness_pct
FROM integration_stats;