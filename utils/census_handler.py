import os
import sys
import pandas as pd
import geopandas as gpd
import zipfile

import warnings
warnings.filterwarnings('ignore')

YEAR = 2024
D_DIR = "D:\\census\\"


def get_census_counties(year=YEAR):
    """
    Reads shapefiles from zip archives in a directory, extracts the necessary
    geospatial data directly into a GeoDataFrame, and filters by state FIPS code.

    Args:
        state_fips (str): A two-digit FIPS code for the state to filter by.
        D_DIR (str): The path to the directory containing the zipped census files.

    Returns:
        geopandas.GeoDataFrame: A GeoDataFrame containing road data for the specified state.
    """
    d_year_dir = os.path.join(D_DIR, str(year))
    county_gdf = gpd.GeoDataFrame()

    for file_name in os.listdir(d_year_dir):
        shpfile = None

        if file_name.endswith('_county.zip'):
            zip_path = os.path.join(d_year_dir, file_name)
            base_name = os.path.splitext(file_name)[0]

            # Get the FIPS code from the file name. Assumes naming convention `tl_<YEAR>_us_county`
            # For example, a file named 'tl_2024_us_county' will have all county boundaries for <YEAR>'
            shp_in_zip_path = None
            try:
                # Open the zip file to inspect its contents
                with zipfile.ZipFile(zip_path, 'r') as zf:
                    # Find the .shp file, which can be located at any path inside the zip
                    shp_in_zip_path = next((path for path in zf.namelist() if path.endswith('.shp')), None)
                    
                    if shp_in_zip_path is None:
                        print(f"Could not find a shapefile in {zip_path}")
                        continue

                # Construct the final path string using the zip:// protocol
                full_path = f"zip://{zip_path}!/{shp_in_zip_path}"
                # print(f"Attempting to read from internal path: {full_path}")

                # GeoPandas reads directly from the zipped file
                county_gdf = gpd.read_file(full_path)
                                
            except Exception as e:
                print(f"Could not read shapefile from {zip_path}: {e}")
                continue    
    return county_gdf


def get_census_boundaries(state_fips, year=YEAR):
    """
    Reads shapefiles from zip archives in a directory, extracts the necessary
    geospatial data directly into a GeoDataFrame, and filters by state FIPS code.

    Args:
        state_fips (str): A two-digit FIPS code for the state to filter by.
        D_DIR (str): The path to the directory containing the zipped census files.

    Returns:
        geopandas.GeoDataFrame: A GeoDataFrame containing boundary data for the specified state.
    """
    d_year_dir = os.path.join(D_DIR, str(year))
    cousub_gdf = gpd.GeoDataFrame()
    tract_gdf = gpd.GeoDataFrame()
    place_gdf = gpd.GeoDataFrame()

    for file_name in os.listdir(d_year_dir):
        shpfile = None

        # County Subdivisions
        if 'cousub' in file_name:
            zip_path = os.path.join(d_year_dir, file_name)
            base_name = os.path.splitext(file_name)[0]
            
            # Find the FIPS for the base_name of file_name
            fips = base_name.split('_')[2]
            
            # Add State Filter
            if fips == state_fips:
                shp_in_zip_path = None
                
                try:
                    # Open the zip file to inspect its contents
                    with zipfile.ZipFile(zip_path, 'r') as zf:
                        # Find the .shp file, which can be located at any path inside the zip
                        shp_in_zip_path = next((path for path in zf.namelist() if path.endswith('.shp')), None)
                        
                        if shp_in_zip_path is None:
                            print(f"Could not find a shapefile in {zip_path}")
                            continue

                    # Construct the final path string using the zip:// protocol
                    full_path = f"zip://{zip_path}!/{shp_in_zip_path}"
                    # print(f"Attempting to read from internal path: {full_path}")

                    # GeoPandas reads directly from the zipped file
                    tmp_gdf = gpd.read_file(full_path)
                    tmp_gdf['STATEFP'] = fips
                    tmp_gdf['boundary_type'] = 'CSD'
                    
                    # Use pd.concat with ignore_index=True for efficiency
                    cousub_gdf = pd.concat([cousub_gdf, tmp_gdf], ignore_index=True)
                                    
                except Exception as e:
                    print(f"Could not read shapefile from {zip_path}: {e}")
                    continue   

        # Census Tracts (county comprehensive)
        elif 'tract' in file_name:
            zip_path = os.path.join(d_year_dir, file_name)
            base_name = os.path.splitext(file_name)[0]
            
            # Find the FIPS for the base_name of file_name
            fips = base_name.split('_')[2]
            
            # Add State Filter
            if fips == state_fips:
                shp_in_zip_path = None
                
                try:
                    # Open the zip file to inspect its contents
                    with zipfile.ZipFile(zip_path, 'r') as zf:
                        # Find the .shp file, which can be located at any path inside the zip
                        shp_in_zip_path = next((path for path in zf.namelist() if path.endswith('.shp')), None)
                        
                        if shp_in_zip_path is None:
                            print(f"Could not find a shapefile in {zip_path}")
                            continue

                    # Construct the final path string using the zip:// protocol
                    full_path = f"zip://{zip_path}!/{shp_in_zip_path}"
                    # print(f"Attempting to read from internal path: {full_path}")

                    # GeoPandas reads directly from the zipped file
                    tmp_gdf = gpd.read_file(full_path)
                    tmp_gdf['STATEFP'] = fips
                    tmp_gdf['boundary_type'] = 'Tract'
                    
                    # Use pd.concat with ignore_index=True for efficiency
                    tract_gdf = pd.concat([tract_gdf, tmp_gdf], ignore_index=True)
                                    
                except Exception as e:
                    print(f"Could not read shapefile from {zip_path}: {e}")
                    continue  

        # Census designated places (county non-comprehensive, but includes human readable names for townships/cities etc.)
        elif 'place' in file_name:
            zip_path = os.path.join(d_year_dir, file_name)
            base_name = os.path.splitext(file_name)[0]
            
            # Find the FIPS for the base_name of file_name
            fips = base_name.split('_')[2]
            
            # Add State Filter
            if fips == state_fips:
                shp_in_zip_path = None
                
                try:
                    # Open the zip file to inspect its contents
                    with zipfile.ZipFile(zip_path, 'r') as zf:
                        # Find the .shp file, which can be located at any path inside the zip
                        shp_in_zip_path = next((path for path in zf.namelist() if path.endswith('.shp')), None)
                        
                        if shp_in_zip_path is None:
                            print(f"Could not find a shapefile in {zip_path}")
                            continue

                    # Construct the final path string using the zip:// protocol
                    full_path = f"zip://{zip_path}!/{shp_in_zip_path}"
                    # print(f"Attempting to read from internal path: {full_path}")

                    # GeoPandas reads directly from the zipped file
                    tmp_gdf = gpd.read_file(full_path)
                    tmp_gdf['STATEFP'] = fips
                    tmp_gdf['boundary_type'] = 'CDP'
                    
                    # Use pd.concat with ignore_index=True for efficiency
                    place_gdf = pd.concat([place_gdf, tmp_gdf], ignore_index=True)
                                    
                except Exception as e:
                    print(f"Could not read shapefile from {zip_path}: {e}")
                    continue  


    return cousub_gdf, place_gdf, tract_gdf


def get_census_roads(state_fips, year=YEAR):
    """
    Reads shapefiles from zip archives in a directory, extracts the necessary
    geospatial data directly into a GeoDataFrame, and filters by state FIPS code.

    Args:
        state_fips (str): A two-digit FIPS code for the state to filter by.
        D_DIR (str): The path to the directory containing the zipped census files.

    Returns:
        geopandas.GeoDataFrame: A GeoDataFrame containing road data for the specified state.
    """
    d_year_dir = os.path.join(D_DIR, str(year))
    roads_gdf = gpd.GeoDataFrame()

    for file_name in os.listdir(d_year_dir):
        shpfile = None

        if file_name.endswith('_roads.zip'):
            zip_path = os.path.join(d_year_dir, file_name)
            base_name = os.path.splitext(file_name)[0]

            # Get the FIPS code from the file name. Assumes naming convention `tl_<YEAR>_<FIPS>_roads`
            # For example, a file named 'tl_2024_01001_roads' will have fips '01001'
            fips = base_name.split('_')[2]
            
            # Add State Filter
            if fips[0:2] == state_fips:
                # print(f"Processing zip file for County FIPS: {fips}")

                shp_in_zip_path = None
                try:
                    # Open the zip file to inspect its contents
                    with zipfile.ZipFile(zip_path, 'r') as zf:
                        # Find the .shp file, which can be located at any path inside the zip
                        shp_in_zip_path = next((path for path in zf.namelist() if path.endswith('.shp')), None)
                        
                        if shp_in_zip_path is None:
                            print(f"Could not find a shapefile in {zip_path}")
                            continue

                    # Construct the final path string using the zip:// protocol
                    full_path = f"zip://{zip_path}!/{shp_in_zip_path}"
                    # print(f"Attempting to read from internal path: {full_path}")

                    # GeoPandas reads directly from the zipped file
                    tmp_gdf = gpd.read_file(full_path)
                    
                    tmp_gdf['STATEFP'] = fips[0:2]
                    tmp_gdf['COUNTYFP'] = fips[2:]
                    
                    # Use pd.concat with ignore_index=True for efficiency
                    roads_gdf = pd.concat([roads_gdf, tmp_gdf], ignore_index=True)
                
                except Exception as e:
                    print(f"Could not read shapefile from {zip_path}: {e}")
                    continue    
    return roads_gdf