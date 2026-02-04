-- ==========================================
-- PostGIS ETL Test Framework Schema
-- ==========================================
-- This schema sets up the testing infrastructure for validating
-- PostGIS ETL processes for GeoDataAnalytics platform

-- Create test database schema
CREATE SCHEMA IF NOT EXISTS test_framework;
CREATE SCHEMA IF NOT EXISTS test_data;
CREATE SCHEMA IF NOT EXISTS test_results;

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;
CREATE EXTENSION IF NOT EXISTS fuzzystrmatch;
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

-- Test configuration table
CREATE TABLE test_framework.test_config (
    id SERIAL PRIMARY KEY,
    test_name VARCHAR(255) NOT NULL,
    test_category VARCHAR(100) NOT NULL,
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE,
    test_timeout_seconds INTEGER DEFAULT 300,
    expected_result_count INTEGER,
    tolerance_threshold FLOAT DEFAULT 0.01
);

-- Test execution log table
CREATE TABLE test_framework.test_execution_log (
    id SERIAL PRIMARY KEY,
    test_config_id INTEGER REFERENCES test_framework.test_config(id),
    execution_time TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    status VARCHAR(20) NOT NULL, -- 'PASSED', 'FAILED', 'ERROR', 'TIMEOUT'
    execution_time_ms INTEGER,
    rows_returned INTEGER,
    error_message TEXT,
    actual_result_count INTEGER,
    performance_metrics JSONB,
    test_output JSONB
);

-- Test validation rules table
CREATE TABLE test_framework.validation_rules (
    id SERIAL PRIMARY KEY,
    test_config_id INTEGER REFERENCES test_framework.test_config(id),
    rule_name VARCHAR(255) NOT NULL,
    rule_type VARCHAR(50) NOT NULL, -- 'ROW_COUNT', 'GEOMETRY_VALID', 'DATA_RANGE', 'SPATIAL_ACCURACY'
    rule_definition JSONB NOT NULL,
    is_critical BOOLEAN DEFAULT TRUE
);

-- Sample test data registry
CREATE TABLE test_framework.test_data_registry (
    id SERIAL PRIMARY KEY,
    dataset_name VARCHAR(255) NOT NULL,
    dataset_type VARCHAR(100) NOT NULL, -- 'FLOOD', 'WEATHER', 'AIR_QUALITY', 'CENSUS', etc.
    source_file VARCHAR(500),
    row_count INTEGER,
    geometry_type VARCHAR(50), -- 'POINT', 'POLYGON', 'LINESTRING', 'MULTIPOLYGON'
    coordinate_system VARCHAR(50) DEFAULT 'EPSG:4326',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    metadata JSONB
);

-- Performance benchmarks table
CREATE TABLE test_framework.performance_benchmarks (
    id SERIAL PRIMARY KEY,
    test_config_id INTEGER REFERENCES test_framework.test_config(id),
    baseline_time_ms INTEGER,
    max_acceptable_time_ms INTEGER,
    memory_usage_mb FLOAT,
    cpu_usage_percent FLOAT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_current_baseline BOOLEAN DEFAULT TRUE
);

-- Indexes for performance
CREATE INDEX idx_test_execution_log_status ON test_framework.test_execution_log(status);
CREATE INDEX idx_test_execution_log_time ON test_framework.test_execution_log(execution_time);
CREATE INDEX idx_test_config_category ON test_framework.test_config(test_category);
CREATE INDEX idx_test_data_registry_type ON test_framework.test_data_registry(dataset_type);

-- Helper functions for testing
CREATE OR REPLACE FUNCTION test_framework.run_test_sql(test_sql TEXT) 
RETURNS TABLE(status VARCHAR, execution_time_ms INTEGER, row_count INTEGER, error_message TEXT) AS $$
DECLARE
    start_time TIMESTAMP;
    end_time TIMESTAMP;
    result RECORD;
BEGIN
    start_time := clock_timestamp();
    
    BEGIN
        EXECUTE test_sql INTO result;
        end_time := clock_timestamp();
        
        RETURN QUERY SELECT 
            'PASSED'::VARCHAR,
            EXTRACT(EPOCH FROM (end_time - start_time)) * 1000 AS INTEGER,
            COALESCE(result.row_count, 0)::INTEGER,
            NULL::TEXT;
            
    EXCEPTION WHEN OTHERS THEN
        end_time := clock_timestamp();
        RETURN QUERY SELECT 
            'FAILED'::VARCHAR,
            EXTRACT(EPOCH FROM (end_time - start_time)) * 1000 AS INTEGER,
            0::INTEGER,
            SQLERRM::TEXT;
    END;
END;
$$ LANGUAGE plpgsql;

-- Function to validate geometry
CREATE OR REPLACE FUNCTION test_framework.validate_geometry(geom GEOMETRY, expected_type VARCHAR)
RETURNS BOOLEAN AS $$
BEGIN
    IF geom IS NULL THEN
        RETURN FALSE;
    END IF;
    
    IF NOT ST_IsValid(geom) THEN
        RETURN FALSE;
    END IF;
    
    IF expected_type IS NOT NULL THEN
        IF UPPER(expected_type) != UPPER(ST_GeometryType(geom)) THEN
            RETURN FALSE;
        END IF;
    END IF;
    
    RETURN TRUE;
END;
$$ LANGUAGE plpgsql;

-- Function to check spatial accuracy between two geometries
CREATE OR REPLACE FUNCTION test_framework.check_spatial_accuracy(
    geom1 GEOMETRY, 
    geom2 GEOMETRY, 
    tolerance_meters FLOAT DEFAULT 10.0
) RETURNS BOOLEAN AS $$
BEGIN
    IF geom1 IS NULL OR geom2 IS NULL THEN
        RETURN FALSE;
    END IF;
    
    -- Convert to appropriate coordinate system for distance calculation
    IF ST_SRID(geom1) != ST_SRID(geom2) THEN
        geom2 := ST_Transform(geom2, ST_SRID(geom1));
    END IF;
    
    -- If both are points, check distance
    IF ST_GeometryType(geom1) = 'ST_Point' AND ST_GeometryType(geom2) = 'ST_Point' THEN
        RETURN ST_Distance(geom1, geom2) <= tolerance_meters;
    END IF;
    
    -- For polygons, check overlap percentage
    IF ST_GeometryType(geom1) IN ('ST_Polygon', 'ST_MultiPolygon') AND 
       ST_GeometryType(geom2) IN ('ST_Polygon', 'ST_MultiPolygon') THEN
        RETURN ST_Intersects(geom1, geom2);
    END IF;
    
    -- Default check for intersection
    RETURN ST_Intersects(geom1, geom2);
END;
$$ LANGUAGE plpgsql;

-- Procedure to log test execution
CREATE OR REPLACE PROCEDURE test_framework.log_test_execution(
    p_test_config_id INTEGER,
    p_status VARCHAR,
    p_execution_time_ms INTEGER,
    p_rows_returned INTEGER,
    p_error_message TEXT DEFAULT NULL,
    p_actual_result_count INTEGER DEFAULT NULL,
    p_performance_metrics JSONB DEFAULT NULL,
    p_test_output JSONB DEFAULT NULL
) AS $$
BEGIN
    INSERT INTO test_framework.test_execution_log (
        test_config_id, 
        status, 
        execution_time_ms, 
        rows_returned, 
        error_message, 
        actual_result_count,
        performance_metrics,
        test_output
    ) VALUES (
        p_test_config_id,
        p_status,
        p_execution_time_ms,
        p_rows_returned,
        p_error_message,
        p_actual_result_count,
        p_performance_metrics,
        p_test_output
    );
END;
$$ LANGUAGE plpgsql;

-- View for test summary statistics
CREATE VIEW test_framework.test_summary AS
SELECT 
    tc.test_name,
    tc.test_category,
    COUNT(tel.id) as total_executions,
    COUNT(CASE WHEN tel.status = 'PASSED' THEN 1 END) as passed_count,
    COUNT(CASE WHEN tel.status = 'FAILED' THEN 1 END) as failed_count,
    COUNT(CASE WHEN tel.status = 'ERROR' THEN 1 END) as error_count,
    ROUND(AVG(tel.execution_time_ms)) as avg_execution_time_ms,
    MAX(tel.execution_time) as last_execution_time
FROM test_framework.test_config tc
LEFT JOIN test_framework.test_execution_log tel ON tc.id = tel.test_config_id
WHERE tc.is_active = TRUE
GROUP BY tc.id, tc.test_name, tc.test_category;

-- Insert initial test categories
INSERT INTO test_framework.test_config (test_name, test_category, description) VALUES
('Flood Zone Validation', 'FLOOD', 'Validates flood zone polygons and attributes'),
('Water Proximity Calculation', 'FLOOD', 'Tests distance calculations to water features'),
('Flood Risk Score Computation', 'FLOOD', 'Validates normalized flood risk scoring'),
('Precipitation Data Processing', 'WEATHER', 'Tests precipitation data aggregation'),
('Extreme Rain Event Detection', 'WEATHER', 'Validates extreme rain identification'),
('Heat Index Calculation', 'HEAT', 'Tests heat stress index computation'),
('Solar Exposure Analysis', 'HEAT', 'Validates solar radiance calculations'),
('Wind Profile Analysis', 'HEAT', 'Tests wind speed/direction processing'),
('Air Quality Index', 'AIR_QUALITY', 'Tests multi-pollutant AQI calculation'),
('NO2 Layer Validation', 'AIR_QUALITY', 'Validates NO2 satellite data processing'),
('ACS Data Integration', 'CENSUS', 'Tests ACS demographic data joins'),
('IRS Migration Processing', 'CENSUS', 'Validates IRS migration data'),
('Geographic Identifier Validation', 'VALIDATION', 'Tests GEOID and FIPS validation'),
('Coordinate System Accuracy', 'VALIDATION', 'Validates CRS transformations'),
('Geometry Quality Check', 'VALIDATION', 'Tests geometry validity and cleanliness'),
('MVT Vector Generation', 'PERFORMANCE', 'Tests Mapbox Vector Tile generation'),
('Spatial Query Performance', 'PERFORMANCE', 'Validates spatial index performance');

COMMIT;