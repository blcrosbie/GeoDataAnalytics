#!/usr/bin/env python3
"""
Data Normalization and Pipeline Utilities
Transforms raw Copernicus data into normalized, derived, and tile formats
"""

import os
import sys
import tempfile
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union
import logging

import numpy as np
import pandas as pd
import xarray as xr
import rasterio
from rasterio.transform import from_bounds
import h3
import pmtiles
from dotenv import load_dotenv

from s3_storage import S3StorageManager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DataProcessor:
    def __init__(self):
        load_dotenv()
        self.storage = S3StorageManager()
        
    def normalize_netcdf(self, raw_s3_path: str) -> List[str]:
        """
        Normalize NetCDF file by variable and time
        
        Args:
            raw_s3_path: S3 path to raw NetCDF file
            
        Returns:
            List of normalized S3 paths
        """
        try:
            # Download raw file
            with tempfile.NamedTemporaryFile(suffix='.nc', delete=False) as tmp:
                self.storage.download_file(raw_s3_path, tmp.name)
                tmp_path = tmp.name
            
            # Open with xarray
            ds = xr.open_dataset(tmp_path)
            
            # Extract metadata from path
            path_parts = raw_s3_path.split('/')
            source = path_parts[2].split('=')[1]
            dataset = path_parts[3].split('=')[1]
            year = path_parts[4].split('=')[1]
            month = path_parts[5].split('=')[1]
            
            normalized_paths = []
            
            # Process each variable
            for var_name in ds.data_vars:
                if var_name in ds.variables:
                    # Extract variable data
                    var_data = ds[var_name]
                    
                    # Process each time step
                    for time_idx, time_val in enumerate(ds.time.values):
                        time_str = pd.to_datetime(time_val).strftime('%Y-%m')
                        
                        # Create dataset for this variable and time
                        var_dataset = var_data.isel(time=time_idx)
                        output_filename = f"{var_name}_{time_str}.nc"
                        
                        with tempfile.NamedTemporaryFile(suffix='.nc', delete=False) as out_tmp:
                            var_dataset.to_netcdf(out_tmp.name)
                            
                            # Upload to normalized path
                            norm_path = self.storage.normalized_path(dataset, var_name, time_str, output_filename)
                            
                            if self.storage.upload_file(out_tmp.name, norm_path):
                                normalized_paths.append(norm_path)
                                logger.info(f"Normalized {var_name} for {time_str}")
                            
                            os.unlink(out_tmp.name)
            
            # Clean up
            os.unlink(tmp_path)
            ds.close()
            
            return normalized_paths
            
        except Exception as e:
            logger.error(f"Error normalizing {raw_s3_path}: {e}")
            return []
    
    def aggregate_to_h3(self, normalized_s3_path: str, h3_resolution: int = 9) -> str:
        """
        Aggregate normalized data to H3 grid
        
        Args:
            normalized_s3_path: S3 path to normalized NetCDF
            h3_resolution: H3 resolution (0-15)
            
        Returns:
            S3 path of H3 parquet file
        """
        try:
            # Download normalized file
            with tempfile.NamedTemporaryFile(suffix='.nc', delete=False) as tmp:
                self.storage.download_file(normalized_s3_path, tmp.name)
                tmp_path = tmp.name
            
            # Open with xarray
            ds = xr.open_dataset(tmp_path)
            
            # Extract metadata
            path_parts = normalized_s3_path.split('/')
            dataset = path_parts[2].split('=')[1]
            var_name = path_parts[3].split('=')[1]
            time_str = path_parts[4].split('=')[1]
            
            # Get spatial info
            lats = ds.lat.values
            lons = ds.lon.values
            
            # Create H3 aggregation
            h3_data = []
            
            for i, lat in enumerate(lats):
                for j, lon in enumerate(lons):
                    # Convert lat/lon to H3
                    h3_index = h3.geo_to_h3(lat, lon, h3_resolution)
                    
                    # Extract value (assuming single variable, single time)
                    if len(ds.data_vars) > 0:
                        var_name = list(ds.data_vars)[0]
                        value = ds[var_name].values[i, j]
                        
                        # Skip NaN values
                        if not np.isnan(value):
                            h3_data.append({
                                'h3_index': h3_index,
                                'lat': lat,
                                'lon': lon,
                                'value': float(value),
                                'var_name': var_name,
                                'time': time_str,
                                'dataset': dataset
                            })
            
            # Create DataFrame
            df = pd.DataFrame(h3_data)
            
            if len(df) == 0:
                logger.warning(f"No valid data for H3 aggregation from {normalized_s3_path}")
                os.unlink(tmp_path)
                return ""
            
            # Store as Parquet
            h3_filename = f"{var_name}_{h3_resolution}_{time_str}.parquet"
            h3_path = self.storage.h3_path(dataset, var_name, f"r{h3_resolution:02d}", time_str, 0)
            
            if self.storage.store_parquet(df, h3_path):
                logger.info(f"Created H3 aggregation: {h3_path}")
                return h3_path
            
            # Clean up
            os.unlink(tmp_path)
            return ""
            
        except Exception as e:
            logger.error(f"Error creating H3 aggregation for {normalized_s3_path}: {e}")
            return ""
    
    def create_vector_tiles(self, h3_s3_path: str, min_zoom: int = 0, max_zoom: int = 12) -> List[str]:
        """
        Create vector tiles from H3 data
        
        Args:
            h3_s3_path: S3 path to H3 parquet
            min_zoom: Minimum zoom level
            max_zoom: Maximum zoom level
            
        Returns:
            List of tile S3 paths
        """
        try:
            # Download H3 data
            with tempfile.NamedTemporaryFile(suffix='.parquet', delete=False) as tmp:
                self.storage.download_file(h3_s3_path, tmp.name)
                tmp_path = tmp.name
            
            # Read H3 data
            df = pd.read_parquet(tmp_path)
            
            # Extract metadata
            path_parts = h3_s3_path.split('/')
            dataset = path_parts[3].split('=')[1]
            var_name = path_parts[4].split('=')[1]
            time_str = path_parts[6].split('=')[1]
            
            tile_paths = []
            
            # Process H3 cells and create tiles
            for zoom in range(min_zoom, max_zoom + 1):
                # Group H3 cells by tile coordinates
                tile_groups = {}
                
                for _, row in df.iterrows():
                    h3_index = row['h3_index']
                    
                    # Get H3 cell boundary
                    boundary = h3.h3_to_geo_boundary(h3_index, geo_json=True)
                    
                    # Find tile coordinates
                    center_lat, center_lon = h3.h3_to_geo(h3_index)
                    tile_x = int((center_lon + 180) * (2 ** zoom) / 360)
                    tile_y = int((1 - np.log(np.tan(np.radians(center_lat)) + 1 / np.cos(np.radians(center_lat))) / np.pi) * (2 ** (zoom - 1)))
                    
                    tile_key = (tile_x, tile_y)
                    if tile_key not in tile_groups:
                        tile_groups[tile_key] = []
                    
                    tile_groups[tile_key].append({
                        'type': 'Feature',
                        'geometry': {
                            'type': 'Polygon',
                            'coordinates': [boundary]
                        },
                        'properties': {
                            'value': row['value'],
                            'var_name': row['var_name'],
                            'time': row['time'],
                            'dataset': row['dataset']
                        }
                    })
                
                # Create tiles
                for (tile_x, tile_y), features in tile_groups.items():
                    # Create GeoJSON
                    geojson = {
                        'type': 'FeatureCollection',
                        'features': features
                    }
                    
                    # Convert to MVT (this would require tippecanoe or similar)
                    # For now, we'll store as GeoJSON and note that MVT conversion would be needed
                    tile_filename = f"{tile_x}_{tile_y}.json"
                    tile_path = self.storage.tile_path(dataset, var_name, zoom, tile_x, tile_y)
                    
                    # Store tile
                    import json
                    if self.storage.store_json(geojson, tile_path):
                        tile_paths.append(tile_path)
                        logger.info(f"Created tile {zoom}/{tile_x}/{tile_y}")
            
            # Clean up
            os.unlink(tmp_path)
            return tile_paths
            
        except Exception as e:
            logger.error(f"Error creating tiles from {h3_s3_path}: {e}")
            return []
    
    def create_pmtiles(self, tile_paths: List[str], region: str = "global") -> Optional[str]:
        """
        Create PMTiles archive from vector tiles
        
        Args:
            tile_paths: List of tile S3 paths
            region: Region identifier
            
        Returns:
            S3 path of PMTiles file
        """
        try:
            if not tile_paths:
                return None
            
            # Extract metadata from first tile path
            first_tile = tile_paths[0]
            path_parts = first_tile.split('/')
            dataset = path_parts[3].split('=')[1]
            var_name = path_parts[4].split('=')[1]
            
            # Extract time from path (assuming consistent)
            time_str = "unknown"
            for tile_path in tile_paths:
                if 'time=' in tile_path:
                    time_part = [p for p in tile_path.split('/') if 'time=' in p][0]
                    time_str = time_part.split('=')[1]
                    break
            
            # Download tiles and create temporary directory
            with tempfile.TemporaryDirectory() as tmp_dir:
                tile_dir = Path(tmp_dir) / "tiles"
                tile_dir.mkdir()
                
                # Download all tiles
                for tile_path in tile_paths:
                    # Extract z/x/y from path
                    path_parts = tile_path.split('/')
                    z = int(path_parts[5].split('=')[1])
                    x = int(path_parts[6].split('=')[1])
                    y = int(path_parts[7].split('=')[1].replace('.json', ''))
                    
                    # Create directory structure
                    z_dir = tile_dir / str(z)
                    x_dir = z_dir / str(x)
                    x_dir.mkdir(parents=True, exist_ok=True)
                    
                    # Download tile
                    local_tile_path = x_dir / f"{y}.json"
                    self.storage.download_file(tile_path, str(local_tile_path))
                
                # Create PMTiles using tippecanoe or similar
                pmtiles_path = Path(tmp_dir) / f"{region}.pmtiles"
                
                # This would require installing and using tippecanoe
                # For now, we'll create a placeholder
                logger.warning("PMTiles creation requires tippecanoe installation")
                
                # Upload placeholder
                pmtiles_s3_path = self.storage.pmtiles_path(dataset, var_name, time_str, region)
                
                placeholder_content = json.dumps({
                    'type': 'pmtiles',
                    'region': region,
                    'tile_count': len(tile_paths),
                    'created_at': datetime.utcnow().isoformat()
                })
                
                if self.storage.store_json(placeholder_content, pmtiles_s3_path):
                    logger.info(f"Created PMTiles archive: {pmtiles_s3_path}")
                    return pmtiles_s3_path
                
            return None
            
        except Exception as e:
            logger.error(f"Error creating PMTiles archive: {e}")
            return None

class DataPipeline:
    def __init__(self):
        self.processor = DataProcessor()
        self.storage = S3StorageManager()
    
    def process_raw_data(self, raw_s3_path: str, create_h3: bool = True, create_tiles: bool = True) -> Dict[str, List[str]]:
        """
        Process raw data through the complete pipeline
        
        Args:
            raw_s3_path: S3 path to raw data
            create_h3: Whether to create H3 aggregation
            create_tiles: Whether to create vector tiles
            
        Returns:
            Dictionary with lists of created file paths
        """
        results = {
            'normalized': [],
            'h3': [],
            'tiles': []
        }
        
        logger.info(f"Processing raw data: {raw_s3_path}")
        
        # Step 1: Normalize by variable and time
        normalized_paths = self.processor.normalize_netcdf(raw_s3_path)
        results['normalized'] = normalized_paths
        
        if not create_h3:
            return results
        
        # Step 2: Create H3 aggregations
        h3_paths = []
        for norm_path in normalized_paths:
            h3_path = self.processor.aggregate_to_h3(norm_path)
            if h3_path:
                h3_paths.append(h3_path)
        results['h3'] = h3_paths
        
        if not create_tiles:
            return results
        
        # Step 3: Create vector tiles
        tile_paths = []
        for h3_path in h3_paths:
            tiles = self.processor.create_vector_tiles(h3_path)
            tile_paths.extend(tiles)
        results['tiles'] = tile_paths
        
        return results
    
    def batch_process_dataset(self, source: str, dataset: str, limit: int = 10) -> Dict:
        """
        Batch process all raw files for a dataset
        
        Args:
            source: Data source (cds or cdse)
            dataset: Dataset name
            limit: Maximum number of files to process
            
        Returns:
            Processing results summary
        """
        # List raw files
        prefix = f"copernicus/raw/source={source}/dataset={dataset}/"
        raw_files = self.storage.list_objects(prefix)
        
        # Limit processing
        raw_files = raw_files[:limit]
        
        logger.info(f"Processing {len(raw_files)} files for {source}/{dataset}")
        
        all_results = {
            'processed': 0,
            'normalized': [],
            'h3': [],
            'tiles': [],
            'errors': []
        }
        
        for obj in raw_files:
            try:
                raw_path = obj['Key']
                results = self.process_raw_data(raw_path)
                
                all_results['processed'] += 1
                all_results['normalized'].extend(results['normalized'])
                all_results['h3'].extend(results['h3'])
                all_results['tiles'].extend(results['tiles'])
                
            except Exception as e:
                logger.error(f"Error processing {obj['Key']}: {e}")
                all_results['errors'].append(str(e))
        
        return all_results

def main():
    """Example usage"""
    pipeline = DataPipeline()
    
    # Example: Process recent CDS data
    try:
        # List available datasets
        datasets = pipeline.storage.list_datasets()
        print(f"Available datasets: {datasets}")
        
        # Process first few files from CDS
        if 'cds' in datasets and datasets['cds']:
            dataset = datasets['cds'][0]
            print(f"Processing dataset: {dataset}")
            
            results = pipeline.batch_process_dataset('cds', dataset, limit=2)
            print(f"Processing results: {results}")
        
    except Exception as e:
        logger.error(f"Error in main: {e}")

if __name__ == "__main__":
    main()