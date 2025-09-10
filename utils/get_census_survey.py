import bs4
import requests

# base_url = 'https://www2.census.gov/programs-surveys/popest/tables/'  # inspect manually, most recent year may not have granular city level data
base_url = 'https://www2.census.gov/programs-surveys/popest/datasets/2020-2023/cities/totals/'
response = requests.get(base_url)
soup = bs4.BeautifulSoup(response.text, 'html.parser')

all_boundaries = soup.findAll('a')
all_paths = []
for item in all_boundaries:
    caps_text = item.text.upper().strip()
    regular_text = item.text.strip()
    # if caps_text == item.text and item.text != '' and ' ' not in item.text:
    #     all_paths.append(f"{base_url}{item.text}")
    if item.text.strip().endswith('.csv'):
        print(item.text)
        all_paths.append(f"{base_url}{item.text.strip()}")


# Manually Select Paths to Census Surveys to Download ad-hoc
select_paths = [
    'https://www2.census.gov/programs-surveys/popest/datasets/2020-2023/counties/asrh/',
    
]

page_paths = {}
for path_url in select_paths:
    # Access page with zip files
    path_response = requests.get(path_url)
    soup = bs4.BeautifulSoup(path_response.text, 'html.parser')
    all_zips_on_page = soup.findAll('a')

    page_paths[path_url] = []

    for item in all_zips_on_page:
        # print(item)
        if item.text.endswith('.zip'):
            page_paths[path_url].append(f"{path_url}{item.text}")
    print(f"Done with {path_url}")