import os
import bs4
import requests # type: ignore
from tqdm import tqdm
import datetime
import concurrent.futures

try:
    import questionary
except ImportError:
    print("'questionary' library is required for the interactive prompt.")
    print("Please install it using: pip install questionary")
    exit(1)

def _download_worker(zip_url, data_dir):
    """Helper function to download a single file."""
    save_fn = os.path.join(data_dir, zip_url.split('/')[-1])
    try:
        with requests.get(zip_url, stream=True) as zfile:
            zfile.raise_for_status()
            with open(save_fn, 'wb') as f:
                for chunk in zfile.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
        return None
    except requests.exceptions.RequestException as e:
        if os.path.exists(save_fn):
            os.remove(save_fn)
        return f"Failed to download {zip_url}: {e}"
    except IOError as e:
        return f"Failed to write file {save_fn}: {e}"

def download_tiger_data(year: int, shape_type: str):
    """
    Downloads TIGER/Line shapefiles from the US Census Bureau for a specific year and shape type.

    Args:
        year (int): The year of the TIGER data to download (e.g., 2024).
        shape_type (str): The TIGER shape type to download (e.g., 'CBSA', 'PLACE', 'TRACT'). Case-insensitive.
    """
    
    # Define the directory on the D: drive and create it if it doesn't exist
    data_dir = os.path.join('D:\\', 'census', str(year))
    os.makedirs(data_dir, exist_ok=True)
    print(f"Data will be saved to: {data_dir}")

    # Construct the base URL for the given year and shape type
    shape_type_upper = shape_type.upper()
    base_url = f'https://www2.census.gov/geo/tiger/TIGER{year}/'
    select_path = f'{base_url}{shape_type_upper}/'

    # Access page with zip files
    try:
        path_response = requests.get(select_path)
        path_response.raise_for_status()  # Will raise an HTTPError for bad responses (4xx or 5xx)
    except requests.exceptions.RequestException as e:
        print(f"Error accessing {select_path}: {e}")
        return

    soup = bs4.BeautifulSoup(path_response.text, 'html.parser')
    all_zips_on_page = soup.find_all('a')

    # Create a list of all Zip file locations on site
    zip_urls_to_download = []
    for item in all_zips_on_page:
        if item.text.endswith('.zip'):
            zip_url = f"{select_path}{item.text}"
            save_fn = os.path.join(data_dir, item.text)
            
            # Check if the file already exists before adding to download list
            if not os.path.exists(save_fn):
                zip_urls_to_download.append(zip_url)

    num_files = len(zip_urls_to_download)
    if num_files == 0:
        print(f"No new files to download for {shape_type_upper}.")
        return
        
    print(f"Found {num_files} files to download for {shape_type_upper}.")
    print(f"\nSTART: {shape_type_upper}\t{num_files} files to download")

    # Download each .zip file
    if num_files > 100:
        print("Using multithreading with 8 workers.")
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            results = list(tqdm(executor.map(lambda url: _download_worker(url, data_dir), zip_urls_to_download), total=num_files, desc=f"Downloading {shape_type_upper}"))
            for result in results:
                if result:
                    print(result)
    else:
        print("Downloading files sequentially.")
        for zipurl in tqdm(zip_urls_to_download, desc=f"Downloading {shape_type_upper}"):
            result = _download_worker(zipurl, data_dir)
            if result:
                print(result)

    print(f"END: {select_path}\n\n")


if __name__ == "__main__":
    try:
        # --- Year Selection ---
        current_year = datetime.date.today().year
        # Census data is often released for the next year, go back to 2007
        years = [str(y) for y in range(current_year + 1, 2006, -1)]
        
        selected_year_str = questionary.select(
            "Select the year for TIGER data:",
            choices=years,
            use_indicator=True
        ).ask()

        if not selected_year_str:
            print("No year selected. Exiting.")
            exit()
            
        selected_year = int(selected_year_str)

        # --- Shape Type Selection ---
        year_url = f'https://www2.census.gov/geo/tiger/TIGER{selected_year}/'
        print(f"Fetching available shapefile types from {year_url}...")
        
        try:
            response = requests.get(year_url)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            print(f"Could not fetch data for year {selected_year}. Error: {e}")
            exit()

        soup = bs4.BeautifulSoup(response.text, 'html.parser')
        
        shape_types = []
        for item in soup.find_all('a'):
            text = item.text.strip()
            # Directories are all caps and end with a slash
            if text.endswith('/') and text[:-1].isupper():
                shape_types.append(text[:-1]) # remove trailing slash

        if not shape_types:
            print(f"No shapefile types found for {selected_year}. The URL might be incorrect or the page structure has changed.")
            exit()

        selected_shape_type = questionary.select(
            f"Select the shapefile type for {selected_year}:",
            choices=sorted(shape_types),
            use_indicator=True
        ).ask()

        if not selected_shape_type:
            print("No shape type selected. Exiting.")
            exit()

        # --- Run Download ---
        download_tiger_data(year=selected_year, shape_type=selected_shape_type)

    except KeyboardInterrupt:
        print("\nOperation cancelled by user. Exiting.")
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}")
