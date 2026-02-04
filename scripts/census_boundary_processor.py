#!/usr/bin/env python3
"""
Census Boundary Data Processor
Extracts and normalizes census boundary shapefiles for upload to PostgreSQL database.
"""

import os
import zipfile
import shapefile
import json
from datetime import datetime
from typing import Dict, List, Tuple, Any


from sqlalchemy import (
    BigInteger, Column, String, Integer, DateTime, Double, Text, func, JSON, 
    DECIMAL, Date, ForeignKey, ForeignKeyConstraint
)
from sqlalchemy import create_engine, text, select, insert
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.types import TypeDecorator, VARCHAR
from sqlalchemy.dialects.postgresql import UUID, JSONB
from geoalchemy2 import Geometry, WKTElement
from geoalchemy2.shape import to_shape, from_shape
from sqlalchemy.exc import DataError
from tqdm import tqdm     # optional progress bar

class Base(DeclarativeBase):
    pass


class GeographicBoundaryModel(Base):
    __tablename__ = "geographic_boundaries"
    __table_args__ = {"schema": "public"}

    geoid = Column(String(64), primary_key=True)
    year = Column(Integer, primary_key=True)
    
    name = Column(String(255), nullable=False)
    
    # Define as GEOMETRY to match your Postgres definition
    geom = Column(Geometry(geometry_type='GEOMETRY', srid=4326))
    boundary_type = Column(String(64), nullable=False)
    boundary_subtype = Column(String(64))
    country = Column(String(3))
    source = Column(String(255))
    accuracy_meters = Column(DECIMAL(10, 2))
    validity_start_date = Column(Date)
    validity_end_date = Column(Date)
    layer_id = Column(UUID(as_uuid=True))
    source_upload_id = Column(UUID(as_uuid=True))
    last_updated = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class GeographicDataModel(Base):
    __tablename__ = "geographic_data"
    __table_args__ = {"schema": "public"}

    id = Column(BigInteger, primary_key=True)
    geoid = Column(String(64), nullable=False)
    year = Column(Integer, nullable=False)
    attribute_key = Column(String(128), nullable=False)
    attribute_value = Column(Text)
    numeric_value = Column(DECIMAL(20, 8))
    data_type = Column(String(32), nullable=False, default='text')
    source = Column(String(128))
    collection_date = Column(Date)
    confidence_level = Column(String(32))
    layer_id = Column(UUID(as_uuid=True))
    source_upload_id = Column(UUID(as_uuid=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Foreign key to geographic_boundaries
    __table_args__ = (
        ForeignKeyConstraint(['geoid', 'year'], ['public.geographic_boundaries.geoid', 'public.geographic_boundaries.year'], 
                            ondelete='CASCADE'),
        {"schema": "public"}
    )


def get_boundary_subtype_from_name(NAME, NAMELSAD):
    if NAME.endswith('(balance)'):
        return 'balance'
        
    elif NAME.endswith('County'):
        return 'county'
    
    last_word = NAMELSAD[len(NAME):].strip()
    # print(last_word)

    if last_word == '' or last_word == 'CDP':
        return 'census_designated_place'

    # ['(state)_reservation',
    #  'reservation',
    #  'indian_reservation',
    #  'rancheria',
    #  'census_designated_place',
    #  'colony',
    #  'pueblo',
    #  'indian_rancheria',
    #  'f_pojoaque',
    #  'indian_colony',
    #  'community',
    #  'indian_community',
    #  'reserve',
    #  'ranch',
    #  'village',
    #  'de_cochiti',
    #  'indian_village',
    #  'settlement',
    #  'trust_land',
    #  'off-reservation_trust_land',
    #  'hawaiian_home_land',
    #  'anvsa',
    #  'otsa',
    #  'sdtsa',
    #  'tdsa',
    #  'joint-use_otsa',
    #  'joint-use_area']

    if last_word.startswith('(state)'):
        last_word = last_word.replace('(', '')
        last_word = last_word.replace(')', '')

    if '-' in last_word:
        last_word = last_word.replace('-', '_')

    # sanitize
    clean_last_word = last_word.strip().lower()
    clean_last_word = clean_last_word.replace(' ', '_')   
        
    return clean_last_word



class CensusBoundaryProcessor:
    def __init__(self, data_dir: str, db_connection_string: str):
        self.data_dir = data_dir
        self.db_connection_string = db_connection_string
        self.engine = create_engine(db_connection_string)
        self.Session = sessionmaker(bind=self.engine)
        
    def create_tables(self):
        """Create database tables if they don't exist."""
        Base.metadata.create_all(self.engine)
        print("Database tables created successfully")
        
    def get_census_files(self, year: int) -> List[str]:
        """Get list of census zip files for a given year."""
        year_dir = os.path.join(self.data_dir, str(year))
        if not os.path.exists(year_dir):
            raise FileNotFoundError(f"Directory {year_dir} not found")
        
        files = []
        for file in os.listdir(year_dir):
            if file.endswith('.zip'):
                files.append(os.path.join(year_dir, file))
        return sorted(files)
    
    def extract_shapefile(self, zip_path: str, extract_dir: str) -> str:
        """Extract shapefile from zip and return the path to .shp file."""
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_dir)
        
        # Find the .shp file
        for file in os.listdir(extract_dir):
            if file.endswith('.shp'):
                return os.path.join(extract_dir, file)
        
        raise FileNotFoundError(f"No .shp file found in {zip_path}")
    
    def parse_filename(self, filename: str) -> Dict[str, str]:
        """Parse census filename to extract metadata."""
        # Example: tl_2020_01_place.zip -> year=2020, statefp=01, layer=place
        parts = os.path.basename(filename).replace('.zip', '').split('_')
        if len(parts) >= 4:
            return {
                'year': parts[1],
                'statefp': parts[2],
                'layer': parts[3],
                'full_filename': os.path.basename(filename)
            }
        return {}
    
    def normalize_record(self, record: Tuple, fields: List, metadata: Dict, geometry) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """Normalize shapefile record to match database schema."""
        # Create field mapping
        field_dict = {}
        for i, field in enumerate(fields[1:]):  # Skip first deletion field
            field_dict[field[0]] = record[i]
        
        # Extract basic info
        geoid = field_dict.get('GEOID', '')
        year = int(metadata['year'])
        name = field_dict.get('NAME', '')
        boundary_type = metadata['layer'].upper()  # Derived from filename
        
        # Use the get_boundary_subtype_from_name function with NAME and NAMELSAD
        boundary_subtype = None
        if 'NAME' in field_dict and 'NAMELSAD' in field_dict:
            boundary_subtype = get_boundary_subtype_from_name(
                field_dict['NAME'], 
                field_dict['NAMELSAD']
            )
        
        # Get state FIPS code
        country = 'US'  # All TIGER data is US
        source = f"Census TIGER/Line {metadata['year']}"
        
        # Calculate accuracy (estimate based on Census documentation)
        accuracy_meters = 7.62 if year >= 2020 else 15.24  # 25ft for 2020+, 50ft for older
        
        # Create individual attribute records for geographic_data table
        attribute_records = []
        attributes_dict = {
            'statefp': field_dict.get('STATEFP', ''),
            'placefp': field_dict.get('PLACEFP', ''),
            'placens': field_dict.get('PLACENS', ''),
            'classfp': field_dict.get('CLASSFP', ''),
            'mtfcc': field_dict.get('MTFCC', ''),
            'funcstat': field_dict.get('FUNCSTAT', ''),
            'aland': field_dict.get('ALAND', 0),
            'awater': field_dict.get('AWATER', 0),
            'intptlat': field_dict.get('INTPTLAT', ''),
            'intptlon': field_dict.get('INTPTLON', ''),
            'source_file': metadata['full_filename'],
            'census_year': metadata['year']
        }
        
        if 'GEOIDFQ' in field_dict:
            attributes_dict['geoidfq'] = field_dict['GEOIDFQ']
        
        # Convert each attribute to individual records
        for key, value in attributes_dict.items():
            if value is not None and value != '':
                # Determine data type
                data_type = 'text'
                numeric_value = None
                if isinstance(value, (int, float)) or (isinstance(value, str) and value.isdigit()):
                    try:
                        numeric_value = float(value)
                        data_type = 'numeric'
                    except ValueError:
                        data_type = 'text'
                
                attribute_records.append({
                    'geoid': geoid,
                    'year': year,
                    'attribute_key': key,
                    'attribute_value': str(value),
                    'numeric_value': numeric_value,
                    'data_type': data_type,
                    'source': source,
                    'collection_date': datetime(year, 1, 1).date()
                })
        
        boundary_record = {
            'geoid': geoid,
            'year': year,
            'name': name,
            'geom': geometry,
            'boundary_type': boundary_type,
            'boundary_subtype': boundary_subtype,
            'country': country,
            'source': source,
            'accuracy_meters': accuracy_meters,
            'validity_start_date': datetime(year, 1, 1).date(),
            'validity_end_date': datetime(year, 12, 31).date()
        }
        
        return boundary_record, attribute_records
    
    def process_shapefile(self, shp_path: str, metadata: Dict) -> List[Tuple[Dict[str, Any], List[Dict[str, Any]]]]:
        """Process a single shapefile and return normalized records."""
        try:
            # Open shapefile with explicit encoding to handle non-UTF8 characters
            sf = shapefile.Reader(shp_path, encoding='latin-1')
            normalized_records = []
            
            print(f"Processing {shp_path}: {len(sf)} records")
            
            for i in range(len(sf)):
                try:
                    record = sf.record(i)
                    shape_obj = sf.shape(i)
                    
                    # Skip if record or shape is None
                    if record is None or shape_obj is None:
                        continue
                    
                    # Convert shape to WKT for PostGIS
                    if hasattr(shape_obj, 'shapeType') and shape_obj.shapeType == 5:  # Polygon
                        # Convert to GeoJSON format
                        if hasattr(shape_obj, '__geo_interface__'):
                            geometry = shape_obj.__geo_interface__
                        else:
                            continue
                    else:
                        continue  # Skip non-polygon geometries
                    
                    # Convert record to tuple if needed
                    if not isinstance(record, tuple):
                        record = tuple(record)
                    
                    boundary_record, attribute_records = self.normalize_record(record, sf.fields, metadata, geometry)
                    normalized_records.append((boundary_record, attribute_records))
                    
                except Exception as e:
                    print(f"Error processing record {i}: {e}")
                    continue
            
            sf.close()
            return normalized_records
            
        except Exception as e:
            print(f"Error processing shapefile {shp_path}: {e}")
            return []
    

    
    def load_to_database(self, records: List[Tuple[Dict[str, Any], List[Dict[str, Any]]]]):
        """Load normalized records to database using SQLAlchemy."""
        if not records:
            return
        
        # Separate boundary and attribute records
        boundary_records = []
        attribute_records = []
        
        for boundary_record, attr_records in records:
            if boundary_record.get('geom') is not None:
                boundary_records.append(boundary_record)
                # Only include attributes if boundary record is valid
                attribute_records.extend(attr_records)
        
        if not boundary_records:
            return
        
        # Convert geometry objects to WKB for PostGIS before any database operations
        processed_boundary_records = []
        for record in boundary_records:
            geom_obj = record['geom']
            if isinstance(geom_obj, dict) and 'type' in geom_obj and 'coordinates' in geom_obj:
                try:
                    # Convert from GeoJSON dict to Shapely geometry, then to PostGIS WKB
                    from shapely.geometry import shape
                    shapely_geom = shape(geom_obj)
                    # Simplify geometry to reduce size while preserving accuracy
                    simplified_geom = shapely_geom.simplify(tolerance=0.00001)
                    record['geom'] = from_shape(simplified_geom, srid=4326)
                    processed_boundary_records.append(record)
                except Exception as geom_error:
                    print(f"Error processing geometry for {record.get('geoid', 'unknown')}: {geom_error}")
                    continue
            else:
                processed_boundary_records.append(record)
        
        if not processed_boundary_records:
            return
        
        boundary_inserted = 0
        boundary_skipped = 0
        boundary_errors = 0
        successful_boundary_keys = set()
        attribute_inserted = 0
        attribute_skipped = 0
        attribute_errors = 0
        
        # Process boundary records one by one to avoid transaction cascading failures
        for record in processed_boundary_records:
            session = self.Session()
            try:
                session.execute(insert(GeographicBoundaryModel), [record])
                session.commit()
                boundary_inserted += 1
                successful_boundary_keys.add((record['geoid'], record['year']))
            except Exception as insert_error:
                session.rollback()
                if "duplicate key" in str(insert_error):
                    boundary_skipped += 1
                    successful_boundary_keys.add((record['geoid'], record['year']))
                else:
                    boundary_errors += 1
                    print(f"Error inserting boundary record {record.get('geoid', 'unknown')}: {insert_error}")
                    # Log more details for debugging
                    if 'geom' in record:
                        try:
                            print(f"  Geometry type: {type(record['geom'])}")
                            if hasattr(record['geom'], 'desc'):
                                print(f"  Geometry desc: {record['geom'].desc}")
                        except:
                            pass
            finally:
                session.close()
        
        # Process attribute records in batches for better performance
        batch_size = 100
        for i in range(0, len(attribute_records), batch_size):
            batch = attribute_records[i:i + batch_size]
            # Filter batch to only include records with successful boundary insertions
            valid_batch = [record for record in batch if (record['geoid'], record['year']) in successful_boundary_keys]
            
            if not valid_batch:
                attribute_skipped += len(batch)
                continue
                
            session = self.Session()
            try:
                session.execute(insert(GeographicDataModel), valid_batch)
                session.commit()
                attribute_inserted += len(valid_batch)
            except Exception as insert_error:
                session.rollback()
                if "duplicate key" in str(insert_error):
                    attribute_skipped += len(valid_batch)
                else:
                    attribute_errors += len(valid_batch)
                    print(f"Error inserting attribute batch: {insert_error}")
                    # Try individual inserts for this batch
                    for record in valid_batch:
                        individual_session = self.Session()
                        try:
                            individual_session.execute(insert(GeographicDataModel), [record])
                            individual_session.commit()
                            attribute_inserted += 1
                        except Exception as individual_error:
                            individual_session.rollback()
                            if "duplicate key" in str(individual_error):
                                attribute_skipped += 1
                            else:
                                attribute_errors += 1
                                print(f"  Error with individual attribute record {record.get('attribute_key', 'unknown')}: {individual_error}")
                        finally:
                            individual_session.close()
            finally:
                session.close()
        
        print(f"Boundary: {boundary_inserted} inserted, {boundary_skipped} skipped (duplicates), {boundary_errors} errors")
        print(f"Attributes: {attribute_inserted} inserted, {attribute_skipped} skipped (duplicates), {attribute_errors} errors")
    
    def process_year(self, year: int, boundary_types: List[str] | None = None):
        """Process all census files for a given year."""
        if boundary_types is None:
            boundary_types = ['place', 'tract', 'county', 'state', 'zcta520']
        
        files = self.get_census_files(year)
        print(f"Found {len(files)} files for {year}")
        
        # Filter by boundary types
        filtered_files = [f for f in files if any(bt in f for bt in boundary_types)]
        print(f"Processing {len(filtered_files)} boundary files")
        
        total_records = 0
        temp_dir = f"/tmp/census_{year}"
        os.makedirs(temp_dir, exist_ok=True)
        
        for file_path in filtered_files:
            metadata = self.parse_filename(file_path)
            if not metadata:
                continue
            
            print(f"\nProcessing {metadata['layer']} for state {metadata['statefp']}")
            
            try:
                # Extract shapefile
                extract_dir = os.path.join(temp_dir, f"extract_{metadata['statefp']}_{metadata['layer']}")
                os.makedirs(extract_dir, exist_ok=True)
                
                shp_path = self.extract_shapefile(file_path, extract_dir)
                
                # Process shapefile
                records = self.process_shapefile(shp_path, metadata)
                
                # Load to database
                if records:
                    self.load_to_database(records)
                    total_records += len(records)
                
                # Clean up
                import shutil
                shutil.rmtree(extract_dir)
                
            except Exception as e:
                print(f"Error processing {file_path}: {e}")
                continue
        
        # Clean up temp directory
        import shutil
        shutil.rmtree(temp_dir)
        
        print(f"\nCompleted {year}: {total_records} total records processed")
    
    def run(self, years: List[int] | None = None, boundary_types: List[str] | None = None):
        """Main execution method."""
        if years is None:
            years = list(range(2010,2026))
        
        if boundary_types is None:
            boundary_types = ['place', 'tract', 'county', 'state']
        

        
        for year in years:
            print(f"\n{'='*50}")
            print(f"PROCESSING YEAR {year}")
            print(f"{'='*50}")
            self.process_year(year, boundary_types)


def main():
    # Configuration
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    data_dir = "/home/jovyan/data/census"

    # Database connection using environment variables
    db_host = os.getenv('POSTGRES_HOST', 'localhost')
    db_connection_string = f"postgresql://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}@{db_host}:5432/{os.getenv('POSTGRES_DB')}"
    
    # Create processor and run
    processor = CensusBoundaryProcessor(data_dir, db_connection_string)
    
    # Create database tables first
    processor.create_tables()
    
    # Process both 2020 and 2025 data for place, tract, and county boundaries
    # processor.run(years=list(range(2010,2026)), boundary_types=['place', 'tract', 'county', 'state'])
    # processor.run(years=list(range(2010,2026)), boundary_types=['zcta520', 'cbsa', 'cd'])
    # processor.run(years=list(range(2010,2026)), boundary_types=['arealm', 'bg'])
    processor.run(years=list(range(2010,2026)), boundary_types=['sldl', 'sldu'])

    


if __name__ == "__main__":
    main()