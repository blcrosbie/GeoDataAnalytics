#!/usr/bin/env python3
"""
Copernicus Data Space Ecosystem (CDSE) Earth Observation Data Fetcher
Fetches satellite imagery from CDSE and stores to S3/Wasabi
"""

import os
import sys
import hashlib
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import logging

import requests
import boto3
import rasterio
from dotenv import load_dotenv
import base64

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class CDSEDataFetcher:
    def __init__(self):
        load_dotenv()
        
        # CDSE Configuration
        self.username = os.getenv('COPERNICUS_USERNAME')
        self.password = os.getenv('COPERNICUS_PASSWORD')
        self.client_id = os.getenv('COPERNICUS_CLIENT_ID')
        self.client_secret = os.getenv('COPERNICUS_CLIENT_SECRET')
        
        if not all([self.username, self.password, self.client_id, self.client_secret]):
            raise ValueError("CDSE credentials (username, password, client_id, client_secret) are required")
        
        # OAuth endpoints
        self.token_url = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
        self.catalog_url = "https://catalogue.dataspace.copernicus.eu/odata/v1"
        
        # S3 Configuration
        self.s3_client = boto3.client(
            's3',
            endpoint_url=os.getenv('S3_ENDPOINT_URL'),
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
            region_name=os.getenv('AWS_DEFAULT_REGION', 'us-east-1')
        )
        self.bucket_name = os.getenv('S3_BUCKET_NAME')
        
        # Authentication
        self.access_token = None
        self.token_expiry = None
        
    def get_access_token(self) -> str:
        """Get or refresh access token"""
        # Check if current token is still valid
        if self.access_token and self.token_expiry and datetime.utcnow() < self.token_expiry:
            return self.access_token
        
        # Get new token
        auth_string = f"{self.client_id}:{self.client_secret}"
        auth_bytes = auth_string.encode('ascii')
        auth_b64 = base64.b64encode(auth_bytes).decode('ascii')
        
        headers = {
            'Authorization': f'Basic {auth_b64}',
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        
        data = {
            'grant_type': 'client_credentials',
            'client_id': self.client_id,
            'client_secret': self.client_secret
        }
        
        try:
            response = requests.post(self.token_url, headers=headers, data=data)
            response.raise_for_status()
            token_data = response.json()
            
            self.access_token = token_data['access_token']
            expires_in = token_data.get('expires_in', 3600)
            self.token_expiry = datetime.utcnow() + timedelta(seconds=expires_in - 60)  # Refresh 1 min early
            
            logger.info("Successfully obtained new access token")
            return self.access_token
            
        except Exception as e:
            logger.error(f"Failed to get access token: {e}")
            raise
    
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
    
    def search_sentinel2(self, 
                        bbox: Tuple[float, float, float, float],
                        start_date: str,
                        end_date: str,
                        max_cloud_cover: float = 10.0,
                        limit: int = 10) -> List[Dict]:
        """
        Search Sentinel-2 data
        
        Args:
            bbox: (min_lon, min_lat, max_lon, max_lat)
            start_date: ISO date string (YYYY-MM-DD)
            end_date: ISO date string (YYYY-MM-DD)
            max_cloud_cover: Maximum cloud cover percentage
            limit: Maximum number of results
            
        Returns:
            List of product information
        """
        token = self.get_access_token()
        
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
        
        # OData filter for Sentinel-2
        filter_expr = f"""
        Collection/Name eq 'SENTINEL-2' and 
        OData.Ce.Intersects(area=geography'SRID=4326;POLYGON(({bbox[0]} {bbox[1]}, {bbox[2]} {bbox[1]}, {bbox[2]} {bbox[3]}, {bbox[0]} {bbox[3]}, {bbox[0]} {bbox[1]}))') and
        ContentDate/Start gt {start_date}T00:00:00.000Z and
        ContentDate/Start lt {end_date}T23:59:59.999Z and
        Attributes/OData.CSC.DoubleAttributes/DoubleAttribute/any(att:att/Name eq 'cloudCover' and att/Value lt {max_cloud_cover})
        """
        
        params = {
            '$filter': filter_expr,
            '$orderby': 'ContentDate/Start desc',
            '$top': limit,
            '$expand': 'Attributes'
        }
        
        try:
            response = requests.get(f"{self.catalog_url}/Products", headers=headers, params=params)
            response.raise_for_status()
            
            data = response.json()
            products = data.get('value', [])
            
            logger.info(f"Found {len(products)} Sentinel-2 products")
            return products
            
        except Exception as e:
            logger.error(f"Error searching Sentinel-2: {e}")
            raise
    
    def download_sentinel2_product(self, product_info: Dict, year: str, month: str) -> str:
        """
        Download Sentinel-2 product
        
        Args:
            product_info: Product information from search
            year: Year for organization
            month: Month for organization
            
        Returns:
            S3 path of downloaded file
        """
        token = self.get_access_token()
        
        product_id = product_info['Id']
        product_name = product_info['Name']
        
        # Generate request key
        request_str = json.dumps(product_info, sort_keys=True)
        request_key = hashlib.sha256(request_str.encode()).hexdigest()[:16]
        
        # Get download URL
        headers = {'Authorization': f'Bearer {token}'}
        
        try:
            # Get download URL
            download_url = f"{self.catalog_url}/Products({product_id})/$value"
            
            response = requests.get(download_url, headers=headers, stream=True)
            response.raise_for_status()
            
            # Download to temp file
            temp_filename = f"/tmp/{product_name}.zip"
            with open(temp_filename, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            # Upload to S3
            s3_path = self.get_s3_path('cdse', 'SENTINEL-2', year, month, f"{product_name}.zip")
            self.s3_client.upload_file(temp_filename, self.bucket_name, s3_path)
            
            # Store manifest
            manifest = {
                'dataset': 'SENTINEL-2',
                'product_id': product_id,
                'product_name': product_name,
                'filename': f"{product_name}.zip",
                's3_path': s3_path,
                'request_key': request_key,
                'fetched_at': datetime.utcnow().isoformat(),
                'file_size': os.path.getsize(temp_filename),
                'product_info': product_info
            }
            self.store_manifest(request_key, manifest)
            
            # Store provenance
            provenance = {
                'source': 'cdse',
                'dataset': 'SENTINEL-2',
                'request_key': request_key,
                'fetch_timestamp': datetime.utcnow().isoformat(),
                'processing_stage': 'raw',
                'data_format': 'SAFE ZIP',
                'access_method': 'cdse_api'
            }
            self.store_provenance(request_key, provenance)
            
            # Clean up temp file
            os.remove(temp_filename)
            
            logger.info(f"Downloaded and stored: {s3_path}")
            return s3_path
            
        except Exception as e:
            logger.error(f"Error downloading product {product_id}: {e}")
            raise
    
    def fetch_recent_sentinel2(self,
                             bbox: Tuple[float, float, float, float],
                             days_back: int = 7,
                             max_cloud_cover: float = 10.0,
                             max_products: int = 5) -> List[str]:
        """
        Fetch recent Sentinel-2 data for an area
        
        Args:
            bbox: (min_lon, min_lat, max_lon, max_lat)
            days_back: Number of days back from today
            max_cloud_cover: Maximum cloud cover percentage
            max_products: Maximum number of products to download
            
        Returns:
            List of S3 paths
        """
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days_back)
        
        start_str = start_date.strftime('%Y-%m-%d')
        end_str = end_date.strftime('%Y-%m-%d')
        year_month = end_date.strftime('%Y-%m')
        
        # Search for products
        products = self.search_sentinel2(
            bbox=bbox,
            start_date=start_str,
            end_date=end_str,
            max_cloud_cover=max_cloud_cover,
            limit=max_products
        )
        
        s3_paths = []
        for product in products:
            try:
                s3_path = self.download_sentinel2_product(product, end_date.strftime('%Y'), end_date.strftime('%m'))
                s3_paths.append(s3_path)
                
                # Rate limiting to avoid overwhelming the service
                time.sleep(2)
                
            except Exception as e:
                logger.error(f"Failed to download product: {e}")
                continue
        
        return s3_paths

def main():
    """Example usage"""
    fetcher = CDSEDataFetcher()
    
    try:
        # Example: Fetch recent Sentinel-2 data for a region
        # bbox = (min_lon, min_lat, max_lon, max_lat) - San Francisco Bay Area
        bbox = (-122.5, 37.4, -122.0, 37.8)
        
        s3_paths = fetcher.fetch_recent_sentinel2(
            bbox=bbox,
            days_back=14,
            max_cloud_cover=15.0,
            max_products=3
        )
        
        print(f"Downloaded {len(s3_paths)} Sentinel-2 products:")
        for path in s3_paths:
            print(f"  - {path}")
        
    except Exception as e:
        logger.error(f"Error in main: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()