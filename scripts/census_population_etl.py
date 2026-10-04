#!/usr/bin/env python3
"""
Census Population Data ETL
ETLs population and housing data from Wasabi S3 to PostgreSQL database.
Uses questionary TUI for interactive prompts.
"""

import os
import io
import json
import tempfile
import zipfile
from datetime import datetime
from typing import Dict, List, Optional, Any
from decimal import Decimal
import re

import boto3
from botocore.config import Config
from dotenv import load_dotenv

try:
    import questionary
except ImportError:
    print("'questionary' library is required for the interactive prompt.")
    print("Please install it using: pip install questionary")
    exit(1)

from sqlalchemy import (
    Column, String, Integer, DateTime, Double, Text, DECIMAL, Date, 
    ForeignKey, ForeignKeyConstraint, create_engine
)
from sqlalchemy import insert
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.dialects.postgresql import UUID
from geoalchemy2 import WKTElement
import shapefile

load_dotenv()


class Base(DeclarativeBase):
    pass


class GeographicDataModel(Base):
    __tablename__ = "geographic_data"
    __table_args__ = {"schema": "public"}

    id = Column(Integer, primary_key=True, autoincrement=True)
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
    created_at = Column(DateTime(timezone=True), server_default='now()')
    updated_at = Column(DateTime(timezone=True), server_default='now()', onupdate='now()')

    __table_args__ = (
        ForeignKeyConstraint(
            ['geoid', 'year'], 
            ['public.geographic_boundaries.geoid', 'public.geographic_boundaries.year'],
            ondelete='CASCADE'
        ),
        {"schema": "public"}
    )


class CensusS3ETL:
    def __init__(self):
        self.s3_client = boto3.client(
            's3',
            endpoint_url=os.getenv('S3_ENDPOINT_URL', 'https://s3.us-east-1.wasabisys.com'),
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
            region_name=os.getenv('AWS_DEFAULT_REGION', 'us-east-1'),
            config=Config(signature_version='s3v4')
        )
        self.bucket_name = os.getenv('S3_BUCKET_NAME', 'geoagent-dev-s3')
        
        db_host = os.getenv('POSTGRES_HOST', 'localhost')
        self.db_connection_string = (
            f"postgresql://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}"
            f"@{db_host}:5432/{os.getenv('POSTGRES_DB')}"
        )
        self.engine = create_engine(self.db_connection_string)
        self.Session = sessionmaker(bind=self.engine)

    def list_s3_tree(self, prefix: str, max_keys: int = 1000) -> List[Dict]:
        """List all objects under a prefix with their full paths."""
        try:
            paginator = self.s3_client.get_paginator('list_objects_v2')
            objects = []
            
            for page in paginator.paginate(Bucket=self.bucket_name, Prefix=prefix, MaxKeys=max_keys):
                for obj in page.get('Contents', []):
                    objects.append({
                        'key': obj['Key'],
                        'size': obj['Size'],
                        'last_modified': obj['LastModified']
                    })
            
            return objects
        except Exception as e:
            print(f"Error listing S3 objects with prefix {prefix}: {e}")
            return []

    def download_s3_content(self, s3_key: str) -> Optional[bytes]:
        """Download file content from S3."""
        try:
            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=s3_key)
            return response['Body'].read()
        except Exception as e:
            print(f"Error downloading {s3_key}: {e}")
            return None

    def parse_population_csv(self, content: bytes, filename: str) -> List[Dict]:
        """Parse census population CSV file into geographic_data records."""
        records = []
        
        try:
            import csv
            text_content = content.decode('utf-8', errors='replace')
            reader = csv.DictReader(io.StringIO(text_content))
            
            for row in reader:
                geoid = row.get('GEOID') or row.get('GEO_ID') or row.get(' geography ')
                if not geoid:
                    continue
                
                geoid = geoid.strip()
                year = self.extract_year_from_filename(filename)
                
                for key, value in row.items():
                    if key in ['GEOID', 'GEO_ID', ' geography ', 'NAME', 'Geographic Area Name']:
                        continue
                    
                    if value is None or value.strip() == '':
                        continue
                    
                    value = value.strip()
                    
                    numeric_value = None
                    data_type = 'text'
                    
                    try:
                        cleaned = value.replace(',', '').replace('$', '').replace('%', '')
                        if cleaned.replace('.', '').replace('-', '').isdigit():
                            numeric_value = Decimal(cleaned)
                            data_type = 'numeric'
                    except:
                        pass
                    
                    records.append({
                        'geoid': geoid,
                        'year': year,
                        'attribute_key': key.lower().strip(),
                        'attribute_value': value,
                        'numeric_value': numeric_value,
                        'data_type': data_type,
                        'source': f'Census Population {year}',
                        'collection_date': datetime(year, 1, 1).date() if year else None
                    })
                    
        except Exception as e:
            print(f"Error parsing CSV {filename}: {e}")
            
        return records

    def parse_population_txt(self, content: bytes, filename: str) -> List[Dict]:
        """Parse census population TXT file into geographic_data records."""
        records = []
        
        try:
            import csv
            text_content = content.decode('utf-8', errors='replace')
            reader = csv.DictReader(io.StringIO(text_content), delimiter='|')
            
            for row in reader:
                geoid = row.get('GEOID') or row.get('GEO_ID') or row.get('GEO_ID_F')
                if not geoid:
                    continue
                    
                geoid = str(geoid).strip()
                year = self.extract_year_from_filename(filename)
                
                for key, value in row.items():
                    if key in ['GEOID', 'GEO_ID', 'GEO_ID_F', 'NAME', 'GEO Display']:
                        continue
                    
                    if value is None or str(value).strip() == '':
                        continue
                    
                    value = str(value).strip()
                    
                    numeric_value = None
                    data_type = 'text'
                    
                    try:
                        cleaned = value.replace(',', '').replace('$', '').replace('%', '')
                        if cleaned.replace('.', '').replace('-', '').isdigit():
                            numeric_value = Decimal(cleaned)
                            data_type = 'numeric'
                    except:
                        pass
                    
                    records.append({
                        'geoid': geoid,
                        'year': year,
                        'attribute_key': key.lower().strip(),
                        'attribute_value': value,
                        'numeric_value': numeric_value,
                        'data_type': data_type,
                        'source': f'Census Population {year}',
                        'collection_date': datetime(year, 1, 1).date() if year else None
                    })
                    
        except Exception as e:
            print(f"Error parsing TXT {filename}: {e}")
            
        return records

    def extract_year_from_filename(self, filename: str) -> int:
        """Extract year from filename."""
        import re
        year_match = re.search(r'(19|20)\d{2}', filename)
        if year_match:
            return int(year_match.group())
        return datetime.now().year

    def load_to_database(self, records: List[Dict]) -> Dict[str, int]:
        """Load records to geographic_data table."""
        if not records:
            return {'inserted': 0, 'skipped': 0, 'errors': 0}
        
        inserted = 0
        skipped = 0
        errors = 0
        
        batch_size = 100
        for i in range(0, len(records), batch_size):
            batch = records[i:i + batch_size]
            session = self.Session()
            
            try:
                session.execute(insert(GeographicDataModel), batch)
                session.commit()
                inserted += len(batch)
            except Exception as e:
                session.rollback()
                if 'duplicate key' in str(e).lower():
                    skipped += len(batch)
                else:
                    errors += len(batch)
                    for record in batch:
                        ind_session = None
                        try:
                            ind_session = self.Session()
                            ind_session.execute(insert(GeographicDataModel), [record])
                            ind_session.commit()
                            inserted += 1
                        except Exception as ind_e:
                            if ind_session:
                                ind_session.rollback()
                            if 'duplicate key' not in str(ind_e).lower():
                                errors += 1
                        finally:
                            if ind_session:
                                ind_session.close()
            finally:
                session.close()
        
        return {'inserted': inserted, 'skipped': skipped, 'errors': errors}

    def process_census_surveys(self, file_keys: List[str]) -> Dict[str, int]:
        """Process census_surveys files (csv, txt)."""
        stats = {'files_processed': 0, 'total_records': 0, 'inserted': 0, 'skipped': 0, 'errors': 0}
        
        for key in file_keys:
            filename = os.path.basename(key)
            ext = filename.split('.')[-1].lower()
            
            print(f"Processing: {key}")
            
            content = self.download_s3_content(key)
            if not content:
                continue
            
            records = []
            if ext == 'csv':
                records = self.parse_population_csv(content, filename)
            elif ext == 'txt':
                records = self.parse_population_txt(content, filename)
            
            if records:
                result = self.load_to_database(records)
                stats['total_records'] += len(records)
                stats['inserted'] += result['inserted']
                stats['skipped'] += result['skipped']
                stats['errors'] += result['errors']
                stats['files_processed'] += 1
                
                print(f"  -> {len(records)} records, inserted: {result['inserted']}, skipped: {result['skipped']}")
        
        return stats

    def run(self):
        """Main execution method with TUI prompts."""
        print("=" * 60)
        print("Census Population Data ETL")
        print("=" * 60)
        
        print("\n1. Connecting to S3 and listing files...")
        
        census_files = self.list_s3_tree('origin/census/')
        census_surveys_files = self.list_s3_tree('origin/census_surveys/')
        
        print(f"   Found {len(census_files)} files in origin/census/")
        print(f"   Found {len(census_surveys_files)} files in origin/census_surveys/")
        
        csv_txt_files = [
            f['key'] for f in census_surveys_files 
            if f['key'].endswith('.csv') or f['key'].endswith('.txt')
        ]
        
        if not csv_txt_files:
            print("No CSV/TXT files found in census_surveys/")
            return
        
        print(f"\n2. Found {len(csv_txt_files)} CSV/TXT files:")
        for f in csv_txt_files[:10]:
            print(f"   - {f}")
        if len(csv_txt_files) > 10:
            print(f"   ... and {len(csv_txt_files) - 10} more")
        
        selected_files = questionary.checkbox(
            "Select files to process (space to toggle, enter to confirm):",
            choices=csv_txt_files
        ).ask()
        
        if not selected_files:
            print("No files selected. Exiting.")
            return
        
        print(f"\n3. Processing {len(selected_files)} files...")
        
        stats = self.process_census_surveys(selected_files)
        
        print("\n" + "=" * 60)
        print("ETL Complete")
        print("=" * 60)
        print(f"Files processed: {stats['files_processed']}")
        print(f"Total records: {stats['total_records']}")
        print(f"Inserted: {stats['inserted']}")
        print(f"Skipped (duplicates): {stats['skipped']}")
        print(f"Errors: {stats['errors']}")


def main():
    etl = CensusS3ETL()
    etl.run()


if __name__ == "__main__":
    main()
