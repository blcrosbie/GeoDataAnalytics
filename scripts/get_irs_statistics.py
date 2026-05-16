import os
import bs4
import requests
from pathlib import Path
from tqdm import tqdm
import datetime
import concurrent.futures
import re

try:
    import questionary
except ImportError:
    print("'questionary' library is required for the interactive prompt.")
    print("Please install it using: pip install questionary")
    exit(1)

def _download_worker(file_url, data_dir):
    """Helper function to download a single file."""
    save_fn = os.path.join(data_dir, file_url.split('/')[-1])
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    try:
        with requests.get(file_url, stream=True, headers=headers) as response:
            response.raise_for_status()
            with open(save_fn, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
        return None
    except requests.exceptions.RequestException as e:
        if os.path.exists(save_fn):
            os.remove(save_fn)
        return f"Failed to download {file_url}: {e}"
    except IOError as e:
        return f"Failed to write file {save_fn}: {e}"

def get_data_type_descriptions():
    """Returns dictionary mapping data types to human-readable descriptions."""
    return {
        'county': 'County Data - IRS tax statistics by county for various tax years',
        'zipcode': 'ZIP Code Data - Individual income tax statistics by ZIP code',
        'congressional': 'Congressional District Data - IRS tax statistics by congressional district',
        'migration': 'Migration Data - Migration patterns based on tax returns'
    }

def get_county_data_urls():
    """Get county data URLs for tax years 2011 to latest available."""
    current_year = datetime.datetime.now().year
    county_urls = []
    
    # County data follows year-specific URL pattern
    for year in range(2011, current_year + 1):
        url = f"https://www.irs.gov/statistics/soi-tax-stats-county-data-{year}"
        county_urls.append({
            'year': year,
            'url': url,
            'description': f"County data for tax year {year}"
        })
    
    return county_urls

def get_zipcode_data_urls():
    """Get ZIP code data URLs for recent tax years."""
    current_year = datetime.datetime.now().year
    zipcode_urls = []
    
    # Use year-specific URLs for more targeted file discovery
    for year in range(2011, current_year + 1):
        if year >= 2020:
            # Newer pattern for recent years
            url = f"https://www.irs.gov/statistics/soi-tax-stats-individual-income-tax-statistics-{year}-zip-code-data-soi"
        else:
            # Older pattern for earlier years
            url = "https://www.irs.gov/statistics/soi-tax-stats-individual-income-tax-statistics-zip-code-data-soi"
        
        zipcode_urls.append({
            'year': year,
            'url': url,
            'description': f"ZIP code data for tax year {year}"
        })
    
    return zipcode_urls

def get_congressional_data_urls():
    """Get congressional district data URLs."""
    current_year = datetime.datetime.now().year
    congressional_urls = []
    
    base_url = "https://www.irs.gov/statistics/soi-tax-stats-data-by-congressional-district"
    
    # Congressional district data
    for year in range(2011, current_year + 1):
        congressional_urls.append({
            'year': year,
            'url': f"{base_url}",
            'description': f"Congressional district data for tax year {year}"
        })
    
    return congressional_urls

def get_migration_data_urls():
    """Get migration data URLs."""
    current_year = datetime.datetime.now().year
    migration_urls = []
    
    # Migration data has newer patterns for recent years (e.g., 2021-2022)
    for year in range(1991, current_year + 1):
        if year >= 2021:
            # Newer pattern for recent years: 2021-2022, 2022-2023, etc.
            prev_year = year - 1
            url = f"https://www.irs.gov/statistics/soi-tax-stats-migration-data-{prev_year}-{year}"
        else:
            # Older pattern for earlier years
            url = "https://www.irs.gov/statistics/soi-tax-stats-migration-data"
        
        migration_urls.append({
            'year': year,
            'url': url,
            'description': f"Migration data for tax year {year}"
        })
    
    return migration_urls

def scrape_irs_page_for_downloads(url, data_type, year):
    """Scrape an IRS statistics page to find downloadable files for a specific year."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Error accessing {url}: {e}")
        return []
    
    soup = bs4.BeautifulSoup(response.text, 'html.parser')
    downloadable_files = []
    
    # Find and expand all accordion elements, specifically targeting 'accordion-list'
    accordion_elements = []
    
    # Look for accordion-list and other accordion containers
    for element in soup.find_all(class_=True):
        classes = element.get('class')
        if classes and isinstance(classes, list):
            class_str = ' '.join(str(c) for c in classes).lower()
            # Target accordion-list specifically and other accordion patterns
            if 'accordion-list' in class_str or 'accordion' in class_str or 'collapse' in class_str:
                accordion_elements.append(element)
    
    # Process accordion elements to expose their content
    for accordion in accordion_elements:
        # Remove all collapsed/hidden classes to expose content
        classes = accordion.get('class', [])
        if isinstance(classes, list):
            filtered_classes = []
            for cls in classes:
                if isinstance(cls, str):
                    cls_lower = cls.lower()
                    # Remove any classes that might hide content
                    if not any(hidden in cls_lower for hidden in ['hidden', 'collapsed', 'hide', 'display-none', 'aria-hidden']):
                        filtered_classes.append(cls)
            accordion['class'] = filtered_classes
        
        # Also remove aria-expanded and aria-hidden attributes
        accordion.attrs.pop('aria-expanded', None)
        accordion.attrs.pop('aria-hidden', None)
        
        # Remove style attributes that might hide content
        if 'style' in accordion.attrs:
            style = accordion.attrs['style']
            if any(hidden in style.lower() for hidden in ['display:none', 'display: none', 'visibility:hidden']):
                accordion.attrs.pop('style')
    
    # Find any nested accordion content inside the expanded accordions
    for accordion in accordion_elements:
        nested_elements = accordion.find_all(class_=True)
        for nested in nested_elements:
            classes = nested.get('class')
            if classes and isinstance(classes, list):
                class_str = ' '.join(str(c) for c in classes).lower()
                if any(acc in class_str for acc in ['accordion', 'collapse', 'content']):
                    # Remove hidden classes from nested elements too
                    nested_classes = nested.get('class', [])
                    if isinstance(nested_classes, list):
                        filtered_nested = []
                        for cls in nested_classes:
                            if isinstance(cls, str):
                                cls_lower = cls.lower()
                                if not any(hidden in cls_lower for hidden in ['hidden', 'collapsed', 'hide', 'display-none', 'aria-hidden']):
                                    filtered_nested.append(cls)
                        nested['class'] = filtered_nested
                    
                    # Remove hiding attributes
                    nested.attrs.pop('aria-expanded', None)
                    nested.attrs.pop('aria-hidden', None)
                    if 'style' in nested.attrs:
                        style = nested.attrs['style']
                        if any(hidden in style.lower() for hidden in ['display:none', 'display: none', 'visibility:hidden']):
                            nested.attrs.pop('style')
    
    # Look for downloadable files and links in the entire page
    for link in soup.find_all('a', href=True):
        href = str(link['href'])
        text = link.text.strip().lower()
        
        # Check for file extensions that indicate downloadable data
        if any(ext in href.lower() for ext in ['.xls', '.xlsx', '.csv', '.zip', '.txt']):
            # Look for the specific year in the link text or filename
            year_str = str(year)
            year_short = year_str[-2:]  # Last 2 digits
            year_prev = str(year - 1)
            year_prev_short = year_prev[-2:]
            
            # For migration data, look for patterns like "2021 to 2022" or "2122"
            matched = False
            if data_type == 'migration':
                # Check for "YYYY to YYYY" format in text
                if (year_prev in text and year_str in text) or \
                   (year_prev_short in text and year_short in text):
                    matched = True
                # Check filename patterns: "2122" for 2021-2022, "2223" for 2022-2023, etc.
                migration_pattern = year_prev_short + year_short
                if migration_pattern in href:
                    matched = True
                # Also check for individual year patterns
                if year_prev_short in href or year_short in href or year_prev in href or year_str in href:
                    matched = True
            elif data_type == 'zipcode':
                # For zipcode data, look for patterns like "22zp" for 2022
                zipcode_pattern = year_short + 'zp'
                if zipcode_pattern in href.lower() or year_str in href or year_short in href:
                    matched = True
                # Also check for year in text or explicit mentions
                if year_str in text or year_short in text or 'zip' in text.lower() and year_str in href:
                    matched = True
            else:
                # For other data types, check normally
                if year_str in href or year_str in text or year_short in href or year_short in text:
                    matched = True
            
            if matched:
                full_url = href if href.startswith('http') else f"https://www.irs.gov{href}"
                downloadable_files.append({
                    'url': full_url,
                    'filename': href.split('/')[-1] or f"irs_{data_type}_{year}_data",
                    'description': text or f"IRS {data_type} data for {year}"
                })
    
    # Also look for tables that might contain download links
    for table in soup.find_all('table'):
        for row in table.find_all('tr'):
            cells = row.find_all(['td', 'th'])
            for cell in cells:
                cell_link = cell.find('a', href=True)
                if cell_link:
                    href = str(cell_link['href'])
                    cell_text = cell.text.strip().lower()
                    
                    if any(ext in href.lower() for ext in ['.xls', '.xlsx', '.csv', '.zip', '.txt']):
                        year_str = str(year)
                        year_short = year_str[-2:]
                        year_prev = str(year - 1)
                        year_prev_short = year_prev[-2:]
                        
                        # For migration data, look for patterns like "2021 to 2022" or "2122"
                        matched = False
                        if data_type == 'migration':
                            # Check for "YYYY to YYYY" format in cell_text
                            if (year_prev in cell_text and year_str in cell_text) or \
                               (year_prev_short in cell_text and year_short in cell_text):
                                matched = True
                            # Check filename patterns: "2122" for 2021-2022, "2223" for 2022-2023, etc.
                            migration_pattern = year_prev_short + year_short
                            if migration_pattern in href:
                                matched = True
                            # Also check for individual year patterns
                            if year_prev_short in href or year_short in href or year_prev in href or year_str in href:
                                matched = True
                        elif data_type == 'zipcode':
                            # For zipcode data, look for patterns like "22zp" for 2022
                            zipcode_pattern = year_short + 'zp'
                            if zipcode_pattern in href.lower() or year_str in href or year_short in href:
                                matched = True
                            # Also check for year in text or explicit mentions
                            if year_str in cell_text or year_short in cell_text or 'zip' in cell_text.lower() and year_str in href:
                                matched = True
                        else:
                            # For other data types, check normally
                            if year_str in href or year_str in cell_text or year_short in href or year_short in cell_text:
                                matched = True
                        
                        if matched:
                            full_url = href if href.startswith('http') else f"https://www.irs.gov{href}"
                            downloadable_files.append({
                                'url': full_url,
                                'filename': href.split('/')[-1] or f"irs_{data_type}_{year}_data",
                                'description': cell_text or f"IRS {data_type} data for {year}"
                            })
    
    # If still no files found, try to find any links with data-related terms
    if not downloadable_files:
        for link in soup.find_all('a', href=True):
            href = str(link['href'])
            text = link.text.strip().lower()
            
            if any(ext in href.lower() for ext in ['.xls', '.xlsx', '.csv', '.zip', '.txt']):
                if any(term in text for term in ['migration', 'data', 'download', 'file']):
                    full_url = href if href.startswith('http') else f"https://www.irs.gov{href}"
                    downloadable_files.append({
                        'url': full_url,
                        'filename': href.split('/')[-1] or f"irs_{data_type}_{year}_data",
                        'description': text or f"IRS {data_type} data for {year}"
                    })
    
    return downloadable_files

def download_irs_data(data_type: str, years: list | None = None):
    """
    Downloads IRS statistics data for the specified data type and years.
    
    Args:
        data_type (str): Type of IRS data ('county', 'zipcode', 'congressional', 'migration')
        years (list): List of years to download. If None, downloads all available years 2011-current
    """
    
    if years is None:
        current_year = datetime.datetime.now().year
        years = list(range(2011, current_year + 1))
    
    # Store downloads under the repo's data/irs folder
    current_file = Path(__file__).resolve()
    repo_root = current_file.parent.parent
    
    # Create data type-specific directory structure
    data_dir = repo_root / 'data' / 'irs' / data_type
    data_dir.mkdir(parents=True, exist_ok=True)
    print(f"Data will be saved to: {data_dir}")
    
    # Get URLs based on data type
    if data_type == 'county':
        data_urls = get_county_data_urls()
    elif data_type == 'zipcode':
        data_urls = get_zipcode_data_urls()
    elif data_type == 'congressional':
        data_urls = get_congressional_data_urls()
    elif data_type == 'migration':
        data_urls = get_migration_data_urls()
    else:
        print(f"Unknown data type: {data_type}")
        return
    
    print(f"Starting download for IRS {data_type} data...")
    
    # Process each year
    for year in years:
        print(f"\nProcessing {data_type} data for tax year {year}...")
        
        # Find the specific URL for this year
        year_url = None
        for url_info in data_urls:
            if url_info['year'] == year:
                year_url = url_info['url']
                break
        
        if not year_url:
            print(f"No URL found for {data_type} {year}")
            continue
        
        # Scrape the year-specific page for download links
        downloadable_files = scrape_irs_page_for_downloads(year_url, data_type, year)
        
        if not downloadable_files:
            print(f"No downloadable files found for {data_type} {year}")
            continue
        
        # Download files for this year
        year_dir = data_dir / str(year)
        year_dir.mkdir(exist_ok=True)
        
        files_to_download = []
        for file_info in downloadable_files:
            file_url = file_info['url']
            filename = file_info['filename']
            
            # Clean up filename
            if not filename.lower().endswith(('.xls', '.xlsx', '.csv', '.zip', '.txt')):
                filename += '.xls'  # Default extension
            
            save_path = year_dir / filename
            
            if not save_path.exists():
                files_to_download.append((file_url, save_path, file_info['description']))
        
        if files_to_download:
            print(f"Found {len(files_to_download)} files for {data_type} {year}")
            
            for file_url, save_path, description in tqdm(files_to_download, desc=f"Downloading {data_type} {year}"):
                result = _download_worker(file_url, str(save_path.parent))
                if result:
                    print(result)
        else:
            print(f"All files already exist for {data_type} {year}")
    
    print(f"Completed download for IRS {data_type} data\n")

def download_all_irs_data(selected_types: list | None = None, years: list | None = None):
    """
    Downloads all IRS statistics data for selected data types.
    
    Args:
        selected_types (list): List of data types to download. If None, downloads all types
        years (list): List of years to download. If None, downloads all available years
    """
    if selected_types is None:
        selected_types = ['county', 'zipcode', 'congressional', 'migration']
    
    if years is None:
        current_year = datetime.datetime.now().year
        years = list(range(2011, current_year + 1))
    
    for data_type in selected_types:
        download_irs_data(data_type, years)

if __name__ == "__main__":
    try:
        # --- Data Type Selection ---
        print("IRS Statistics Data Downloader")
        print("=" * 40)
        
        data_type_descriptions = get_data_type_descriptions()
        
        # Create choices for data types
        data_type_choices = []
        for code, description in data_type_descriptions.items():
            data_type_choices.append(f"{code} - {description}")
        
        # Let user select multiple data types
        selected_data_types_full = questionary.checkbox(
            "Select IRS data types to download (space to toggle, enter to confirm):",
            choices=data_type_choices
        ).ask() or []
        
        if not selected_data_types_full:
            print("No data types selected. Exiting.")
            exit()
        
        # Extract just the data type codes
        selected_data_types = [item.split(' - ')[0] for item in selected_data_types_full]
        
        # --- Year Range Selection ---
        current_year = datetime.datetime.now().year
        
        year_selection = questionary.select(
            "Select year range:",
            choices=[
                f"All years (2011-{current_year})",
                "Recent years (2018-present)",
                "Custom range"
            ]
        ).ask()
        
        if year_selection == f"All years (2011-{current_year})":
            selected_years = list(range(2011, current_year + 1))
        elif year_selection == "Recent years (2018-present)":
            selected_years = list(range(2018, current_year + 1))
        else:  # Custom range
            start_year = questionary.text(
                "Enter start year (2011 or later):",
                validate=lambda val: val.isdigit() and int(val) >= 2011
            ).ask()
            
            end_year = questionary.text(
                f"Enter end year ({start_year} or later):",
                validate=lambda val: val.isdigit() and int(val) >= int(start_year)
            ).ask()
            
            selected_years = list(range(int(start_year), int(end_year) + 1))
        
        print(f"\nDownloading IRS data for:")
        print(f"Data types: {', '.join(selected_data_types)}")
        print(f"Years: {selected_years[0]} to {selected_years[-1]}")
        print("=" * 50)
        
        # --- Download Data ---
        for data_type in selected_data_types:
            print(f"\n{'='*50}")
            print(f"Processing {data_type} data...")
            download_irs_data(data_type, selected_years)
        
        print(f"\nAll downloads completed!")
        print("Data saved to: data/irs_statistics/")
        
    except KeyboardInterrupt:
        print("\nOperation cancelled by user. Exiting.")
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}")
