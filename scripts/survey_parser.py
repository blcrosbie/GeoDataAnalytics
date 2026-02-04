#!/usr/bin/env python3
"""
Survey Data Parser for Geographic Database Integration
Core functions to parse survey files, extract documentation, and align with geographic boundaries.
"""

import os
import pandas as pd
import json
import re
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
import logging
from dataclasses import dataclass, asdict
from datetime import datetime
import sqlite3
from collections import defaultdict

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class SurveyMetadata:
    """Metadata structure for parsed survey datasets."""
    survey_code: str
    dataset_name: str
    file_path: str
    file_type: str
    file_size: int
    row_count: int
    column_count: int
    geographic_columns: List[str]
    year: Optional[int] = None
    geo_coverage: Optional[str] = None
    methodology: Optional[str] = None
    taxonomy: Optional[str] = None

@dataclass
class ColumnDefinition:
    """Column definition extracted from documentation."""
    column_name: str
    description: str
    data_type: str
    measurement_unit: Optional[str] = None
    categories: Optional[List[str]] = None
    source_document: str = ""

class SurveyDataParser:
    """Focused parser for survey data extraction and geographic alignment."""
    
    def __init__(self, base_data_dir: str,         db_path: Optional[str] = None):
        self.base_data_dir = Path(base_data_dir)
        if db_path:
            self.db_path = db_path
        else:
            self.db_path = str(self.base_data_dir.parent / 'geodata.db')
        self.survey_catalog = []
        self.documentation_cache = {}
        self.geographic_boundaries = {}
        
    def scan_and_catalog_surveys(self) -> List[SurveyMetadata]:
        """Scan all survey directories and catalog available datasets."""
        logger.info("Scanning survey directories...")
        
        surveys_dir = self.base_data_dir / 'census_surveys'
        catalog = []
        
        if not surveys_dir.exists():
            logger.warning(f"Survey directory not found: {surveys_dir}")
            return catalog
            
        for survey_code in os.listdir(surveys_dir):
            survey_path = surveys_dir / survey_code
            if not survey_path.is_dir():
                continue
                
            for dataset in os.listdir(survey_path):
                dataset_path = survey_path / dataset
                if not dataset_path.is_dir():
                    continue
                    
                # Process all data files in dataset
                for file_name in os.listdir(dataset_path):
                    file_path = dataset_path / file_name
                    
                    if file_path.suffix.lower() in ['.csv', '.txt', '.xlsx', '.xls']:
                        metadata = self._analyze_survey_file(
                            survey_code, dataset, file_path
                        )
                        if metadata:
                            catalog.append(metadata)
        
        self.survey_catalog = catalog
        logger.info(f"Cataloged {len(catalog)} survey datasets")
        return catalog
    
    def _analyze_survey_file(self, survey_code: str, dataset: str, file_path: Path) -> Optional[SurveyMetadata]:
        """Analyze a single survey file and extract metadata."""
        try:
            file_size = file_path.stat().st_size
            
            # Try to read the file and get basic info
            if file_path.suffix.lower() == '.csv':
                df = pd.read_csv(file_path, nrows=5)
            elif file_path.suffix.lower() in ['.xlsx', '.xls']:
                df = pd.read_excel(file_path, nrows=5)
            elif file_path.suffix.lower() == '.txt':
                # Try tab-delimited first, then comma
                try:
                    df = pd.read_csv(file_path, sep='\t', nrows=5)
                except:
                    df = pd.read_csv(file_path, nrows=5)
            else:
                return None
            
            # Identify geographic columns
            geographic_columns = self._identify_geographic_columns(df)
            
            # Extract year from filename or data
            year = self._extract_year(str(file_path), df)
            
            return SurveyMetadata(
                survey_code=survey_code,
                dataset_name=dataset,
                file_path=str(file_path),
                file_type=file_path.suffix.lower(),
                file_size=file_size,
                row_count=0,  # Will be updated during full processing
                column_count=len(df.columns),
                geographic_columns=geographic_columns,
                year=year,
                geo_coverage=self._infer_geo_coverage(geographic_columns),
                methodology=None,  # Will be extracted from docs
                taxonomy=None      # Will be extracted from docs
            )
            
        except Exception as e:
            logger.error(f"Error analyzing {file_path}: {e}")
            return None
    
    def _identify_geographic_columns(self, df: pd.DataFrame) -> List[str]:
        """Identify geographic columns in the dataframe."""
        geographic_patterns = [
            r'.*GEO.*ID.*', r'.*GEO_ID.*', r'.*GEOID.*',
            r'.*STATE.*FP.*', r'.*COUNTY.*FP.*',
            r'.*TRACT.*', r'.*BLOCK.*',
            r'.*ZIP.*', r'.*ZCTA.*',
            r'.*FIPS.*', r'.*STATE.*', r'.*COUNTY.*'
        ]
        
        geo_columns = []
        for col in df.columns:
            col_upper = col.upper().strip()
            for pattern in geographic_patterns:
                if re.match(pattern, col_upper):
                    geo_columns.append(col)
                    break
        
        return geo_columns
    
    def _extract_year(self, file_path: str, df: pd.DataFrame) -> Optional[int]:
        """Extract year from filename or data."""
        # Try filename first
        year_match = re.search(r'20\d{2}|19\d{2}', file_path)
        if year_match:
            year = int(year_match.group())
            if 1990 <= year <= 2030:  # Reasonable year range
                return year
        
        # Try column names
        for col in df.columns:
            year_match = re.search(r'20\d{2}|19\d{2}', str(col))
            if year_match:
                year = int(year_match.group())
                if 1990 <= year <= 2030:
                    return year
        
        return None
    
    def _infer_geo_coverage(self, geo_columns: List[str]) -> Optional[str]:
        """Infer geographic coverage level from columns."""
        if not geo_columns:
            return None
        
        col_str = ' '.join(geo_columns).upper()
        
        if 'BLOCK' in col_str:
            return 'block'
        elif 'TRACT' in col_str:
            return 'tract'
        elif 'COUNTY' in col_str and not 'TRACT' in col_str:
            return 'county'
        elif 'STATE' in col_str and not 'COUNTY' in col_str:
            return 'state'
        elif 'ZIP' in col_str or 'ZCTA' in col_str:
            return 'zipcode'
        else:
            return 'unknown'
    
    def extract_documentation(self, survey_code: str, dataset: str) -> Dict[str, Any]:
        """Extract documentation from PDF/DOC files for a specific survey."""
        logger.info(f"Extracting documentation for {survey_code}/{dataset}")
        
        doc_dir = self.base_data_dir / 'census_surveys' / survey_code / dataset
        documentation = {
            'survey_code': survey_code,
            'dataset': dataset,
            'methodology': '',
            'taxonomy': '',
            'column_definitions': {},
            'source_files': []
        }
        
        if not doc_dir.exists():
            logger.warning(f"Dataset directory not found: {doc_dir}")
            return documentation
        
        # Look for documentation files
        for file_name in os.listdir(doc_dir):
            file_path = doc_dir / file_name
            if file_path.suffix.lower() in ['.pdf', '.doc', '.docx', '.txt']:
                doc_content = self._extract_document_content(file_path)
                documentation['source_files'].append(str(file_path))
                
                # Extract methodology
                methodology = self._extract_methodology(doc_content)
                if methodology:
                    documentation['methodology'] += methodology + '\n'
                
                # Extract taxonomy/categories
                taxonomy = self._extract_taxonomy(doc_content)
                if taxonomy:
                    documentation['taxonomy'] += taxonomy + '\n'
                
                # Extract column definitions
                column_defs = self._extract_column_definitions(doc_content, str(file_path))
                documentation['column_definitions'].update(column_defs)
        
        return documentation
    
    def _extract_document_content(self, file_path: Path) -> str:
        """Extract text content from document files."""
        if file_path.suffix.lower() == '.txt':
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    return f.read()
            except Exception as e:
                logger.error(f"Error reading TXT file {file_path}: {e}")
                return ""
        
        # For PDF/DOC, return placeholder for now
        # TODO: Implement PDF/DOC extraction libraries
        return f"[Document content from {file_path.name}]"
    
    def _extract_methodology(self, content: str) -> str:
        """Extract survey methodology from document content."""
        methodology_patterns = [
            r'(?:Methodology|Method|Data Collection|Survey Design)[\s:]*([^.]*[^.]*)',
            r'(?:Sample|Sampling|Weighting)[\s:]*([^.]*[^.]*)',
            r'(?:Response Rate|Margin of Error)[\s:]*([^.]*[^.]*)'
        ]
        
        methodology_text = []
        for pattern in methodology_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE | re.DOTALL)
            for match in matches:
                clean_text = re.sub(r'\s+', ' ', match.strip())
                if len(clean_text) > 20:  # Filter out short matches
                    methodology_text.append(clean_text)
        
        return '\n'.join(methodology_text)
    
    def _extract_taxonomy(self, content: str) -> str:
        """Extract survey taxonomy and categories from document content."""
        taxonomy_patterns = [
            r'(?:Categories|Classifications|Variables)[\s:]*([^.]*[^.]*)',
            r'(?:Demographics|Population Groups)[\s:]*([^.]*[^.]*)',
            r'(?:Income|Education|Employment|Housing)[\s:]*([^.]*[^.]*)'
        ]
        
        taxonomy_text = []
        for pattern in taxonomy_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE | re.DOTALL)
            for match in matches:
                clean_text = re.sub(r'\s+', ' ', match.strip())
                if len(clean_text) > 20:
                    taxonomy_text.append(clean_text)
        
        return '\n'.join(taxonomy_text)
    
    def _extract_column_definitions(self, content: str, source_file: str) -> Dict[str, ColumnDefinition]:
        """Extract column definitions from document content."""
        column_patterns = [
            r'([A-Z][A-Z0-9_]+)[\s:\-]+([^.]+?)(?:\n|\.|$)',
            r'Variable\s+([A-Z][A-Z0-9_]+)[\s:\-]+([^.]+?)(?:\n|\.|$)',
            r'Column\s+([A-Z][A-Z0-9_]+)[\s:\-]+([^.]+?)(?:\n|\.|$)',
            r'([A-Z]\d{5}_\d{3}[A-Z])[\s:\-]+([^.]+?)(?:\n|\.|$)'
        ]
        
        column_defs = {}
        for pattern in column_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE | re.DOTALL)
            for column, description in matches:
                column = column.upper().strip()
                description = re.sub(r'\s+', ' ', description.strip()).rstrip('.')
                
                if len(column) >= 3 and len(description) > 10:
                    # Try to extract data type and units from description
                    data_type = self._infer_data_type_from_description(description)
                    measurement_unit = self._extract_units(description)
                    
                    column_defs[column] = ColumnDefinition(
                        column_name=column,
                        description=description,
                        data_type=data_type,
                        measurement_unit=measurement_unit,
                        source_document=source_file
                    )
        
        return column_defs
    
    def _infer_data_type_from_description(self, description: str) -> str:
        """Infer data type from column description."""
        desc_lower = description.lower()
        
        if any(word in desc_lower for word in ['count', 'number', 'population', 'age', 'income', 'percent']):
            if 'percent' in desc_lower or 'rate' in desc_lower:
                return 'percentage'
            else:
                return 'numeric'
        elif any(word in desc_lower for word in ['yes', 'no', 'true', 'false', 'binary']):
            return 'boolean'
        elif any(word in desc_lower for word in ['category', 'type', 'classification', 'group']):
            return 'categorical'
        else:
            return 'text'
    
    def _extract_units(self, description: str) -> Optional[str]:
        """Extract measurement units from description."""
        unit_patterns = [
            r'(\$|dollars|USD)',
            r'(\%|percent|percentage)',
            r'(years|yrs?|months|days)',
            r'(people|persons|households)',
            r'(square|sq\.|sq|mi|km)'
        ]
        
        for pattern in unit_patterns:
            match = re.search(pattern, description.lower())
            if match:
                return match.group(1)
        
        return None
    
    def preprocess_data_file(self, metadata: SurveyMetadata) -> pd.DataFrame:
        """Preprocess data file to remove headers/summaries and get to main data table."""
        logger.info(f"Preprocessing {metadata.file_path}")
        
        file_path = Path(metadata.file_path)
        
        try:
            # Read the file with different strategies based on type
            if file_path.suffix.lower() == '.csv':
                # Try to detect the actual start of data
                df = self._read_csv_with_header_detection(file_path)
            elif file_path.suffix.lower() in ['.xlsx', '.xls']:
                df = self._read_excel_with_header_detection(file_path)
            elif file_path.suffix.lower() == '.txt':
                df = self._read_txt_with_header_detection(file_path)
            else:
                raise ValueError(f"Unsupported file type: {file_path.suffix}")
            
            # Update row count in metadata
            metadata.row_count = len(df)
            
            # Clean column names
            df = self._clean_column_names(df)
            
            logger.info(f"Loaded {len(df)} rows, {len(df.columns)} columns")
            return df
            
        except Exception as e:
            logger.error(f"Error preprocessing {file_path}: {e}")
            return pd.DataFrame()
    
    def _read_csv_with_header_detection(self, file_path: Path) -> pd.DataFrame:
        """Read CSV file with automatic header/summary detection."""
        # Read initial lines to understand structure
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
        
        # Find the actual data start (look for consistent column count)
        data_start = 0
        max_cols = 0
        
        for i, line in enumerate(lines[:20]):  # Check first 20 lines
            cols = len(line.split(','))
            if cols > max_cols:
                max_cols = cols
                data_start = i
        
        # Try reading from the detected start
        try:
            df = pd.read_csv(file_path, skiprows=data_start, encoding='utf-8')
            
            # Additional validation: if we got very few columns, try different approach
            if len(df.columns) < 3:
                # Try reading without skipping rows first
                df = pd.read_csv(file_path, encoding='utf-8')
                
                # Look for row that contains actual column headers
                for i in range(min(10, len(df))):
                    if df.iloc[i].notna().sum() > len(df.columns) * 0.7:  # 70% non-null
                        df.columns = df.iloc[i].astype(str)
                        df = df.iloc[i+1:].reset_index(drop=True)
                        break
            
            return df
            
        except Exception as e:
            logger.warning(f"Standard CSV reading failed: {e}")
            # Fallback to basic reading
            return pd.read_csv(file_path, encoding='utf-8')
    
    def _read_excel_with_header_detection(self, file_path: Path) -> pd.DataFrame:
        """Read Excel file with header detection."""
        # Try different sheets
        excel_file = pd.ExcelFile(file_path)
        
        for sheet_name in excel_file.sheet_names[:3]:  # Try first 3 sheets
            try:
                df = pd.read_excel(file_path, sheet_name=sheet_name)
                
                # Look for actual data start
                for i in range(min(10, len(df))):
                    if df.iloc[i].notna().sum() > len(df.columns) * 0.7:
                        df.columns = df.iloc[i].astype(str)
                        df = df.iloc[i+1:].reset_index(drop=True)
                        break
                
                if len(df.columns) >= 3:  # Reasonable number of columns
                    return df
                    
            except Exception as e:
                logger.warning(f"Error reading sheet {sheet_name}: {e}")
                continue
        
        # Fallback
        return pd.read_excel(file_path)
    
    def _read_txt_with_header_detection(self, file_path: Path) -> pd.DataFrame:
        """Read TXT file with automatic delimiter and header detection."""
        # Try different delimiters
        delimiters = ['\t', ',', '|', ';']
        
        for delimiter in delimiters:
            try:
                df = pd.read_csv(file_path, delimiter=delimiter, encoding='utf-8')
                
                # Check if this looks like valid data
                if len(df.columns) >= 3 and len(df) > 5:
                    return df
                    
            except Exception:
                continue
        
        # Last resort - let pandas detect
        return pd.read_csv(file_path, sep=None, engine='python', encoding='utf-8')
    
    def _clean_column_names(self, df: pd.DataFrame) -> pd.DataFrame:
        """Clean and standardize column names."""
        new_columns = []
        
        for col in df.columns:
            # Convert to string and clean
            col_str = str(col).strip()
            
            # Remove special characters and spaces, replace with underscore
            col_clean = re.sub(r'[^\w]', '_', col_str)
            
            # Remove multiple underscores
            col_clean = re.sub(r'_+', '_', col_clean)
            
            # Remove leading/trailing underscores
            col_clean = col_clean.strip('_')
            
            # Make uppercase
            col_clean = col_clean.upper()
            
            new_columns.append(col_clean)
        
        df.columns = new_columns
        return df
    
    def get_geographic_boundaries_from_db(self) -> Dict[str, Any]:
        """Get most recent GEOID/Year combos from geographic_boundaries table."""
        logger.info("Fetching geographic boundaries from database...")
        
        try:
            conn = sqlite3.connect(self.db_path)
            query = """
            SELECT geoid, year, geo_level, geo_name, state_fips, county_fips
            FROM geographic_boundaries 
            WHERE year = (SELECT MAX(year) FROM geographic_boundaries)
            ORDER BY geo_level, geoid
            """
            
            df = pd.read_sql(query, conn)
            conn.close()
            
            # Convert to dictionary for easy lookup
            boundaries = {
                'latest_year': df['year'].iloc[0] if not df.empty else None,
                'by_geoid': df.set_index('GEOID').to_dict('index'),
                'by_level': defaultdict(list)
            }
            
            # Group by geographic level
            for _, row in df.iterrows():
                level = row['GEO_LEVEL']
                boundaries['by_level'][level].append(row.to_dict())
            
            logger.info(f"Loaded {len(df)} geographic boundary records")
            return boundaries
            
        except Exception as e:
            logger.error(f"Error fetching geographic boundaries: {e}")
            return {}
    
    def align_survey_with_geographic_boundaries(self, metadata: SurveyMetadata, df: pd.DataFrame) -> Dict[str, Any]:
        """Align survey data with geographic boundaries database."""
        logger.info(f"Aligning {metadata.survey_code}/{metadata.dataset_name} with geographic boundaries")
        
        if not self.geographic_boundaries:
            self.geographic_boundaries = self.get_geographic_boundaries_from_db()
        
        alignment_results = {
            'survey_metadata': asdict(metadata),
            'alignment_status': 'no_geographic_columns',
            'matched_geoids': [],
            'unmatched_geoids': [],
            'coverage_analysis': {},
            'recommendations': []
        }
        
        # Find geographic columns in the data
        geo_columns = [col for col in df.columns if any(geo_term in col.upper() 
                       for geo_term in ['GEOID', 'GEO_ID', 'STATEFP', 'COUNTYFP'])]
        
        if not geo_columns:
            alignment_results['recommendations'].append(
                "No geographic identifier columns found in survey data"
            )
            return alignment_results
        
        alignment_results['alignment_status'] = 'geographic_columns_found'
        
        # Try to match with database boundaries
        for geo_col in geo_columns:
            if geo_col not in df.columns:
                continue
                
            survey_geoids = set(df[geo_col].dropna().astype(str).unique())
            db_geoids = set(self.geographic_boundaries.get('by_geoid', {}).keys())
            
            matched = survey_geoids.intersection(db_geoids)
            unmatched = survey_geoids - db_geoids
            
            alignment_results['matched_geoids'].extend(list(matched))
            alignment_results['unmatched_geoids'].extend(list(unmatched))
            
            # Coverage analysis
            coverage_rate = len(matched) / len(survey_geoids) * 100 if survey_geoids else 0
            alignment_results['coverage_analysis'][geo_col] = {
                'survey_geoids_count': len(survey_geoids),
                'matched_geoids_count': len(matched),
                'coverage_rate': round(coverage_rate, 2),
                'db_latest_year': self.geographic_boundaries.get('latest_year')
            }
        
        # Generate recommendations
        for geo_col, analysis in alignment_results['coverage_analysis'].items():
            if analysis['coverage_rate'] < 80:
                alignment_results['recommendations'].append(
                    f"Low coverage ({analysis['coverage_rate']}%) for {geo_col} - check year compatibility"
                )
        
        if alignment_results['unmatched_geoids']:
            alignment_results['recommendations'].append(
                f"Found {len(alignment_results['unmatched_geoids'])} unmatched GEOIDs - verify data quality"
            )
        
        return alignment_results
    
    def prepare_for_geographic_data_table(self, metadata: SurveyMetadata, df: pd.DataFrame, 
                                        documentation: Dict[str, Any]) -> pd.DataFrame:
        """Prepare survey data for upload to public.geographic_data table."""
        logger.info(f"Preparing {metadata.survey_code}/{metadata.dataset_name} for geographic_data table")
        
        # Find the best geographic identifier column
        geoid_column = self._find_best_geoid_column(df, metadata.geographic_columns)
        
        if not geoid_column:
            logger.warning("No suitable GEOID column found for geographic_data table")
            return pd.DataFrame()
        
        # Create base geographic_data structure
        geo_df = pd.DataFrame()
        
        # Core geographic_data table columns
        geo_df['geoid'] = df[geoid_column].astype(str)
        geo_df['year'] = metadata.year or self._extract_year_from_data(df)
        geo_df['survey_code'] = metadata.survey_code
        geo_df['dataset_name'] = metadata.dataset_name
        geo_df['geo_level'] = metadata.geo_coverage or 'unknown'
        
        # Add survey metadata
        geo_df['methodology'] = documentation.get('methodology', '')[:500]  # Truncate if needed
        geo_df['taxonomy'] = documentation.get('taxonomy', '')[:500]
        
        # Add data columns (exclude already used geographic columns)
        data_columns = [col for col in df.columns 
                       if col not in [geoid_column] + metadata.geographic_columns]
        
        # Map column definitions from documentation
        column_definitions = documentation.get('column_definitions', {})
        
        for col in data_columns:
            # Get column description from docs if available
            col_def = column_definitions.get(col.upper())
            if col_def:
                # Store as JSON to preserve structure
                col_info = {
                    'description': col_def.description,
                    'data_type': col_def.data_type,
                    'measurement_unit': col_def.measurement_unit
                }
                geo_df[f'{col}_meta'] = [json.dumps(col_info)] * len(geo_df)
            else:
                geo_df[f'{col}_meta'] = [json.dumps({'description': f'Survey data column: {col}'})] * len(geo_df)
            
            # Store actual data
            geo_df[col] = df[col]
        
        # Add quality metrics
        geo_df['data_quality_score'] = self._calculate_data_quality_score(df)
        geo_df['processing_timestamp'] = datetime.now().isoformat()
        
        # Remove duplicates and sort
        geo_df = geo_df.drop_duplicates(subset=['geoid', 'year', 'survey_code'])
        geo_df = geo_df.sort_values(['geoid', 'year'])
        
        logger.info(f"Prepared {len(geo_df)} records for geographic_data table")
        return geo_df
    
    def _find_best_geoid_column(self, df: pd.DataFrame, geo_columns: List[str]) -> Optional[str]:
        """Find the best GEOID column for geographic alignment."""
        # Priority order for geographic identifiers
        priority_patterns = [
            'GEOID', 'GEO_ID',  # Full geographic identifiers
            'COUNTYFP', 'STATEFP',  # FIPS codes
            'TRACTCE', 'BLOCKCE'  # Census codes
        ]
        
        # Check for exact matches first
        for pattern in priority_patterns:
            for col in geo_columns:
                if pattern in col.upper():
                    return col
        
        # Check for partial matches
        for col in geo_columns:
            if any(term in col.upper() for term in ['GEO', 'FIPS', 'ID']):
                return col
        
        return None
    
    def _extract_year_from_data(self, df: pd.DataFrame) -> Optional[int]:
        """Extract year from data if not in metadata."""
        # Try column names
        for col in df.columns:
            year_match = re.search(r'20\d{2}|19\d{2}', str(col))
            if year_match:
                year = int(year_match.group())
                if 1990 <= year <= 2030:
                    return year
        
        # Default to current year if nothing found
        return datetime.now().year
    
    def _calculate_data_quality_score(self, df: pd.DataFrame) -> List[float]:
        """Calculate data quality score for each row."""
        scores = []
        
        for idx in range(len(df)):
            row = df.iloc[idx]
            # Calculate completeness (percentage of non-null values)
            completeness = row.count() / len(row) * 100
            
            # Calculate consistency (check for obvious outliers or errors)
            consistency_score = 100  # Start with perfect score
            
            # Check for suspicious patterns
            numeric_cols = df.select_dtypes(include=['number']).columns
            for col in numeric_cols:
                val = row[col]
                if not pd.isna(val):
                    try:
                        val_num = float(val)
                        # Check for negative values where they don't make sense
                        if col.upper() in ['POP', 'POPULATION', 'COUNT', 'TOTAL'] and val_num < 0:
                            consistency_score -= 10
                        # Check for extremely large values
                        if abs(val_num) > 1e9:  # Values over 1 billion
                            consistency_score -= 5
                    except (ValueError, TypeError):
                        pass  # Not a numeric value, skip checks
            
            # Combine scores
            final_score = (completeness * 0.7 + consistency_score * 0.3)
            scores.append(max(0, min(100, final_score)))  # Clamp between 0-100
        
        return scores
    
    def generate_upload_sql(self, geo_df: pd.DataFrame, table_name: str = 'public.geographic_data') -> str:
        """Generate SQL statements for uploading to geographic_data table."""
        if geo_df.empty:
            return "-- No data to upload"
        
        # Get column names
        columns = list(geo_df.columns)
        
        # Generate INSERT statements in batches
        sql_statements = []
        batch_size = 1000
        
        sql_statements.append(f"-- Insert data into {table_name}")
        sql_statements.append(f"-- Generated: {datetime.now().isoformat()}")
        sql_statements.append("")
        
        # CREATE TABLE statement (if needed)
        sql_statements.append(f"-- Table structure for {table_name}")
        sql_statements.append("""
        CREATE TABLE IF NOT EXISTS public.geographic_data (
            id SERIAL PRIMARY KEY,
            geoid VARCHAR(50) NOT NULL,
            year INTEGER NOT NULL,
            survey_code VARCHAR(50) NOT NULL,
            dataset_name VARCHAR(100),
            geo_level VARCHAR(20),
            methodology TEXT,
            taxonomy TEXT,
            data_quality_score FLOAT,
            processing_timestamp TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(geoid, year, survey_code)
        );
        """)
        
        # Prepare INSERT statements
        sql_statements.append(f"-- Data insertion for {len(geo_df)} records")
        sql_statements.append("BEGIN;")
        
        for i in range(0, len(geo_df), batch_size):
            batch = geo_df.iloc[i:i+batch_size]
            
            # Convert batch to values
            values = []
            for _, row in batch.iterrows():
                row_values = []
                for col in columns:
                    val = row[col]
                    if pd.isna(val):
                        row_values.append('NULL')
                    elif isinstance(val, str):
                        # Escape single quotes in strings
                        escaped_val = val.replace("'", "''")
                        row_values.append(f"'{escaped_val}'")
                    else:
                        row_values.append(str(val))
                values.append(f"({', '.join(row_values)})")
            
            # Create INSERT statement
            insert_sql = f"""
            INSERT INTO {table_name} ({', '.join(columns)})
            VALUES {', '.join(values)}
            ON CONFLICT (geoid, year, survey_code) 
            DO UPDATE SET 
                dataset_name = EXCLUDED.dataset_name,
                geo_level = EXCLUDED.geo_level,
                methodology = EXCLUDED.methodology,
                taxonomy = EXCLUDED.taxonomy,
                data_quality_score = EXCLUDED.data_quality_score,
                processing_timestamp = EXCLUDED.processing_timestamp;
            """
            sql_statements.append(insert_sql)
        
        sql_statements.append("COMMIT;")
        sql_statements.append("")
        sql_statements.append(f"-- Total records: {len(geo_df)}")
        sql_statements.append(f"-- Batches: {(len(geo_df) // batch_size) + 1}")
        
        return '\n'.join(sql_statements)

def main():
    """Main function to demonstrate survey parsing and geographic alignment."""
    # Get the repository root directory
    current_file = Path(__file__).resolve()
    repo_root = current_file.parent.parent
    data_dir = repo_root / 'data'
    
    parser = SurveyDataParser(str(data_dir))
    
    # Step 1: Scan and catalog all surveys
    print("=== Step 1: Scanning and Cataloging Surveys ===")
    catalog = parser.scan_and_catalog_surveys()
    
    if not catalog:
        print("No survey data found. Please run get_census_survey.py first.")
        return
    
    print(f"Found {len(catalog)} survey datasets:")
    for metadata in catalog:
        print(f"  {metadata.survey_code}/{metadata.dataset_name}: {metadata.file_type} "
              f"({metadata.column_count} cols, {len(metadata.geographic_columns)} geo cols)")
    
    # Step 2: Extract documentation for first survey
    print(f"\n=== Step 2: Extracting Documentation ===")
    first_survey = catalog[0]
    documentation = parser.extract_documentation(first_survey.survey_code, first_survey.dataset_name)
    
    print(f"Documentation for {first_survey.survey_code}/{first_survey.dataset_name}:")
    print(f"  Source files: {len(documentation['source_files'])}")
    print(f"  Column definitions: {len(documentation['column_definitions'])}")
    print(f"  Methodology length: {len(documentation['methodology'])} chars")
    
    # Step 3: Preprocess data
    print(f"\n=== Step 3: Preprocessing Data ===")
    df = parser.preprocess_data_file(first_survey)
    if not df.empty:
        print(f"Loaded data: {len(df)} rows, {len(df.columns)} columns")
        print(f"Sample columns: {list(df.columns)[:10]}")
    else:
        print("Failed to load data")
        return
    
    # Step 4: Geographic alignment
    print(f"\n=== Step 4: Geographic Alignment ===")
    alignment = parser.align_survey_with_geographic_boundaries(first_survey, df)
    
    print(f"Alignment status: {alignment['alignment_status']}")
    print(f"Coverage analysis: {alignment['coverage_analysis']}")
    if alignment['recommendations']:
        print("Recommendations:")
        for rec in alignment['recommendations']:
            print(f"  - {rec}")

if __name__ == "__main__":
    main()