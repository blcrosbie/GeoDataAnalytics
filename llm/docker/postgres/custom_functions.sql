-- Custom PostGIS functions for the GeoDataAnalytics test suite
-- These functions provide specialized spatial analysis capabilities

-- Function to calculate flood risk score based on multiple factors
CREATE OR REPLACE FUNCTION test_framework.calculate_flood_risk_score(
    p_elevation NUMERIC,
    p_distance_to_water NUMERIC,
    p_flood_zone_type VARCHAR(10)
) RETURNS NUMERIC AS $$
DECLARE
    v_elevation_score NUMERIC;
    v_distance_score NUMERIC;
    v_zone_score NUMERIC;
    v_total_score NUMERIC;
BEGIN
    -- Elevation score (lower elevation = higher risk)
    v_elevation_score := CASE 
        WHEN p_elevation < 0 THEN 1.0
        WHEN p_elevation < 10 THEN 0.8
        WHEN p_elevation < 50 THEN 0.6
        WHEN p_elevation < 100 THEN 0.4
        WHEN p_elevation < 500 THEN 0.2
        ELSE 0.1
    END;
    
    -- Distance to water score (closer = higher risk)
    v_distance_score := CASE 
        WHEN p_distance_to_water < 100 THEN 1.0
        WHEN p_distance_to_water < 500 THEN 0.8
        WHEN p_distance_to_water < 1000 THEN 0.6
        WHEN p_distance_to_water < 2000 THEN 0.4
        WHEN p_distance_to_water < 5000 THEN 0.2
        ELSE 0.1
    END;
    
    -- Flood zone type score
    v_zone_score := CASE p_flood_zone_type
        WHEN 'AE' THEN 1.0
        WHEN 'AH' THEN 0.9
        WHEN 'AO' THEN 0.8
        WHEN 'A' THEN 0.7
        WHEN 'X' THEN 0.3
        WHEN 'D' THEN 0.5
        ELSE 0.2
    END;
    
    -- Calculate weighted average
    v_total_score := (v_elevation_score * 0.3) + 
                    (v_distance_score * 0.4) + 
                    (v_zone_score * 0.3);
    
    RETURN ROUND(v_total_score, 3);
END;
$$ LANGUAGE plpgsql;

-- Function to validate geometry quality
CREATE OR REPLACE FUNCTION test_framework.validate_geometry_quality(
    p_geometry GEOMETRY
) RETURNS JSON AS $$
DECLARE
    v_result JSON;
    v_is_valid BOOLEAN;
    v_area NUMERIC;
    v_perimeter NUMERIC;
    v_num_points INTEGER;
    v_geometry_type TEXT;
BEGIN
    v_is_valid := ST_IsValid(p_geometry);
    v_area := COALESCE(ST_Area(p_geometry), 0);
    v_perimeter := COALESCE(ST_Perimeter(p_geometry), 0);
    v_num_points := ST_NPoints(p_geometry);
    v_geometry_type := ST_GeometryType(p_geometry);
    
    v_result := json_build_object(
        'is_valid', v_is_valid,
        'area', v_area,
        'perimeter', v_perimeter,
        'num_points', v_num_points,
        'geometry_type', v_geometry_type,
        'bounds', ST_AsText(ST_Envelope(p_geometry)),
        'centroid', ST_AsText(ST_Centroid(p_geometry)),
        'quality_score', CASE 
            WHEN v_is_valid AND v_num_points > 3 THEN 1.0
            WHEN v_is_valid THEN 0.7
            ELSE 0.0
        END
    );
    
    RETURN v_result;
END;
$$ LANGUAGE plpgsql;

-- Function to calculate heat stress index
CREATE OR REPLACE FUNCTION test_framework.calculate_heat_stress_index(
    p_temperature NUMERIC,
    p_humidity NUMERIC,
    p_wind_speed NUMERIC DEFAULT 0
) RETURNS NUMERIC AS $$
DECLARE
    v_heat_index NUMERIC;
    v_stress_index NUMERIC;
BEGIN
    -- Calculate heat index (simplified formula)
    IF p_temperature < 80 THEN
        v_heat_index := p_temperature;
    ELSE
        v_heat_index := p_temperature + 
                        (0.5 * p_humidity * (p_temperature - 58)) / 
                        (1 - 0.01 * p_humidity);
    END IF;
    
    -- Calculate stress index considering wind speed
    v_stress_index := v_heat_index - (p_wind_speed * 0.1);
    
    RETURN ROUND(v_stress_index, 1);
END;
$$ LANGUAGE plpgsql;

-- Function to validate coordinate reference system
CREATE OR REPLACE FUNCTION test_framework.validate_crs(
    p_geometry GEOMETRY,
    p_expected_srid INTEGER DEFAULT 4326
) RETURNS JSON AS $$
DECLARE
    v_result JSON;
    v_actual_srid INTEGER;
    v_is_valid_crs BOOLEAN;
    v_needs_transform BOOLEAN;
BEGIN
    v_actual_srid := ST_SRID(p_geometry);
    v_is_valid_crs := (v_actual_srid = p_expected_srid);
    v_needs_transform := (v_actual_srid != p_expected_srid AND v_actual_srid != 0);
    
    v_result := json_build_object(
        'expected_srid', p_expected_srid,
        'actual_srid', v_actual_srid,
        'is_valid_crs', v_is_valid_crs,
        'needs_transform', v_needs_transform,
        'geometry_type', ST_GeometryType(p_geometry),
        'bounds', ST_AsText(ST_Envelope(p_geometry)),
        'area_degrees', ST_Area(p_geometry::geography),
        'centroid', ST_AsText(ST_Centroid(p_geometry))
    );
    
    RETURN v_result;
END;
$$ LANGUAGE plpgsql;

-- Function to calculate vector tile performance metrics
CREATE OR REPLACE FUNCTION test_framework.calculate_tile_performance(
    p_zoom_level INTEGER,
    p_geometry_count INTEGER,
    p_total_vertices INTEGER,
    p_tile_size_bytes INTEGER DEFAULT 0
) RETURNS JSON AS $$
DECLARE
    v_result JSON;
    v_complexity_score NUMERIC;
    v_estimated_size INTEGER;
    v_performance_rating TEXT;
BEGIN
    -- Calculate complexity score
    v_complexity_score := (p_total_vertices::NUMERIC / GREATEST(p_geometry_count, 1)) * p_zoom_level;
    
    -- Estimate tile size (rough calculation)
    v_estimated_size := p_total_vertices * 8 + p_geometry_count * 16;
    
    -- Performance rating
    v_performance_rating := CASE 
        WHEN v_complexity_score < 100 THEN 'EXCELLENT'
        WHEN v_complexity_score < 500 THEN 'GOOD'
        WHEN v_complexity_score < 1000 THEN 'ACCEPTABLE'
        ELSE 'POOR'
    END;
    
    v_result := json_build_object(
        'zoom_level', p_zoom_level,
        'geometry_count', p_geometry_count,
        'total_vertices', p_total_vertices,
        'complexity_score', ROUND(v_complexity_score, 2),
        'estimated_size_bytes', v_estimated_size,
        'actual_size_bytes', p_tile_size_bytes,
        'performance_rating', v_performance_rating,
        'vertices_per_geometry', ROUND(p_total_vertices::NUMERIC / GREATEST(p_geometry_count, 1), 2),
        'compression_ratio', CASE 
            WHEN p_tile_size_bytes > 0 THEN ROUND(p_estimated_size::NUMERIC / p_tile_size_bytes, 2)
            ELSE NULL
        END
    );
    
    RETURN v_result;
END;
$$ LANGUAGE plpgsql;

-- Function to validate GEOID format and range
CREATE OR REPLACE FUNCTION test_framework.validate_geoid(
    p_geoid VARCHAR(20),
    p_geoid_type VARCHAR(10) DEFAULT 'BLOCK'
) RETURNS JSON AS $$
DECLARE
    v_result JSON;
    v_is_valid_format BOOLEAN;
    v_is_valid_range BOOLEAN;
    v_state_fips VARCHAR(2);
    v_county_fips VARCHAR(3);
    v_tract_code VARCHAR(6);
    v_block_group VARCHAR(1);
    v_block_code VARCHAR(1);
BEGIN
    -- Check format validity
    v_is_valid_format := p_geoid ~ '^[0-9]+$';
    
    -- Parse components based on type
    CASE p_geoid_type
        WHEN 'STATE' THEN
            v_is_valid_range := LENGTH(p_geoid) = 2 AND p_geoid::INTEGER BETWEEN 1 AND 56;
        WHEN 'COUNTY' THEN
            v_state_fips := SUBSTRING(p_geoid, 1, 2);
            v_county_fips := SUBSTRING(p_geoid, 3, 3);
            v_is_valid_range := LENGTH(p_geoid) = 5 AND 
                               v_state_fips::INTEGER BETWEEN 1 AND 56 AND
                               v_county_fips::INTEGER BETWEEN 1 AND 999;
        WHEN 'TRACT' THEN
            v_state_fips := SUBSTRING(p_geoid, 1, 2);
            v_county_fips := SUBSTRING(p_geoid, 3, 3);
            v_tract_code := SUBSTRING(p_geoid, 6, 6);
            v_is_valid_range := LENGTH(p_geoid) = 11 AND 
                               v_state_fips::INTEGER BETWEEN 1 AND 56;
        WHEN 'BLOCK_GROUP' THEN
            v_is_valid_range := LENGTH(p_geoid) = 12;
        WHEN 'BLOCK' THEN
            v_is_valid_range := LENGTH(p_geoid) = 15;
        ELSE
            v_is_valid_range := FALSE;
    END CASE;
    
    v_result := json_build_object(
        'geoid', p_geoid,
        'geoid_type', p_geoid_type,
        'is_valid_format', v_is_valid_format,
        'is_valid_range', v_is_valid_range,
        'is_valid', v_is_valid_format AND v_is_valid_range,
        'length', LENGTH(p_geoid),
        'state_fips', v_state_fips,
        'county_fips', v_county_fips,
        'tract_code', v_tract_code,
        'block_group', v_block_group,
        'block_code', v_block_code
    );
    
    RETURN v_result;
END;
$$ LANGUAGE plpgsql;

-- Create indexes for custom functions
CREATE INDEX IF NOT EXISTS idx_custom_functions_geoid ON test_data.test_geoids(geoid) WHERE geoid IS NOT NULL;

COMMIT;