#!/usr/bin/env python3
"""
Simple batch downloader for Census TIGER data (2010-2025)
Iterates through all years and shape types with error handling and retry logic.
"""

import os
import time
import requests
import re
from pathlib import Path
import concurrent.futures

# Simple progress bar replacement
class SimpleProgress:
    def __init__(self, iterable, desc=None):
        self.iterable = iterable
        self.desc = desc
        self.total = len(iterable) if hasattr(iterable, '__len__') else None
    
    def __iter__(self):
        if self.desc:
            print(f"{self.desc}...", flush=True)
        for i, item in enumerate(self.iterable):
            if self.total and self.total > 1:
                print(f"  Progress: {i+1}/{self.total}", end='\r', flush=True)
            yield item
        if self.desc and self.total:
            print(f"\n{self.desc} completed. {self.total} items processed.")

def download_with_retry(zip_url, data_dir, max_retries=3):
    """Download with 429 error handling and retry logic."""
    save_fn = os.path.join(data_dir, zip_url.split('/')[-1])
    
    for attempt in range(max_retries + 1):
        try:
            with requests.get(zip_url, stream=True, timeout=120, headers={'User-Agent': 'Mozilla/5.0'}) as zfile:
                zfile.raise_for_status()
                with open(save_fn, 'wb') as f:
                    for chunk in zfile.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
            return None
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                if attempt < max_retries:
                    wait_time = 60 * (attempt + 1)
                    print(f"Rate limited (429) on {os.path.basename(zip_url)}. Waiting {wait_time}s... (attempt {attempt + 1}/{max_retries + 1})")
                    time.sleep(wait_time)
                    continue
                else:
                    return f"Failed after {max_retries + 1} attempts: {e}"
            else:
                return f"HTTP error downloading {zip_url}: {e}"
        except Exception as e:
            if attempt < max_retries:
                print(f"Error downloading {os.path.basename(zip_url)}: {e}. Retrying... (attempt {attempt + 1})")
                time.sleep(5)
                continue
            else:
                return f"Failed after {max_retries + 1} attempts: {e}"

def get_shape_types_for_year(year: int):
    """Fetch all available shape types for a given year using regex."""
    year_url = f'https://www2.census.gov/geo/tiger/TIGER{year}/'
    
    try:
        response = requests.get(year_url, timeout=120, headers={'User-Agent': 'Mozilla/5.0'})
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Could not fetch data for year {year}. Error: {e}")
        return []
    
    # Use regex to find directory links (all caps ending with /)
    pattern = r'href="([A-Z]+)/"'
    matches = re.findall(pattern, response.text)
    
    return sorted(set(matches))

def download_shape_type(year: int, shape_type: str):
    """Download all files for a specific year and shape type."""
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

    # Use regex to find .zip files
    zip_pattern = r'href="([^"]+\.zip)"'
    zip_matches = re.findall(zip_pattern, path_response.text)

    zip_urls_to_download = []
    for zip_file in zip_matches:
        zip_url = f"{select_path}{zip_file}"
        save_fn = os.path.join(data_dir, zip_file)
        
        if not os.path.exists(save_fn):
            zip_urls_to_download.append(zip_url)

    num_files = len(zip_urls_to_download)
    if num_files == 0:
        print(f"No new files to download for {year} {shape_type_upper}.")
        return
        
    print(f"Found {num_files} files to download for {year} {shape_type_upper}.")

    # Download with reduced threading
    if num_files > 20:
        print(f"Using multithreading with 2 workers for {num_files} files.")
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            results = list(SimpleProgress(
                executor.map(lambda url: download_with_retry(url, data_dir), zip_urls_to_download), 
                desc=f"Downloading {year} {shape_type_upper}"
            ))
            for result in results:
                if result:
                    print(result)
    else:
        print(f"Downloading {num_files} files sequentially.")
        for zipurl in SimpleProgress(zip_urls_to_download, desc=f"Downloading {year} {shape_type_upper}"):
            result = download_with_retry(zipurl, data_dir)
            if result:
                print(result)

    print(f"Completed: {select_path}")

def main():
    """Main function to iterate through years and download shape types."""
    # Start with 2024 for testing
    years = [2024]
    
    print("Starting batch download of Census TIGER data")
    print(f"Testing with year: {years[0]}")
    
    for year in years:
        print(f"\n{'='*60}")
        print(f"Processing year {year}")
        print(f"{'='*60}")
        
        shape_types = get_shape_types_for_year(year)
        
        if not shape_types:
            print(f"No shapefile types found for {year}. Skipping year.")
            continue
            
        print(f"Found {len(shape_types)} shape types for {year}: {', '.join(shape_types[:5])}{'...' if len(shape_types) > 5 else ''}")
        
        # Test with just one shape type first
        test_shape_types = ['TRACT']  # Most common and reliable
        print(f"Testing with: {', '.join(test_shape_types)}")
        
        for shape_type in test_shape_types:
            print(f"\n--- Processing {year} {shape_type} ---")
            download_shape_type(year, shape_type)
            
            # Pause between requests
            time.sleep(10)
        
        print(f"\nCompleted test downloads for year {year}")

    print(f"\n{'='*60}")
    print("Test complete!")
    print("Modify years list and test_shape_types to run full batch")
    print(f"{'='*60}")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nOperation cancelled by user. Exiting.")
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}")