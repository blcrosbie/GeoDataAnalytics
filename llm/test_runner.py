#!/usr/bin/env python3
"""
Automated Test Runner for PostGIS ETL Pipeline
Executes SQL tests and provides comprehensive reporting and validation
"""

import os
import sys
import argparse
import logging
import json
import psycopg2
from psycopg2 import sql, extras
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Union
import pandas as pd
import subprocess
import time

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('test_runner.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class PostGISTestRunner:
    """Automated test runner for PostGIS ETL pipeline validation."""
    
    def __init__(self, db_connection_string: str, test_scripts_dir: Optional[str] = None):
        """
        Initialize the test runner.
        
        Args:
            db_connection_string: PostgreSQL connection string
            test_scripts_dir: Directory containing SQL test scripts
        """
        self.db_connection_string = db_connection_string
        self.test_scripts_dir = test_scripts_dir or os.path.dirname(__file__) or '.'
        self.connection: Optional[psycopg2.extensions.connection] = None
        self.test_results: List[Dict[str, Any]] = []
        self.execution_summary: Dict[str, Any] = {}
        
        # Define test categories and their corresponding script files
        self.test_categories = {
            'FLOOD': 'test_flood_exposure.sql',
            'WEATHER': 'test_weather_extreme_rain.sql',
            'HEAT': 'test_heat_sun_wind.sql',
            'AIR_QUALITY': 'test_air_quality_ghg.sql',
            'CENSUS': 'test_neighborhood_trends.sql',
            'VALIDATION': 'test_geographic_validation.sql',
            'PERFORMANCE': 'test_vectorization_mvt_performance.sql'
        }
        
        # Performance thresholds (in milliseconds)
        self.performance_thresholds = {
            'FAST': 1000,      # 1 second
            'MEDIUM': 5000,    # 5 seconds
            'SLOW': 30000      # 30 seconds
        }
    
    def connect_to_database(self) -> bool:
        """Establish database connection."""
        try:
            self.connection = psycopg2.connect(self.db_connection_string)
            self.connection.autocommit = False
            logger.info("Successfully connected to database")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            return False
    
    def setup_test_environment(self) -> bool:
        """Initialize test environment with schema and fixtures."""
        if not self.connection:
            logger.error("No database connection available")
            return False
            
        try:
            with self.connection.cursor() as cursor:
                # Load test framework schema
                framework_schema_file = os.path.join(self.test_scripts_dir, 'test_framework_schema.sql')
                if os.path.exists(framework_schema_file):
                    with open(framework_schema_file, 'r') as f:
                        cursor.execute(f.read())
                    logger.info("Test framework schema loaded")
                
                # Load test data fixtures
                fixtures_file = os.path.join(self.test_scripts_dir, 'test_data_fixtures.sql')
                if os.path.exists(fixtures_file):
                    with open(fixtures_file, 'r') as f:
                        cursor.execute(f.read())
                    logger.info("Test data fixtures loaded")
                
                self.connection.commit()
                logger.info("Test environment setup completed successfully")
                return True
                
        except Exception as e:
            logger.error(f"Failed to setup test environment: {e}")
            if self.connection:
                self.connection.rollback()
            return False
    
    def execute_sql_script(self, script_path: str) -> List[Dict[str, Any]]:
        """
        Execute a SQL test script and return results.
        
        Args:
            script_path: Path to SQL script file
            
        Returns:
            List of test results
        """
        if not os.path.exists(script_path):
            logger.error(f"Test script not found: {script_path}")
            return []
        
        if not self.connection:
            logger.error("No database connection available")
            return []
            
        test_results: List[Dict[str, Any]] = []
        
        try:
            with self.connection.cursor() as cursor:
                with open(script_path, 'r') as f:
                    sql_content = f.read()
                
                # Split script into individual test queries (assuming they end with semicolons)
                test_queries = [q.strip() for q in sql_content.split(';') if q.strip() and not q.strip().startswith('--')]
                
                for i, query in enumerate(test_queries, 1):
                    if not query or query.startswith('EXPLAIN'):
                        continue
                    
                    start_time = time.time()
                    
                    try:
                        cursor.execute(query)
                        results = cursor.fetchall()
                        execution_time = (time.time() - start_time) * 1000  # Convert to milliseconds
                        
                        # Parse results assuming they return test_name, status, and other columns
                        for row in results:
                            if len(row) >= 2:
                                test_result = {
                                    'test_name': row[0] if row[0] is not None else f'Query_{i}_{os.path.basename(script_path)}',
                                    'status': row[1] if row[1] is not None else 'UNKNOWN',
                                    'execution_time_ms': round(execution_time, 2),
                                    'execution_timestamp': datetime.now(timezone.utc).isoformat(),
                                    'script_file': os.path.basename(script_path),
                                    'query_number': i,
                                    'raw_results': row[2:] if len(row) > 2 else []
                                }
                                test_results.append(test_result)
                                
                    except Exception as query_error:
                        execution_time = (time.time() - start_time) * 1000
                        error_result = {
                            'test_name': f'Query_{i}_{os.path.basename(script_path)}',
                            'status': 'ERROR',
                            'execution_time_ms': round(execution_time, 2),
                            'execution_timestamp': datetime.now(timezone.utc).isoformat(),
                            'script_file': os.path.basename(script_path),
                            'query_number': i,
                            'error_message': str(query_error),
                            'raw_results': []
                        }
                        test_results.append(error_result)
                        logger.error(f"Query {i} in {script_path} failed: {query_error}")
                
                self.connection.commit()
                logger.info(f"Executed {len(test_queries)} queries from {script_path}")
                
        except Exception as e:
            logger.error(f"Failed to execute script {script_path}: {e}")
            if self.connection:
                self.connection.rollback()
        
        return test_results
    
    def run_all_tests(self) -> Dict[str, Any]:
        """Run all configured test categories."""
        logger.info("Starting comprehensive test execution")
        
        all_results: List[Dict[str, Any]] = []
        category_results: Dict[str, List[Dict[str, Any]]] = {}
        
        for category, script_file in self.test_categories.items():
            logger.info(f"Running {category} tests from {script_file}")
            
            script_path = os.path.join(self.test_scripts_dir, script_file)
            if not os.path.exists(script_path):
                logger.warning(f"Script file not found for category {category}: {script_file}")
                continue
            
            category_test_results = self.execute_sql_script(script_path)
            
            # Add category information to each result
            for result in category_test_results:
                result['category'] = category
            
            all_results.extend(category_test_results)
            category_results[category] = category_test_results
            
            logger.info(f"Completed {category} tests: {len(category_test_results)} tests executed")
        
        self.test_results = all_results
        self.execution_summary = self.generate_execution_summary(all_results, category_results)
        
        logger.info("All test execution completed")
        return self.execution_summary
    
    def run_category_tests(self, category: str) -> List[Dict[str, Any]]:
        """Run tests for a specific category."""
        if category not in self.test_categories:
            logger.error(f"Unknown test category: {category}")
            return []
        
        script_file = self.test_categories[category]
        script_path = os.path.join(self.test_scripts_dir, script_file)
        
        logger.info(f"Running {category} tests from {script_file}")
        
        test_results = self.execute_sql_script(script_path)
        
        # Add category information
        for result in test_results:
            result['category'] = category
        
        logger.info(f"Completed {category} tests: {len(test_results)} tests executed")
        return test_results
    
    def generate_execution_summary(self, all_results: List[Dict], category_results: Dict[str, List[Dict]]) -> Dict[str, Any]:
        """Generate comprehensive execution summary."""
        total_tests = len(all_results)
        passed_tests = len([r for r in all_results if r.get('status') == 'PASS'])
        failed_tests = len([r for r in all_results if r.get('status') == 'FAIL'])
        error_tests = len([r for r in all_results if r.get('status') == 'ERROR'])
        
        execution_times = [r.get('execution_time_ms', 0) for r in all_results]
        avg_execution_time = sum(execution_times) / len(execution_times) if execution_times else 0
        max_execution_time = max(execution_times) if execution_times else 0
        
        summary = {
            'execution_timestamp': datetime.now(timezone.utc).isoformat(),
            'total_tests': total_tests,
            'passed_tests': passed_tests,
            'failed_tests': failed_tests,
            'error_tests': error_tests,
            'success_rate': round((passed_tests / total_tests * 100) if total_tests > 0 else 0, 2),
            'average_execution_time_ms': round(avg_execution_time, 2),
            'max_execution_time_ms': round(max_execution_time, 2),
            'category_breakdown': {},
            'failed_tests_details': [r for r in all_results if r.get('status') in ['FAIL', 'ERROR']],
            'performance_summary': self.generate_performance_summary(all_results)
        }
        
        # Category breakdown
        for category, results in category_results.items():
            category_passed = len([r for r in results if r.get('status') == 'PASS'])
            category_total = len(results)
            summary['category_breakdown'][category] = {
                'total': category_total,
                'passed': category_passed,
                'failed': category_total - category_passed,
                'success_rate': round((category_passed / category_total * 100) if category_total > 0 else 0, 2)
            }
        
        return summary
    
    def generate_performance_summary(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate performance analysis summary."""
        execution_times = [r.get('execution_time_ms', 0) for r in results]
        
        fast_tests = len([t for t in execution_times if t <= self.performance_thresholds['FAST']])
        medium_tests = len([t for t in execution_times if 
                           self.performance_thresholds['FAST'] < t <= self.performance_thresholds['MEDIUM']])
        slow_tests = len([t for t in execution_times if 
                         self.performance_thresholds['MEDIUM'] < t <= self.performance_thresholds['SLOW']])
        very_slow_tests = len([t for t in execution_times if t > self.performance_thresholds['SLOW']])
        
        return {
            'fast_tests': fast_tests,
            'medium_tests': medium_tests,
            'slow_tests': slow_tests,
            'very_slow_tests': very_slow_tests,
            'average_time_ms': round(sum(execution_times) / len(execution_times), 2) if execution_times else 0,
            'median_time_ms': round(sorted(execution_times)[len(execution_times) // 2] if execution_times else 0, 2),
            'max_time_ms': max(execution_times) if execution_times else 0,
            'min_time_ms': min(execution_times) if execution_times else 0
        }
    
    def save_results_to_database(self) -> bool:
        """Save test execution results to database."""
        if not self.connection:
            logger.error("No database connection available")
            return False
            
        try:
            with self.connection.cursor() as cursor:
                for result in self.test_results:
                    # Get test config ID
                    cursor.execute(
                        "SELECT id FROM test_framework.test_config WHERE test_name = %s",
                        (result['test_name'],)
                    )
                    config_result = cursor.fetchone()
                    config_id = config_result[0] if config_result else None
                    
                    if config_id:
                        # Log test execution
                        cursor.execute("""
                            INSERT INTO test_framework.test_execution_log 
                            (test_config_id, status, execution_time_ms, rows_returned, error_message, test_output)
                            VALUES (%s, %s, %s, %s, %s, %s)
                        """, (
                            config_id,
                            result['status'],
                            result.get('execution_time_ms', 0),
                            len(result.get('raw_results', [])),
                            result.get('error_message'),
                            json.dumps(result.get('raw_results', []))
                        ))
                
                self.connection.commit()
                logger.info("Test results saved to database")
                return True
                
        except Exception as e:
            logger.error(f"Failed to save results to database: {e}")
            if self.connection:
                self.connection.rollback()
            return False
    
    def generate_html_report(self, output_file: Optional[str] = None) -> str:
        """Generate HTML test report."""
        if not output_file:
            output_file = f"test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        
        html_template = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>PostGIS ETL Test Report</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                .header {{ background: #f0f0f0; padding: 20px; border-radius: 5px; }}
                .summary {{ margin: 20px 0; }}
                .passed {{ color: green; }}
                .failed {{ color: red; }}
                .error {{ color: orange; }}
                table {{ border-collapse: collapse; width: 100%; }}
                th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
                th {{ background-color: #f2f2f2; }}
                .category-section {{ margin: 20px 0; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>PostGIS ETL Pipeline Test Report</h1>
                <p>Generated: {execution_timestamp}</p>
            </div>
            
            <div class="summary">
                <h2>Execution Summary</h2>
                <p>Total Tests: {total_tests}</p>
                <p class="passed">Passed: {passed_tests}</p>
                <p class="failed">Failed: {failed_tests}</p>
                <p class="error">Errors: {error_tests}</p>
                <p>Success Rate: {success_rate}%</p>
                <p>Average Execution Time: {average_execution_time_ms}ms</p>
            </div>
            
            <div class="category-breakdown">
                <h2>Category Breakdown</h2>
                {category_table}
            </div>
            
            <div class="performance-summary">
                <h2>Performance Summary</h2>
                <p>Fast Tests (&lt;1s): {fast_tests}</p>
                <p>Medium Tests (1-5s): {medium_tests}</p>
                <p>Slow Tests (5-30s): {slow_tests}</p>
                <p>Very Slow Tests (&gt;30s): {very_slow_tests}</p>
                <p>Max Execution Time: {max_time_ms}ms</p>
            </div>
            
            <div class="failed-tests">
                <h2>Failed Tests</h2>
                {failed_tests_table}
            </div>
        </body>
        </html>
        """
        
        # Generate category table
        category_rows = ""
        for category, stats in self.execution_summary.get('category_breakdown', {}).items():
            category_rows += f"""
            <tr>
                <td>{category}</td>
                <td>{stats['total']}</td>
                <td>{stats['passed']}</td>
                <td>{stats['failed']}</td>
                <td>{stats['success_rate']}%</td>
            </tr>
            """
        
        category_table = f"""
        <table>
            <tr>
                <th>Category</th>
                <th>Total</th>
                <th>Passed</th>
                <th>Failed</th>
                <th>Success Rate</th>
            </tr>
            {category_rows}
        </table>
        """
        
        # Generate failed tests table
        failed_rows = ""
        for test in self.execution_summary.get('failed_tests_details', []):
            failed_rows += f"""
            <tr>
                <td>{test.get('test_name', 'Unknown')}</td>
                <td>{test.get('category', 'Unknown')}</td>
                <td class="{test.get('status', 'unknown').lower()}">{test.get('status', 'Unknown')}</td>
                <td>{test.get('execution_time_ms', 0)}ms</td>
                <td>{test.get('error_message', 'N/A')}</td>
            </tr>
            """
        
        failed_tests_table = f"""
        <table>
            <tr>
                <th>Test Name</th>
                <th>Category</th>
                <th>Status</th>
                <th>Execution Time</th>
                <th>Error Message</th>
            </tr>
            {failed_rows}
        </table>
        """ if failed_rows else "<p>No failed tests!</p>"
        
        perf_summary = self.execution_summary.get('performance_summary', {})
        
        html_content = html_template.format(
            execution_timestamp=self.execution_summary.get('execution_timestamp', 'Unknown'),
            total_tests=self.execution_summary.get('total_tests', 0),
            passed_tests=self.execution_summary.get('passed_tests', 0),
            failed_tests=self.execution_summary.get('failed_tests', 0),
            error_tests=self.execution_summary.get('error_tests', 0),
            success_rate=self.execution_summary.get('success_rate', 0),
            average_execution_time_ms=self.execution_summary.get('average_execution_time_ms', 0),
            category_table=category_table,
            fast_tests=perf_summary.get('fast_tests', 0),
            medium_tests=perf_summary.get('medium_tests', 0),
            slow_tests=perf_summary.get('slow_tests', 0),
            very_slow_tests=perf_summary.get('very_slow_tests', 0),
            max_time_ms=perf_summary.get('max_time_ms', 0),
            failed_tests_table=failed_tests_table
        )
        
        with open(output_file, 'w') as f:
            f.write(html_content)
        
        logger.info(f"HTML report generated: {output_file}")
        return output_file
    
    def generate_json_report(self, output_file: Optional[str] = None) -> str:
        """Generate JSON test report."""
        if not output_file:
            output_file = f"test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        report_data = {
            'execution_summary': self.execution_summary,
            'detailed_results': self.test_results,
            'generation_timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        with open(output_file, 'w') as f:
            json.dump(report_data, f, indent=2, default=str)
        
        logger.info(f"JSON report generated: {output_file}")
        return output_file
    
    def cleanup(self):
        """Clean up database connection."""
        if self.connection:
            self.connection.close()
            logger.info("Database connection closed")

def main():
    """Main function to run test runner from command line."""
    parser = argparse.ArgumentParser(description='PostGIS ETL Test Runner')
    parser.add_argument('--connection', required=True, help='PostgreSQL connection string')
    parser.add_argument('--scripts-dir', help='Directory containing test SQL scripts')
    parser.add_argument('--category', help='Run specific test category only')
    parser.add_argument('--output-dir', default='.', help='Output directory for reports')
    parser.add_argument('--html-report', action='store_true', help='Generate HTML report')
    parser.add_argument('--json-report', action='store_true', help='Generate JSON report')
    parser.add_argument('--save-to-db', action='store_true', help='Save results to database')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose logging')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Initialize test runner
    runner = PostGISTestRunner(args.connection, args.scripts_dir)
    
    try:
        # Connect to database
        if not runner.connect_to_database():
            logger.error("Failed to connect to database. Exiting.")
            sys.exit(1)
        
        # Setup test environment
        if not runner.setup_test_environment():
            logger.error("Failed to setup test environment. Exiting.")
            sys.exit(1)
        
        # Run tests
        if args.category:
            results = runner.run_category_tests(args.category)
            runner.test_results = results
            runner.execution_summary = runner.generate_execution_summary(results, {args.category: results})
        else:
            runner.run_all_tests()
        
        # Generate reports
        if args.html_report:
            html_file = os.path.join(args.output_dir, f"test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html")
            runner.generate_html_report(html_file)
        
        if args.json_report:
            json_file = os.path.join(args.output_dir, f"test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
            runner.generate_json_report(json_file)
        
        # Save to database if requested
        if args.save_to_db:
            runner.save_results_to_database()
        
        # Print summary
        summary = runner.execution_summary
        print(f"\n{'='*50}")
        print("TEST EXECUTION SUMMARY")
        print(f"{'='*50}")
        print(f"Total Tests: {summary.get('total_tests', 0)}")
        print(f"Passed: {summary.get('passed_tests', 0)}")
        print(f"Failed: {summary.get('failed_tests', 0)}")
        print(f"Errors: {summary.get('error_tests', 0)}")
        print(f"Success Rate: {summary.get('success_rate', 0)}%")
        print(f"Avg Execution Time: {summary.get('average_execution_time_ms', 0)}ms")
        print(f"{'='*50}")
        
        # Exit with appropriate code
        failed_count = summary.get('failed_tests', 0) + summary.get('error_tests', 0)
        sys.exit(1 if failed_count > 0 else 0)
    
    except KeyboardInterrupt:
        logger.info("Test execution interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error during test execution: {e}")
        sys.exit(1)
    finally:
        runner.cleanup()

if __name__ == "__main__":
    main()