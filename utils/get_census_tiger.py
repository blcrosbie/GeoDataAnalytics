import os
import bs4
import requests # type: ignore
from tqdm import tqdm
import datetime

try:
    import questionary
except ImportError:
    print("'questionary' library is required for the interactive prompt.")
    print("Please install it using: pip install questionary")
    exit(1)

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

    # Create a Lookup of all Zip file locations on site to their respective TIGER dataset
    page_paths = {}
    
    # Access page with zip files
    try:
        path_response = requests.get(select_path)
        path_response.raise_for_status()  # Will raise an HTTPError for bad responses (4xx or 5xx)
    except requests.exceptions.RequestException as e:
        print(f"Error accessing {select_path}: {e}")
        return

    soup = bs4.BeautifulSoup(path_response.text, 'html.parser')
    all_zips_on_page = soup.find_all('a')

    page_paths[select_path] = []

    for item in all_zips_on_page:
        if item.text.endswith('.zip'):
            zip_url = f"{select_path}{item.text}"
            save_fn = os.path.join(data_dir, item.text)
            
            # Check if the file already exists before adding to download list
            if not os.path.exists(save_fn):
                page_paths[select_path].append(zip_url)

    print(f"Found {len(page_paths[select_path])} files to download for {shape_type_upper}.")

    # Download each .zip file
    for zippage, zipurls in page_paths.items():
        if not zipurls:
            print(f"No new files to download for {zippage.split('/')[-2]}.")
            continue
            
        print(f"\nSTART: {zippage.split('/')[-2]}\t{len(zipurls)} files to download")
        
        for zipurl in tqdm(zipurls, desc=f"Downloading {shape_type_upper}"):
            save_fn = os.path.join(data_dir, zipurl.split('/')[-1])
            try:
                with requests.get(zipurl, stream=True) as zfile:
                    zfile.raise_for_status()
                    with open(save_fn, 'wb') as f:
                        for chunk in zfile.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
            except requests.exceptions.RequestException as e:
                print(f"Failed to download {zipurl}: {e}")
                # Optional: clean up partially downloaded file
                if os.path.exists(save_fn):
                    os.remove(save_fn)
            except IOError as e:
                print(f"Failed to write file {save_fn}: {e}")

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
