-- ==========================================
-- Neighborhood Trends SQL Tests for ACS/IRS Data
-- Tests for American Community Survey, IRS migration, and population estimates data
-- ==========================================

-- Test 1: ACS Data Integration Validation
-- Validates ACS demographic data joins with geographic boundaries
WITH acs_integration_validation AS (
    SELECT 
        geoid,
        year,
        total_population,
        median_household_income,
        median_age,
        education_bachelors_or_higher_pct,
        CASE 
            WHEN total_population < 0 OR total_population > 100000 THEN 'POPULATION_OUT_OF_RANGE'
            WHEN median_household_income < 0 OR median_household_income > 500000 THEN 'INCOME_OUT_OF_RANGE'
            WHEN median_age < 0 OR median_age > 100 THEN 'AGE_OUT_OF_RANGE'
            WHEN education_bachelors_or_higher_pct < 0 OR education_bachelors_or_higher_pct > 100 THEN 'EDUCATION_OUT_OF_RANGE'
            WHEN geoid NOT LIKE '%' || SUBSTRING(geoid, -5) THEN 'INVALID_GEOID_FORMAT'
            ELSE 'VALID'
        END as acs_validity
    FROM serving.acs_demographics
),
acs_stats AS (
    SELECT 
        COUNT(*) as total_acs_records,
        COUNT(CASE WHEN acs_validity = 'VALID' THEN 1 END) as valid_acs_records,
        COUNT(CASE WHEN acs_validity LIKE '%OUT_OF_RANGE' THEN 1 END) as out_of_range_records,
        COUNT(DISTINCT year) as unique_years,
        COUNT(DISTINCT LEFT(geoid, 2)) as unique_states,
        AVG(total_population) as avg_population,
        AVG(median_household_income) as avg_income,
        AVG(median_age) as avg_age,
        AVG(education_bachelors_or_higher_pct) as avg_education_pct
    FROM acs_integration_validation
)
SELECT 
    'ACS Data Integration Validation' as test_name,
    CASE 
        WHEN total_acs_records = 0 THEN 'FAIL: No ACS demographic data found'
        WHEN valid_acs_records < total_acs_records * 0.95 THEN 'FAIL: ACS data validation failed'
        WHEN unique_years < 3 THEN 'FAIL: Insufficient temporal coverage'
        ELSE 'PASS: ACS data integration valid'
    END as status,
    total_acs_records,
    valid_acs_records,
    out_of_range_records,
    unique_years,
    unique_states,
    ROUND(avg_population, 0) as average_population,
    ROUND(avg_income, 0) as average_median_income,
    ROUND(avg_age, 1) as average_median_age,
    ROUND(avg_education_pct, 1) as average_education_percentage
FROM acs_stats;

-- Test 2: IRS Migration Data Validation
-- Validates IRS migration flow data and consistency
WITH irs_migration_validation AS (
    SELECT 
        origin_state_fips,
        destination_state_fips,
        year,
        migration_count,
        agi_total,
        avg_agi_per_return,
        CASE 
            WHEN origin_state_fips < 1 OR origin_state_fips > 56 THEN 'INVALID_ORIGIN_FIPS'
            WHEN destination_state_fips < 1 OR destination_state_fips > 56 THEN 'INVALID_DESTINATION_FIPS'
            WHEN origin_state_fips = destination_state_fips THEN 'SAME_STATE_MIGRATION'
            WHEN migration_count < 0 OR migration_count > 1000000 THEN 'MIGRATION_COUNT_OUT_OF_RANGE'
            WHEN agi_total < 0 OR agi_total > 100000000000 THEN 'AGI_OUT_OF_RANGE'
            WHEN avg_agi_per_return < 0 OR avg_agi_per_return > 1000000 THEN 'AVG_AGI_OUT_OF_RANGE'
            ELSE 'VALID'
        END as migration_validity
    FROM serving.irs_migration_flows
),
migration_stats AS (
    SELECT 
        COUNT(*) as total_migration_records,
        COUNT(CASE WHEN migration_validity = 'VALID' THEN 1 END) as valid_migration_records,
        COUNT(CASE WHEN migration_validity LIKE 'INVALID%' THEN 1 END) as invalid_fips_records,
        COUNT(CASE WHEN migration_validity = 'SAME_STATE_MIGRATION' THEN 1 END) as same_state_records,
        COUNT(DISTINCT year) as unique_years,
        COUNT(DISTINCT origin_state_fips) as unique_origin_states,
        COUNT(DISTINCT destination_state_fips) as unique_destination_states,
        SUM(migration_count) as total_migrations,
        AVG(avg_agi_per_return) as avg_agi_per_return
    FROM irs_migration_validation
)
SELECT 
    'IRS Migration Data Validation' as test_name,
    CASE 
        WHEN total_migration_records = 0 THEN 'FAIL: No IRS migration data found'
        WHEN valid_migration_records < total_migration_records * 0.90 THEN 'FAIL: IRS migration validation failed'
        WHEN unique_years < 3 THEN 'FAIL: Insufficient temporal coverage'
        ELSE 'PASS: IRS migration data valid'
    END as status,
    total_migration_records,
    valid_migration_records,
    invalid_fips_records,
    same_state_records,
    unique_years,
    unique_origin_states,
    unique_destination_states,
    total_migrations,
    ROUND(avg_agi_per_return, 0) as average_agi_per_return
FROM migration_stats;

-- Test 3: Population Estimates Consistency
-- Validates population estimates consistency across years and with ACS data
WITH pop_est_validation AS (
    SELECT 
        geoid,
        year,
        total_population,
        male_population,
        female_population,
        housing_units,
        CASE 
            WHEN total_population < 0 OR total_population > 10000000 THEN 'POPULATION_OUT_OF_RANGE'
            WHEN male_population < 0 OR female_population < 0 THEN 'INVALID_GENDER_POPULATION'
            WHEN (male_population + female_population) > total_population * 1.1 THEN 'GENDER_SUM_EXCEEDS_TOTAL'
            WHEN housing_units < 0 OR housing_units > total_population * 2 THEN 'HOUSING_UNITS_OUT_OF_RANGE'
            ELSE 'VALID'
        END as pop_est_validity
    FROM serving.population_estimates
),
pop_est_stats AS (
    SELECT 
        COUNT(*) as total_pop_est_records,
        COUNT(CASE WHEN pop_est_validity = 'VALID' THEN 1 END) as valid_pop_est_records,
        COUNT(CASE WHEN pop_est_validity LIKE 'INVALID%' THEN 1 END) as invalid_records,
        COUNT(DISTINCT year) as unique_years,
        AVG(total_population) as avg_population,
        MAX(total_population) as max_population,
        MIN(total_population) as min_population,
        AVG(housing_units) as avg_housing_units
    FROM pop_est_validation
)
SELECT 
    'Population Estimates Consistency' as test_name,
    CASE 
        WHEN total_pop_est_records = 0 THEN 'FAIL: No population estimate data found'
        WHEN valid_pop_est_records < total_pop_est_records * 0.98 THEN 'FAIL: Population estimates validation failed'
        ELSE 'PASS: Population estimates consistent'
    END as status,
    total_pop_est_records,
    valid_pop_est_records,
    invalid_records,
    unique_years,
    ROUND(avg_population, 0) as average_population,
    max_population,
    min_population,
    ROUND(avg_housing_units, 0) as average_housing_units
FROM pop_est_stats;

-- Test 4: Cross-Source Consistency Validation
-- Validates consistency between ACS, Population Estimates, and IRS data
WITH cross_source_validation AS (
    SELECT 
        acs.geoid,
        acs.year,
        acs.total_population as acs_population,
        pe.total_population as pop_est_population,
        CASE 
            WHEN acs.total_population IS NULL OR pe.total_population IS NULL THEN 'MISSING_DATA'
            WHEN ABS(acs.total_population - pe.total_population) / GREATEST(acs.total_population, pe.total_population) > 0.05 THEN 'LARGE_POPULATION_DIFFERENCE'
            WHEN acs.median_household_income < 0 OR acs.median_household_income > 500000 THEN 'INCOME_OUT_OF_RANGE'
            ELSE 'VALID'
        END as cross_source_validity
    FROM serving.acs_demographics acs
    JOIN serving.population_estimates pe ON acs.geoid = pe.geoid AND acs.year = pe.year
),
cross_source_stats AS (
    SELECT 
        COUNT(*) as total_cross_source_records,
        COUNT(CASE WHEN cross_source_validity = 'VALID' THEN 1 END) as valid_cross_source,
        COUNT(CASE WHEN cross_source_validity = 'LARGE_POPULATION_DIFFERENCE' THEN 1 END) as population_differences,
        COUNT(CASE WHEN cross_source_validity = 'MISSING_DATA' THEN 1 END) as missing_data_records,
        AVG(acs_population) as avg_acs_population,
        AVG(pop_est_population) as avg_pop_est_population,
        AVG(ABS(acs_population - pop_est_population)) as avg_population_difference
    FROM cross_source_validation
)
SELECT 
    'Cross-Source Consistency Validation' as test_name,
    CASE 
        WHEN total_cross_source_records = 0 THEN 'FAIL: No cross-source data for comparison'
        WHEN valid_cross_source < total_cross_source_records * 0.90 THEN 'FAIL: Cross-source consistency validation failed'
        ELSE 'PASS: Cross-source data consistent'
    END as status,
    total_cross_source_records,
    valid_cross_source,
    population_differences,
    missing_data_records,
    ROUND(avg_acs_population, 0) as average_acs_population,
    ROUND(avg_pop_est_population, 0) as average_pop_est_population,
    ROUND(avg_population_difference, 0) as average_population_difference
FROM cross_source_stats;

-- Test 5: Demographic Trend Calculation Validation
-- Validates demographic trend calculations and change detection
WITH demographic_trend_validation AS (
    SELECT 
        geoid,
        trend_period,  -- 1_year, 3_year, 5_year
        metric_name,
        trend_direction,  -- increasing, decreasing, stable
        change_percent,
        statistical_significance,
        CASE 
            WHEN trend_period NOT IN ('1_year', '3_year', '5_year') THEN 'INVALID_PERIOD'
            WHEN metric_name NOT IN ('population', 'income', 'age', 'education') THEN 'INVALID_METRIC'
            WHEN trend_direction NOT IN ('increasing', 'decreasing', 'stable') THEN 'INVALID_DIRECTION'
            WHEN change_percent < -100 OR change_percent > 100 THEN 'INVALID_PERCENTAGE'
            WHEN statistical_significance NOT IN ('significant', 'not_significant') THEN 'INVALID_SIGNIFICANCE'
            ELSE 'VALID'
        END as trend_validity
    FROM serving.demographic_trends
),
trend_stats AS (
    SELECT 
        COUNT(*) as total_trend_records,
        COUNT(CASE WHEN trend_validity = 'VALID' THEN 1 END) as valid_trend_records,
        COUNT(CASE WHEN trend_validity LIKE 'INVALID%' THEN 1 END) as invalid_trend_records,
        COUNT(DISTINCT trend_period) as unique_periods,
        COUNT(DISTINCT metric_name) as unique_metrics,
        COUNT(CASE WHEN trend_direction = 'increasing' THEN 1 END) as increasing_trends,
        COUNT(CASE WHEN trend_direction = 'decreasing' THEN 1 END) as decreasing_trends,
        COUNT(CASE WHEN trend_direction = 'stable' THEN 1 END) as stable_trends
    FROM demographic_trend_validation
)
SELECT 
    'Demographic Trend Calculation Validation' as test_name,
    CASE 
        WHEN total_trend_records = 0 THEN 'FAIL: No demographic trend data found'
        WHEN valid_trend_records < total_trend_records * 0.95 THEN 'FAIL: Demographic trend validation failed'
        WHEN unique_periods != 3 THEN 'FAIL: Incomplete trend period coverage'
        WHEN unique_metrics < 3 THEN 'FAIL: Insufficient metric coverage'
        ELSE 'PASS: Demographic trend calculation valid'
    END as status,
    total_trend_records,
    valid_trend_records,
    invalid_trend_records,
    unique_periods,
    unique_metrics,
    increasing_trends,
    decreasing_trends,
    stable_trends
FROM trend_stats;

-- Test 6: Housing and Economic Indicators Validation
-- Validates housing market indicators and economic data integration
WITH housing_economic_validation AS (
    SELECT 
        geoid,
        year,
        median_home_value,
        median_rent,
        homeownership_rate_pct,
        poverty_rate_pct,
        unemployment_rate_pct,
        CASE 
            WHEN median_home_value < 0 OR median_home_value > 10000000 THEN 'HOME_VALUE_OUT_OF_RANGE'
            WHEN median_rent < 0 OR median_rent > 10000 THEN 'RENT_OUT_OF_RANGE'
            WHEN homeownership_rate_pct < 0 OR homeownership_rate_pct > 100 THEN 'HOMEOWNERSHIP_OUT_OF_RANGE'
            WHEN poverty_rate_pct < 0 OR poverty_rate_pct > 100 THEN 'POVERTY_OUT_OF_RANGE'
            WHEN unemployment_rate_pct < 0 OR unemployment_rate_pct > 50 THEN 'UNEMPLOYMENT_OUT_OF_RANGE'
            ELSE 'VALID'
        END as housing_economic_validity
    FROM serving.housing_economic_indicators
),
housing_stats AS (
    SELECT 
        COUNT(*) as total_housing_records,
        COUNT(CASE WHEN housing_economic_validity = 'VALID' THEN 1 END) as valid_housing_records,
        COUNT(CASE WHEN housing_economic_validity LIKE '%OUT_OF_RANGE' THEN 1 END) as out_of_range_records,
        AVG(median_home_value) as avg_home_value,
        AVG(median_rent) as avg_rent,
        AVG(homeownership_rate_pct) as avg_homeownership_rate,
        AVG(poverty_rate_pct) as avg_poverty_rate,
        AVG(unemployment_rate_pct) as avg_unemployment_rate
    FROM housing_economic_validation
)
SELECT 
    'Housing and Economic Indicators Validation' as test_name,
    CASE 
        WHEN total_housing_records = 0 THEN 'FAIL: No housing/economic indicator data found'
        WHEN valid_housing_records < total_housing_records * 0.95 THEN 'FAIL: Housing/economic validation failed'
        ELSE 'PASS: Housing and economic indicators valid'
    END as status,
    total_housing_records,
    valid_housing_records,
    out_of_range_records,
    ROUND(avg_home_value, 0) as average_home_value,
    ROUND(avg_rent, 0) as average_rent,
    ROUND(avg_homeownership_rate, 1) as average_homeownership_rate,
    ROUND(avg_poverty_rate, 1) as average_poverty_rate,
    ROUND(avg_unemployment_rate, 1) as average_unemployment_rate
FROM housing_stats;

-- Test 7: Geographic Coverage Analysis
-- Validates geographic coverage completeness across different administrative levels
WITH geographic_coverage_validation AS (
    SELECT 
        CASE 
            WHEN LENGTH(geoid) = 2 THEN 'STATE'
            WHEN LENGTH(geoid) = 5 THEN 'COUNTY'
            WHEN LENGTH(geoid) BETWEEN 11 AND 12 THEN 'TRACT'
            WHEN LENGTH(geoid) = 7 THEN 'PLACE'
            ELSE 'OTHER'
        END as geographic_level,
        geoid,
        year,
        total_population,
        CASE 
            WHEN total_population IS NULL OR total_population <= 0 THEN 'NO_POPULATION'
            ELSE 'VALID'
        END as coverage_validity
    FROM serving.acs_demographics
),
coverage_stats AS (
    SELECT 
        geographic_level,
        COUNT(*) as total_records,
        COUNT(CASE WHEN coverage_validity = 'VALID' THEN 1 END) as valid_records,
        COUNT(DISTINCT year) as unique_years,
        SUM(total_population) as total_level_population,
        AVG(total_population) as avg_level_population
    FROM geographic_coverage_validation
    GROUP BY geographic_level
)
SELECT 
    'Geographic Coverage Analysis' as test_name,
    CASE 
        WHEN COUNT(*) = 0 THEN 'FAIL: No geographic coverage data'
        WHEN COUNT(CASE WHEN valid_records = 0 THEN 1 END) > 0 THEN 'FAIL: Some geographic levels have no valid data'
        ELSE 'PASS: Geographic coverage analysis valid'
    END as status,
    geographic_level,
    total_records,
    valid_records,
    unique_years,
    ROUND(total_level_population, 0) as total_population_by_level,
    ROUND(avg_level_population, 0) as average_population_by_geographic_unit
FROM coverage_stats
GROUP BY geographic_level, total_records, valid_records, unique_years, total_level_population, avg_level_population;

-- Test 8: Performance Test: Demographic Query Performance
-- Tests performance of complex demographic spatial queries
EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
SELECT 
    COUNT(*) as high_income_tracts,
    AVG(median_household_income) as avg_income,
    AVG(total_population) as avg_population,
    AVG(median_age) as avg_age
FROM serving.acs_demographics acs
JOIN serving.census_tracts ct ON acs.geoid = ct.geoid
WHERE acs.year = 2022
AND acs.median_household_income > 100000
AND acs.total_population > 1000
AND ST_Intersects(
    ct.geom,
    ST_MakeEnvelope(-125.0, 32.0, -114.0, 42.0, 4326)
);

-- Test 9: Comprehensive Neighborhood Trends Integration
-- Tests end-to-end integration of all demographic and economic data sources
WITH neighborhood_integration AS (
    SELECT 
        acs.geoid,
        acs.year,
        acs.total_population,
        acs.median_household_income,
        acs.education_bachelors_or_higher_pct,
        pe.total_population as pop_est_population,
        he.median_home_value,
        he.poverty_rate_pct,
        dt.trend_direction as population_trend,
        CASE 
            WHEN acs.total_population IS NULL THEN 'MISSING_ACS_POPULATION'
            WHEN pe.total_population IS NULL THEN 'MISSING_POP_EST_POPULATION'
            WHEN he.median_home_value IS NULL THEN 'MISSING_HOME_VALUE'
            WHEN dt.trend_direction IS NULL THEN 'MISSING_TREND_DATA'
            WHEN ABS(acs.total_population - pe.total_population) / GREATEST(acs.total_population, pe.total_population) > 0.05 THEN 'POPULATION_MISMATCH'
            ELSE 'VALID'
        END as integration_status
    FROM serving.acs_demographics acs
    LEFT JOIN serving.population_estimates pe ON acs.geoid = pe.geoid AND acs.year = pe.year
    LEFT JOIN serving.housing_economic_indicators he ON acs.geoid = he.geoid AND acs.year = he.year
    LEFT JOIN serving.demographic_trends dt ON acs.geoid = dt.geoid AND dt.metric_name = 'population' AND dt.trend_period = '3_year'
    WHERE acs.year = 2022
),
integration_stats AS (
    SELECT 
        COUNT(*) as total_integrated_records,
        COUNT(CASE WHEN integration_status = 'VALID' THEN 1 END) as fully_valid_records,
        COUNT(CASE WHEN integration_status LIKE 'MISSING%' THEN 1 END) as missing_data_records,
        COUNT(CASE WHEN integration_status = 'POPULATION_MISMATCH' THEN 1 END) as population_mismatches,
        AVG(median_household_income) as avg_integrated_income,
        AVG(education_bachelors_or_higher_pct) as avg_education,
        AVG(median_home_value) as avg_home_value,
        AVG(poverty_rate_pct) as avg_poverty_rate
    FROM neighborhood_integration
)
SELECT 
    'Comprehensive Neighborhood Trends Integration' as test_name,
    CASE 
        WHEN total_integrated_records = 0 THEN 'FAIL: No integrated neighborhood data'
        WHEN fully_valid_records < total_integrated_records * 0.80 THEN 'FAIL: Neighborhood integration validation failed'
        ELSE 'PASS: Comprehensive neighborhood trends integration successful'
    END as status,
    total_integrated_records,
    fully_valid_records,
    missing_data_records,
    population_mismatches,
    ROUND((fully_valid_records::FLOAT / NULLIF(total_integrated_records, 0)) * 100, 2) as integration_completeness_pct,
    ROUND(avg_integrated_income, 0) as average_integrated_income,
    ROUND(avg_education, 1) as average_education_percentage,
    ROUND(avg_home_value, 0) as average_home_value,
    ROUND(avg_poverty_rate, 1) as average_poverty_rate
FROM integration_stats;