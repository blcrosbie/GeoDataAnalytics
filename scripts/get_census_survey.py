import os
import bs4
import requests
from pathlib import Path
from tqdm import tqdm
import datetime
import concurrent.futures

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

def get_survey_descriptions():
    """Returns dictionary mapping survey codes to human-readable descriptions."""
    return {
        'acs': 'American Community Survey - Annual detailed demographic, social, economic, housing data for communities',
        'cbp': 'County Business Patterns - Annual data on business establishments, employment, payroll by industry/county',
        'cps': 'Current Population Survey - Monthly labor force statistics, employment, unemployment, demographics',
        'popest': 'Population Estimates - Annual population, housing unit estimates with demographic components',
        'saipe': 'Small Area Income/Poverty Estimates - School district, county, state income/poverty estimates',
        'economic-census': 'Economic Census - Comprehensive economic data every 5 years on business activity',
        'abs': 'Annual Business Survey - Annual data on US employer firms, characteristics, finances',
        'ahs': 'American Housing Survey - Biennial housing characteristics survey',
        'aies': 'Annual Integrated Economic Survey - Replacement for economic census, annual business data',
        'meps': 'Medical Expenditure Panel Survey - Healthcare utilization, expenditures, insurance data',
        'nsch': 'National Survey of Children\'s Health - Annual survey on children\'s physical/mental health',
        'sipp': 'Survey of Income and Program Participation - Longitudinal economic/demographic survey',
        'decennial': 'Decennial Census - Complete population count every 10 years',
        'international-programs': 'International Programs - Global demographic data, comparisons',
        'household-pulse': 'Household Pulse Survey - Rapid experimental surveys on social/economic impacts',
        'retail': 'Retail Trade Survey - Monthly retail sales, inventory data',
        'wholesale': 'Wholesale Trade Survey - Monthly wholesale trade, sales data',
        'manufacturing': 'Manufacturing Surveys - Industrial production, capacity, orders data',
        'construction': 'Construction Surveys - Building permits, starts, spending data',
        'services': 'Services Surveys - Service sector revenue, employment data',
        'trade': 'International Trade - Export/import statistics, trade balance data',
        'gov-finances': 'Government Finances - State/local government revenue, expenditure data',
        'education': 'Education Surveys - School enrollment, finances, staffing data',
        'transportation': 'Transportation Statistics - Freight, passenger, infrastructure data',
        'agriculture': 'Census of Agriculture - Comprehensive farm, crop, livestock data every 5 years',
        'commuting': 'Commuting/Transportation - Journey to work, transportation mode data',
        'metro-micro': 'Metropolitan/Micropolitan Areas - Urban area definitions, classifications',
        'state': 'State Data Center - State-specific data, programs',
        'county': 'County Data - County-level statistics, characteristics',
        'place': 'Place/City Data - Incorporated place, city statistics',
        'tract': 'Census Tract Data - Small geographic area demographic/economic data',
        'block-group': 'Block Group Data - Very small geographic area detailed data',
    }

def get_available_surveys():
    """Fetch available survey programs from Census Bureau."""
    base_url = 'https://www2.census.gov/programs-surveys/'
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    try:
        response = requests.get(base_url, headers=headers)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Error accessing {base_url}: {e}")
        return []
    
    soup = bs4.BeautifulSoup(response.text, 'html.parser')
    surveys = []
    
    for item in soup.find_all('a'):
        text = item.text.strip()
        # Directories end with a slash and are lowercase survey codes
        if text.endswith('/') and len(text) > 2 and text[:-1].islower():
            surveys.append(text[:-1])  # remove trailing slash
    
    # Filter out non-survey directories and focus on major data programs
    survey_blacklist = ['about', 'research', 'tables', 'stp64.txt', 'international-programs']
    surveys = [s for s in surveys if s not in survey_blacklist and len(s) >= 2]
    
    return sorted(surveys)

def get_survey_datasets(survey_code):
    """Get available datasets for a specific survey."""
    survey_url = f'https://www2.census.gov/programs-surveys/{survey_code}/'
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    try:
        response = requests.get(survey_url, headers=headers)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Error accessing {survey_url}: {e}")
        return []
    
    soup = bs4.BeautifulSoup(response.text, 'html.parser')
    datasets = []
    
    for item in soup.find_all('a'):
        text = item.text.strip()
        if text.endswith('/') and text not in ['../', './']:
            datasets.append(text[:-1])  # remove trailing slash
    
    return sorted(datasets)

def crawl_and_download(base_url: str, data_dir: Path, survey_code: str, path_parts: list | None = None):
    """
    Recursively crawl directory structure and download data files.
    
    Args:
        base_url (str): Base URL to start crawling
        data_dir (Path): Local directory to save files
        survey_code (str): Survey code for logging
        path_parts (list): Parts of the path for directory structure
    """
    if path_parts is None:
        path_parts = []
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    try:
        response = requests.get(base_url, headers=headers)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Error accessing {base_url}: {e}")
        return
    
    soup = bs4.BeautifulSoup(response.text, 'html.parser')
    links = soup.find_all('a')
    
    # Separate directories from files
    directories = []
    downloadable_files = []
    
    for link in links:
        text = link.text.strip()
        if text.endswith('/') and text not in ['../', './']:
            directories.append(text[:-1])
        elif text.endswith(('.zip', '.csv', '.txt', '.pdf', '.xlsx', '.xls', '.doc', '.docx')):
            downloadable_files.append(text)
    
    # Create local directory structure matching the URL path
    local_subdir = data_dir
    if path_parts:
        local_subdir = data_dir / Path(*path_parts)
        local_subdir.mkdir(parents=True, exist_ok=True)
    
    # Download files in current directory
    files_to_download = []
    for filename in downloadable_files:
        file_url = f"{base_url}{filename}"
        save_path = local_subdir / filename
        
        if not save_path.exists():
            files_to_download.append((file_url, save_path))
    
    if files_to_download:
        num_files = len(files_to_download)
        path_str = "/".join(path_parts) if path_parts else "root"
        print(f"Found {num_files} files in {survey_code}/{path_str}")
        
        for file_url, save_path in tqdm(files_to_download, desc=f"Downloading {survey_code}/{path_str}"):
            result = _download_worker(file_url, str(save_path.parent))
            if result:
                print(result)
    
    # Recursively crawl subdirectories
    for subdir in directories:
        subdir_url = f"{base_url}{subdir}/"
        new_path_parts = path_parts + [subdir]
        
        # Limit depth to prevent infinite crawling
        if len(new_path_parts) > 5:
            print(f"Max depth reached for {survey_code}/{'/'.join(new_path_parts)}")
            continue
            
        crawl_and_download(subdir_url, data_dir, survey_code, new_path_parts)

def download_survey_data(survey_code: str, dataset: str):
    """
    Downloads survey data from US Census Bureau for a specific survey and dataset.
    Recursively crawls through directory structure to find all data files.
    
    Args:
        survey_code (str): The survey program code (e.g., 'acs', 'popest', 'cps').
        dataset (str): The specific dataset within the survey program.
    """
    
    # Store downloads under the repo's data/census folder
    current_file = Path(__file__).resolve()
    repo_root = current_file.parent.parent
    
    # Create survey-specific directory structure
    data_dir = repo_root / 'data' / 'census_surveys' / survey_code / dataset
    data_dir.mkdir(parents=True, exist_ok=True)
    print(f"Data will be saved to: {data_dir}")
    
    # Construct the URL for the survey dataset
    dataset_url = f'https://www2.census.gov/programs-surveys/{survey_code}/{dataset}/'
    
    print(f"Starting recursive crawl for {survey_code}/{dataset}...")
    crawl_and_download(dataset_url, data_dir, survey_code)
    print(f"Completed crawl for {survey_code}/{dataset}\n")

def scrape_survey_documentation(survey_code):
    """Attempt to scrape documentation for a survey to understand data structure."""
    doc_urls = [
        f'https://www2.census.gov/programs-surveys/{survey_code}/technical-documentation/',
        f'https://www2.census.gov/programs-surveys/{survey_code}/documentation/',
        f'https://www.census.gov/programs-surveys/{survey_code}/'
    ]
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    for doc_url in doc_urls:
        try:
            response = requests.get(doc_url, headers=headers)
            response.raise_for_status()
            print(f"Found documentation at: {doc_url}")
            return doc_url
        except requests.exceptions.RequestException:
            continue
    
    print(f"No documentation found for {survey_code}")
    return None

if __name__ == "__main__":
    try:
        # --- Survey Selection ---
        print("Fetching available survey programs...")
        available_surveys = get_available_surveys()
        survey_descriptions = get_survey_descriptions()
        
        if not available_surveys:
            print("No surveys found. The Census website structure may have changed.")
            exit()
        
        # Focus on major demographic/economic surveys for USA with descriptions
        priority_surveys = ['acs', 'popest', 'cps', 'saipe', 'cbp', 'economic-census']
        filtered_surveys = [s for s in available_surveys if s in priority_surveys]
        
        # Add other surveys if priority ones don't exist
        other_surveys = [s for s in available_surveys if s not in priority_surveys]
        final_surveys = filtered_surveys + other_surveys[:10]  # Limit options
        
        # Create choices with descriptions
        survey_choices = []
        for survey in final_surveys:
            description = survey_descriptions.get(survey, f"Census survey: {survey}")
            survey_choices.append(f"{survey} - {description}")
        
        selected_survey_full = questionary.select(
            "Select the survey program:",
            choices=survey_choices,
            use_indicator=True
        ).ask()
        
        if not selected_survey_full:
            print("No survey selected. Exiting.")
            exit()
        
        # Extract just the survey code from the selection
        selected_survey = selected_survey_full.split(' - ')[0]
        
        # --- Dataset Selection ---
        print(f"Fetching available datasets for {selected_survey}...")
        available_datasets = get_survey_datasets(selected_survey)
        
        if not available_datasets:
            print(f"No datasets found for {selected_survey}.")
            exit()
        
        # Let user select multiple datasets
        selected_datasets = questionary.checkbox(
            f"Select datasets for {selected_survey} (space to toggle, enter to confirm):",
            choices=available_datasets[:20]  # Limit options for usability
        ).ask()
        
        if not selected_datasets:
            print("No datasets selected. Exiting.")
            exit()
        
        # --- Download Data ---
        for dataset in selected_datasets:
            print(f"\n{'='*50}")
            print(f"Processing {selected_survey}/{dataset}...")
            download_survey_data(survey_code=selected_survey, dataset=dataset)
        
        # --- Documentation ---
        doc_url = scrape_survey_documentation(selected_survey)
        if doc_url:
            print(f"\nDocumentation available at: {doc_url}")
            print("Review this URL to understand data structure and column meanings.")
        
    except KeyboardInterrupt:
        print("\nOperation cancelled by user. Exiting.")
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}")