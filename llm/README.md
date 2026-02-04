# PostGIS ETL Test Suite

This directory contains a comprehensive test suite for validating the PostGIS ETL pipeline for the GeoDataAnalytics platform.

## Overview

The test suite provides automated validation for all major ETL components including flood exposure, weather patterns, air quality, demographic data, geographic validation, and vector tile generation.

## Files

### Core Test Files

- **`test_framework_schema.sql`** - Database schema and helper functions for test execution
- **`test_flood_exposure.sql`** - Flood zone and water proximity validation tests
- **`test_weather_extreme_rain.sql`** - Precipitation and extreme weather event tests
- **`test_heat_sun_wind.sql`** - Temperature, solar, and wind data validation
- **`test_air_quality_ghg.sql`** - Air quality index and pollutant tests
- **`test_neighborhood_trends.sql`** - ACS/IRS demographic data tests
- **`test_geographic_validation.sql`** - GEOID and coordinate system validation
- **`test_vectorization_mvt_performance.sql`** - Vector tile generation performance tests

### Supporting Files

- **`test_data_fixtures.sql`** - Sample data for testing and validation
- **`test_runner.py`** - Automated test execution and reporting tool

## Test Categories

### 1. Flood Exposure Tests (`test_flood_exposure.sql`)
- Flood zone polygon validation
- Water proximity distance calculations
- Flood risk score computation
- Elevation derivative integration
- Spatial relationship validation

### 2. Weather & Extreme Rain Tests (`test_weather_extreme_rain.sql`)
- Precipitation data quality validation
- Extreme rain event detection
- Temporal aggregation validation
- Rain intensity index calculation
- Storm event spatial validation

### 3. Heat/Sun/Wind Tests (`test_heat_sun_wind.sql`)
- Heat stress index calculation
- Heat days frequency validation
- Solar exposure index calculation
- Wind profile analysis
- Temperature-humidity relationship validation

### 4. Air Quality/GHG Tests (`test_air_quality_ghg.sql`)
- Sentinel-5P data quality validation
- Air Quality Index calculation
- Pollutant concentration validation
- Ground station vs satellite comparison
- CH4 hotspot detection

### 5. Neighborhood Trends Tests (`test_neighborhood_trends.sql`)
- ACS data integration validation
- IRS migration data validation
- Population estimates consistency
- Cross-source consistency validation
- Demographic trend calculation

### 6. Geographic Validation Tests (`test_geographic_validation.sql`)
- GEOID format and range validation
- Coordinate system (CRS) validation
- Geometry quality checks
- Spatial relationship validation
- H3 index spatial accuracy

### 7. Vectorization/MVT Tests (`test_vectorization_mvt_performance.sql`)
- MVT tile generation validation
- Geometry simplification quality
- Tile compression performance
- Multi-layer tile integration
- Caching performance validation

## Usage

### Running All Tests

```bash
python test_runner.py \
  --connection "postgresql://user:password@localhost:5432/geodata_analytics" \
  --html-report --json-report --save-to-db
```

### Running Specific Test Category

```bash
python test_runner.py \
  --connection "postgresql://user:password@localhost:5432/geodata_analytics" \
  --category FLOOD \
  --html-report
```

### Test Runner Options

- `--connection` - PostgreSQL connection string (required)
- `--scripts-dir` - Directory containing SQL test scripts
- `--category` - Run specific test category only
- `--output-dir` - Output directory for reports
- `--html-report` - Generate HTML report
- `--json-report` - Generate JSON report
- `--save-to-db` - Save results to database
- `--verbose` - Enable verbose logging

## Test Data Schema

The test framework uses the following schemas:

- `test_framework` - Test configuration, execution logs, and validation rules
- `test_data` - Sample data fixtures for testing
- `test_results` - Test execution results and performance metrics

## Validation Criteria

### Data Quality Standards

- **Completeness**: ≥95% of expected records present
- **Validity**: ≤5% invalid or out-of-range values
- **Consistency**: Cross-source data consistency ≥90%
- **Accuracy**: Geographic accuracy ≥95% for spatial joins

### Performance Standards

- **Fast Tests**: <1 second execution time
- **Medium Tests**: 1-5 seconds execution time
- **Slow Tests**: 5-30 seconds execution time
- **Very Slow Tests**: >30 seconds (requires investigation)

## Reports

### HTML Report
- Executive summary with pass/fail rates
- Category breakdown by test type
- Performance analysis
- Detailed failure information

### JSON Report
- Machine-readable test results
- Detailed execution metrics
- Error messages and diagnostic data
- Performance benchmarks

### Database Storage
- Test execution logs in `test_framework.test_execution_log`
- Performance metrics for trend analysis
- Validation rule results
- Historical test data

## Integration with ETL Pipeline

These tests are designed to validate:

1. **Data Ingestion**: Raw data quality and format validation
2. **Processing**: Transformation and calculation accuracy
3. **Geographic Operations**: Spatial joins and coordinate transformations
4. **Vectorization**: Tile generation and performance optimization
5. **Integration**: Cross-system data consistency

## Best Practices

1. **Run tests after ETL pipeline updates**
2. **Monitor test performance trends**
3. **Review failed tests for data quality issues**
4. **Update test fixtures when data schema changes**
5. **Maintain test documentation and requirements**

## Troubleshooting

### Common Issues

1. **Database Connection Errors**
   - Verify connection string format
   - Check database accessibility
   - Confirm user permissions

2. **Missing Test Scripts**
   - Verify `--scripts-dir` parameter
   - Check file permissions
   - Validate SQL syntax

3. **Test Data Issues**
   - Run `test_data_fixtures.sql` to reload test data
   - Check for schema changes
   - Validate spatial indexes

4. **Performance Test Failures**
   - Check spatial index status
   - Monitor database resources
   - Verify geometry simplification settings

### Debug Mode

Use `--verbose` flag for detailed logging:

```bash
python test_runner.py --connection "..." --verbose
```

## Extending the Test Suite

To add new test categories:

1. Create new SQL test file following existing patterns
2. Add category to `test_categories` dictionary in `test_runner.py`
3. Update test configuration in `test_framework_schema.sql`
4. Add sample data to `test_data_fixtures.sql` if needed

## Dependencies

- PostgreSQL 13+ with PostGIS 3.0+
- Python 3.8+ with psycopg2
- pandas (for data processing)
- Standard Python libraries

## Security Considerations

- Test database should be isolated from production
- Connection strings should use environment variables
- Test data should not contain sensitive information
- Database permissions should be limited to test functions

## Maintenance

- Regular updates of test fixtures
- Performance baseline updates
- Schema validation updates
- Documentation maintenance