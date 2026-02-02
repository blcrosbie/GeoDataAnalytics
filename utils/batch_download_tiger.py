#!/usr/bin/env python3
"""
Batch downloader for Census TIGER data (2010-2025)
Iterates through all years and shape types with error handling and retry logic.
"""

import os
import time
import requests
from pathlib import Path
from tqdm import tqdm
import concurrent.futures

# Handle missing dependencies gracefully
try:
    import bs4
except ImportError:
    print("Error: beautifulsoup4 is required. Install with: sudo apt install python3-bs4")
    exit(1)

try:
    from get_census_tiger import _download_worker
except ImportError:
    print("Error: get_census_tiger.py not found in the same directory")
    exit(1)

def get_shape_types_for_year(year: int):
    """Fetch all available shape types for a given year."""
    year_url = f'https://www2.census.gov/geo/tiger/TIGER{year}/'
    
    try:
        response = requests.get(year_url, timeout=120, headers={'User-Agent': 'Mozilla/5.0'})
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Could not fetch data for year {year}. Error: {e}")
        return []
    
    soup = bs4.BeautifulSoup(response.text, 'html.parser')
    shape_types = []
    
    for item in soup.find_all('a'):
        text = item.text.strip()
        if text.endswith('/') and text[:-1].isupper():
            shape_types.append(text[:-1])
    
    return sorted(shape_types)

def download_with_retry(zip_url, data_dir, max_retries=3):
    """Download with 429 error handling and retry logic."""
    for attempt in range(max_retries + 1):
        try:
            return _download_worker(zip_url, data_dir)
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                if attempt < max_retries:
                    wait_time = 60 * (attempt + 1)  # 60, 120, 180 seconds
                    print(f"Rate limited (429) on {zip_url}. Waiting {wait_time}s... (attempt {attempt + 1}/{max_retries + 1})")
                    time.sleep(wait_time)
                    continue
                else:
                    return f"Failed after {max_retries + 1} attempts: {e}"
            else:
                raise e
        except Exception as e:
            if attempt < max_retries:
                time.sleep(5)  # Brief pause for other errors
                continue
            else:
                return f"Failed after {max_retries + 1} attempts: {e}"

def download_tiger_data_with_retry(year: int, shape_type: str):
    """
    Modified version of download_tiger_data with retry logic and reduced threading.
    """
    # Store downloads under the repo's data/census folder
    current_file = Path(__file__).resolve()
    repo_root = current_file.parent.parent
    data_dir = repo_root / 'data' / 'census' / str(year)
    data_dir.mkdir(parents=True, exist_ok=True)

    shape_type_upper = shape_type.upper()
    base_url = f'https://www2.census.gov/geo/tiger/TIGER{year}/'
    select_path = f'{base_url}{shape_type_upper}/'

    try:
        path_response = requests.get(select_path, timeout=120, headers={'User-Agent': 'Mozilla/5.0'})
        path_response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Error accessing {select_path}: {e}")
        return

    soup = bs4.BeautifulSoup(path_response.text, 'html.parser')
    all_zips_on_page = soup.find_all('a')

    zip_urls_to_download = []
    for item in all_zips_on_page:
        if item.text.endswith('.zip'):
            zip_url = f"{select_path}{item.text}"
            save_fn = os.path.join(data_dir, item.text)
            
            if not os.path.exists(save_fn):
                zip_urls_to_download.append(zip_url)

    num_files = len(zip_urls_to_download)
    if num_files == 0:
        print(f"No new files to download for {year} {shape_type_upper}.")
        return
        
    print(f"Found {num_files} files to download for {year} {shape_type_upper}.")

    # Download with reduced threading (2 workers instead of 8)
    if num_files > 20:  # Lower threshold for threading
        print(f"Using multithreading with 2 workers for {num_files} files.")
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            results = list(tqdm(
                executor.map(lambda url: download_with_retry(url, data_dir), zip_urls_to_download), 
                total=num_files, 
                desc=f"Downloading {year} {shape_type_upper}"
            ))
            for result in results:
                if result:
                    print(result)
    else:
        print(f"Downloading {num_files} files sequentially.")
        for zipurl in tqdm(zip_urls_to_download, desc=f"Downloading {year} {shape_type_upper}"):
            result = download_with_retry(zipurl, data_dir)
            if result:
                print(result)

    print(f"Completed: {select_path}")

def main():
    """Main function to iterate through years 2010-2025 and download specific boundary types."""
    # Test with just 2024 first
    years = list(range(2010, 2026))  # Start with just one year for testing
    
    # Specific boundary types to download (matching other upsert script)
    # boundary_types = ['place', 'tract', 'county', 'state', 'zcta520']  # run 1
    # boundary_types = ['areawater']  # run 2
    # boundary_types = ['cbsa', 'cd'] # run 3
    # boundary_types = ['arealm', 'bg']  # run 4
    # boundary_types = ['sldl', 'sldu']  # run 5
    boundary_types = ['roads', 'linearwater']  # run 6

    print("Starting batch download of Census TIGER data")
    print(f"Testing with year: {years[0]}")
    print(f"Boundary types to download: {', '.join(boundary_types)}")
    
    for year in years:
        print(f"\n{'='*60}")
        print(f"Processing year {year}")
        print(f"{'='*60}")
        
        # Check which boundary types are available for this year
        available_shape_types = get_shape_types_for_year(year)
        
        if not available_shape_types:
            print(f"No shapefile types found for {year}. Skipping year.")
            continue
            
        # Filter to only the boundary types we want, checking availability
        shape_types_to_download = []
        for boundary_type in boundary_types:
            if boundary_type.upper() in available_shape_types:
                shape_types_to_download.append(boundary_type)
            else:
                print(f"Warning: {boundary_type} not available for year {year}")
        
        if not shape_types_to_download:
            print(f"No requested boundary types available for {year}. Skipping year.")
            continue
            
        print(f"Downloading {len(shape_types_to_download)} boundary types for {year}: {', '.join(shape_types_to_download)}")
        
        for shape_type in shape_types_to_download:
            print(f"\n--- Processing {year} {shape_type} ---")
            download_tiger_data_with_retry(year, shape_type)
            
            # Longer pause between shape types
            time.sleep(5)
        
        print(f"\nCompleted downloads for year {year}")

    print(f"\n{'='*60}")
    print("Test batch download complete!")
    print("To run full batch, change years = list(range(2010, 2026))")
    print(f"{'='*60}")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nOperation cancelled by user. Exiting.")
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}")
