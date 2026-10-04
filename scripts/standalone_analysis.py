#!/usr/bin/env python3
"""
Enhanced Standalone Survey Data Analysis Script
Wide-scope analysis with column overlap, PDF mapping, and year-based filtering.
"""

import sys
import json
import re
from pathlib import Path
from datetime import datetime
from collections import defaultdict, Counter
from typing import Dict, List, Any, Tuple, Set, Optional
import pandas as pd
import numpy as np
import uuid

# Add workspace directory to path to import our modules
sys.path.append(str(Path(__file__).parent))

from process_survey_data import SurveyDataProcessor

def process_xlsx_to_csv_with_enumeration(xlsx_path: str, output_dir: Optional[str] = None) -> Dict[str, Any]:
    """Process XLSX file: convert each sheet to CSV with enumeration and metadata."""
    xlsx_file = Path(xlsx_path)
    
    if not xlsx_file.exists():
        raise FileNotFoundError(f"XLSX file not found: {xlsx_path}")
    
    # Create output directory if not specified
    if output_dir is None:
        output_dir = str(xlsx_file.parent / f"{xlsx_file.stem}_processed")
    
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)
    
    try:
        # Read Excel file
        excel_file = pd.ExcelFile(xlsx_path)
        sheet_processing_results = []
        
        for sheet_name in excel_file.sheet_names:
            try:
                # Read sheet data
                df = pd.read_excel(xlsx_path, sheet_name=sheet_name)
                
                # Generate unique enumeration ID for this sheet
                sheet_id = str(uuid.uuid4())[:8]
                processing_timestamp = datetime.now().isoformat()
                
                # Create CSV filename with enumeration
                csv_filename = f"{xlsx_file.stem}_sheet_{sheet_name}_{sheet_id}.csv"
                csv_path = output_path / csv_filename
                
                # Save to CSV
                df.to_csv(csv_path, index=False)
                
                # Collect metadata
                sheet_metadata = {
                    'sheet_name': sheet_name,
                    'sheet_id': sheet_id,
                    'original_xlsx': str(xlsx_path),
                    'output_csv': str(csv_path),
                    'processing_timestamp': processing_timestamp,
                    'row_count': len(df),
                    'column_count': len(df.columns),
                    'columns': list(df.columns),
                    'file_size_csv': csv_path.stat().st_size if csv_path.exists() else 0,
                    'data_quality': {
                        'null_columns': df.isnull().sum().to_dict(),
                        'duplicate_rows': df.duplicated().sum(),
                        'memory_usage_mb': round(df.memory_usage(deep=True).sum() / 1024**2, 2)
                    }
                }
                
                sheet_processing_results.append(sheet_metadata)
                
                print(f"✅ Processed sheet '{sheet_name}' -> {csv_filename}")
                print(f"   Rows: {len(df):,}, Columns: {len(df.columns)}")
                
            except Exception as sheet_error:
                print(f"⚠️  Error processing sheet '{sheet_name}': {sheet_error}")
                sheet_processing_results.append({
                    'sheet_name': sheet_name,
                    'error': str(sheet_error),
                    'processing_timestamp': datetime.now().isoformat()
                })
        
        # Create processing summary
        processing_summary = {
            'xlsx_file': str(xlsx_path),
            'output_directory': output_dir,
            'processing_timestamp': datetime.now().isoformat(),
            'total_sheets': len(excel_file.sheet_names),
            'successfully_processed': len([r for r in sheet_processing_results if 'error' not in r]),
            'failed_sheets': len([r for r in sheet_processing_results if 'error' in r]),
            'sheet_results': sheet_processing_results,
            'enumeration_registry': {
                result['sheet_id']: {
                    'sheet_name': result['sheet_name'],
                    'csv_path': result.get('output_csv'),
                    'processing_timestamp': result['processing_timestamp']
                }
                for result in sheet_processing_results if 'error' not in result
            }
        }
        
        # Save processing manifest
        manifest_path = output_path / f"{xlsx_file.stem}_manifest.json"
        with open(manifest_path, 'w') as f:
            json.dump(processing_summary, f, indent=2, default=str)
        
        print(f"📋 Processing complete!")
        print(f"   Total sheets: {processing_summary['total_sheets']}")
        print(f"   Successfully processed: {processing_summary['successfully_processed']}")
        print(f"   Failed: {processing_summary['failed_sheets']}")
        print(f"   Manifest saved: {manifest_path}")
        
        return processing_summary
        
    except Exception as e:
        raise Exception(f"Failed to process XLSX file {xlsx_path}: {e}")

def batch_process_xlsx_files(directory_path: str, output_base_dir: Optional[str] = None) -> Dict[str, Any]:
    """Batch process all XLSX files in a directory."""
    dir_path = Path(directory_path)
    
    if not dir_path.exists() or not dir_path.is_dir():
        raise ValueError(f"Invalid directory: {directory_path}")
    
    # Find all XLSX files
    xlsx_files = list(dir_path.glob("**/*.xlsx"))
    
    if not xlsx_files:
        print(f"📁 No XLSX files found in {directory_path}")
        return {'processed_files': [], 'summary': {'total_files': 0, 'successful': 0, 'failed': 0}}
    
    if output_base_dir is None:
        output_base_dir = str(dir_path / "xlsx_processed_output")
    
    base_output_path = Path(output_base_dir)
    base_output_path.mkdir(exist_ok=True)
    
    batch_results = []
    successful_processing = 0
    failed_processing = 0
    
    print(f"🚀 Starting batch XLSX processing...")
    print(f"   Found {len(xlsx_files)} XLSX files")
    print(f"   Output directory: {output_base_dir}")
    
    for xlsx_file in xlsx_files:
        try:
            print(f"\n📊 Processing: {xlsx_file.name}")
            
            # Create specific output directory for this file
            file_output_dir = base_output_path / xlsx_file.stem
            
            # Process the XLSX file
            result = process_xlsx_to_csv_with_enumeration(str(xlsx_file), str(file_output_dir))
            
            batch_results.append(result)
            successful_processing += 1
            
        except Exception as e:
            print(f"❌ Failed to process {xlsx_file.name}: {e}")
            failed_processing += 1
            batch_results.append({
                'xlsx_file': str(xlsx_file),
                'error': str(e),
                'processing_timestamp': datetime.now().isoformat()
            })
    
    # Create batch summary
    batch_summary = {
        'batch_timestamp': datetime.now().isoformat(),
        'input_directory': directory_path,
        'output_base_directory': output_base_dir,
        'total_files_found': len(xlsx_files),
        'successfully_processed': successful_processing,
        'failed_processing': failed_processing,
        'processing_results': batch_results,
        'global_enumeration_index': {
            result['enumeration_registry']: result
            for result in batch_results if 'enumeration_registry' in result
        }
    }
    
    # Save batch manifest
    batch_manifest_path = base_output_path / "batch_processing_manifest.json"
    with open(batch_manifest_path, 'w') as f:
        json.dump(batch_summary, f, indent=2, default=str)
    
    print(f"\n🎉 Batch processing complete!")
    print(f"   Total files: {len(xlsx_files)}")
    print(f"   Successful: {successful_processing}")
    print(f"   Failed: {failed_processing}")
    print(f"   Batch manifest: {batch_manifest_path}")
    
    return batch_summary

def detect_geographic_level_and_geoid(df: pd.DataFrame) -> Dict[str, Any]:
    """Detect geographic level and identify GEOID columns in the dataset."""
    geoid_detection = {
        'detected_level': None,
        'geoid_columns': [],
        'confidence_scores': {},
        'alternative_geoid_candidates': [],
        'geographic_validation': {}
    }
    
    # Common GEOID column names and patterns
    geoid_patterns = {
        'state': {
            'patterns': [r'^STATEFP$', r'^STATE_FIPS$', r'^STATE$', r'^ST$'],
            'length': 2,
            'description': 'State FIPS code (2 digits)'
        },
        'county': {
            'patterns': [r'^COUNTYFP$', r'^COUNTY_FIPS$', r'^COUNTY$', r'^FIPS$'],
            'length': 5,
            'description': 'County FIPS code (5 digits: state + county)'
        },
        'tract': {
            'patterns': [r'^TRACTCE$', r'^TRACT$', r'^CENSUS_TRACT$', r'^TRACTCODE$'],
            'length': [6, 11],  # Can be 6-digit tract code or 11-digit GEOID
            'description': 'Census tract (6 digits) or full GEOID (11 digits)'
        },
        'block': {
            'patterns': [r'^BLOCKCE$', r'^BLOCK$', r'^CENSUS_BLOCK$'],
            'length': [4, 15],  # 4-digit block code or 15-digit full GEOID
            'description': 'Census block (4 digits) or full GEOID (15 digits)'
        },
        'place': {
            'patterns': [r'^PLACEFP$', r'^PLACE_FIPS$', r'^PLACE$', r'^CITY$'],
            'length': 7,
            'description': 'Place FIPS code (7 digits)'
        },
        'zcta': {
            'patterns': [r'^ZCTA$', r'^ZIP$', r'^ZIPCODE$', r'^ZIP_CODE$'],
            'length': 5,
            'description': 'ZIP Code Tabulation Area (5 digits)'
        }
    }
    
    columns = df.columns.tolist()
    detected_levels = []
    
    # Check each geographic level
    for geo_level, patterns_info in geoid_patterns.items():
        best_match = None
        best_score = 0
        
        for col in columns:
            col_upper = col.upper().strip()
            
            # Check against patterns
            for pattern in patterns_info['patterns']:
                if re.match(pattern, col_upper, re.IGNORECASE):
                    score = 100  # Direct match
                    
                    # Additional validation on actual data
                    if len(df[col].dropna()) > 0:
                        sample_values = df[col].dropna().astype(str)
                        sample_list = sample_values.head(100).tolist()
                        
                        # Check length consistency
                        if isinstance(patterns_info['length'], list):
                            length_match = any(len(val) in patterns_info['length'] for val in sample_list)
                        else:
                            length_match = all(len(val) == patterns_info['length'] for val in sample_list)
                        
                        if length_match:
                            score += 20
                        
                        # Check if values are numeric
                        numeric_count = sum(val.isdigit() for val in sample_list)
                        numeric_ratio = numeric_count / min(len(sample_list), 100) if sample_list else 0
                        if numeric_ratio > 0.9:
                            score += 10
                    
                    if score > best_score:
                        best_score = score
                        best_match = col
        
        if best_match:
            detected_levels.append({
                'level': geo_level,
                'column': best_match,
                'confidence': best_score,
                'description': patterns_info['description']
            })
            
            if best_score >= 80:  # High confidence match
                geoid_detection['geoid_columns'].append(best_match)
                geoid_detection['confidence_scores'][best_match] = best_score
            else:
                geoid_detection['alternative_geoid_candidates'].append({
                    'column': best_match,
                    'potential_level': geo_level,
                    'confidence': best_score
                })
    
    # Determine the most likely geographic level
    if detected_levels:
        detected_levels.sort(key=lambda x: x['confidence'], reverse=True)
        geoid_detection['detected_level'] = detected_levels[0]['level']
        
        # Validate consistency
        primary_geoid = detected_levels[0]['column']
        if len(df[primary_geoid].dropna()) > 0:
            unique_values = df[primary_geoid].nunique()
            total_rows = len(df)
            null_count = df[primary_geoid].isna().sum()
            sample_values = df[primary_geoid].dropna().astype(str).head(10).tolist()
            
            geoid_detection['geographic_validation'] = {
                'unique_geoids': unique_values,
                'total_rows': total_rows,
                'uniqueness_ratio': unique_values / total_rows if total_rows > 0 else 0,
                'null_count': int(null_count),
                'sample_values': sample_values
            }
    
    return geoid_detection

def detect_coordinate_columns(df: pd.DataFrame) -> Dict[str, Any]:
    """Detect latitude/longitude and other coordinate columns in the dataset."""
    coordinate_detection = {
        'latitude_columns': [],
        'longitude_columns': [],
        'geometry_columns': [],
        'coordinate_systems': {},
        'confidence_scores': {}
    }
    
    columns = df.columns.tolist()
    
    # Latitude patterns
    lat_patterns = [
        r'^LAT$', r'^LATITUDE$', r'^LAT_D$', r'^DEC_LAT$',
        r'^Y$', r'^Y_COORD$', r'^COORD_Y$', r'^INTPTLAT$'
    ]
    
    # Longitude patterns
    lon_patterns = [
        r'^LON$', r'^LONGITUDE$', r'^LNG$', r'^LONG$', r'^LON_D$',
        r'^X$', r'^X_COORD$', r'^COORD_X$', r'^INTPTLON$'
    ]
    
    # Geometry patterns (WKT, GeoJSON, etc.)
    geom_patterns = [
        r'^GEOM$', r'^GEOMETRY$', r'^SHAPE$', r'^POLYGON$', r'^POINT$',
        r'^WKT$', r'^GEOJSON$', r'^GEOM_WKT$'
    ]
    
    for col in columns:
        col_upper = col.upper().strip()
        
        # Check latitude patterns
        for pattern in lat_patterns:
            if re.match(pattern, col_upper, re.IGNORECASE):
                if len(df[col].dropna()) > 0:
                    # Validate coordinate ranges
                    try:
                        numeric_vals = pd.to_numeric(df[col].dropna(), errors='coerce')
                        if len(numeric_vals) > 0:
                            valid_lats = numeric_vals[(numeric_vals >= -90) & (numeric_vals <= 90)]
                            total_non_null = len(df[col].dropna())
                            
                            if len(valid_lats) > 0 and total_non_null > 0:
                                confidence = min(100, (len(valid_lats) / total_non_null) * 100)
                                coordinate_detection['latitude_columns'].append(col)
                                coordinate_detection['confidence_scores'][f'{col}_lat'] = confidence
                    except Exception:
                        pass
                break
        
        # Check longitude patterns
        for pattern in lon_patterns:
            if re.match(pattern, col_upper, re.IGNORECASE):
                if len(df[col].dropna()) > 0:
                    try:
                        numeric_vals = pd.to_numeric(df[col].dropna(), errors='coerce')
                        if len(numeric_vals) > 0:
                            valid_lons = numeric_vals[(numeric_vals >= -180) & (numeric_vals <= 180)]
                            total_non_null = len(df[col].dropna())
                            
                            if len(valid_lons) > 0 and total_non_null > 0:
                                confidence = min(100, (len(valid_lons) / total_non_null) * 100)
                                coordinate_detection['longitude_columns'].append(col)
                                coordinate_detection['confidence_scores'][f'{col}_lon'] = confidence
                    except Exception:
                        pass
                break
        
        # Check geometry patterns
        for pattern in geom_patterns:
            if re.match(pattern, col_upper, re.IGNORECASE):
                if len(df[col].dropna()) > 0:
                    sample_values = df[col].dropna().astype(str).head(10).tolist()
                    
                    # Look for WKT patterns
                    wkt_indicators = ['POINT(', 'POLYGON(', 'LINESTRING(', 'MULTI']
                    has_wkt = any(any(indicator in val.upper() for indicator in wkt_indicators) for val in sample_values)
                    
                    if has_wkt:
                        coordinate_detection['geometry_columns'].append(col)
                        coordinate_detection['confidence_scores'][f'{col}_geom'] = 85
                break
    
    # Determine coordinate system if we have lat/lon
    if coordinate_detection['latitude_columns'] and coordinate_detection['longitude_columns']:
        coordinate_detection['coordinate_systems'] = {
            'detected_system': 'WGS84',  # Default assumption
            'srid': 4326,
            'confidence': 90
        }
    
    return coordinate_detection

def transform_to_geographic_data_model(csv_path: str, output_dir: str = None) -> Dict[str, Any]:
    """Transform CSV data to postgres geographic data model format."""
    csv_file = Path(csv_path)
    
    if not csv_file.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")
    
    if output_dir is None:
        output_dir = str(csv_file.parent / f"{csv_file.stem}_geographic_transform")
    
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)
    
    # Read the CSV file
    df = pd.read_csv(csv_path)
    
    transformation_result = {
        'input_csv': str(csv_path),
        'output_directory': output_dir,
        'transformation_timestamp': datetime.now().isoformat(),
        'input_shape': {'rows': len(df), 'columns': len(df.columns)},
        'geographic_analysis': {},
        'transformed_tables': {},
        'sql_statements': {},
        'validation_results': {}
    }
    
    print(f"🔄 Transforming {csv_file.name} to geographic data model...")
    print(f"   Input shape: {len(df):,} rows x {len(df.columns)} columns")
    
    # Detect geographic information
    print("🔍 Analyzing geographic structure...")
    geoid_analysis = detect_geographic_level_and_geoid(df)
    coordinate_analysis = detect_coordinate_columns(df)
    
    transformation_result['geographic_analysis'] = {
        'geoid_detection': geoid_analysis,
        'coordinate_detection': coordinate_analysis
    }
    
    # Determine target table based on detected level
    target_table = None
    if geoid_analysis['detected_level']:
        level_mapping = {
            'state': 'serving.states',
            'county': 'serving.counties',
            'tract': 'serving.census_tracts',
            'place': 'serving.places',
            'zcta': 'serving.zip_codes'
        }
        target_table = level_mapping.get(geoid_analysis['detected_level'])
    
    print(f"📍 Detected geographic level: {geoid_analysis['detected_level']}")
    print(f"🎯 Target table: {target_table}")
    
    # Generate transformation based on what we detected
    if geoid_analysis['geoid_columns'] and target_table:
        primary_geoid_col = geoid_analysis['geoid_columns'][0]
        
        # Create transformed dataframe for geographic table
        geo_df = df.copy()
        
        # Standardize geoid column name
        geo_df = geo_df.rename(columns={primary_geoid_col: 'geoid'})
        
        # Add geometry if we have coordinates
        if coordinate_analysis['latitude_columns'] and coordinate_analysis['longitude_columns']:
            lat_col = coordinate_analysis['latitude_columns'][0]
            lon_col = coordinate_analysis['longitude_columns'][0]
            
            # Create point geometry
            geo_df['longitude'] = pd.to_numeric(geo_df[lon_col], errors='coerce')
            geo_df['latitude'] = pd.to_numeric(geo_df[lat_col], errors='coerce')
            
            # Filter for valid coordinates
            valid_mask = (
                (geo_df['latitude'] >= -90) & (geo_df['latitude'] <= 90) &
                (geo_df['longitude'] >= -180) & (geo_df['longitude'] <= 180)
            )
            geo_df = geo_df[valid_mask]
            
            print(f"📐 Created point geometries for {len(geo_df)} valid locations")
            
            # Generate SQL for PostGIS
            sql_create = f"""
-- Create table: {target_table}
CREATE TABLE IF NOT EXISTS {target_table} (
    geoid VARCHAR(15) PRIMARY KEY,
    geom GEOMETRY(POINT, 4326),
    latitude DECIMAL(10, 8),
    longitude DECIMAL(11, 8),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create spatial index
CREATE INDEX IF NOT EXISTS idx_{target_table.replace('.', '_')}_geom ON {target_table} USING GIST (geom);

-- Sample insert statement
INSERT INTO {target_table} (geoid, geom, latitude, longitude) VALUES
    (%s, ST_SetSRID(ST_MakePoint(longitude, latitude), 4326), %s, %s);
"""
            
            transformation_result['sql_statements']['create_table'] = sql_create
            
            # Save transformed data
            transformed_csv = output_path / f"{target_table.replace('.', '_')}.csv"
            geo_df[['geoid', 'latitude', 'longitude']].to_csv(transformed_csv, index=False)
            
            transformation_result['transformed_tables'][target_table] = {
                'csv_file': str(transformed_csv),
                'row_count': len(geo_df),
                'geometry_type': 'POINT',
                'srid': 4326
            }
            
        else:
            print("⚠️  No coordinate columns found - geometry not created")
    
    # Save transformation results
    result_file = output_path / f"transformation_result.json"
    with open(result_file, 'w') as f:
        json.dump(transformation_result, f, indent=2, default=str)
    
    print(f"✅ Transformation complete!")
    print(f"   Results saved to: {output_path}")
    print(f"   Transformation manifest: {result_file}")
    
    return transformation_result

def validate_geoid_patterns(geoid_series: pd.Series) -> Dict[str, Any]:
    """Comprehensive GEOID validation following census data standards."""
    validation_results = {
        'total_records': len(geoid_series),
        'null_count': geoid_series.isna().sum(),
        'unique_geoids': geoid_series.nunique(),
        'geoid_levels': {},
        'invalid_geoids': [],
        'validation_summary': {}
    }
    
    # Convert to string and clean
    geoids = geoid_series.dropna().astype(str).str.strip()
    
    # GEOID validation rules based on length and pattern
    geoid_rules = {
        'STATE': {
            'length': 2,
            'pattern': r'^[0-9]{2}$',
            'description': 'State FIPS code',
            'valid_range': (1, 56)
        },
        'COUNTY': {
            'length': 5,
            'pattern': r'^[0-9]{5}$',
            'description': 'County FIPS code (state + county)',
            'state_code_range': (1, 56),
            'county_code_range': (1, 999)
        },
        'PLACE': {
            'length': 7,
            'pattern': r'^[0-9]{5}[0-9]{2}$',
            'description': 'Place FIPS code',
            'state_code_range': (1, 56),
            'place_code_range': (1, 99)
        },
        'TRACT': {
            'length': 11,
            'pattern': r'^[0-9]{2}[0-9]{3}[0-9]{6}$',
            'description': 'Census tract GEOID (state + county + tract)',
            'state_code_range': (1, 56),
            'county_code_range': (1, 999),
            'tract_code_range': (1, 999999)
        },
        'BLOCK_GROUP': {
            'length': 12,
            'pattern': r'^[0-9]{2}[0-9]{3}[0-9]{6}[0-9]{1}$',
            'description': 'Block group GEOID',
            'block_group_range': (1, 9)
        },
        'BLOCK': {
            'length': 15,
            'pattern': r'^[0-9]{2}[0-9]{3}[0-9]{6}[0-9]{1}[0-9]{3}$',
            'description': 'Census block GEOID',
            'block_range': (0, 999)
        },
        'ZCTA': {
            'length': 5,
            'pattern': r'^[0-9]{5}$',
            'description': 'ZIP Code Tabulation Area',
            'zcta_range': (1001, 99950)
        }
    }
    
    # Classify GEOIDs by level
    for geoid in geoids:
        geoid_level = 'OTHER'
        is_valid = False
        validation_details = {}
        
        # Check each GEOID rule
        for level, rules in geoid_rules.items():
            if len(geoid) == rules['length'] and re.match(rules['pattern'], geoid):
                geoid_level = level
                
                # Validate components based on level
                if level == 'STATE':
                    state_code = int(geoid)
                    is_valid = rules['valid_range'][0] <= state_code <= rules['valid_range'][1]
                    validation_details = {
                        'state_code': state_code,
                        'within_range': is_valid
                    }
                
                elif level == 'COUNTY':
                    state_code = int(geoid[:2])
                    county_code = int(geoid[2:])
                    is_valid = (
                        rules['state_code_range'][0] <= state_code <= rules['state_code_range'][1] and
                        rules['county_code_range'][0] <= county_code <= rules['county_code_range'][1]
                    )
                    validation_details = {
                        'state_code': state_code,
                        'county_code': county_code,
                        'state_valid': rules['state_code_range'][0] <= state_code <= rules['state_code_range'][1],
                        'county_valid': rules['county_code_range'][0] <= county_code <= rules['county_code_range'][1]
                    }
                
                elif level == 'PLACE':
                    state_code = int(geoid[:2])
                    place_code = int(geoid[5:])
                    is_valid = (
                        rules['state_code_range'][0] <= state_code <= rules['state_code_range'][1] and
                        rules['place_code_range'][0] <= place_code <= rules['place_code_range'][1]
                    )
                    validation_details = {
                        'state_code': state_code,
                        'place_code': place_code,
                        'state_valid': rules['state_code_range'][0] <= state_code <= rules['state_code_range'][1],
                        'place_valid': rules['place_code_range'][0] <= place_code <= rules['place_code_range'][1]
                    }
                
                elif level == 'TRACT':
                    state_code = int(geoid[:2])
                    county_code = int(geoid[2:5])
                    tract_code = int(geoid[5:])
                    is_valid = (
                        rules['state_code_range'][0] <= state_code <= rules['state_code_range'][1] and
                        rules['county_code_range'][0] <= county_code <= rules['county_code_range'][1] and
                        tract_code > 0
                    )
                    validation_details = {
                        'state_code': state_code,
                        'county_code': county_code,
                        'tract_code': tract_code,
                        'components_valid': is_valid
                    }
                
                elif level in ['BLOCK_GROUP', 'BLOCK']:
                    state_code = int(geoid[:2])
                    county_code = int(geoid[2:5])
                    tract_code = int(geoid[5:11])
                    bg_code = int(geoid[11:12]) if level == 'BLOCK_GROUP' else int(geoid[11])
                    block_code = int(geoid[12:15]) if level == 'BLOCK' else None
                    
                    is_valid = (
                        rules['state_code_range'][0] <= state_code <= rules['state_code_range'][1] and
                        rules['county_code_range'][0] <= county_code <= rules['county_code_range'][1] and
                        tract_code > 0 and
                        0 <= bg_code <= 9
                    )
                    
                    validation_details = {
                        'state_code': state_code,
                        'county_code': county_code,
                        'tract_code': tract_code,
                        'block_group_code': bg_code,
                        'components_valid': is_valid
                    }
                    
                    if level == 'BLOCK':
                        block_valid = 0 <= block_code <= 999
                        is_valid = is_valid and block_valid
                        validation_details['block_code'] = block_code
                        validation_details['block_valid'] = block_valid
                
                elif level == 'ZCTA':
                    zcta_code = int(geoid)
                    is_valid = rules['zcta_range'][0] <= zcta_code <= rules['zcta_range'][1]
                    validation_details = {
                        'zcta_code': zcta_code,
                        'within_range': is_valid
                    }
                
                break
        
        # Count by level
        if geoid_level not in validation_results['geoid_levels']:
            validation_results['geoid_levels'][geoid_level] = {
                'count': 0,
                'valid_count': 0,
                'invalid_count': 0,
                'description': geoid_rules.get(geoid_level, {}).get('description', 'Other')
            }
        
        validation_results['geoid_levels'][geoid_level]['count'] += 1
        
        if is_valid:
            validation_results['geoid_levels'][geoid_level]['valid_count'] += 1
        else:
            validation_results['geoid_levels'][geoid_level]['invalid_count'] += 1
            validation_results['invalid_geoids'].append({
                'geoid': geoid,
                'detected_level': geoid_level,
                'validation_details': validation_details
            })
    
    # Calculate validation summary
    total_valid = sum(level['valid_count'] for level in validation_results['geoid_levels'].values())
    total_invalid = len(validation_results['invalid_geoids'])
    
    validation_results['validation_summary'] = {
        'total_valid': total_valid,
        'total_invalid': total_invalid,
        'validation_rate': (total_valid / len(geoids)) * 100 if len(geoids) > 0 else 0,
        'primary_level': max(validation_results['geoid_levels'].items(), 
                           key=lambda x: x[1]['count'])[0] if validation_results['geoid_levels'] else 'UNKNOWN',
        'levels_detected': list(validation_results['geoid_levels'].keys())
    }
    
    return validation_results

def generate_geographic_data_sql(transformed_data: Dict[str, Any]) -> Dict[str, str]:
    """Generate complete SQL statements for creating and populating geographic tables."""
    sql_statements = {
        'create_statements': {},
        'insert_statements': {},
        'index_statements': {},
        'validation_queries': {}
    }
    
    # Standard table schemas for geographic data
    table_schemas = {
        'serving.states': """
CREATE TABLE IF NOT EXISTS serving.states (
    geoid VARCHAR(2) PRIMARY KEY,
    name VARCHAR(100),
    geom GEOMETRY(MULTIPOLYGON, 4326),
    centroid GEOMETRY(POINT, 4326),
    area_sqkm DECIMAL(12, 4),
    population INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);""",
        
        'serving.counties': """
CREATE TABLE IF NOT EXISTS serving.counties (
    geoid VARCHAR(5) PRIMARY KEY,
    name VARCHAR(100),
    state_geoid VARCHAR(2) REFERENCES serving.states(geoid),
    geom GEOMETRY(MULTIPOLYGON, 4326),
    centroid GEOMETRY(POINT, 4326),
    area_sqkm DECIMAL(12, 4),
    population INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);""",
        
        'serving.census_tracts': """
CREATE TABLE IF NOT EXISTS serving.census_tracts (
    geoid VARCHAR(11) PRIMARY KEY,
    tract_code VARCHAR(6),
    county_geoid VARCHAR(5) REFERENCES serving.counties(geoid),
    state_geoid VARCHAR(2) REFERENCES serving.states(geoid),
    geom GEOMETRY(MULTIPOLYGON, 4326),
    centroid GEOMETRY(POINT, 4326),
    area_sqkm DECIMAL(12, 4),
    population INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);""",
        
        'serving.places': """
CREATE TABLE IF NOT EXISTS serving.places (
    geoid VARCHAR(7) PRIMARY KEY,
    name VARCHAR(100),
    state_geoid VARCHAR(2) REFERENCES serving.states(geoid),
    geom GEOMETRY(MULTIPOLYGON, 4326),
    centroid GEOMETRY(POINT, 4326),
    area_sqkm DECIMAL(12, 4),
    population INTEGER,
    place_type VARCHAR(20),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);""",
        
        'serving.zip_codes': """
CREATE TABLE IF NOT EXISTS serving.zip_codes (
    zcta VARCHAR(5) PRIMARY KEY,
    geom GEOMETRY(MULTIPOLYGON, 4326),
    centroid GEOMETRY(POINT, 4326),
    area_sqkm DECIMAL(12, 4),
    population INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);"""
    }
    
    # Generate create statements
    for table_name, schema in table_schemas.items():
        sql_statements['create_statements'][table_name] = schema
    
    # Generate spatial index statements
    index_statements = """
-- Spatial indexes for performance
CREATE INDEX IF NOT EXISTS idx_states_geom ON serving.states USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_counties_geom ON serving.counties USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_census_tracts_geom ON serving.census_tracts USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_places_geom ON serving.places USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_zip_codes_geom ON serving.zip_codes USING GIST (geom);

-- Non-spatial indexes
CREATE INDEX IF NOT EXISTS idx_counties_state ON serving.counties (state_geoid);
CREATE INDEX IF NOT EXISTS idx_tracts_county ON serving.census_tracts (county_geoid);
CREATE INDEX IF NOT EXISTS idx_tracts_state ON serving.census_tracts (state_geoid);
CREATE INDEX IF NOT EXISTS idx_places_state ON serving.places (state_geoid);
"""
    sql_statements['index_statements'] = index_statements
    
    # Generate validation queries (from the original SQL file)
    validation_queries = """
-- GEOID Format and Range Validation
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
    FROM serving.counties
)
SELECT 
    'GEOID Format and Range Validation' as test_name,
    COUNT(*) as total_geo_ids,
    COUNT(CASE WHEN geoid_validity LIKE 'VALID%' THEN 1 END) as valid_geo_ids,
    COUNT(CASE WHEN geoid_validity LIKE 'INVALID%' THEN 1 END) as invalid_geo_ids,
    ROUND((COUNT(CASE WHEN geoid_validity LIKE 'VALID%' THEN 1 END)::FLOAT / COUNT(*)) * 100, 2) as geoid_validity_pct
FROM geoid_validation;

-- Geometry Quality and Validity Checks
SELECT 
    'Geometry Quality and Validity Checks' as test_name,
    COUNT(*) as total_geometries,
    COUNT(CASE WHEN ST_IsValid(geom) THEN 1 END) as valid_geometries,
    COUNT(CASE WHEN ST_IsSimple(geom) THEN 1 END) as simple_geometries,
    COUNT(CASE WHEN NOT ST_IsValid(geom) THEN 1 END) as invalid_geometries
FROM serving.counties
LIMIT 1000;
"""
    sql_statements['validation_queries'] = validation_queries
    
    return sql_statements

def create_enumeration_system(processed_results: Dict[str, Any]) -> Dict[str, Any]:
    """Create a comprehensive enumeration system for tracking all processed sheets and transformations."""
    enumeration_system = {
        'global_registry': {},
        'processing_log': [],
        'transformation_chain': {},
        'quality_metrics': {},
        'enumeration_timestamp': datetime.now().isoformat()
    }
    
    # Process each result and create enumeration entries
    if 'processed_files' in processed_results:
        for file_result in processed_results['processed_files']:
            if 'enumeration_registry' in file_result:
                for sheet_id, sheet_info in file_result['enumeration_registry'].items():
                    enum_entry = {
                        'enumeration_id': str(uuid.uuid4())[:8],
                        'sheet_id': sheet_id,
                        'sheet_name': sheet_info['sheet_name'],
                        'csv_path': sheet_info['csv_path'],
                        'processing_timestamp': sheet_info['processing_timestamp'],
                        'source_file': file_result.get('xlsx_file', 'unknown'),
                        'status': 'processed',
                        'transformations_applied': [],
                        'quality_score': 0,
                        'geographic_validation': None
                    }
                    
                    enumeration_system['global_registry'][sheet_id] = enum_entry
                    enumeration_system['processing_log'].append({
                        'timestamp': sheet_info['processing_timestamp'],
                        'action': 'xlsx_processed',
                        'sheet_id': sheet_id,
                        'details': f"Processed sheet: {sheet_info['sheet_name']}"
                    })
    
    return enumeration_system

def run_enhanced_geographic_analysis(input_path: str, output_dir: str = None, 
                                  process_xlsx: bool = True, transform_to_pg: bool = True) -> Dict[str, Any]:
    """Main enhanced analysis function that combines XLSX processing and geographic transformation."""
    input_file = Path(input_path)
    
    if not input_file.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")
    
    if output_dir is None:
        output_dir = str(input_file.parent / f"{input_file.stem}_enhanced_analysis")
    
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)
    
    analysis_result = {
        'input_file': str(input_path),
        'output_directory': output_dir,
        'analysis_timestamp': datetime.now().isoformat(),
        'processing_steps': [],
        'enumeration_system': {},
        'final_results': {}
    }
    
    print(f"🚀 Starting Enhanced Geographic Analysis")
    print(f"   Input: {input_file.name}")
    print(f"   Output: {output_dir}")
    
    try:
        # Step 1: Process XLSX if needed
        if process_xlsx and input_file.suffix.lower() in ['.xlsx', '.xls']:
            print(f"\n📊 Step 1: Processing XLSX file...")
            
            xlsx_result = process_xlsx_to_csv_with_enumeration(str(input_file), str(output_path / "csv_output"))
            analysis_result['processing_steps'].append({
                'step': 1,
                'name': 'xlsx_processing',
                'status': 'completed',
                'result': xlsx_result
            })
            analysis_result['final_results']['xlsx_processing'] = xlsx_result
            
            # Create enumeration system
            enumeration = create_enumeration_system({'processed_files': [xlsx_result]})
            analysis_result['enumeration_system'] = enumeration
            
        # Step 2: Transform to geographic data model
        if transform_to_pg:
            print(f"\n🗺️  Step 2: Transforming to geographic data model...")
            
            # Get all CSV files from XLSX processing or use input if it's already CSV
            if input_file.suffix.lower() in ['.xlsx', '.xls']:
                csv_files = list((output_path / "csv_output").glob("*.csv"))
            else:
                csv_files = [input_file]
            
            transformation_results = []
            
            for csv_file in csv_files:
                print(f"   Transforming: {csv_file.name}")
                
                try:
                    transform_result = transform_to_geographic_data_model(
                        str(csv_file), 
                        str(output_path / "geographic_transform" / csv_file.stem)
                    )
                    transformation_results.append(transform_result)
                    
                except Exception as e:
                    print(f"   ⚠️  Transformation failed for {csv_file.name}: {e}")
                    transformation_results.append({
                        'csv_file': str(csv_file),
                        'error': str(e),
                        'timestamp': datetime.now().isoformat()
                    })
            
            analysis_result['processing_steps'].append({
                'step': 2,
                'name': 'geographic_transformation',
                'status': 'completed',
                'result': transformation_results
            })
            analysis_result['final_results']['geographic_transformation'] = transformation_results
        
        # Step 3: Generate SQL and validation scripts
        print(f"\n🔧 Step 3: Generating SQL scripts...")
        
        sql_scripts = {}
        if 'geographic_transformation' in analysis_result['final_results']:
            for transform_result in analysis_result['final_results']['geographic_transformation']:
                if 'geographic_analysis' in transform_result:
                    sql_scripts.update(generate_geographic_data_sql(transform_result))
        
        analysis_result['processing_steps'].append({
            'step': 3,
            'name': 'sql_generation',
            'status': 'completed',
            'result': 'sql_scripts_generated'
        })
        
        # Save SQL scripts
        sql_dir = output_path / "sql_scripts"
        sql_dir.mkdir(exist_ok=True)
        
        for script_name, script_content in sql_scripts.items():
            script_file = sql_dir / f"{script_name.replace('.', '_')}.sql"
            with open(script_file, 'w') as f:
                f.write(script_content)
        
        analysis_result['final_results']['sql_scripts'] = sql_scripts
        analysis_result['final_results']['sql_files'] = {name: str(sql_dir / f"{name.replace('.', '_')}.sql") for name in sql_scripts.keys()}
        
        # Step 4: Create comprehensive report
        print(f"\n📋 Step 4: Creating comprehensive report...")
        
        report = {
            'summary': {
                'input_file': str(input_path),
                'total_processing_steps': len(analysis_result['processing_steps']),
                'successful_steps': len([s for s in analysis_result['processing_steps'] if s['status'] == 'completed']),
                'enumeration_entries': len(analysis_result['enumeration_system'].get('global_registry', {})),
                'sql_scripts_generated': len(sql_scripts)
            },
            'processing_details': analysis_result['processing_steps'],
            'enumeration_system': analysis_result['enumeration_system'],
            'quality_metrics': {
                'processing_completion_rate': 100 if len(analysis_result['processing_steps']) > 0 else 0,
                'transformation_success_rate': 0
            }
        }
        
        # Calculate transformation success rate
        if 'geographic_transformation' in analysis_result['final_results']:
            transforms = analysis_result['final_results']['geographic_transformation']
            successful_transforms = len([t for t in transforms if 'error' not in t])
            total_transforms = len(transforms)
            if total_transforms > 0:
                report['quality_metrics']['transformation_success_rate'] = (successful_transforms / total_transforms) * 100
        
        # Save comprehensive report
        report_file = output_path / "comprehensive_analysis_report.json"
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2, default=str)
        
        analysis_result['final_results']['comprehensive_report'] = report
        
        print(f"\n🎉 Enhanced Geographic Analysis Complete!")
        print(f"   Report saved: {report_file}")
        print(f"   Processing steps: {len(analysis_result['processing_steps'])}")
        print(f"   Enumeration entries: {len(analysis_result['enumeration_system'].get('global_registry', {}))}")
        print(f"   SQL scripts: {len(sql_scripts)}")
        
        return analysis_result
        
    except Exception as e:
        print(f"❌ Analysis failed: {e}")
        analysis_result['error'] = str(e)
        analysis_result['status'] = 'failed'
        return analysis_result

def extract_years_from_path(file_path: str) -> Set[int]:
    """Extract years from file path and name."""
    years = set()
    path_str = str(file_path).upper()
    filename = Path(file_path).name.upper()
    
    # Common year patterns in census data
    year_patterns = [
        r'20(\d{2})',  # 20XX patterns
        r'19(\d{2})',  # 19XX patterns
        r'(\d{4})',    # 4-digit years
    ]
    
    # Check filename first
    for pattern in year_patterns:
        matches = re.findall(pattern, filename)
        for match in matches:
            year = int(match)
            if 1900 <= year <= 2030:  # Reasonable year range
                years.add(year)
    
    # Check full path if no years found in filename
    if not years:
        for pattern in year_patterns:
            matches = re.findall(pattern, path_str)
            for match in matches:
                year = int(match)
                if 1900 <= year <= 2030:
                    years.add(year)
    
    return years

def filter_files_by_year_range(files: List[Any], start_year: int, end_year: int) -> List[Any]:
    """Filter files by year range extracted from paths."""
    filtered_files = []
    
    for file_info in files:
        file_years = extract_years_from_path(file_info.path)
        
        # Include file if:
        # 1. It has years within the range, OR
        # 2. It has no years (assume it's relevant), OR  
        # 3. The file modification time is within range
        include_file = False
        
        if file_years:
            for year in file_years:
                if start_year <= year <= end_year:
                    include_file = True
                    break
        else:
            # Check modification time for files without explicit years
            mod_year = datetime.fromtimestamp(file_info.modified_time).year
            if start_year <= mod_year <= end_year:
                include_file = True
        
        if include_file:
            filtered_files.append(file_info)
    
    return filtered_files

def analyze_column_overlap(csv_analyses: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Analyze column overlap across multiple CSV files."""
    column_files = defaultdict(list)  # column -> list of files
    file_columns = {}  # file -> set of columns
    
    for analysis in csv_analyses:
        file_path = analysis.get('file_path', '')
        file_name = Path(file_path).name
        columns = analysis.get('columns', [])
        
        file_columns[file_name] = set(columns)
        
        for col in columns:
            column_files[col].append(file_name)
    
    # Calculate overlap statistics
    overlap_analysis = {
        'total_unique_columns': len(column_files),
        'total_files': len(csv_analyses),
        'column_frequency': {},
        'high_overlap_columns': [],
        'unique_columns': [],
        'common_columns': [],
        'file_similarity_matrix': {}
    }
    
    # Column frequency analysis
    for col, files in column_files.items():
        freq = len(files)
        overlap_analysis['column_frequency'][col] = {
            'frequency': freq,
            'files': files,
            'percentage': (freq / len(csv_analyses)) * 100
        }
    
    # Find high overlap columns (present in 50%+ of files)
    overlap_analysis['high_overlap_columns'] = [
        (col, info['frequency'], info['files'])
        for col, info in overlap_analysis['column_frequency'].items()
        if info['frequency'] >= len(csv_analyses) * 0.5
    ]
    overlap_analysis['high_overlap_columns'].sort(key=lambda x: x[1], reverse=True)
    
    # Find unique columns (present in only 1 file)
    overlap_analysis['unique_columns'] = [
        (col, info['files'][0])
        for col, info in overlap_analysis['column_frequency'].items()
        if info['frequency'] == 1
    ]
    
    # Find common columns (present in 80%+ of files)
    overlap_analysis['common_columns'] = [
        col for col, info in overlap_analysis['column_frequency'].items()
        if info['frequency'] >= len(csv_analyses) * 0.8
    ]
    
    # File similarity matrix (Jaccard similarity)
    file_list = list(file_columns.keys())
    for i, file1 in enumerate(file_list):
        overlap_analysis['file_similarity_matrix'][file1] = {}
        for j, file2 in enumerate(file_list):
            if i != j:
                set1, set2 = file_columns[file1], file_columns[file2]
                intersection = len(set1.intersection(set2))
                union = len(set1.union(set2))
                similarity = (intersection / union) * 100 if union > 0 else 0
                overlap_analysis['file_similarity_matrix'][file1][file2] = round(similarity, 1)
    
    return overlap_analysis

def enhance_pdf_column_mapping(processor, documents: List[Any], csv_columns: Set[str]) -> Dict[str, Any]:
    """Enhanced PDF-to-CSV column mapping with better key:value extraction."""
    mapping_results = {
        'extracted_mappings': {},
        'confidence_scores': {},
        'unmatched_columns': [],
        'potential_matches': [],
        'mapping_statistics': {}
    }
    
    # Extract enhanced column descriptions from all documents
    doc_descriptions = processor.extract_column_descriptions_from_docs(documents)
    
    # Enhanced pattern matching for better column mapping
    enhanced_patterns = [
        # Standard census patterns
        r'([A-Z][A-Z0-9_]+)[\s:=-]+\s*([^.\n\r]+)',
        r'Variable\s+([A-Z][A-Z0-9_]+)[\s:=-]+\s*([^.\n\r]+)',
        r'Column\s+([A-Z][A-Z0-9_]+)[\s:=-]+\s*([^.\n\r]+)',
        r'([A-Z]\d{5}_\d{3}[A-Z])[\s:=-]+\s*([^.\n\r]+)',
        r'([A-Z]{2,}\d*)[\s:=-]+\s*([^.\n\r]+)',
        
        # Table-style patterns
        r'\|\s*([A-Z][A-Z0-9_]*)\s*\|\s*([^|]+)\s*\|',
        r'([A-Z][A-Z0-9_]*)\s*\|\s*([^|\n\r]+)',
        
        # Definition patterns
        r'([A-Z][A-Z0-9_]+)\s*-\s*Definition[:\s]*([^.\n\r]+)',
        r'([A-Z][A-Z0-9_]+)\s*means[:\s]*([^.\n\r]+)',
        r'([A-Z][A-Z0-9_]+)\s*represents[:\s]*([^.\n\r]+)',
        
        # Parentheses explanations
        r'([A-Z][A-Z0-9_]+)\s*\(([^)]+)\)',
        
        # Equals sign patterns
        r'([A-Z][A-Z0-9_]+)\s*=\s*([^.\n\r]+)',
        
        # Bullet/list patterns
        r'•\s*([A-Z][A-Z0-9_]+):\s*([^.\n\r]+)',
        r'-\s*([A-Z][A-Z0-9_]+):\s*([^.\n\r]+)',
        r'\*\s*([A-Z][A-Z0-9_]+):\s*([^.\n\r]+)',
    ]
    
    # Process all document text with enhanced patterns
    all_extracted = {}
    
    for doc_info in documents:
        if doc_info.path in processor.document_cache:
            text = processor.document_cache[doc_info.path]
        else:
            text = processor.extract_document_text(doc_info.path)
            processor.document_cache[doc_info.path] = text
        
        # Apply all patterns
        for pattern in enhanced_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE | re.MULTILINE)
            for column, description in matches:
                column = column.upper().strip()
                description = re.sub(r'\s+', ' ', description.strip())
                description = description.rstrip('.')
                
                if len(column) >= 3 and len(description) > 5:
                    if column not in all_extracted:
                        all_extracted[column] = []
                    all_extracted[column].append(description)
    
    # Match extracted descriptions to CSV columns
    matched_columns = {}
    unmatched_columns = []
    
    for csv_col in csv_columns:
        csv_col_upper = csv_col.upper()
        best_match = None
        best_score = 0
        
        # Direct match
        if csv_col_upper in all_extracted:
            # Use the longest description for direct matches
            descriptions = all_extracted[csv_col_upper]
            best_desc = max(descriptions, key=len)
            best_match = best_desc
            best_score = 100
        
        # Partial match
        else:
            for extracted_col, descriptions in all_extracted.items():
                # Check if CSV column contains extracted pattern
                if extracted_col in csv_col_upper or csv_col_upper in extracted_col:
                    # Calculate similarity score
                    score = 0
                    if extracted_col in csv_col_upper:
                        score += 70
                    if csv_col_upper in extracted_col:
                        score += 50
                    
                    # Bonus for common prefixes/suffixes
                    if csv_col_upper.startswith(extracted_col[:3]):
                        score += 10
                    if csv_col_upper.endswith(extracted_col[-3:]):
                        score += 10
                    
                    if score > best_score:
                        best_score = score
                        best_match = max(descriptions, key=len)
        
        if best_match and best_score >= 60:
            matched_columns[csv_col] = {
                'description': best_match,
                'confidence': best_score,
                'source': 'extracted'
            }
        else:
            unmatched_columns.append(csv_col)
    
    mapping_results['extracted_mappings'] = matched_columns
    mapping_results['unmatched_columns'] = unmatched_columns
    mapping_results['confidence_scores'] = {
        col: info['confidence'] for col, info in matched_columns.items()
    }
    
    # Generate potential matches for unmatched columns
    for unmatched in unmatched_columns:
        potential = []
        for extracted_col, descriptions in all_extracted.items():
            # Calculate partial similarity
            similarity = 0
            for desc in descriptions:
                # Simple string similarity
                common_chars = set(unmatched.upper()) & set(extracted_col)
                if len(common_chars) > 3:
                    similarity = len(common_chars) / max(len(unmatched), len(extracted_col)) * 50
                    break
            
            if similarity > 20:
                potential.append({
                    'column': extracted_col,
                    'description': descriptions[0],
                    'similarity': similarity
                })
        
        if potential:
            potential.sort(key=lambda x: x['similarity'], reverse=True)
            mapping_results['potential_matches'].append({
                'csv_column': unmatched,
                'matches': potential[:3]
            })
    
    # Statistics
    mapping_results['mapping_statistics'] = {
        'total_csv_columns': len(csv_columns),
        'matched_columns': len(matched_columns),
        'unmatched_columns': len(unmatched_columns),
        'match_rate': round((len(matched_columns) / len(csv_columns)) * 100, 1) if csv_columns else 0,
        'high_confidence_matches': len([c for c, s in mapping_results['confidence_scores'].items() if s >= 80]),
        'average_confidence': round(sum(mapping_results['confidence_scores'].values()) / len(mapping_results['confidence_scores']), 1) if mapping_results['confidence_scores'] else 0
    }
    
    return mapping_results

def run_wide_scope_analysis(data_dir: Optional[str] = None, start_year: int = 2020, end_year: int = 2025, 
                          max_files: int = 50):
    """Run wide-scope analysis with enhanced features."""
    
    print(f"🔍 Starting WIDE SCOPE Survey Data Analysis ({start_year}-{end_year})")
    print("=" * 60)
    
    # Determine data directory
    if data_dir is None:
        current_file = Path(__file__).resolve()
        repo_root = current_file.parent.parent
        data_dir = str(repo_root / 'data')
    
    print(f"📁 Data Directory: {data_dir}")
    print(f"📅 Year Range: {start_year}-{end_year}")
    
    # Initialize processor
    processor = SurveyDataProcessor(data_dir)
    
    # Deep filesystem scan with year filtering
    print("\n🚀 Deep Filesystem Scan with Year Filtering...")
    found_files = processor.deep_scan_filesystem(max_depth=10)
    
    # Filter files by year range
    data_files = filter_files_by_year_range(found_files.get('data', []), start_year, end_year)
    document_files = filter_files_by_year_range(found_files.get('documents', []), start_year, end_year)
    
    print(f"📋 Year-Filtered Results:")
    print(f"   • Data files in range: {len(data_files)}")
    print(f"   • Document files in range: {len(document_files)}")
    print(f"   • Total files filtered: {len(found_files.get('data', [])) + len(found_files.get('documents', [])) - len(data_files) - len(document_files)}")
    
    # Limit files for analysis
    data_files_to_analyze = data_files[:max_files]
    document_files_to_analyze = document_files[:min(20, len(document_files))]  # Limit docs to 20
    
    print(f"📊 Analyzing {len(data_files_to_analyze)} data files and {len(document_files_to_analyze)} document files...")
    
    # Analyze CSV files
    csv_analyses = []
    all_columns = set()
    
    for i, file_info in enumerate(data_files_to_analyze):
        print(f"   Analyzing file {i+1}/{len(data_files_to_analyze)}: {Path(file_info.path).name}")
        analysis = processor.analyze_csv_structure(file_info.path, sample_size=1000)
        csv_analyses.append(analysis)
        all_columns.update(analysis.get('columns', []))
    
    print(f"\n📈 Column Overlap Analysis...")
    overlap_analysis = analyze_column_overlap(csv_analyses)
    
    print(f"\n📄 Enhanced PDF Column Mapping...")
    enhanced_mapping = enhance_pdf_column_mapping(processor, document_files_to_analyze, all_columns)
    
    # Compile comprehensive results
    results = {
        'analysis_metadata': {
            'timestamp': datetime.now().isoformat(),
            'year_range': f"{start_year}-{end_year}",
            'data_dir': data_dir,
            'total_files_scanned': len(data_files) + len(document_files),
            'files_analyzed': {
                'data_files': len(data_files_to_analyze),
                'document_files': len(document_files_to_analyze)
            }
        },
        'column_overlap_analysis': overlap_analysis,
        'enhanced_column_mapping': enhanced_mapping,
        'csv_analyses': csv_analyses[:5],  # Limit to 5 for JSON size
        'all_columns_count': len(all_columns) if csv_analyses else 0,
        'recommendations': []
    }
    
    # Display results
    print(f"\n📊 WIDE SCOPE ANALYSIS RESULTS")
    print("=" * 60)
    
    # Year filtering results
    analysis_meta = results['analysis_metadata']
    print(f"📅 Analysis Scope:")
    print(f"   • Year Range: {analysis_meta['year_range']}")
    print(f"   • Data Files Analyzed: {analysis_meta['files_analyzed']['data_files']}")
    print(f"   • Document Files Analyzed: {analysis_meta['files_analyzed']['document_files']}")
    print(f"   • Total Unique Columns: {analysis_meta.get('all_columns_count', 0)}")
    
    # Column overlap results
    overlap = results['column_overlap_analysis']
    print(f"\n🔗 Column Overlap Analysis:")
    print(f"   • Total Unique Columns: {overlap['total_unique_columns']}")
    print(f"   • Files Analyzed: {overlap['total_files']}")
    print(f"   • High Overlap Columns (50%+): {len(overlap['high_overlap_columns'])}")
    print(f"   • Common Columns (80%+): {len(overlap['common_columns'])}")
    print(f"   • Unique Columns (1 file only): {len(overlap['unique_columns'])}")
    
    if overlap['high_overlap_columns'][:10]:
        print(f"\n   📊 Top Overlap Columns:")
        for col, freq, files in overlap['high_overlap_columns'][:10]:
            print(f"      • {col}: {freq} files ({len(files)} listed)")
    
    # File similarity matrix (show top 5 files)
    sim_matrix = overlap['file_similarity_matrix']
    if sim_matrix:
        file_names = list(sim_matrix.keys())[:5]
        print(f"\n   📈 File Similarity Matrix (Top 5 Files):")
        print(f"      {'File':<30} {'Most Similar':<30} {'Similarity':<10}")
        for file1 in file_names:
            if file1 in sim_matrix:
                similarities = sim_matrix[file1]
                most_similar = max(similarities.items(), key=lambda x: x[1]) if similarities else ("N/A", 0)
                print(f"      {file1[:28]:<30} {most_similar[0][:28]:<30} {most_similar[1]:<10}%")
    
    # Enhanced mapping results
    mapping = results['enhanced_column_mapping']
    mapping_stats = mapping['mapping_statistics']
    print(f"\n📄 Enhanced PDF Column Mapping:")
    print(f"   • Total CSV Columns: {mapping_stats['total_csv_columns']}")
    print(f"   • Matched Columns: {mapping_stats['matched_columns']}")
    print(f"   • Unmatched Columns: {mapping_stats['unmatched_columns']}")
    print(f"   • Match Rate: {mapping_stats['match_rate']}%")
    print(f"   • High Confidence Matches: {mapping_stats['high_confidence_matches']}")
    print(f"   • Average Confidence: {mapping_stats['average_confidence']}")
    
    # Show best matched columns
    matched_cols = mapping['extracted_mappings']
    if matched_cols:
        high_conf_matches = [(col, info['description'], info['confidence']) 
                           for col, info in matched_cols.items() 
                           if info['confidence'] >= 80]
        high_conf_matches.sort(key=lambda x: x[2], reverse=True)
        
        if high_conf_matches[:15]:
            print(f"\n   🎯 High Confidence Matches (Top 15):")
            for col, desc, conf in high_conf_matches[:15]:
                print(f"      • {col} (Conf: {conf}%): {desc[:80]}...")
    
    # Show unmatched columns with potential matches
    potential_matches = mapping['potential_matches']
    if potential_matches[:5]:
        print(f"\n   🔍 Potential Matches for Unmatched Columns:")
        for pot in potential_matches[:5]:
            csv_col = pot['csv_column']
            best_match = pot['matches'][0] if pot['matches'] else None
            if best_match:
                print(f"      • {csv_col} → {best_match['column']} (Sim: {best_match['similarity']:.1f}%)")
    
    # CSV file summaries
    print(f"\n📈 CSV File Analysis Summary:")
    for i, analysis in enumerate(csv_analyses[:3]):
        file_name = Path(analysis.get('file_path', '')).name
        print(f"   📋 {i+1}. {file_name}")
        print(f"      • Rows: {analysis.get('total_rows', 0):,}")
        print(f"      • Columns: {analysis.get('total_columns', 0)}")
        print(f"      • File size: {analysis.get('file_size', 0):,} bytes")
        
        # Data quality summary
        data_quality = analysis.get('data_quality', {})
        if data_quality:
            completeness = data_quality.get('completeness', {})
            if completeness:
                avg_complete = sum(completeness.values()) / len(completeness)
                print(f"      • Avg data completeness: {avg_complete:.1f}%")
    
    # Generate recommendations
    recommendations = []
    
    if mapping_stats['match_rate'] < 50:
        recommendations.append("Consider adding more documentation files to improve column mapping")
    
    if overlap['total_unique_columns'] > overlap['total_files'] * 50:
        recommendations.append("High column diversity detected - consider standardization across datasets")
    
    if len(overlap['common_columns']) < 5:
        recommendations.append("Low column overlap detected - datasets may be from different survey types")
    
    if mapping_stats['high_confidence_matches'] < mapping_stats['matched_columns'] * 0.5:
        recommendations.append("Many low-confidence matches - review document quality and patterns")
    
    results['recommendations'] = recommendations
    
    if recommendations:
        print(f"\n💡 Recommendations:")
        for i, rec in enumerate(recommendations, 1):
            print(f"   {i}. {rec}")
    
    # Save comprehensive results to reports directory
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    # Get reports directory
    current_file = Path(__file__).resolve()
    repo_root = current_file.parent.parent
    reports_dir = repo_root / 'reports'
    reports_dir.mkdir(exist_ok=True)
    
    results_file = reports_dir / f"wide_scope_analysis_{start_year}_{end_year}_{timestamp}.json"
    
    print(f"\n💾 Saving comprehensive results to: {results_file}")
    
    try:
        # Convert results to JSON-serializable format
        def make_json_serializable(obj):
            if isinstance(obj, dict):
                return {k: make_json_serializable(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [make_json_serializable(item) for item in obj]
            elif isinstance(obj, (str, int, float, bool)) or obj is None:
                return obj
            else:
                return str(obj)
        
        json_results = make_json_serializable(results)
        
        with open(results_file, 'w', encoding='utf-8') as f:
            json.dump(json_results, f, indent=2, default=str)
            
        # Also create a summary CSV file
        summary_file = reports_dir / f"column_overlap_summary_{start_year}_{end_year}_{timestamp}.csv"
        with open(summary_file, 'w', encoding='utf-8') as f:
            f.write("Column,Frequency,Percentage,Files\n")
            for col, info in overlap['column_frequency'].items():
                files_str = "; ".join(info['files'][:5])  # Limit to 5 files per row
                f.write(f"{col},{info['frequency']},{info['percentage']:.1f},\"{files_str}\"\n")
        
        print(f"✅ Analysis complete! Results saved to:")
        print(f"   📄 {results_file}")
        print(f"   📊 {summary_file}")
        
    except Exception as e:
        print(f"⚠️  Error saving results: {e}")
    
    return results

def run_standalone_analysis(data_dir: Optional[str] = None, max_files: int = 5):
    """Legacy function - redirects to wide scope analysis."""
    return run_wide_scope_analysis(data_dir, 2020, 2025, max_files)

def quick_data_quality_check(csv_path: str):
    """Quick quality check for a single CSV file."""
    print(f"🔍 Quick Quality Check: {Path(csv_path).name}")
    
    processor = SurveyDataProcessor(str(Path(csv_path).parent.parent))
    analysis = processor.analyze_csv_structure(csv_path, sample_size=500)
    
    print(f"📊 Quality Metrics:")
    print(f"   • File size: {analysis.get('file_size', 0):,} bytes")
    print(f"   • Total rows: {analysis.get('total_rows', 0):,}")
    print(f"   • Total columns: {analysis.get('total_columns', 0)}")
    
    missing_values = analysis.get('missing_values', {})
    if missing_values:
        high_missing = [col for col, pct in missing_values.items() if pct > 20]
        if high_missing:
            print(f"   ⚠️  Columns with >20% missing values: {len(high_missing)}")
            for col in high_missing[:3]:
                print(f"      - {col}: {missing_values[col]:.1f}% missing")
    
    data_quality = analysis.get('data_quality', {})
    completeness = data_quality.get('completeness', {})
    if completeness:
        avg_complete = sum(completeness.values()) / len(completeness)
        print(f"   ✅ Average data completeness: {avg_complete:.1f}%")
    
    return analysis

def create_mapping_visualization(results: Dict[str, Any], timestamp: str):
    """Create visualization files for column mappings."""
    try:
        # Get reports directory
        current_file = Path(__file__).resolve()
        repo_root = current_file.parent.parent
        reports_dir = repo_root / 'reports'
        reports_dir.mkdir(exist_ok=True)
        
        # Create detailed CSV mapping file
        mapping_file = reports_dir / f"detailed_column_mapping_{timestamp}.csv"
        enhanced_mapping = results.get('enhanced_column_mapping', {})
        
        with open(mapping_file, 'w', encoding='utf-8') as f:
            f.write("CSV_Column,Description,Confidence,Source,Match_Type\n")
            
            # Matched columns
            for csv_col, info in enhanced_mapping.get('extracted_mappings', {}).items():
                f.write(f"{csv_col},\"{info['description']}\",{info['confidence']},{info['source']},Matched\n")
            
            # Unmatched columns with potential matches
            for pot in enhanced_mapping.get('potential_matches', []):
                csv_col = pot['csv_column']
                for match in pot['matches']:
                    f.write(f"{csv_col},\"{match['description']}\",{match['similarity']:.1f},Potential,Potential\n")
        
        # Create file similarity matrix CSV
        overlap = results.get('column_overlap_analysis', {})
        sim_matrix = overlap.get('file_similarity_matrix', {})
        sim_file = None
        
        if sim_matrix:
            sim_file = reports_dir / f"file_similarity_matrix_{timestamp}.csv"
            files = list(sim_matrix.keys())
            
            with open(sim_file, 'w', encoding='utf-8') as f:
                f.write("File1,File2,Similarity_Percent\n")
                for file1, similarities in sim_matrix.items():
                    for file2, similarity in similarities.items():
                        f.write(f"{file1},{file2},{similarity}\n")
        
        # Create column frequency analysis CSV
        freq_file = reports_dir / f"column_frequency_analysis_{timestamp}.csv"
        col_freq = overlap.get('column_frequency', {})
        
        with open(freq_file, 'w', encoding='utf-8') as f:
            f.write("Column,Frequency,Percentage,Files_Count,Sample_Files\n")
            for col, info in sorted(col_freq.items(), key=lambda x: x[1]['frequency'], reverse=True):
                files_list = info['files'][:3]  # Limit to 3 files
                files_str = "; ".join(files_list)
                f.write(f"{col},{info['frequency']},{info['percentage']:.1f},{len(info['files'])},\"{files_str}\"\n")
        
        print(f"📊 Visualization files created:")
        print(f"   📄 {mapping_file}")
        if 'sim_file' in locals():
            print(f"   📈 {sim_file}")
        print(f"   📊 {freq_file}")
        
    except Exception as e:
        print(f"⚠️  Error creating visualization files: {e}")

def main():
    """Main function for enhanced geographic analysis."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Enhanced Geographic Data Analysis')
    parser.add_argument('--data-dir', type=str, help='Data directory path')
    parser.add_argument('--csv-file', type=str, help='Single CSV file for quick quality check')
    parser.add_argument('--xlsx-file', type=str, help='Single XLSX file for enhanced geographic analysis')
    parser.add_argument('--input-file', type=str, help='Input file (XLSX or CSV) for enhanced geographic analysis')
    parser.add_argument('--output-dir', type=str, help='Output directory for processed files')
    parser.add_argument('--max-files', type=int, default=50, help='Maximum data files to analyze (default: 50)')
    parser.add_argument('--start-year', type=int, default=2020, help='Start year for filtering (default: 2020)')
    parser.add_argument('--end-year', type=int, default=2025, help='End year for filtering (default: 2025)')
    parser.add_argument('--wide-scope', action='store_true', help='Run wide scope analysis (legacy behavior)')
    parser.add_argument('--process-xlsx', action='store_true', help='Process XLSX files to CSV with enumeration')
    parser.add_argument('--transform-geo', action='store_true', help='Transform data to geographic data model')
    parser.add_argument('--batch-xlsx', type=str, help='Batch process all XLSX files in directory')
    
    args = parser.parse_args()
    
    try:
        # Enhanced geographic analysis (new primary functionality)
        if args.input_file:
            print("🚀 Running Enhanced Geographic Analysis")
            results = run_enhanced_geographic_analysis(
                args.input_file,
                args.output_dir,
                process_xlsx=args.process_xlsx,
                transform_to_pg=args.transform_geo
            )
            
        elif args.xlsx_file:
            print("📊 Processing Single XLSX File")
            results = run_enhanced_geographic_analysis(
                args.xlsx_file,
                args.output_dir,
                process_xlsx=True,
                transform_to_pg=True
            )
            
        elif args.batch_xlsx:
            print("📁 Batch Processing XLSX Files")
            results = batch_process_xlsx_files(args.batch_xlsx, args.output_dir)
            
        elif args.csv_file:
            print("🔍 Quick CSV Quality Check")
            quick_data_quality_check(args.csv_file)
            
        elif args.wide_scope:
            print("🌍 Running Wide Scope Analysis (Legacy)")
            # Run wide scope analysis with year filtering
            results = run_wide_scope_analysis(
                args.data_dir, 
                args.start_year, 
                args.end_year, 
                args.max_files
            )
            
            # Create visualization files
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            create_mapping_visualization(results, timestamp)
            
        else:
            # Default: enhanced analysis if no specific option provided
            print("🚀 Enhanced Geographic Analysis - Use --help for options")
            parser.print_help()
            return
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    main()