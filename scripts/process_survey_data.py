#!/usr/bin/env python3
"""
Enhanced Census Survey Data Processor
Processes downloaded survey data with OCR analysis for PDF/DOC documentation,
deep filesystem traversal, and comprehensive column mapping for RAG/Vector DB usage.
"""

import os
import pandas as pd
import json
import re
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
import zipfile
import csv
import logging
from dataclasses import dataclass
from collections import defaultdict
import geopandas as gpd
import numpy as np
from shapely.geometry import Point, Polygon

# OCR and document processing imports
try:
    import PyPDF2
    import pdfplumber
    import pytesseract
    from PIL import Image
    import docx
    OCR_AVAILABLE = True
except ImportError as e:
    OCR_AVAILABLE = False
    print(f"OCR libraries not available: {e}")

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class FileInfo:
    path: str
    type: str
    size: int
    modified_time: float
    
@dataclass
class ColumnInfo:
    name: str
    data_type: str
    description: str
    source_file: str
    sample_values: List[str]
    null_count: int = 0

@dataclass
class GeographicMatch:
    survey_id: str
    geo_level: str  # 'county', 'tract', 'block', 'zipcode'
    geo_id: str
    matched_shapefile: str
    confidence_score: float
    overlap_percentage: float
    validation_status: str  # 'valid', 'partial', 'invalid'

class SurveyDataProcessor:
    """Enhanced Census survey data processor with OCR and deep analysis capabilities."""
    
    def __init__(self, base_data_dir: str):
        self.base_data_dir = Path(base_data_dir)
        self.metadata = {}
        self.column_descriptions = {}
        self.document_cache = {}
        self.supported_data_extensions = {'.csv', '.xlsx', '.xls', '.txt'}
        self.supported_doc_extensions = {'.pdf', '.docx', '.doc'}
        self.shapefile_cache = {}
        self.geographic_matches = []
        
    def deep_scan_filesystem(self, max_depth: int = 10) -> Dict[str, List[FileInfo]]:
        """Recursively scan entire filesystem for data and documentation files."""
        found_files = defaultdict(list)
        scanned_count = 0
        
        def scan_recursive(directory: Path, current_depth: int = 0):
            nonlocal scanned_count
            if current_depth > max_depth:
                return
                
            try:
                for item in directory.iterdir():
                    if item.is_file():
                        scanned_count += 1
                        if scanned_count % 100 == 0:
                            logger.info(f"Scanned {scanned_count} files...")
                            
                        file_ext = item.suffix.lower()
                        file_size = item.stat().st_size
                        modified_time = item.stat().st_mtime
                        
                        if file_ext in self.supported_data_extensions:
                            found_files['data'].append(FileInfo(
                                str(item), file_ext, file_size, modified_time
                            ))
                        elif file_ext in self.supported_doc_extensions:
                            found_files['documents'].append(FileInfo(
                                str(item), file_ext, file_size, modified_time
                            ))
                            
                    elif item.is_dir() and not item.name.startswith('.'):
                        scan_recursive(item, current_depth + 1)
                        
            except PermissionError:
                logger.warning(f"Permission denied accessing: {directory}")
            except Exception as e:
                logger.error(f"Error scanning {directory}: {e}")
        
        # Start scanning from base directory
        logger.info(f"Starting deep filesystem scan from: {self.base_data_dir}")
        scan_recursive(self.base_data_dir)
        
        logger.info(f"Deep scan complete. Found {len(found_files['data'])} data files and {len(found_files['documents'])} document files")
        return dict(found_files)
        
    def extract_document_text(self, file_path: str) -> str:
        """Extract text from PDF, DOCX, or DOC files using OCR or text extraction."""
        if not OCR_AVAILABLE:
            return "OCR libraries not available"
            
        path_obj = Path(file_path)
        file_ext = path_obj.suffix.lower()
        
        try:
            if file_ext == '.pdf':
                return self._extract_pdf_text(path_obj)
            elif file_ext in ['.docx', '.doc']:
                return self._extract_docx_text(path_obj)
            else:
                return f"Unsupported file type: {file_ext}"
        except Exception as e:
            logger.error(f"Error extracting text from {file_path}: {e}")
            return f"Error: {str(e)}"
    
    def _extract_pdf_text(self, file_path: Path) -> str:
        """Extract text from PDF using multiple methods."""
        text = ""
        
        # Try pdfplumber first (better for tables)
        try:
            import pdfplumber
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
        except Exception as e:
            logger.warning(f"pdfplumber failed for {file_path}: {e}")
            
        # Fallback to PyPDF2
        if not text.strip():
            try:
                import PyPDF2
                with open(file_path, 'rb') as file:
                    pdf_reader = PyPDF2.PdfReader(file)
                    for page in pdf_reader.pages:
                        text += page.extract_text() + "\n"
            except Exception as e:
                logger.warning(f"PyPDF2 failed for {file_path}: {e}")
                
        # Last resort: OCR with pytesseract
        if not text.strip():
            try:
                import pytesseract
                from pdf2image import convert_from_path
                images = convert_from_path(file_path)
                for img in images:
                    ocr_text = pytesseract.image_to_string(img)
                    text += ocr_text + "\n"
            except Exception as e:
                logger.warning(f"OCR failed for {file_path}: {e}")
                
        return text.strip()
    
    def _extract_docx_text(self, file_path: Path) -> str:
        """Extract text from DOCX files."""
        try:
            import docx
            doc = docx.Document(file_path)
            text = ""
            for paragraph in doc.paragraphs:
                text += paragraph.text + "\n"
            
            # Extract text from tables
            for table in doc.tables:
                for row in table.rows:
                    row_text = " | ".join(cell.text for cell in row.cells)
                    text += row_text + "\n"
                    
            return text.strip()
        except Exception as e:
            logger.error(f"Error reading DOCX {file_path}: {e}")
            return f"Error: {str(e)}"
    
    def extract_column_descriptions_from_docs(self, documents: List[FileInfo]) -> Dict[str, str]:
        """Extract column descriptions from documentation files using pattern matching."""
        column_descriptions = {}
        
        # Common column name patterns in census documentation
        column_patterns = [
            r'([A-Z][A-Z0-9_]+)[\s:]+([^.]+?)(?:\n|\.|$)',
            r'([A-Z][A-Z0-9_]+)\s*-\s*([^.\n]+)',
            r'Variable\s+([A-Z][A-Z0-9_]+)[\s:]+([^.\n]+)',
            r'Column\s+([A-Z][A-Z0-9_]+)[\s:]+([^.\n]+)',
            r'([A-Z]\d{5}_\d{3}[A-Z])[\s:]+([^.\n]+)'
        ]
        
        for doc_info in documents:
            if doc_info.path in self.document_cache:
                text = self.document_cache[doc_info.path]
            else:
                text = self.extract_document_text(doc_info.path)
                self.document_cache[doc_info.path] = text
                
            logger.info(f"Extracting column descriptions from: {Path(doc_info.path).name}")
            
            # Apply pattern matching
            for pattern in column_patterns:
                matches = re.findall(pattern, text, re.IGNORECASE)
                for column, description in matches:
                    column = column.upper().strip()
                    description = description.strip()
                    
                    # Clean up description
                    description = re.sub(r'\s+', ' ', description)
                    description = description.rstrip('.')
                    
                    if len(column) >= 3 and len(description) > 5:
                        column_descriptions[column] = description
                        
        logger.info(f"Extracted {len(column_descriptions)} column descriptions from documentation")
        return column_descriptions
    
    def scan_survey_directories(self) -> Dict[str, List[str]]:
        """Scan for available survey data directories."""
        surveys_dir = self.base_data_dir / 'census_surveys'
        survey_data = {}
        
        if not surveys_dir.exists():
            logger.warning(f"Survey directory not found: {surveys_dir}")
            return survey_data
            
        for survey_code in os.listdir(surveys_dir):
            survey_path = surveys_dir / survey_code
            if survey_path.is_dir():
                datasets = [d for d in os.listdir(survey_path) if (survey_path / d).is_dir()]
                survey_data[survey_code] = datasets
                
        return survey_data
    
    def extract_zip_metadata(self, zip_path: str) -> Dict[str, Any]:
        """Extract metadata from zip file (file names, sizes, etc)."""
        metadata = {
            'file_name': os.path.basename(zip_path),
            'file_size': os.path.getsize(zip_path),
            'contained_files': []
        }
        
        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                for file_info in zf.infolist():
                    metadata['contained_files'].append({
                        'name': file_info.filename,
                        'size': file_info.file_size,
                        'date_time': file_info.date_time
                    })
        except Exception as e:
            metadata['error'] = str(e)
            
        return metadata
    
    def analyze_csv_structure(self, csv_path: str, sample_size: int = 1000) -> Dict[str, Any]:
        """Analyze CSV file structure with comprehensive data quality checks."""
        structure = {
            'file_path': str(csv_path),
            'file_size': os.path.getsize(csv_path),
            'total_rows': 0,
            'total_columns': 0,
            'columns': [],
            'sample_data': [],
            'column_types': {},
            'data_quality': {},
            'statistics': {},
            'missing_values': {},
            'unique_counts': {},
            'data_anomalies': []
        }
        
        try:
            # First pass: read header and count rows
            with open(csv_path, 'r', encoding='utf-8', errors='ignore') as f:
                reader = csv.reader(f)
                headers = next(reader, [])
                structure['columns'] = headers
                structure['total_columns'] = len(headers)
                
                # Count total rows
                row_count = sum(1 for _ in reader)
                structure['total_rows'] = row_count
                
            # Second pass: sample data for analysis
            df_sample = None
            try:
                # Try pandas for better analysis
                df_sample = pd.read_csv(csv_path, nrows=sample_size, encoding='utf-8', encoding_errors='ignore')
                
                # Basic statistics
                numeric_cols = df_sample.select_dtypes(include=['number']).columns
                structure['statistics'] = {}
                for col in numeric_cols:
                    try:
                        structure['statistics'][col] = {
                            'mean': float(df_sample[col].mean()) if not df_sample[col].empty else None,
                            'std': float(df_sample[col].std()) if not df_sample[col].empty else None,
                            'min': float(df_sample[col].min()) if not df_sample[col].empty else None,
                            'max': float(df_sample[col].max()) if not df_sample[col].empty else None
                        }
                    except (ValueError, TypeError):
                        structure['statistics'][col] = {
                            'mean': None, 'std': None, 'min': None, 'max': None
                        }
                
                # Missing values analysis
                missing_pct = (df_sample.isnull().sum() / len(df_sample) * 100).to_dict()
                structure['missing_values'] = {k: round(v, 2) for k, v in missing_pct.items()}
                
                # Unique counts
                unique_counts = df_sample.nunique().to_dict()
                structure['unique_counts'] = unique_counts
                
                # Data quality checks
                structure['data_quality'] = self._assess_data_quality(df_sample)
                
                # Convert sample to list format
                structure['sample_data'] = df_sample.head(10).fillna('').values.tolist()
                
            except Exception:
                # Fallback to basic CSV reading
                with open(csv_path, 'r', encoding='utf-8', errors='ignore') as f:
                    reader = csv.reader(f)
                    next(reader)  # Skip headers
                    sample_rows = []
                    for i, row in enumerate(reader):
                        if i >= 10:
                            break
                        sample_rows.append(row)
                    structure['sample_data'] = sample_rows
                
            # Column type analysis
            for col in headers:
                if df_sample is not None and col in df_sample.columns:
                    structure['column_types'][col] = str(df_sample[col].dtype)
                else:
                    # Fallback type inference
                    sample_values = []
                    for row in structure['sample_data']:
                        for i, header in enumerate(headers):
                            if header == col and i < len(row):
                                sample_values.append(row[i])
                    structure['column_types'][col] = self._infer_column_type(sample_values)
                    
        except Exception as e:
            structure['error'] = str(e)
            logger.error(f"Error analyzing CSV {csv_path}: {e}")
            
        return structure
    
    def _assess_data_quality(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Assess data quality metrics for a DataFrame."""
        quality_metrics = {
            'completeness': {},
            'consistency': {},
            'validity': {}
        }
        
        for col in df.columns:
            # Completeness: percentage of non-null values
            completeness = (df[col].notna().sum() / len(df)) * 100
            quality_metrics['completeness'][col] = round(completeness, 2)
            
            # Consistency: check for duplicate values in key columns
            if col.upper() in ['ID', 'GEOID', 'STATEFP', 'COUNTYFP']:
                duplicates = df[col].duplicated().sum()
                quality_metrics['consistency'][col] = {
                    'duplicates': int(duplicates),
                    'duplicate_rate': round((duplicates / len(df)) * 100, 2)
                }
            
            # Validity: basic range checks for known columns
            if 'STATEFP' in col.upper():
                valid_states = df[col].between(1, 56).sum()  # Valid FIPS state codes
                quality_metrics['validity'][col] = {
                    'valid_count': int(valid_states),
                    'validity_rate': round((valid_states / len(df)) * 100, 2)
                }
                
        return quality_metrics
    
    def detect_data_anomalies(self, df: pd.DataFrame, column_info: Dict[str, ColumnInfo]) -> List[Dict[str, Any]]:
        """Detect data anomalies and quality issues."""
        anomalies = []
        
        for col_name, col_info in column_info.items():
            if col_name not in df.columns:
                continue
                
            series = df[col_name]
            
            # Check for extreme outliers in numeric data
            if pd.api.types.is_numeric_dtype(series):
                Q1 = series.quantile(0.25)
                Q3 = series.quantile(0.75)
                IQR = Q3 - Q1
                lower_bound = Q1 - 1.5 * IQR
                upper_bound = Q3 + 1.5 * IQR
                
                outliers = series[(series < lower_bound) | (series > upper_bound)]
                if len(outliers) > 0:
                    anomalies.append({
                        'type': 'outlier',
                        'column': col_name,
                        'count': len(outliers),
                        'percentage': (len(outliers) / len(series)) * 100,
                        'severity': 'high' if len(outliers) > len(series) * 0.05 else 'medium',
                        'description': f"Statistical outliers detected in {col_name}"
                    })
            
            # Check for suspicious patterns in text data
            elif pd.api.types.is_string_dtype(series):
                # Check for suspiciously repetitive values
                value_counts = series.value_counts()
                if len(value_counts) > 0:
                    most_common_pct = (value_counts.iloc[0] / len(series)) * 100
                    if most_common_pct > 90:
                        anomalies.append({
                            'type': 'repetitive_values',
                            'column': col_name,
                            'dominant_value': str(value_counts.index[0]),
                            'percentage': most_common_pct,
                            'severity': 'high',
                            'description': f"Column {col_name} is {most_common_pct:.1f}% identical values"
                        })
                
                # Check for suspicious null-like strings
                null_patterns = ['', ' ', 'NULL', 'null', 'N/A', 'n/a', '#N/A', '#REF!', '0']
                null_like_count = series.str.strip().isin(null_patterns).sum()
                if null_like_count > 0:
                    anomalies.append({
                        'type': 'suspicious_nulls',
                        'column': col_name,
                        'count': null_like_count,
                        'percentage': (null_like_count / len(series)) * 100,
                        'severity': 'medium',
                        'description': f"Suspicious null-like values found in {col_name}"
                    })
            
            # Geographic validation
            if any(geo_term in col_name.upper() for geo_term in ['STATE', 'FIPS', 'GEOID']):
                if col_name.upper() == 'STATEFP' or 'STATE' in col_name.upper():
                    # Validate state FIPS codes (1-56)
                    if pd.api.types.is_numeric_dtype(series):
                        invalid_states = series[~series.between(1, 56)]
                        if len(invalid_states) > 0:
                            anomalies.append({
                                'type': 'invalid_geographic_codes',
                                'column': col_name,
                                'count': len(invalid_states),
                                'percentage': (len(invalid_states) / len(series)) * 100,
                                'severity': 'high',
                                'description': f"Invalid state FIPS codes found in {col_name}"
                            })
        
        return anomalies
    
    def load_shapefile(self, shapefile_path: str) -> Optional[gpd.GeoDataFrame]:
        """Load and cache shapefile for geographic validation."""
        if shapefile_path in self.shapefile_cache:
            return self.shapefile_cache[shapefile_path]
            
        try:
            gdf = gpd.read_file(shapefile_path)
            self.shapefile_cache[shapefile_path] = gdf
            logger.info(f"Loaded shapefile: {shapefile_path} with {len(gdf)} features")
            return gdf
        except Exception as e:
            logger.error(f"Error loading shapefile {shapefile_path}: {e}")
            return None
    
    def scan_available_shapefiles(self) -> Dict[str, List[str]]:
        """Scan for available shapefiles in the data directory."""
        shapefiles = defaultdict(list)
        
        for pattern in ['**/*.shp', '**/*.geojson', '**/*.gpkg']:
            for shp_file in self.base_data_dir.rglob(pattern):
                rel_path = shp_file.relative_to(self.base_data_dir)
                parent_dir = rel_path.parts[0] if len(rel_path.parts) > 1 else 'root'
                shapefiles[parent_dir].append(str(shp_file))
                
        logger.info(f"Found shapefiles in {len(shapefiles)} directories")
        return dict(shapefiles)
    
    def validate_geographic_identifiers(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Validate and analyze geographic identifiers in survey data."""
        validation_results = {
            'identified_columns': {},
            'validation_summary': {},
            'geographic_coverage': {},
            'recommendations': []
        }
        
        # Common geographic identifier patterns
        geo_patterns = {
            'STATEFP': r'^\d{2}$',
            'COUNTYFP': r'^\d{3}$',
            'GEOID': r'^\d{5,11}$',
            'GEO_ID': r'^\d{5,11}$',
            'TRACTCE': r'^\d{5,1}$',
            'BLOCKCE': r'^\d{3}$',
            'ZCTA520': r'^\d{5}$',
            'ZIPCODE': r'^\d{5}$',
            'ZIP': r'^\d{5}$'
        }
        
        for col_name in df.columns:
            col_upper = col_name.upper()
            
            for geo_id, pattern in geo_patterns.items():
                if geo_id in col_upper:
                    # Validate the column
                    series = df[col_name].dropna()
                    valid_count = series.astype(str).str.match(pattern).sum()
                    total_count = len(series)
                    
                    validation_results['identified_columns'][col_name] = {
                        'type': geo_id,
                        'pattern': pattern,
                        'total_values': total_count,
                        'valid_values': int(valid_count),
                        'validity_rate': round((valid_count / total_count * 100) if total_count > 0 else 0, 2),
                        'sample_values': series.head(5).astype(str).tolist()
                    }
                    
                    # Geographic coverage analysis
                    unique_values = series.unique()
                    validation_results['geographic_coverage'][col_name] = {
                        'unique_locations': len(unique_values),
                        'coverage_type': geo_id,
                        'top_locations': dict(series.value_counts().head(10))
                    }
                    break
        
        # Generate recommendations
        for col, info in validation_results['identified_columns'].items():
            if info['validity_rate'] < 95:
                validation_results['recommendations'].append(
                    f"Column {col} has low validity rate ({info['validity_rate']}%) for {info['type']}"
                )
        
        return validation_results
    
    def detect_overlapping_datapoints(self, survey_df: pd.DataFrame, 
                                    shapefile_gdf: gpd.GeoDataFrame,
                                    geo_column: str) -> List[GeographicMatch]:
        """Detect overlapping datapoints between survey data and shapefile boundaries."""
        overlaps = []
        
        # Try to identify the geometry column in shapefile
        geom_col = None
        for col in shapefile_gdf.columns:
            if shapefile_gdf[col].dtype.name in ['geometry', 'object']:
                geom_col = col
                break
        
        if geom_col is None:
            logger.warning("No geometry column found in shapefile")
            return overlaps
        
        # Convert survey data to GeoDataFrame if it has coordinates
        survey_gdf = None
        if 'LATITUDE' in survey_df.columns and 'LONGITUDE' in survey_df.columns:
            # Create points from lat/lon
            geometry = [Point(xy) for xy in zip(survey_df['LONGITUDE'], survey_df['LATITUDE'])]
            survey_gdf = gpd.GeoDataFrame(survey_df, geometry=geometry, crs='EPSG:4326')
        elif geo_column in survey_df.columns:
            # Join by geographic identifier
            id_col = self._find_matching_id_column(survey_df[geo_column], shapefile_gdf)
            if id_col:
                survey_gdf = survey_df.merge(shapefile_gdf[[id_col, geom_col]], 
                                            left_on=geo_column, right_on=id_col, how='inner')
        
        if survey_gdf is None:
            logger.warning("Could not create GeoDataFrame from survey data")
            return overlaps
        
        # Perform spatial join to find overlaps
        try:
            # Ensure both GeoDataFrames have the same CRS
            if survey_gdf.crs != shapefile_gdf.crs:
                survey_gdf = survey_gdf.to_crs(shapefile_gdf.crs)
            
            # Spatial join
            joined = gpd.sjoin(survey_gdf, shapefile_gdf, how='inner', predicate='intersects')
            
            # Analyze overlaps
            for _, row in joined.iterrows():
                # Calculate overlap percentage if polygons
                if hasattr(row['geometry'], 'area') and hasattr(row[f'{geom_col}_right'], 'area'):
                    intersection = row['geometry'].intersection(row[f'{geom_col}_right'])
                    overlap_pct = (intersection.area / row['geometry'].area) * 100 if row['geometry'].area > 0 else 0
                else:
                    overlap_pct = 100  # Point-in-polygon case
                
                match = GeographicMatch(
                    survey_id=str(row.get('id', '')),
                    geo_level=geo_column,
                    geo_id=str(row[geo_column]),
                    matched_shapefile=str(shapefile_gdf.attrs.get('source', 'unknown')),
                    confidence_score=min(100, overlap_pct),
                    overlap_percentage=overlap_pct,
                    validation_status='valid' if overlap_pct >= 80 else 'partial' if overlap_pct >= 50 else 'invalid'
                )
                overlaps.append(match)
                
        except Exception as e:
            logger.error(f"Error in spatial join: {e}")
        
        logger.info(f"Found {len(overlaps)} geographic matches")
        return overlaps
    
    def _find_matching_id_column(self, survey_series: pd.Series, shapefile_gdf: gpd.GeoDataFrame) -> Optional[str]:
        """Find matching ID column between survey data and shapefile."""
        survey_vals = set(survey_series.astype(str).unique())
        
        for col in shapefile_gdf.columns:
            if col == 'geometry':
                continue
                
            shapefile_vals = set(shapefile_gdf[col].astype(str).unique())
            
            # Check for significant overlap
            intersection = len(survey_vals.intersection(shapefile_vals))
            if intersection > 0 and intersection / len(survey_vals) > 0.5:
                return col
        
        return None
    
    def generate_geographic_quality_report(self, df: pd.DataFrame, 
                                        overlaps: List[GeographicMatch]) -> Dict[str, Any]:
        """Generate comprehensive geographic data quality report."""
        report = {
            'data_quality_metrics': {},
            'overlap_analysis': {},
            'geographic_coverage': {},
            'validation_issues': [],
            'recommendations': []
        }
        
        # Data quality metrics
        total_records = len(df)
        report['data_quality_metrics'] = {
            'total_records': total_records,
            'geographic_matches': len(overlaps),
            'match_rate': round((len(overlaps) / total_records * 100) if total_records > 0 else 0, 2)
        }
        
        # Overlap analysis
        if overlaps:
            overlap_stats = {
                'high_confidence': len([o for o in overlaps if o.confidence_score >= 80]),
                'medium_confidence': len([o for o in overlaps if 50 <= o.confidence_score < 80]),
                'low_confidence': len([o for o in overlaps if o.confidence_score < 50]),
                'average_confidence': round(np.mean([o.confidence_score for o in overlaps]), 2)
            }
            report['overlap_analysis'] = overlap_stats
        
        # Geographic coverage by level
        coverage_by_level = defaultdict(list)
        for overlap in overlaps:
            coverage_by_level[overlap.geo_level].append(overlap)
        
        report['geographic_coverage'] = {
            level: {
                'count': len(matches),
                'avg_confidence': round(np.mean([m.confidence_score for m in matches]), 2) if matches else 0
            }
            for level, matches in coverage_by_level.items()
        }
        
        # Validation issues
        for overlap in overlaps:
            if overlap.validation_status == 'invalid':
                report['validation_issues'].append({
                    'survey_id': overlap.survey_id,
                    'geo_id': overlap.geo_id,
                    'issue': 'Low geographic match confidence',
                    'confidence': overlap.confidence_score
                })
        
        # Recommendations
        if report['data_quality_metrics']['match_rate'] < 80:
            report['recommendations'].append(
                "Low geographic match rate - verify coordinate systems and identifier formats"
            )
        
        if len(report['validation_issues']) > 0:
            report['recommendations'].append(
                f"Found {len(report['validation_issues'])} records with invalid geographic matches"
            )
        
        return report
    
    def generate_geographic_documentation(self, results: Dict[str, Any]) -> str:
        """Generate comprehensive documentation for geographic data alignment."""
        doc_lines = []
        
        # Header
        doc_lines.append("# Geographic Data Alignment Report")
        doc_lines.append(f"Generated: {results.get('timestamp', 'Unknown')}")
        doc_lines.append("")
        
        # Executive Summary
        doc_lines.append("## Executive Summary")
        fs_scan = results.get('filesystem_scan', {})
        doc_lines.append(f"- Data files processed: {fs_scan.get('data_files', 0)}")
        doc_lines.append(f"- Shapefile directories: {fs_scan.get('shapefile_directories', 0)}")
        doc_lines.append(f"- Total shapefiles: {fs_scan.get('total_shapefiles', 0)}")
        
        geo_analysis = results.get('geographic_analysis', {})
        doc_lines.append(f"- Files with geographic data: {geo_analysis.get('files_with_geographic_data', 0)}")
        doc_lines.append(f"- Geographic columns identified: {len(geo_analysis.get('geographic_columns_found', {}))}")
        doc_lines.append("")
        
        # Geographic Validation Results
        doc_lines.append("## Geographic Validation Results")
        
        geo_columns = geo_analysis.get('geographic_columns_found', {})
        if geo_columns:
            doc_lines.append("### Detected Geographic Columns")
            doc_lines.append("| Column | Type | Validity Rate | Sample Values |")
            doc_lines.append("|--------|------|---------------|---------------|")
            
            for col_name, col_info in geo_columns.items():
                validity = col_info.get('validity_rate', 0)
                col_type = col_info.get('type', 'Unknown')
                samples = ', '.join(str(v) for v in col_info.get('sample_values', [])[:3])
                doc_lines.append(f"| {col_name} | {col_type} | {validity}% | {samples} |")
        else:
            doc_lines.append("⚠️ No geographic columns detected in the survey data.")
        doc_lines.append("")
        
        # Shapefile Integration Status
        doc_lines.append("## Shapefile Integration Status")
        
        if fs_scan.get('total_shapefiles', 0) > 0:
            doc_lines.append("✅ Shapefiles found and available for geographic validation")
            doc_lines.append("")
            doc_lines.append("### Available Shapefile Categories:")
            shapefiles = self.scan_available_shapefiles()
            for category, files in shapefiles.items():
                doc_lines.append(f"- **{category}**: {len(files)} files")
        else:
            doc_lines.append("❌ No shapefiles found in the data directory")
            doc_lines.append("")
            doc_lines.append("### Recommended Shapefile Sources:")
            doc_lines.append("- US Census TIGER/Line shapefiles for county/tract boundaries")
            doc_lines.append("- USPS ZIP Code Tabulation Areas (ZCTAs)")
            doc_lines.append("- State and county boundary shapefiles")
        doc_lines.append("")
        
        # Data Quality Assessment
        doc_lines.append("## Data Quality Assessment")
        
        recommendations = results.get('recommendations', [])
        if recommendations:
            doc_lines.append("### Key Findings and Recommendations")
            for i, rec in enumerate(recommendations, 1):
                doc_lines.append(f"{i}. {rec}")
        else:
            doc_lines.append("✅ No major data quality issues detected")
        doc_lines.append("")
        
        # Geographic Coverage Analysis
        doc_lines.append("## Geographic Coverage Analysis")
        
        for col_name, col_info in geo_columns.items():
            doc_lines.append(f"### {col_name} Coverage")
            
            # Coverage statistics
            coverage = col_info.get('geographic_coverage', {})
            if coverage:
                unique_locations = coverage.get('unique_locations', 0)
                doc_lines.append(f"- Unique geographic units: {unique_locations}")
                
                top_locations = coverage.get('top_locations', {})
                if top_locations:
                    doc_lines.append("- Top locations:")
                    for location, count in list(top_locations.items())[:5]:
                        doc_lines.append(f"  - {location}: {count} records")
            
            doc_lines.append("")
        
        # Usage Instructions
        doc_lines.append("## Usage Instructions")
        doc_lines.append("")
        doc_lines.append("### For Data Analysts:")
        doc_lines.append("1. Use the validated geographic columns for spatial analysis")
        doc_lines.append("2. Join survey data with shapefiles using the identified GEOID columns")
        doc_lines.append("3. Filter out records with invalid geographic identifiers")
        doc_lines.append("")
        
        doc_lines.append("### For Developers:")
        doc_lines.append("1. Use the `validate_geographic_identifiers()` method for new datasets")
        doc_lines.append("2. Leverage `detect_overlapping_datapoints()` for spatial validation")
        doc_lines.append("3. Cache shapefiles using `load_shapefile()` for performance")
        doc_lines.append("")
        
        # Technical Details
        doc_lines.append("## Technical Details")
        doc_lines.append("")
        doc_lines.append("### Supported Geographic Identifiers:")
        doc_lines.append("- **STATEFP**: 2-digit state FIPS codes (01-56)")
        doc_lines.append("- **COUNTYFP**: 3-digit county FIPS codes within states")
        doc_lines.append("- **GEOID/GEO_ID**: 5-11 digit geographic identifiers")
        doc_lines.append("- **TRACTCE**: Census tract codes")
        doc_lines.append("- **BLOCKCE**: Census block codes")
        doc_lines.append("- **ZCTA520**: 5-digit ZIP Code Tabulation Areas")
        doc_lines.append("")
        
        doc_lines.append("### Validation Patterns:")
        doc_lines.append("- Regular expression matching for format validation")
        doc_lines.append("- Range validation for FIPS codes")
        doc_lines.append("- Spatial join for coordinate-based validation")
        doc_lines.append("")
        
        # Next Steps
        doc_lines.append("## Next Steps")
        doc_lines.append("")
        doc_lines.append("1. **Add Shapefiles**: Download and add relevant shapefiles to enable full spatial validation")
        doc_lines.append("2. **Enhance Documentation**: Add PDF/DOC files with column descriptions for better mapping")
        doc_lines.append("3. **Coordinate Validation**: If dataset has lat/lon columns, enable point-in-polygon validation")
        doc_lines.append("4. **Automated Processing**: Set up scheduled runs to keep geographic validation current")
        doc_lines.append("")
        
        doc_lines.append("---")
        doc_lines.append("*Report generated by GeoDataAnalytics Survey Processor*")
        
        return "\n".join(doc_lines)
    
    def save_geographic_documentation(self, results: Dict[str, Any], output_path: str = None):
        """Save geographic documentation to file."""
        if output_path is None:
            timestamp = pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")
            output_path = self.base_data_dir / f'geographic_alignment_report_{timestamp}.md'
        
        doc_content = self.generate_geographic_documentation(results)
        
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(doc_content)
            logger.info(f"Geographic documentation saved to: {output_path}")
            return str(output_path)
        except Exception as e:
            logger.error(f"Error saving documentation: {e}")
            return None
    
    def save_processing_results(self, results: Dict[str, Any], survey_code: str, dataset: str):
        """Save processing results to JSON file for later use."""
        results_dir = self.base_data_dir / 'census_surveys' / survey_code / dataset
        results_dir.mkdir(parents=True, exist_ok=True)
        
        results_file = results_dir / f'{survey_code}_{dataset}_metadata.json'
        
        try:
            with open(results_file, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2, default=str)
            print(f"Processing results saved to: {results_file}")
        except Exception as e:
            print(f"Error saving results: {e}")

def main():
    """Main function to demonstrate survey data processing with geographic validation."""
    # Get the repository root directory
    current_file = Path(__file__).resolve()
    repo_root = current_file.parent.parent
    data_dir = repo_root / 'data'
    
    processor = SurveyDataProcessor(str(data_dir))
    
    # Scan for available surveys
    available_surveys = processor.scan_survey_directories()
    print("Available survey datasets:")
    for survey_code, datasets in available_surveys.items():
        print(f"  {survey_code}: {datasets}")
    
    # Choose processing method
    if available_surveys:
        print("\nProcessing Options:")
        print("1. Enhanced processing with geographic validation")
        print("2. Standard processing (legacy)")
        
        choice = input("\nEnter choice (1 or 2, default=1): ").strip() or "1"
        
        if choice == "1":
            print("\nRunning geographic-enhanced processing pipeline...")
            results = processor.geographic_enhanced_processing_pipeline()
            
            # Save geographic documentation
            doc_path = processor.save_geographic_documentation(results)
            if doc_path:
                print(f"📄 Geographic documentation saved to: {doc_path}")
            
            # Print geographic summary
            geo_analysis = results.get('geographic_analysis', {})
            print(f"\nGeographic Processing Summary:")
            print(f"  Files with geographic data: {geo_analysis.get('files_with_geographic_data', 0)}")
            print(f"  Geographic columns found: {len(geo_analysis.get('geographic_columns_found', {}))}")
            print(f"  Shapefile directories: {results['filesystem_scan'].get('shapefile_directories', 0)}")
            
            # Print geographic columns
            if geo_analysis.get('geographic_columns_found'):
                print("\nGeographic Columns Detected:")
                for col, info in geo_analysis['geographic_columns_found'].items():
                    print(f"  {col}: {info['type']} ({info['validity_rate']}% valid)")
        else:
            print("\nRunning standard processing pipeline...")
            results = processor.enhanced_processing_pipeline()
            
            # Print standard summary
            print(f"\nStandard Processing Summary:")
            print(f"  Data files analyzed: {results['csv_analysis'].get('files_analyzed', 0)}")
            print(f"  Columns mapped: {results['column_mapping'].get('total_columns_mapped', 0)}")
        
        # Print recommendations
        if results.get('recommendations'):
            print(f"\nRecommendations:")
            for rec in results['recommendations']:
                print(f"  • {rec}")
        
        # Also process a specific survey if available
        first_survey = list(available_surveys.keys())[0]
        first_dataset = available_surveys[first_survey][0] if available_surveys[first_survey] else None
        
        if first_dataset:
            detailed = input(f"\nProcess detailed analysis for {first_survey}/{first_dataset}? (y/n): ").strip().lower()
            if detailed == 'y':
                print(f"\nProcessing {first_survey}/{first_dataset}...")
                survey_results = processor.process_survey_dataset(first_survey, first_dataset)
                processor.save_processing_results(survey_results, first_survey, first_dataset)
                
                summary = survey_results['data_summary']
                print(f"\nDetailed Survey Analysis:")
                print(f"  CSV files analyzed: {summary['total_csv_files']}")
                print(f"  ZIP files found: {summary['total_zip_files']}")
                print(f"  Total columns: {summary['total_columns_analyzed']}")
                print(f"  Unique columns: {summary['unique_columns']}")
    else:
        print("\nNo survey data found. Please run get_census_survey.py first.")
        return

if __name__ == "__main__":
    main()