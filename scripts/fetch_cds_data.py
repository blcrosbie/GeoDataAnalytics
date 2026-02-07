#!/usr/bin/env python3
"""
Climate Data Store (CDS) Weather Data Fetcher
Fetches weather and climate data from CDS and stores to S3/Wasabi
"""

import os
import sys
import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import logging

import cdsapi
import boto3
import xarray as xr
import pandas as pd
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class CDSDataFetcher:
    def __init__(self):
        load_dotenv()
        
        # CDS Configuration
        self.cds_url = os.getenv('CDS_URL', 'https://cds.climate.copernicus.eu/api/v2')
        self.cds_key = os.getenv('CDS_KEY')
        if not self.cds_key:
            raise ValueError("CDS_KEY environment variable is required")
        
        # S3 Configuration
        self.s3_client = boto3.client(
            's3',
            endpoint_url=os.getenv('S3_ENDPOINT_URL'),
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
            region_name=os.getenv('AWS_DEFAULT_REGION', 'us-east-1')
        )
        self.bucket_name = os.getenv('S3_BUCKET_NAME')
        
        # Initialize CDS client
        self.cds_client = cdsapi.Client(url=self.cds_url, key=self.cds_key)
        
    def get_s3_path(self, source: str, dataset: str, year: str, month: str, filename: str) -> str:
        """Generate S3 key for storing data"""
        return f"copernicus/raw/source={source}/dataset={dataset}/year={year}/month={month}/{filename}"
    
    def store_manifest(self, request_key: str, manifest_data: Dict):
        """Store request manifest to S3"""
        manifest_key = f"copernicus/manifests/request_key={request_key}.json"
        self.s3_client.put_object(
            Bucket=self.bucket_name,
            Key=manifest_key,
            Body=json.dumps(manifest_data, indent=2, default=str)
        )
        logger.info(f"Stored manifest: {manifest_key}")
    
    def store_provenance(self, request_key: str, provenance_data: Dict):
        """Store provenance data to S3"""
        provenance_key = f"copernicus/provenance/request_key={request_key}.json"
        self.s3_client.put_object(
            Bucket=self.bucket_name,
            Key=provenance_key,
            Body=json.dumps(provenance_data, indent=2, default=str)
        )
        logger.info(f"Stored provenance: {provenance_key}")
    
    def fetch_era5_pressure_levels(self, 
                                   variables: List[str],
                                   year: str,
                                   month: str,
                                   days: List[str],
                                   hours: List[str],
                                   pressure_levels: List[str],
                                   area: Optional[Tuple[float, float, float, float]] = None) -> str:
        """
        Fetch ERA5 pressure level data
        
        Args:
            variables: List of variables (e.g., ['geopotential', 'temperature'])
            year: Year string (e.g., '2024')
            month: Month string (e.g., '03')
            days: List of days (e.g., ['01', '02'])
            hours: List of hours (e.g., ['00:00', '06:00', '12:00', '18:00'])
            pressure_levels: List of pressure levels (e.g., ['1000', '850', '500'])
            area: Bounding box (North, West, South, East)
        
        Returns:
            S3 path of stored file
        """
        dataset = 'reanalysis-era5-pressure-levels'
        
        request = {
            'product_type': ['reanalysis'],
            'variable': variables,
            'year': [year],
            'month': [month],
            'day': days,
            'time': hours,
            'pressure_level': pressure_levels,
            'data_format': 'netcdf',
        }
        
        if area:
            request['area'] = area
        
        # Generate request key for tracking
        request_str = json.dumps(request, sort_keys=True)
        request_key = hashlib.sha256(request_str.encode()).hexdigest()[:16]
        
        filename = f"era5_pressure_levels_{year}{month}_{request_key}.nc"
        s3_path = self.get_s3_path('cds', dataset, year, month, filename)
        
        # Check if file already exists
        try:
            self.s3_client.head_object(Bucket=self.bucket_name, Key=s3_path)
            logger.info(f"File already exists: {s3_path}")
            return s3_path
        except:
            logger.info(f"Fetching new data for {dataset}")
        
        # Fetch data from CDS
        try:
            result = self.cds_client.retrieve(dataset, request, filename)
            logger.info(f"CDS request completed: {result}")
            
            # Upload to S3
            self.s3_client.upload_file(filename, self.bucket_name, s3_path)
            logger.info(f"Uploaded to S3: {s3_path}")
            
            # Store manifest
            manifest = {
                'dataset': dataset,
                'request': request,
                'filename': filename,
                's3_path': s3_path,
                'request_key': request_key,
                'fetched_at': datetime.utcnow().isoformat(),
                'file_size': os.path.getsize(filename)
            }
            self.store_manifest(request_key, manifest)
            
            # Store provenance
            provenance = {
                'source': 'cds',
                'dataset': dataset,
                'request_key': request_key,
                'fetch_timestamp': datetime.utcnow().isoformat(),
                'processing_stage': 'raw',
                'data_format': 'netcdf',
                'access_method': 'cdsapi'
            }
            self.store_provenance(request_key, provenance)
            
            # Clean up local file
            os.remove(filename)
            
            return s3_path
            
        except Exception as e:
            logger.error(f"Error fetching {dataset}: {e}")
            raise
    
    def fetch_era5_surface(self,
                          variables: List[str],
                          year: str,
                          month: str,
                          days: List[str],
                          hours: List[str],
                          area: Optional[Tuple[float, float, float, float]] = None) -> str:
        """
        Fetch ERA5 single level (surface) data
        
        Args:
            variables: List of variables (e.g., ['2m_temperature', 'total_precipitation'])
            year: Year string
            month: Month string
            days: List of days
            hours: List of hours
            area: Bounding box (North, West, South, East)
        
        Returns:
            S3 path of stored file
        """
        dataset = 'reanalysis-era5-single-levels'
        
        request = {
            'product_type': ['reanalysis'],
            'variable': variables,
            'year': [year],
            'month': [month],
            'day': days,
            'time': hours,
            'data_format': 'netcdf',
        }
        
        if area:
            request['area'] = area
        
        # Generate request key
        request_str = json.dumps(request, sort_keys=True)
        request_key = hashlib.sha256(request_str.encode()).hexdigest()[:16]
        
        filename = f"era5_surface_{year}{month}_{request_key}.nc"
        s3_path = self.get_s3_path('cds', dataset, year, month, filename)
        
        # Check if file already exists
        try:
            self.s3_client.head_object(Bucket=self.bucket_name, Key=s3_path)
            logger.info(f"File already exists: {s3_path}")
            return s3_path
        except:
            pass
        
        # Fetch data from CDS
        try:
            result = self.cds_client.retrieve(dataset, request, filename)
            logger.info(f"CDS request completed: {result}")
            
            # Upload to S3
            self.s3_client.upload_file(filename, self.bucket_name, s3_path)
            logger.info(f"Uploaded to S3: {s3_path}")
            
            # Store manifest and provenance
            manifest = {
                'dataset': dataset,
                'request': request,
                'filename': filename,
                's3_path': s3_path,
                'request_key': request_key,
                'fetched_at': datetime.utcnow().isoformat(),
                'file_size': os.path.getsize(filename)
            }
            self.store_manifest(request_key, manifest)
            
            provenance = {
                'source': 'cds',
                'dataset': dataset,
                'request_key': request_key,
                'fetch_timestamp': datetime.utcnow().isoformat(),
                'processing_stage': 'raw',
                'data_format': 'netcdf',
                'access_method': 'cdsapi'
            }
            self.store_provenance(request_key, provenance)
            
            # Clean up local file
            os.remove(filename)
            
            return s3_path
            
        except Exception as e:
            logger.error(f"Error fetching {dataset}: {e}")
            raise

def main():
    """Example usage"""
    fetcher = CDSDataFetcher()
    
    # Example: Fetch recent temperature and precipitation data
    try:
        # Surface data for dashboard
        s3_path = fetcher.fetch_era5_surface(
            variables=['2m_temperature', 'total_precipitation', 'mean_sea_level_pressure'],
            year='2024',
            month='12',
            days=[str(d).zfill(2) for d in range(1, 32)],  # All days in December
            hours=['00:00', '06:00', '12:00', '18:00'],
            area=(50, -130, 20, -60)  # North America
        )
        print(f"Surface data stored: {s3_path}")
        
        # Pressure level data for analysis
        s3_path = fetcher.fetch_era5_pressure_levels(
            variables=['geopotential', 'temperature', 'u_component_of_wind', 'v_component_of_wind'],
            year='2024',
            month='12',
            days=['01', '15'],  # Sample days
            hours=['00:00', '12:00'],
            pressure_levels=['1000', '850', '500', '250'],
            area=(50, -130, 20, -60)  # North America
        )
        print(f"Pressure level data stored: {s3_path}")
        
    except Exception as e:
        logger.error(f"Error in main: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()