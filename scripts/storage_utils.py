#!/usr/bin/env python3
"""
Storage utilities for monitoring and managing local data storage
"""

import os
import shutil
import logging
from pathlib import Path
from typing import Dict, List, Tuple
import psutil

logger = logging.getLogger(__name__)

class StorageManager:
    """Manages local storage with monitoring and cleanup capabilities"""
    
    def __init__(self, base_data_dir: Path, storage_limit_gb: float = 50.0, warning_threshold: float = 0.8):
        """
        Initialize storage manager
        
        Args:
            base_data_dir: Base directory for data storage
            storage_limit_gb: Maximum storage to use in GB
            warning_threshold: Warning threshold (0.8 = 80%)
        """
        self.base_data_dir = base_data_dir
        self.storage_limit_bytes = storage_limit_gb * 1024 * 1024 * 1024
        self.warning_threshold = warning_threshold
        self.cds_dir = base_data_dir / 'cds'
        self.cdse_dir = base_data_dir / 'cdse'
        
        # Ensure directories exist
        self.cds_dir.mkdir(parents=True, exist_ok=True)
        self.cdse_dir.mkdir(parents=True, exist_ok=True)
    
    def get_disk_usage(self) -> Dict[str, int]:
        """Get disk usage statistics"""
        stat = shutil.disk_usage(self.base_data_dir)
        return {
            'total': stat.total,
            'used': stat.used,
            'free': stat.free,
            'percentage_used': stat.used / stat.total
        }
    
    def get_data_directory_usage(self) -> Dict[str, int]:
        """Get usage of our data directories"""
        usage = {}
        
        for dir_name, dir_path in [('cds', self.cds_dir), ('cdse', self.cdse_dir)]:
            if dir_path.exists():
                size = sum(f.stat().st_size for f in dir_path.rglob('*') if f.is_file())
                usage[dir_name] = size
            else:
                usage[dir_name] = 0
        
        usage['total_data'] = sum(usage.values())
        return usage
    
    def check_storage_status(self) -> Dict[str, any]:
        """Check storage status and return information"""
        disk_usage = self.get_disk_usage()
        data_usage = self.get_data_directory_usage()
        
        storage_ratio = data_usage['total_data'] / self.storage_limit_bytes
        is_warning = storage_ratio >= self.warning_threshold
        is_critical = storage_ratio >= 1.0
        
        return {
            'disk_total_gb': disk_usage['total'] / (1024**3),
            'disk_used_gb': disk_usage['used'] / (1024**3),
            'disk_free_gb': disk_usage['free'] / (1024**3),
            'disk_percentage': disk_usage['percentage_used'],
            'data_cds_gb': data_usage['cds'] / (1024**3),
            'data_cdse_gb': data_usage['cdse'] / (1024**3),
            'data_total_gb': data_usage['total_data'] / (1024**3),
            'data_limit_gb': self.storage_limit_bytes / (1024**3),
            'data_usage_percentage': storage_ratio,
            'is_warning': is_warning,
            'is_critical': is_critical
        }
    
    def cleanup_old_files(self, source: str = 'all', keep_files: int = 10) -> Dict[str, int]:
        """
        Clean up old files, keeping the most recent N files per source
        
        Args:
            source: 'cds', 'cdse', or 'all'
            keep_files: Number of most recent files to keep
            
        Returns:
            Dictionary with cleanup statistics
        """
        cleaned_files = 0
        freed_bytes = 0
        
        directories = []
        if source == 'all':
            directories = [('cds', self.cds_dir), ('cdse', self.cdse_dir)]
        elif source == 'cds':
            directories = [('cds', self.cds_dir)]
        elif source == 'cdse':
            directories = [('cdse', self.cdse_dir)]
        
        for source_name, dir_path in directories:
            if not dir_path.exists():
                continue
            
            # Get all files with their modification times
            files = []
            for file_path in dir_path.rglob('*'):
                if file_path.is_file():
                    files.append((file_path.stat().st_mtime, file_path))
            
            # Sort by modification time (oldest first)
            files.sort()
            
            # Remove oldest files, keeping the most recent N
            files_to_remove = files[:-keep_files] if len(files) > keep_files else []
            
            for mtime, file_path in files_to_remove:
                try:
                    file_size = file_path.stat().st_size
                    file_path.unlink()
                    cleaned_files += 1
                    freed_bytes += file_size
                    logger.info(f"Removed old file: {file_path}")
                except Exception as e:
                    logger.error(f"Failed to remove {file_path}: {e}")
        
        return {
            'files_removed': cleaned_files,
            'bytes_freed': freed_bytes,
            'gb_freed': freed_bytes / (1024**3)
        }
    
    def ensure_storage_space(self, required_bytes: int, source: str) -> bool:
        """
        Ensure enough storage space, cleanup if necessary
        
        Args:
            required_bytes: Bytes required for new download
            source: Source type ('cds' or 'cdse')
            
        Returns:
            True if space is available, False otherwise
        """
        status = self.check_storage_status()
        
        # Check if we have enough space
        available_space = self.storage_limit_bytes - status['total_data'] * (1024**3)
        
        if available_space >= required_bytes:
            return True
        
        logger.warning(f"Storage limit reached. Cleaning up old {source} files...")
        
        # Cleanup old files from the specific source first
        cleanup_result = self.cleanup_old_files(source, keep_files=5)
        
        # Check again
        status_after = self.check_storage_status()
        available_space_after = self.storage_limit_bytes - status_after['total_data'] * (1024**3)
        
        if available_space_after >= required_bytes:
            logger.info(f"Cleanup successful. Freed {cleanup_result['gb_freed']:.2f} GB")
            return True
        
        # If still not enough, cleanup all sources
        logger.warning("Still insufficient space. Cleaning up all sources...")
        cleanup_result = self.cleanup_old_files('all', keep_files=3)
        
        status_final = self.check_storage_status()
        available_space_final = self.storage_limit_bytes - status_final['total_data'] * (1024**3)
        
        if available_space_final >= required_bytes:
            logger.info(f"Final cleanup successful. Freed {cleanup_result['gb_freed']:.2f} GB")
            return True
        
        logger.error(f"Insufficient storage space. Required: {required_bytes/(1024**3):.2f} GB, Available: {available_space_final/(1024**3):.2f} GB")
        return False
    
    def get_local_path(self, source: str, dataset: str, year: str, month: str, filename: str) -> Path:
        """
        Generate local file path for storage
        
        Args:
            source: 'cds' or 'cdse'
            dataset: Dataset name
            year: Year string
            month: Month string
            filename: Filename
            
        Returns:
            Path object for local storage
        """
        base_dir = self.cds_dir if source == 'cds' else self.cdse_dir
        return base_dir / dataset / year / month / filename
    
    def log_storage_status(self):
        """Log current storage status"""
        status = self.check_storage_status()
        
        logger.info("=== Storage Status ===")
        logger.info(f"Disk Usage: {status['disk_used_gb']:.1f}/{status['disk_total_gb']:.1f} GB ({status['disk_percentage']:.1%})")
        logger.info(f"CDS Data: {status['data_cds_gb']:.2f} GB")
        logger.info(f"CDSE Data: {status['data_cdse_gb']:.2f} GB")
        logger.info(f"Total Data: {status['data_total_gb']:.2f}/{status['data_limit_gb']:.1f} GB ({status['data_usage_percentage']:.1%})")
        
        if status['is_warning']:
            logger.warning("⚠️  Storage usage above warning threshold!")
        if status['is_critical']:
            logger.error("🚨 Storage limit reached!")
        logger.info("====================")