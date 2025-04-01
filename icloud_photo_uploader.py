#!/usr/bin/env python3
"""
iCloud Photo Uploader

This script scans a specified directory for photos and uploads them to iCloud.
Only JPEG files are supported for upload.
"""

import os
import sys
import argparse
import getpass
import logging
from datetime import datetime
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from PIL import Image
from tqdm import tqdm
from pyicloud import PyiCloudService

# Default log file paths
DEFAULT_FAILED_UPLOADS_LOG = 'failed_uploads.log'
DEFAULT_GENERAL_LOG = 'icloud_upload.log'

# Global variables for log files - will be updated by CLI args if provided
FAILED_UPLOADS_LOG = DEFAULT_FAILED_UPLOADS_LOG
GENERAL_LOG = DEFAULT_GENERAL_LOG

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(GENERAL_LOG)
    ]
)
logger = logging.getLogger(__name__)

# Create a separate logger for failed uploads
failed_logger = logging.getLogger('failed_uploads')
failed_logger.setLevel(logging.INFO)
failed_handler = logging.FileHandler(FAILED_UPLOADS_LOG)
failed_handler.setFormatter(logging.Formatter('%(message)s'))
failed_logger.addHandler(failed_handler)
failed_logger.propagate = False

# File extensions for photos - now only JPEGs
PHOTO_EXTENSIONS = {'.jpg', '.jpeg'}

def is_photo_file(file_path):
    """Check if a file is a JPEG photo based on its extension."""
    return Path(file_path).suffix.lower() in PHOTO_EXTENSIONS

def scan_directory(directory):
    """Scan directory recursively for JPEG photos and return a list of photo paths."""
    photo_paths = []
    directory_path = Path(directory)
    
    if not directory_path.exists():
        logger.error(f"Directory not found: {directory}")
        return []
        
    logger.info(f"Scanning directory recursively: {directory}")
    
    for root, _, files in os.walk(directory):
        for filename in files:
            file_path = Path(root) / filename
            if is_photo_file(file_path):
                photo_paths.append(file_path)
    
    logger.info(f"Found {len(photo_paths)} JPEG photos")
    return photo_paths

def get_password(username, password=None):
    """Get the password either from args or user input."""
    # Return if password was provided directly
    if password:
        return password
    
    # Prompt user for password
    entered_password = getpass.getpass(f"Enter iCloud password for {username}: ")
    return entered_password

def authenticate_icloud(username, password=None):
    """Authenticate with iCloud."""
    password = get_password(username, password)

    logger.info(f"Authenticating to iCloud as {username}")
    api = PyiCloudService(username, password)
    
    if api.requires_2fa:
        logger.info("Two-factor authentication required.")
        code = input("Enter the verification code: ")
        result = api.validate_2fa_code(code)
        logger.info(f"2FA validation result: {result}")
        
        if not result:
            logger.error("Failed to verify 2FA code")
            return None
    
    return api

def upload_photo(api, photo_path, album_name=None):
    """Upload a single photo to iCloud using upload_file method."""
    try:
        # Upload to the specified album or default to Camera Roll
        if album_name:
            # Check if album exists, create if it doesn't
            albums = {album.title: album for album in api.photos.albums}
            if album_name not in albums:
                logger.info(f"Creating new album: {album_name}")
                api.photos.create_album(album_name)
                # Refresh albums list
                time.sleep(2)  # Give iCloud time to process
                albums = {album.title: album for album in api.photos.albums}
            
            # Upload to the specified album
            if album_name in albums:
                # Upload to album using the path
                albums[album_name].add(photo_path)
            else:
                logger.error(f"Could not find or create album: {album_name}")
                failed_logger.info(str(photo_path))
                return False
        else:
            # Upload to Camera Roll
            api.photos.upload_file(photo_path)
        
        return True
    except Exception as e:
        logger.error(f"Error uploading {photo_path}: {e}")
        failed_logger.info(str(photo_path))
        return False

def read_failed_uploads():
    """Read the failed uploads log file and return a list of photo paths."""
    try:
        if not os.path.exists(FAILED_UPLOADS_LOG):
            logger.error(f"Failed uploads log file not found: {FAILED_UPLOADS_LOG}")
            return []
            
        with open(FAILED_UPLOADS_LOG, 'r') as f:
            failed_paths = [Path(line.strip()) for line in f.readlines()]
            
        # Remove duplicates while preserving order
        failed_paths = list(dict.fromkeys(failed_paths))
        return failed_paths
    except Exception as e:
        logger.error(f"Error reading failed uploads log: {e}")
        return []

def clear_failed_uploads_log():
    """Clear the contents of the failed uploads log file."""
    try:
        with open(FAILED_UPLOADS_LOG, 'w') as f:
            pass  # Just truncate the file
    except Exception as e:
        logger.error(f"Error clearing failed uploads log: {e}")

def main():
    """Main function to parse arguments and run the uploader."""
    parser = argparse.ArgumentParser(description='Upload JPEG photos from a directory to iCloud.')
    
    # Create a mutually exclusive group for directory and retry mode
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument('--directory', '-d', help='Directory containing photos to upload (will be scanned recursively)')
    mode_group.add_argument('--retry', '-r', action='store_true', help='Retry failed uploads from the failed uploads log')
    
    parser.add_argument('--username', '-u', required=True, help='iCloud username/email')
    parser.add_argument('--password', '-p', help='iCloud password (if not provided, will prompt)')
    parser.add_argument('--album', '-a', help='iCloud album to upload to (if not specified, uploads to Camera Roll)')
    parser.add_argument('--threads', '-t', type=int, default=5, help='Number of upload threads (default: 5)')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose logging')
    parser.add_argument('--failed-log', '-f', default=DEFAULT_FAILED_UPLOADS_LOG, 
                       help=f'Path to the failed uploads log file (default: {DEFAULT_FAILED_UPLOADS_LOG})')
    parser.add_argument('--general-log', '-g', default=DEFAULT_GENERAL_LOG,
                       help=f'Path to the general log file (default: {DEFAULT_GENERAL_LOG})')
    
    args = parser.parse_args()
    
    # Update global log file paths
    global FAILED_UPLOADS_LOG, GENERAL_LOG
    FAILED_UPLOADS_LOG = args.failed_log
    GENERAL_LOG = args.general_log
    
    # Reconfigure logging with new file paths
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    logger.addHandler(logging.StreamHandler())
    logger.addHandler(logging.FileHandler(GENERAL_LOG))
    
    # Reconfigure failed uploads logger
    for handler in failed_logger.handlers[:]:
        failed_logger.removeHandler(handler)
    failed_handler = logging.FileHandler(FAILED_UPLOADS_LOG)
    failed_handler.setFormatter(logging.Formatter('%(message)s'))
    failed_logger.addHandler(failed_handler)
    
    if args.verbose:
        logger.setLevel(logging.DEBUG)
    
    # Get photo list
    if args.retry:
        photos = read_failed_uploads()
        if not photos:
            logger.error(f"No failed uploads found to retry in {FAILED_UPLOADS_LOG}. Exiting.")
            return 1
        logger.info(f"Found {len(photos)} failed uploads to retry")
    else:
        photos = scan_directory(args.directory)
        if not photos:
            logger.error("No JPEG photos found to upload. Exiting.")
            return 1
    
    # Authenticate with iCloud
    api = authenticate_icloud(
        args.username, 
        args.password
    )
    if not api:
        logger.error("Authentication failed. Exiting.")
        return 1
    
    # Upload photos
    logger.info(f"Starting upload of {len(photos)} JPEG photos" +
                (f" to album '{args.album}'" if args.album else ""))
    
    successful = 0
    failed = 0
    
    with ThreadPoolExecutor(max_workers=args.threads) as executor:
        # Create upload tasks
        upload_tasks = {
            executor.submit(upload_photo, api, photo, args.album): photo
            for photo in photos
        }
        
        # Process results with progress bar
        with tqdm(total=len(photos), desc="Uploading") as pbar:
            for future in upload_tasks:
                photo = upload_tasks[future]
                try:
                    result = future.result()
                    if result:
                        successful += 1
                    else:
                        failed += 1
                except Exception as e:
                    logger.error(f"Error processing {photo}: {e}")
                    failed += 1
                finally:
                    pbar.update(1)
    
    # Final report
    logger.info(f"Upload complete: {successful} successful, {failed} failed")
    if failed > 0:
        logger.info(f"Failed uploads have been logged to {FAILED_UPLOADS_LOG}")
    elif args.retry and successful > 0:
        # Clear the failed uploads log if all retries were successful
        clear_failed_uploads_log()
        logger.info("All retries successful - cleared failed uploads log")
    
    return 0 if failed == 0 else 1

if __name__ == "__main__":
    sys.exit(main()) 