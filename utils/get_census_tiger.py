import os
import bs4
import requests # type: ignore
from tqdm import tqdm

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

# Find most recent tiger sets
base_url = 'https://www2.census.gov/geo/tiger/TIGER2024/'

response = requests.get(base_url)
soup = bs4.BeautifulSoup(response.text, 'html.parser')

# Search through all TIGER sets in URL Path
all_boundaries = soup.find_all('a')
all_paths = []
for item in all_boundaries:
    caps_text = item.text.upper()
    if caps_text == item.text and item.text != '' and ' ' not in item.text:
        all_paths.append(f"{base_url}{item.text}")


# Manual selection of paths (for simpler approach)
select_paths = [
    # 'https://www2.census.gov/geo/tiger/TIGER2024/CBSA/',
    # 'https://www2.census.gov/geo/tiger/TIGER2024/CD/',
    # 'https://www2.census.gov/geo/tiger/TIGER2024/COASTLINE/',
    # 'https://www2.census.gov/geo/tiger/TIGER2024/CONCITY/',
    # 'https://www2.census.gov/geo/tiger/TIGER2024/COUNTY/',
    # 'https://www2.census.gov/geo/tiger/TIGER2024/COUSUB/',
    # 'https://www2.census.gov/geo/tiger/TIGER2024/CSA/',
    # 'https://www2.census.gov/geo/tiger/TIGER2024/EDGES/',
    # 'https://www2.census.gov/geo/tiger/TIGER2024/INTERNATIONALBOUNDARY/',
    # 'https://www2.census.gov/geo/tiger/TIGER2024/PLACE/',
    # 'https://www2.census.gov/geo/tiger/TIGER2024/PRISECROADS/',
    # 'https://www2.census.gov/geo/tiger/TIGER2024/PUMA20/',
    # 'https://www2.census.gov/geo/tiger/TIGER2024/RAILS/',
    # 'https://www2.census.gov/geo/tiger/TIGER2024/ROADS/',
    # 'https://www2.census.gov/geo/tiger/TIGER2024/STATE/',
    'https://www2.census.gov/geo/tiger/TIGER2024/TRACT/',
    # 'https://www2.census.gov/geo/tiger/TIGER2024/ZCTA520/'
]

# Create a Lookup of all Zip file locations on site to their respective TIGER dataset
page_paths = {}
for path_url in select_paths:
    # Access page with zip files
    path_response = requests.get(path_url)
    soup = bs4.BeautifulSoup(path_response.text, 'html.parser')
    all_zips_on_page = soup.find_all('a')

    page_paths[path_url] = []

    for item in all_zips_on_page:
        # print(item)
        if item.text.endswith('.zip'):
            page_paths[path_url].append(f"{path_url}{item.text}")
    print(f"Done with {path_url}")

# Create Lookup of each TIGER set to each .zip found on its subpage and download each .zip
for zippage, zipurls in page_paths.items():
    print(f"START: {zippage.split('/')[-1]}\t{len(zipurls)} files to download")
    count = 0
    for zipurl in zipurls:
        save_fn = os.path.join(DATA_DIR, zipurl.split('/')[-1])
        with requests.get(zipurl, stream=True) as zfile:
            zfile.raise_for_status()
            with open(save_fn, 'wb') as f:
                for chunk in zfile.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                f.close()
        count += 1
        if count % 100 == 0:
            print(f"Progress: {round(count/len(zipurls), 2) * 100}%\t\t{count}/{len(zipurls)} Complete")

    print(f"END: {zippage}\n\n")
            