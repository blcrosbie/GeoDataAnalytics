-- Initialize PostGIS extensions and create test framework schema
-- This script runs when the PostgreSQL container starts for the first time

-- Create necessary extensions
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;
CREATE EXTENSION IF NOT EXISTS postgis_raster;
CREATE EXTENSION IF NOT EXISTS fuzzystrmatch;
CREATE EXTENSION IF NOT EXISTS postgis_tiger_geocoder;
CREATE EXTENSION IF NOT EXISTS address_standardizer;
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS btree_gin;
CREATE EXTENSION IF NOT EXISTS btree_gist;

-- Create test framework schema
CREATE SCHEMA IF NOT EXISTS test_framework;
CREATE SCHEMA IF NOT EXISTS test_data;
CREATE SCHEMA IF NOT EXISTS test_results;

-- Set search path
ALTER DATABASE geodata_analytics SET search_path TO public, test_framework, test_data, test_results;

-- Create test framework tables
CREATE TABLE IF NOT EXISTS test_framework.test_categories (
    category_id SERIAL PRIMARY KEY,
    category_name VARCHAR(50) UNIQUE NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS test_framework.test_execution_log (
    execution_id SERIAL PRIMARY KEY,
    category_name VARCHAR(50) REFERENCES test_framework.test_categories(category_name),
    script_name VARCHAR(255) NOT NULL,
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP,
    status VARCHAR(20) CHECK (status IN ('RUNNING', 'PASSED', 'FAILED', 'SKIPPED')),
    total_tests INTEGER DEFAULT 0,
    passed_tests INTEGER DEFAULT 0,
    failed_tests INTEGER DEFAULT 0,
    error_message TEXT,
    execution_time_seconds NUMERIC(10,3),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS test_framework.test_validation_rules (
    rule_id SERIAL PRIMARY KEY,
    category_name VARCHAR(50) REFERENCES test_framework.test_categories(category_name),
    rule_name VARCHAR(255) NOT NULL,
    rule_type VARCHAR(50) NOT NULL, -- 'COMPLETENESS', 'VALIDITY', 'CONSISTENCY', 'ACCURACY'
    threshold_value NUMERIC(5,2) NOT NULL,
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create test results tables
CREATE TABLE IF NOT EXISTS test_results.test_results (
    result_id SERIAL PRIMARY KEY,
    execution_id INTEGER REFERENCES test_framework.test_execution_log(execution_id),
    test_name VARCHAR(255) NOT NULL,
    test_category VARCHAR(50) NOT NULL,
    expected_result TEXT,
    actual_result TEXT,
    status VARCHAR(20) CHECK (status IN ('PASSED', 'FAILED', 'SKIPPED')),
    error_message TEXT,
    execution_time_ms NUMERIC(10,3),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS test_results.performance_metrics (
    metric_id SERIAL PRIMARY KEY,
    execution_id INTEGER REFERENCES test_framework.test_execution_log(execution_id),
    metric_name VARCHAR(255) NOT NULL,
    metric_value NUMERIC(15,3),
    metric_unit VARCHAR(50),
    benchmark_value NUMERIC(15,3),
    performance_rating VARCHAR(20) CHECK (performance_rating IN ('EXCELLENT', 'GOOD', 'ACCEPTABLE', 'POOR')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insert test categories
INSERT INTO test_framework.test_categories (category_name, description) VALUES
('FLOOD', 'Flood zone and water proximity validation tests'),
('WEATHER', 'Precipitation and extreme weather event tests'),
('HEAT_SUN_WIND', 'Temperature, solar, and wind data validation'),
('AIR_QUALITY', 'Air quality index and pollutant tests'),
('DEMOGRAPHICS', 'ACS/IRS demographic data tests'),
('GEOGRAPHIC', 'GEOID and coordinate system validation'),
('VECTORIZATION', 'Vector tile generation performance tests')
ON CONFLICT (category_name) DO NOTHING;

-- Insert validation rules
INSERT INTO test_framework.test_validation_rules (category_name, rule_name, rule_type, threshold_value, description) VALUES
('FLOOD', 'Data Completeness', 'COMPLETENESS', 95.0, 'At least 95% of expected flood zone records present'),
('FLOOD', 'Geometry Validity', 'VALIDITY', 95.0, 'At least 95% of flood zone geometries are valid'),
('WEATHER', 'Precipitation Data Quality', 'VALIDITY', 95.0, 'At least 95% of precipitation values are within valid ranges'),
('AIR_QUALITY', 'AQI Calculation Accuracy', 'ACCURACY', 90.0, 'AQI calculations match expected values 90% of the time'),
('DEMOGRAPHICS', 'Cross-source Consistency', 'CONSISTENCY', 90.0, 'Demographic data consistent across sources'),
('GEOGRAPHIC', 'Coordinate System Accuracy', 'ACCURACY', 95.0, 'Geographic accuracy for spatial joins'),
('VECTORIZATION', 'Tile Generation Performance', 'ACCURACY', 80.0, 'Vector tiles generated within performance benchmarks')
ON CONFLICT DO NOTHING;

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_test_execution_log_category ON test_framework.test_execution_log(category_name);
CREATE INDEX IF NOT EXISTS idx_test_execution_log_status ON test_framework.test_execution_log(status);
CREATE INDEX IF NOT EXISTS idx_test_results_execution_id ON test_results.test_results(execution_id);
CREATE INDEX IF NOT EXISTS idx_test_results_category ON test_results.test_results(test_category);
CREATE INDEX IF NOT EXISTS idx_performance_metrics_execution_id ON test_results.performance_metrics(execution_id);

-- Create helper functions
CREATE OR REPLACE FUNCTION test_framework.log_test_start(
    p_category_name VARCHAR(50),
    p_script_name VARCHAR(255)
) RETURNS INTEGER AS $$
DECLARE
    v_execution_id INTEGER;
BEGIN
    INSERT INTO test_framework.test_execution_log (category_name, script_name, start_time, status)
    VALUES (p_category_name, p_script_name, CURRENT_TIMESTAMP, 'RUNNING')
    RETURNING execution_id INTO v_execution_id;
    
    RETURN v_execution_id;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION test_framework.log_test_complete(
    p_execution_id INTEGER,
    p_total_tests INTEGER DEFAULT 0,
    p_passed_tests INTEGER DEFAULT 0,
    p_failed_tests INTEGER DEFAULT 0,
    p_error_message TEXT DEFAULT NULL
) RETURNS VOID AS $$
BEGIN
    UPDATE test_framework.test_execution_log 
    SET 
        end_time = CURRENT_TIMESTAMP,
        status = CASE WHEN p_failed_tests > 0 THEN 'FAILED' ELSE 'PASSED' END,
        total_tests = p_total_tests,
        passed_tests = p_passed_tests,
        failed_tests = p_failed_tests,
        error_message = p_error_message,
        execution_time_seconds = EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - start_time))
    WHERE execution_id = p_execution_id;
END;
$$ LANGUAGE plpgsql;

-- Grant permissions
GRANT USAGE ON SCHEMA test_framework TO PUBLIC;
GRANT USAGE ON SCHEMA test_data TO PUBLIC;
GRANT USAGE ON SCHEMA test_results TO PUBLIC;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA test_framework TO PUBLIC;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA test_data TO PUBLIC;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA test_results TO PUBLIC;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA test_framework TO PUBLIC;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA test_data TO PUBLIC;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA test_results TO PUBLIC;

-- Create sample data for testing (will be populated by test_data_fixtures.sql)
-- This is just a placeholder to ensure the schema is ready

COMMIT;