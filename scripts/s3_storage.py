#!/usr/bin/env python3
"""
S3/Wasabi Storage Utilities for GeoDataAnalytics
Manages storage and organization of Copernicus data
"""

import os
import json
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Union
import logging

import boto3
import pyarrow as pa
import pyarrow.parquet as pq
import h3
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class S3StorageManager:
    def __init__(self):
        load_dotenv()
        
        self.s3_client = boto3.client(
            's3',
            endpoint_url=os.getenv('S3_ENDPOINT_URL'),
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
            region_name=os.getenv('AWS_DEFAULT_REGION', 'us-east-1')
        )
        self.bucket_name = os.getenv('S3_BUCKET_NAME')
        
        if not self.bucket_name:
            raise ValueError("S3_BUCKET_NAME environment variable is required")
    
    def raw_path(self, source: str, dataset: str, year: str, month: str, filename: str) -> str:
        """Generate path for raw data"""
        return f"copernicus/raw/source={source}/dataset={dataset}/year={year}/month={month}/{filename}"
    
    def normalized_path(self, dataset: str, variable: str, time_str: str, filename: str) -> str:
        """Generate path for normalized data"""
        return f"copernicus/normalized/dataset={dataset}/var={variable}/time={time_str}/{filename}"
    
    def h3_path(self, dataset: str, variable: str, resolution: str, time_str: str, part_num: int) -> str:
        """Generate path for H3 aggregated data"""
        return f"copernicus/derived/h3/dataset={dataset}/var={variable}/res={resolution}/time={time_str}/part-{part_num:05d}.parquet"
    
    def tile_path(self, dataset: str, variable: str, z: int, x: int, y: int) -> str:
        """Generate path for vector tiles"""
        return f"copernicus/derived/tiles/dataset={dataset}/var={variable}/z={z}/x={x}/y={y}.pbf"
    
    def pmtiles_path(self, dataset: str, variable: str, time_str: str, region: str) -> str:
        """Generate path for PMTiles archives"""
        return f"copernicus/derived/pmtiles/dataset={dataset}/var={variable}/time={time_str}/region={region}.pmtiles"
    
    def manifest_path(self, request_key: str) -> str:
        """Generate path for manifest"""
        return f"copernicus/manifests/request_key={request_key}.json"
    
    def provenance_path(self, request_key: str) -> str:
        """Generate path for provenance"""
        return f"copernicus/provenance/request_key={request_key}.json"
    
    def upload_file(self, local_path: str, s3_path: str, metadata: Optional[Dict] = None) -> bool:
        """Upload file to S3"""
        try:
            extra_args = {}
            if metadata:
                extra_args['Metadata'] = metadata
            
            self.s3_client.upload_file(local_path, self.bucket_name, s3_path, ExtraArgs=extra_args)
            logger.info(f"Uploaded: {s3_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to upload {local_path}: {e}")
            return False
    
    def upload_bytes(self, data: bytes, s3_path: str, metadata: Optional[Dict] = None) -> bool:
        """Upload bytes to S3"""
        try:
            extra_args = {}
            if metadata:
                extra_args['Metadata'] = metadata
            
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=s3_path,
                Body=data,
                **extra_args
            )
            logger.info(f"Uploaded bytes: {s3_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to upload bytes to {s3_path}: {e}")
            return False
    
    def download_file(self, s3_path: str, local_path: str) -> bool:
        """Download file from S3"""
        try:
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            self.s3_client.download_file(self.bucket_name, s3_path, local_path)
            logger.info(f"Downloaded: {s3_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to download {s3_path}: {e}")
            return False
    
    def download_bytes(self, s3_path: str) -> Optional[bytes]:
        """Download bytes from S3"""
        try:
            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=s3_path)
            return response['Body'].read()
        except Exception as e:
            logger.error(f"Failed to download bytes {s3_path}: {e}")
            return None
    
    def exists(self, s3_path: str) -> bool:
        """Check if object exists in S3"""
        try:
            self.s3_client.head_object(Bucket=self.bucket_name, Key=s3_path)
            return True
        except:
            return False
    
    def list_objects(self, prefix: str, max_keys: int = 1000) -> List[Dict]:
        """List objects with given prefix"""
        try:
            paginator = self.s3_client.get_paginator('list_objects_v2')
            objects = []
            
            for page in paginator.paginate(Bucket=self.bucket_name, Prefix=prefix, MaxKeys=max_keys):
                objects.extend(page.get('Contents', []))
            
            return objects
        except Exception as e:
            logger.error(f"Failed to list objects with prefix {prefix}: {e}")
            return []
    
    def get_object_metadata(self, s3_path: str) -> Optional[Dict]:
        """Get object metadata"""
        try:
            response = self.s3_client.head_object(Bucket=self.bucket_name, Key=s3_path)
            return {
                'size': response.get('ContentLength'),
                'last_modified': response.get('LastModified'),
                'etag': response.get('ETag'),
                'metadata': response.get('Metadata', {})
            }
        except Exception as e:
            logger.error(f"Failed to get metadata for {s3_path}: {e}")
            return None
    
    def store_json(self, data: Dict, s3_path: str) -> bool:
        """Store JSON data"""
        try:
            json_bytes = json.dumps(data, indent=2, default=str).encode('utf-8')
            return self.upload_bytes(json_bytes, s3_path, {'content-type': 'application/json'})
        except Exception as e:
            logger.error(f"Failed to store JSON to {s3_path}: {e}")
            return False
    
    def load_json(self, s3_path: str) -> Optional[Dict]:
        """Load JSON data"""
        try:
            json_bytes = self.download_bytes(s3_path)
            if json_bytes:
                return json.loads(json_bytes.decode('utf-8'))
            return None
        except Exception as e:
            logger.error(f"Failed to load JSON from {s3_path}: {e}")
            return None
    
    def store_parquet(self, df, s3_path: str, metadata: Optional[Dict] = None) -> bool:
        """Store DataFrame as Parquet"""
        try:
            # Convert to PyArrow Table
            table = pa.Table.from_pandas(df)
            
            # Write to buffer
            buf = pa.BufferOutputStream()
            pq.write_table(table, buf)
            
            # Upload to S3
            extra_args = {'content-type': 'application/octet-stream'}
            if metadata:
                extra_args['Metadata'] = metadata
            
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=s3_path,
                Body=buf.getvalue().to_pybytes(),
                **extra_args
            )
            
            logger.info(f"Stored Parquet: {s3_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to store Parquet to {s3_path}: {e}")
            return False
    
    def list_datasets(self) -> Dict[str, List[str]]:
        """List available datasets by source"""
        datasets = {}
        
        # List raw datasets
        raw_prefix = "copernicus/raw/"
        for obj in self.list_objects(raw_prefix):
            # Extract source and dataset from path
            path_parts = obj['Key'].split('/')
            if len(path_parts) >= 4:
                source_part = path_parts[2]  # source=xxx
                dataset_part = path_parts[3]  # dataset=yyy
                
                source = source_part.split('=')[1]
                dataset = dataset_part.split('=')[1]
                
                if source not in datasets:
                    datasets[source] = []
                if dataset not in datasets[source]:
                    datasets[source].append(dataset)
        
        return datasets
    
    def get_dataset_info(self, source: str, dataset: str) -> Dict:
        """Get information about a specific dataset"""
        prefix = f"copernicus/raw/source={source}/dataset={dataset}/"
        objects = self.list_objects(prefix)
        
        if not objects:
            return {}
        
        total_size = sum(obj['Size'] for obj in objects)
        date_range = {}
        
        # Extract date information from paths
        for obj in objects:
            path_parts = obj['Key'].split('/')
            if len(path_parts) >= 6:
                year_part = path_parts[4]  # year=YYYY
                month_part = path_parts[5]  # month=MM
                
                if 'year=' in year_part and 'month=' in month_part:
                    year = year_part.split('=')[1]
                    month = month_part.split('=')[1]
                    
                    date_key = f"{year}-{month}"
                    if date_key not in date_range:
                        date_range[date_key] = 0
                    date_range[date_key] += obj['Size']
        
        return {
            'source': source,
            'dataset': dataset,
            'total_objects': len(objects),
            'total_size_bytes': total_size,
            'total_size_mb': total_size / (1024 * 1024),
            'date_distribution': date_range,
            'earliest_date': min(date_range.keys()) if date_range else None,
            'latest_date': max(date_range.keys()) if date_range else None
        }

def main():
    """Example usage"""
    storage = S3StorageManager()
    
    # Example: Store and retrieve JSON
    test_data = {
        'test': 'data',
        'timestamp': datetime.utcnow().isoformat()
    }
    
    json_path = "test/example.json"
    if storage.store_json(test_data, json_path):
        print(f"Stored JSON to {json_path}")
        
        retrieved = storage.load_json(json_path)
        print(f"Retrieved: {retrieved}")
    
    # List datasets
    datasets = storage.list_datasets()
    print(f"Available datasets: {datasets}")
    
    # Get info about specific dataset
    for source, dataset_list in datasets.items():
        for dataset in dataset_list[:2]:  # First 2 datasets
            info = storage.get_dataset_info(source, dataset)
            print(f"Dataset info: {info}")

if __name__ == "__main__":
    main()