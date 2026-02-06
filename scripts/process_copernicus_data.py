"""
Copernicus Sentinel Data Processing and Analysis Tools

This module provides utilities for processing downloaded Sentinel satellite data,
including format conversion, band extraction, and basic analysis operations.

Supported Operations:
- SAFE format extraction and conversion
- Band extraction for multispectral data
- Cloud mask generation
- Basic raster statistics
- Data quality assessment
"""

import os
import json
import zipfile
import rasterio
import numpy as np
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import rasterio
from rasterio.plot import show
from rasterio.warp import reproject, Resampling
import geopandas as gpd
from shapely.geometry import box

class SentinelDataProcessor:
    """Class for processing Sentinel satellite data."""
    
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.processed_dir = data_dir / 'processed'
        self.processed_dir.mkdir(exist_ok=True)
    
    def extract_safe_archive(self, archive_path: str) -> Optional[Path]:
        """Extract SAFE format archive and return the extracted directory path."""
        try:
            with zipfile.ZipFile(archive_path, 'r') as zip_ref:
                zip_ref.extractall(self.data_dir)
            
            # Find the extracted SAFE directory
            archive_name = Path(archive_path).stem
            safe_dir = self.data_dir / archive_name
            
            if safe_dir.exists():
                print(f"Extracted: {archive_name}")
                return safe_dir
            else:
                print(f"Warning: Could not find extracted directory for {archive_name}")
                return None
                
        except Exception as e:
            print(f"Error extracting {archive_path}: {e}")
            return None
    
    def get_sentinel2_bands(self, safe_dir: Path) -> Dict[str, Path]:
        """Get paths to Sentinel-2 band files."""
        bands = {}
        
        # Sentinel-2 L1C/L2A structure
        img_dir = safe_dir / 'GRANULE' / next((safe_dir / 'GRANULE').iterdir()) / 'IMG_DATA'
        
        if img_dir.exists():
            for band_file in img_dir.glob('*.jp2'):
                # Extract band name from filename
                if 'B01' in band_file.name:
                    bands['coastal'] = band_file
                elif 'B02' in band_file.name:
                    bands['blue'] = band_file
                elif 'B03' in band_file.name:
                    bands['green'] = band_file
                elif 'B04' in band_file.name:
                    bands['red'] = band_file
                elif 'B05' in band_file.name:
                    bands['red_edge1'] = band_file
                elif 'B06' in band_file.name:
                    bands['red_edge2'] = band_file
                elif 'B07' in band_file.name:
                    bands['red_edge3'] = band_file
                elif 'B08' in band_file.name:
                    bands['nir'] = band_file
                elif 'B8A' in band_file.name:
                    bands['red_edge4'] = band_file
                elif 'B09' in band_file.name:
                    bands['water_vapor'] = band_file
                elif 'B10' in band_file.name:
                    bands['cirrus'] = band_file
                elif 'B11' in band_file.name:
                    bands['swir1'] = band_file
                elif 'B12' in band_file.name:
                    bands['swir2'] = band_file
        
        return bands
    
    def get_sentinel1_bands(self, safe_dir: Path) -> Dict[str, Path]:
        """Get paths to Sentinel-1 band files."""
        bands = {}
        
        # Sentinel-1 structure
        img_dir = safe_dir / 'measurement'
        
        if img_dir.exists():
            for band_file in img_dir.glob('*.tiff'):
                if 'vv' in band_file.name.lower():
                    bands['vv'] = band_file
                elif 'vh' in band_file.name.lower():
                    bands['vh'] = band_file
                elif 'hh' in band_file.name.lower():
                    bands['hh'] = band_file
                elif 'hv' in band_file.name.lower():
                    bands['hv'] = band_file
        
        return bands
    
    def extract_rgb_composite(self, safe_dir: Path, output_path: Optional[Path] = None) -> Optional[Path]:
        """Extract RGB composite from Sentinel-2 data."""
        bands = self.get_sentinel2_bands(safe_dir)
        
        if not all(band in bands for band in ['red', 'green', 'blue']):
            print("RGB bands not found in this product")
            return None
        
        if not output_path:
            product_name = safe_dir.name
            output_path = self.processed_dir / f"{product_name}_rgb.tif"
        
        try:
            # Read RGB bands
            with rasterio.open(bands['red']) as src_red:
                red = src_red.read(1)
                profile = src_red.profile
            
            with rasterio.open(bands['green']) as src_green:
                green = src_green.read(1)
            
            with rasterio.open(bands['blue']) as src_blue:
                blue = src_blue.read(1)
            
            # Stack bands
            rgb = np.stack([red, green, blue], axis=0)
            
            # Update profile for RGB output
            profile.update(count=3, dtype=rgb.dtype)
            
            # Write RGB composite
            with rasterio.open(output_path, 'w', **profile) as dst:
                dst.write(rgb)
            
            print(f"RGB composite saved: {output_path}")
            return output_path
            
        except Exception as e:
            print(f"Error creating RGB composite: {e}")
            return None
    
    def calculate_ndvi(self, safe_dir: Path, output_path: Optional[Path] = None) -> Optional[Path]:
        """Calculate NDVI from Sentinel-2 NIR and Red bands."""
        bands = self.get_sentinel2_bands(safe_dir)
        
        if not all(band in bands for band in ['nir', 'red']):
            print("NIR and Red bands not found for NDVI calculation")
            return None
        
        if not output_path:
            product_name = safe_dir.name
            output_path = self.processed_dir / f"{product_name}_ndvi.tif"
        
        try:
            # Read NIR and Red bands
            with rasterio.open(bands['nir']) as src_nir:
                nir = src_nir.read(1).astype(np.float32)
                profile = src_nir.profile
            
            with rasterio.open(bands['red']) as src_red:
                red = src_red.read(1).astype(np.float32)
            
            # Calculate NDVI: (NIR - Red) / (NIR + Red)
            # Add small epsilon to avoid division by zero
            epsilon = 1e-8
            ndvi = (nir - red) / (nir + red + epsilon)
            
            # Clip values to valid range [-1, 1]
            ndvi = np.clip(ndvi, -1, 1)
            
            # Update profile for NDVI output
            profile.update(count=1, dtype=np.float32)
            
            # Write NDVI
            with rasterio.open(output_path, 'w', **profile) as dst:
                dst.write(ndvi, 1)
            
            print(f"NDVI saved: {output_path}")
            return output_path
            
        except Exception as e:
            print(f"Error calculating NDVI: {e}")
            return None
    
    def get_raster_statistics(self, raster_path: Path) -> Dict:
        """Calculate basic statistics for a raster file."""
        try:
            with rasterio.open(raster_path) as src:
                data = src.read(1)
                
                # Mask nodata values
                if src.nodata is not None:
                    data = np.ma.masked_equal(data, src.nodata)
                
                stats = {
                    'mean': float(np.mean(data)),
                    'std': float(np.std(data)),
                    'min': float(np.min(data)),
                    'max': float(np.max(data)),
                    'median': float(np.median(data)),
                    'valid_pixels': int(np.count_nonzero(~np.ma.getmask(data))),
                    'total_pixels': int(data.size),
                    'nodata_pixels': int(np.count_nonzero(np.ma.getmask(data))),
                    'crs': str(src.crs),
                    'transform': list(src.transform)[:6],  # First 6 elements
                    'width': src.width,
                    'height': src.height
                }
                
                return stats
                
        except Exception as e:
            print(f"Error calculating statistics for {raster_path}: {e}")
            return {}
    
    def create_quicklook(self, raster_path: Path, output_path: Optional[Path] = None, 
                        width: int = 800) -> Optional[Path]:
        """Create a quicklook (thumbnail) image from raster data."""
        if not output_path:
            output_path = self.processed_dir / f"{raster_path.stem}_quicklook.jpg"
        
        try:
            with rasterio.open(raster_path) as src:
                # Calculate new height to maintain aspect ratio
                height = int(width * src.height / src.width)
                
                # Read and resample data
                data = src.read(
                    out_shape=(src.count, height, width),
                    resampling=Resampling.average
                )
                
                # Create output profile
                profile = src.profile
                profile.update(width=width, height=height, driver='JPEG')
                
                # Write quicklook
                with rasterio.open(output_path, 'w', **profile) as dst:
                    dst.write(data)
                
                print(f"Quicklook saved: {output_path}")
                return output_path
                
        except Exception as e:
            print(f"Error creating quicklook: {e}")
            return None
    
    def process_sentinel_product(self, archive_path: str, operations: List[str]) -> Dict[str, Optional[Path]]:
        """Process a Sentinel product with specified operations."""
        results = {}
        
        # Extract archive
        safe_dir = self.extract_safe_archive(archive_path)
        if not safe_dir:
            return results
        
        product_name = safe_dir.name
        
        # Perform requested operations
        for operation in operations:
            if operation == 'rgb':
                rgb_path = self.extract_rgb_composite(safe_dir)
                if rgb_path:
                    results['rgb'] = rgb_path
                    results['rgb_stats'] = self.get_raster_statistics(rgb_path)
                    results['rgb_quicklook'] = self.create_quicklook(rgb_path)
            
            elif operation == 'ndvi':
                ndvi_path = self.calculate_ndvi(safe_dir)
                if ndvi_path:
                    results['ndvi'] = ndvi_path
                    results['ndvi_stats'] = self.get_raster_statistics(ndvi_path)
                    results['ndvi_quicklook'] = self.create_quicklook(ndvi_path)
            
            elif operation == 'statistics':
                bands = self.get_sentinel2_bands(safe_dir) if 'sentinel-2' in product_name.lower() else self.get_sentinel1_bands(safe_dir)
                stats = {}
                for band_name, band_path in bands.items():
                    stats[band_name] = self.get_raster_statistics(band_path)
                results['band_statistics'] = stats
        
        return results
    
    def batch_process_directory(self, operations: List[str]) -> Dict[str, Dict]:
        """Process all Sentinel products in a directory."""
        all_results = {}
        
        # Find all zip archives
        archives = list(self.data_dir.glob('*.zip'))
        
        if not archives:
            print("No Sentinel archives found in directory")
            return all_results
        
        print(f"Found {len(archives)} archives to process")
        
        for archive_path in archives:
            print(f"\nProcessing: {archive_path.name}")
            product_results = self.process_sentinel_product(str(archive_path), operations)
            all_results[archive_path.name] = product_results
        
        return all_results

def main():
    """Main function for interactive processing."""
    try:
        # Get data directory
        current_file = Path(__file__).resolve()
        repo_root = current_file.parent.parent
        data_dir = repo_root / 'data' / 'copernicus'
        
        if not data_dir.exists():
            print(f"Data directory not found: {data_dir}")
            print("Please download Sentinel data first using get_copernicus_sentinel.py")
            return
        
        # Select mission directory
        mission_dirs = [d for d in data_dir.iterdir() if d.is_dir()]
        if not mission_dirs:
            print("No mission directories found")
            return
        
        mission_choices = [d.name for d in mission_dirs]
        selected_mission = questionary.select(
            "Select mission directory:",
            choices=mission_choices
        ).ask()
        
        if not selected_mission:
            print("No mission selected. Exiting.")
            return
        
        mission_dir = data_dir / selected_mission
        
        # Select processing operations
        operation_choices = [
            'rgb - Create RGB composite',
            'ndvi - Calculate NDVI',
            'statistics - Calculate band statistics',
            'quicklook - Create thumbnail images'
        ]
        
        selected_operations = questionary.checkbox(
            "Select processing operations:",
            choices=operation_choices
        ).ask()
        
        if not selected_operations:
            print("No operations selected. Exiting.")
            return
        
        # Extract operation codes
        operations = []
        for op in selected_operations:
            op_code = op.split(' - ')[0]
            operations.append(op_code)
        
        # Process data
        processor = SentinelDataProcessor(mission_dir)
        results = processor.batch_process_directory(operations)
        
        # Save results summary
        summary_path = mission_dir / 'processing_summary.json'
        with open(summary_path, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        print(f"\nProcessing completed. Summary saved to: {summary_path}")
        
    except KeyboardInterrupt:
        print("\nOperation cancelled by user. Exiting.")
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}")

if __name__ == "__main__":
    main()