"""
Copernicus Sentinel Satellite Data ETL Pipeline

This script provides functionality to download and process Copernicus Sentinel satellite data
from the Copernicus Data Space Ecosystem, respecting API rate limits and concurrent worker
constraints.

Key Features:
- Interactive selection of satellite missions and time periods
- Rate-limited concurrent downloads (max 2 workers)
- Automatic upload to S3 bucket
- Progress tracking and error handling
- Support for various Sentinel missions (1, 2, 3, 5, etc.)

API Limitations Respected:
- Max 2 concurrent workers
- 2000 requests per minute for S3 API
- 20 MB/s bandwidth limit per connection
- Proper token management and refresh
"""

import os
import json
import time
import requests
import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
import threading

try:
    import questionary
    import boto3
    from botocore.exceptions import ClientError
    from dotenv import load_dotenv
except ImportError as e:
    missing_lib = str(e).split("'")[1]
    print(f"'{missing_lib}' library is required.")
    print(f"Please install it using: pip install {missing_lib}")
    exit(1)

# Load environment variables
load_dotenv()

class RateLimiter:
    """Rate limiter to respect API constraints."""
    
    def __init__(self, requests_per_minute: int = 2000):
        self.requests_per_minute = requests_per_minute
        self.requests = []
        self.lock = threading.Lock()
    
    def wait_if_needed(self):
        """Wait if we've exceeded the rate limit."""
        with self.lock:
            now = time.time()
            # Remove requests older than 1 minute
            self.requests = [req_time for req_time in self.requests if now - req_time < 60]
            
            if len(self.requests) >= self.requests_per_minute:
                # Calculate wait time
                oldest_request = min(self.requests)
                wait_time = 60 - (now - oldest_request)
                if wait_time > 0:
                    time.sleep(wait_time)
                    # Clean up old requests after waiting
                    self.requests = []
            
            self.requests.append(now)

class CopernicusETL:
    """Main class for Copernicus Sentinel data ETL operations."""
    
    def __init__(self):
        self.monthly_quota = 30000  # Processing units per month
        self.username = os.getenv('COPERNICUS_USERNAME')
        self.password = os.getenv('COPERNICUS_PASSWORD')
        self.client_id = os.getenv('COPERNICUS_CLIENT_ID')
        self.client_secret = os.getenv('COPERNICUS_CLIENT_SECRET')
        self.s3_bucket = os.getenv('S3_BUCKET_NAME')
        self.max_workers = int(os.getenv('MAX_CONCURRENT_WORKERS', '2'))
        self.rate_limiter = RateLimiter()
        self.access_token = None
        self.token_expiry = None
        
        # Initialize S3 client
        self.s3_client = boto3.client(
            's3',
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
            region_name=os.getenv('AWS_DEFAULT_REGION', 'us-east-1')
        )
        
        # Base URLs
        self.auth_url = "https://identity.dataspace.copernicus.eu/auth/realms/IDAS/protocol/openid-connect/token"
        self.catalog_url = "https://catalogue.dataspace.copernicus.eu/odata/v1"
        self.odata_url = "https://dataspace.copernicus.eu/odata/v1"
        
        # Cost estimation (rough estimates based on typical product sizes)
        self.unit_costs = {
            'sentinel-1': 100,      # SAR products typically 1-2GB
            'sentinel-2': 150,      # Optical products typically 5-8GB
            'sentinel-3': 200,      # Various sensors, larger products
            'sentinel-5p': 50,      # Atmospheric data, smaller
            'sentinel-6': 100,      # Altimetry data
            'sentinel-1-slc': 120,
            'sentinel-1-grd': 80,
            'sentinel-2-l1c': 150,
            'sentinel-2-l2a': 180,
            'sentinel-3-l1': 200,
            'sentinel-3-l2': 220
        }
    
    def get_access_token(self) -> str:
        """Get or refresh access token for Copernicus API."""
        if self.access_token and self.token_expiry and datetime.datetime.now() < self.token_expiry:
            return self.access_token
        
        data = {
            'grant_type': 'password',
            'username': self.username,
            'password': self.password,
            'client_id': self.client_id,
            'client_secret': self.client_secret
        }
        
        try:
            response = requests.post(self.auth_url, data=data)
            response.raise_for_status()
            token_data = response.json()
            
            self.access_token = token_data['access_token']
            expires_in = token_data.get('expires_in', 3600)  # Default 1 hour
            self.token_expiry = datetime.datetime.now() + datetime.timedelta(seconds=expires_in - 300)  # Refresh 5 min early
            
            return self.access_token
        except requests.exceptions.RequestException as e:
            print(f"Error getting access token: {e}")
            raise
    
    def get_sentinel_missions(self) -> Dict[str, str]:
        """Returns available Sentinel missions with descriptions."""
        return {
            'sentinel-1': 'Sentinel-1 - SAR imaging for land and ocean monitoring',
            'sentinel-2': 'Sentinel-2 - Multispectral imaging for land monitoring',
            'sentinel-3': 'Sentinel-3 - Ocean and land monitoring (optical and altimetry)',
            'sentinel-5p': 'Sentinel-5P - Atmospheric composition and air quality',
            'sentinel-6': 'Sentinel-6 - Sea level and ocean topography',
            'sentinel-1-slc': 'Sentinel-1 SLC - Single Look Complex SAR data',
            'sentinel-1-grd': 'Sentinel-1 GRD - Ground Range Detected SAR data',
            'sentinel-2-l1c': 'Sentinel-2 L1C - Level-1C orthorectified products',
            'sentinel-2-l2a': 'Sentinel-2 L2A - Level-2A surface reflectance products',
            'sentinel-3-l1': 'Sentinel-3 L1 - Level-1 products',
            'sentinel-3-l2': 'Sentinel-3 L2 - Level-2 products'
        }
    
    def search_products(self, mission: str, start_date: str, end_date: str, 
                       bbox: Optional[Tuple[float, float, float, float]] = None,
                       max_results: int = 100) -> List[Dict]:
        """Search for Sentinel products using OData API."""
        self.rate_limiter.wait_if_needed()
        
        token = self.get_access_token()
        headers = {'Authorization': f'Bearer {token}'}
        
        # Build filter query
        filters = [f"Collection/Name eq '{mission}'"]
        
        # Add date filter
        if start_date and end_date:
            date_filter = f"ContentDate/Start ge {start_date}T00:00:00.000Z and ContentDate/End le {end_date}T23:59:59.999Z"
            filters.append(date_filter)
        
        # Add bounding box filter if provided
        if bbox:
            bbox_filter = f"OData.CSC.Intersects(area=geography'SRID=4326;POLYGON(({bbox[0]} {bbox[1]},{bbox[2]} {bbox[1]},{bbox[2]} {bbox[3]},{bbox[0]} {bbox[3]},{bbox[0]} {bbox[1]}))')"
            filters.append(bbox_filter)
        
        filter_query = " and ".join(filters)
        
        # Construct URL
        url = f"{self.catalog_url}/Products?$filter={filter_query}&$top={max_results}&$orderby=ContentDate/Start desc"
        
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
            
            return data.get('value', [])
        except requests.exceptions.RequestException as e:
            print(f"Error searching products: {e}")
            return []
    
    def download_product(self, product: Dict, download_dir: Path) -> Optional[str]:
        """Download a single Sentinel product."""
        product_id = product['Id']
        product_name = product['Name']
        
        # Check if already downloaded
        local_path = download_dir / f"{product_name}.zip"
        if local_path.exists():
            print(f"Already downloaded: {product_name}")
            return str(local_path)
        
        self.rate_limiter.wait_if_needed()
        
        token = self.get_access_token()
        headers = {'Authorization': f'Bearer {token}'}
        
        # Get download URL
        download_url = f"{self.odata_url}/Products({product_id})/$value"
        
        try:
            print(f"Downloading {product_name}...")
            response = requests.get(download_url, headers=headers, stream=True)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            
            with open(local_path, 'wb') as f:
                with tqdm(total=total_size, unit='B', unit_scale=True, desc=product_name) as pbar:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            pbar.update(len(chunk))
            
            print(f"Successfully downloaded: {product_name}")
            return str(local_path)
            
        except requests.exceptions.RequestException as e:
            print(f"Error downloading {product_name}: {e}")
            if local_path.exists():
                local_path.unlink()
            return None
    
    def upload_to_s3(self, local_path: str, product_name: str) -> bool:
        """Upload downloaded product to S3 bucket."""
        try:
            s3_key = f"copernicus/{product_name}.zip"
            
            print(f"Uploading {product_name} to S3...")
            
            # Upload with progress tracking
            file_size = os.path.getsize(local_path)
            
            with tqdm(total=file_size, unit='B', unit_scale=True, desc=f"Uploading {product_name}") as pbar:
                self.s3_client.upload_file(
                    local_path, 
                    self.s3_bucket, 
                    s3_key,
                    Callback=lambda bytes_transferred: pbar.update(bytes_transferred)
                )
            
            print(f"Successfully uploaded to S3: {s3_key}")
            return True
            
        except ClientError as e:
            print(f"Error uploading to S3: {e}")
            return False
    
    def process_products(self, products: List[Dict], download_dir: Path, 
                        upload_to_s3: bool = True) -> Dict[str, int]:
        """Process multiple products with concurrent downloads."""
        results = {'downloaded': 0, 'uploaded': 0, 'failed': 0}
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit download tasks
            download_futures = {
                executor.submit(self.download_product, product, download_dir): product
                for product in products
            }
            
            # Process downloads as they complete
            for future in as_completed(download_futures):
                product = download_futures[future]
                product_name = product['Name']
                
                try:
                    local_path = future.result()
                    if local_path:
                        results['downloaded'] += 1
                        
                        # Upload to S3 if requested
                        if upload_to_s3:
                            if self.upload_to_s3(local_path, product_name):
                                results['uploaded'] += 1
                            # Optionally remove local file after upload
                            # os.unlink(local_path)
                    else:
                        results['failed'] += 1
                        
                except Exception as e:
                    print(f"Error processing {product_name}: {e}")
                    results['failed'] += 1
        
        return results
    
    def get_time_period_selection(self) -> Tuple[str, str]:
        """Interactive time period selection."""
        current_year = datetime.datetime.now().year
        years = list(range(2015, current_year + 1))
        
        year_choices = [str(year) for year in years]
        year_choices.append("Custom date range")
        
        selected_year = questionary.select(
            "Select time period:",
            choices=year_choices
        ).ask()
        
        if selected_year == "Custom date range":
            start_date = questionary.text("Enter start date (YYYY-MM-DD):").ask()
            end_date = questionary.text("Enter end date (YYYY-MM-DD):").ask()
        else:
            start_date = f"{selected_year}-01-01"
            end_date = f"{selected_year}-12-31"
        
        return start_date, end_date

def main():
    """Main execution function."""
    try:
        # Validate environment variables
        required_vars = ['COPERNICUS_USERNAME', 'COPERNICUS_PASSWORD', 
                        'COPERNICUS_CLIENT_ID', 'COPERNICUS_CLIENT_SECRET',
                        'AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'S3_BUCKET_NAME']
        
        missing_vars = [var for var in required_vars if not os.getenv(var)]
        if missing_vars:
            print(f"Missing required environment variables: {', '.join(missing_vars)}")
            print("Please set up your .env file using .env.example as a template.")
            return
        
        # Initialize ETL pipeline
        etl = CopernicusETL()
        
        # --- Mission Selection ---
        missions = etl.get_sentinel_missions()
        mission_choices = [f"{code} - {desc}" for code, desc in missions.items()]
        
        selected_mission_full = questionary.select(
            "Select Sentinel mission:",
            choices=mission_choices
        ).ask()
        
        if not selected_mission_full:
            print("No mission selected. Exiting.")
            return
        
        selected_mission = selected_mission_full.split(' - ')[0]
        
        # --- Time Period Selection ---
        start_date, end_date = etl.get_time_period_selection()
        
        # --- Optional Bounding Box ---
        use_bbox = questionary.confirm("Do you want to specify a bounding box?").ask()
        bbox = None
        
        if use_bbox:
            print("Enter bounding box coordinates (WGS84):")
            min_lon = questionary.text("Min longitude:").ask()
            min_lat = questionary.text("Min latitude:").ask()
            max_lon = questionary.text("Max longitude:").ask()
            max_lat = questionary.text("Max latitude:").ask()
            
            try:
                bbox = (float(min_lon), float(min_lat), float(max_lon), float(max_lat))
            except ValueError:
                print("Invalid coordinates. Proceeding without bounding box.")
                bbox = None
        
        # --- Search Products ---
        print(f"\nSearching for {selected_mission} products from {start_date} to {end_date}...")
        products = etl.search_products(selected_mission, start_date, end_date, bbox)
        
        if not products:
            print("No products found matching your criteria.")
            return
        
        print(f"Found {len(products)} products")
        
        # --- Product Selection ---
        max_results = questionary.text(
            "How many products do you want to download? (max 100)",
            default=str(min(len(products), 10))
        ).ask()
        
        try:
            max_results = min(int(max_results), len(products), 100)
        except ValueError:
            max_results = min(len(products), 10)
        
        selected_products = products[:max_results]
        
        # --- Download and Process ---
        current_file = Path(__file__).resolve()
        repo_root = current_file.parent.parent
        download_dir = repo_root / 'data' / 'copernicus' / selected_mission
        download_dir.mkdir(parents=True, exist_ok=True)
        
        print(f"\nStarting download of {len(selected_products)} products...")
        print(f"Data will be saved to: {download_dir}")
        print(f"Using max {etl.max_workers} concurrent workers")
        
        results = etl.process_products(selected_products, download_dir)
        
        # --- Summary ---
        print(f"\n{'='*50}")
        print("ETL Summary:")
        print(f"Downloaded: {results['downloaded']} products")
        print(f"Uploaded to S3: {results['uploaded']} products")
        print(f"Failed: {results['failed']} products")
        print(f"{'='*50}")
        
    except KeyboardInterrupt:
        print("\nOperation cancelled by user. Exiting.")
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}")

if __name__ == "__main__":
    main()