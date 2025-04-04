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
import sqlite3
from datetime import datetime
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from PIL import Image
from tqdm import tqdm
from pyicloud import PyiCloudService

# Default log file paths
DEFAULT_TODO_DB = 'todo_uploads.db'
DEFAULT_GENERAL_LOG = 'icloud_upload.log'

# Global variables for log files - will be updated by CLI args if provided
TODO_DB = DEFAULT_TODO_DB
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

def init_database():
    """Initialize SQLite database with necessary tables."""
    try:
        with sqlite3.connect(TODO_DB) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS todo_photos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    photo_path TEXT UNIQUE NOT NULL,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status TEXT DEFAULT 'pending'
                )
            ''')
            conn.commit()
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
        sys.exit(1)

def remove_from_todo(photo_path):
    """Remove a successfully uploaded photo path from the todo database."""
    try:
        with sqlite3.connect(TODO_DB) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE todo_photos SET status = 'completed' WHERE photo_path = ?",
                (str(photo_path),)
            )
            conn.commit()
    except Exception as e:
        logger.error(f"Error removing {photo_path} from todo database: {e}")

def add_to_todo(photo_paths):
    """Add photo paths to the todo database if they're not already there."""
    try:
        with sqlite3.connect(TODO_DB) as conn:
            cursor = conn.cursor()
            # Use INSERT OR IGNORE to skip duplicates
            cursor.executemany(
                "INSERT OR IGNORE INTO todo_photos (photo_path) VALUES (?)",
                [(str(path),) for path in photo_paths]
            )
            conn.commit()
    except Exception as e:
        logger.error(f"Error adding paths to todo database: {e}")

def read_todo_list():
    """Read pending photos from the todo database."""
    try:
        with sqlite3.connect(TODO_DB) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT photo_path FROM todo_photos WHERE status = 'pending'")
            todo_paths = [Path(row[0]) for row in cursor.fetchall()]
            return todo_paths
    except Exception as e:
        logger.error(f"Error reading todo database: {e}")
        return []

def get_todo_stats():
    """Get statistics about todo items."""
    try:
        with sqlite3.connect(TODO_DB) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    status, 
                    COUNT(*) as count 
                FROM todo_photos 
                GROUP BY status
            """)
            return dict(cursor.fetchall())
    except Exception as e:
        logger.error(f"Error getting todo stats: {e}")
        return {}

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
    """Upload a single photo to iCloud and remove from todo list if successful."""
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
                return False
        else:
            # Upload to Camera Roll
            api.photos.upload_file(photo_path)
        
        # If upload was successful, remove from todo list
        remove_from_todo(photo_path)
        return True
    except Exception as e:
        logger.error(f"Error uploading {photo_path}: {e}")
        return False

def main():
    """Main function to parse arguments and run the uploader."""
    parser = argparse.ArgumentParser(description='Upload JPEG photos from a directory to iCloud.')
    
    # Create a mutually exclusive group for directory and retry mode
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument('--directory', '-d', help='Directory containing photos to upload (will be scanned recursively)')
    mode_group.add_argument('--retry', '-r', action='store_true', help='Retry uploads from the todo database')
    mode_group.add_argument('--stats', '-s', action='store_true', help='Show upload statistics and exit')
    
    parser.add_argument('--username', '-u', help='iCloud username/email')
    parser.add_argument('--password', '-p', help='iCloud password (if not provided, will prompt)')
    parser.add_argument('--album', '-a', help='iCloud album to upload to (if not specified, uploads to Camera Roll)')
    parser.add_argument('--threads', '-t', type=int, default=5, help='Number of upload threads (default: 5)')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose logging')
    parser.add_argument('--todo-db', '-f', default=DEFAULT_TODO_DB, 
                       help=f'Path to the todo database file (default: {DEFAULT_TODO_DB})')
    parser.add_argument('--general-log', '-g', default=DEFAULT_GENERAL_LOG,
                       help=f'Path to the general log file (default: {DEFAULT_GENERAL_LOG})')
    
    args = parser.parse_args()
    
    # Update global paths
    global TODO_DB, GENERAL_LOG
    TODO_DB = args.todo_db
    GENERAL_LOG = args.general_log
    
    # Initialize the database
    init_database()
    
    # Reconfigure logging with new file paths
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    logger.addHandler(logging.StreamHandler())
    logger.addHandler(logging.FileHandler(GENERAL_LOG))
    
    if args.verbose:
        logger.setLevel(logging.DEBUG)
    
    # Show stats if requested
    if args.stats:
        stats = get_todo_stats()
        logger.info("Upload Statistics:")
        logger.info(f"Pending uploads: {stats.get('pending', 0)}")
        logger.info(f"Completed uploads: {stats.get('completed', 0)}")
        return 0
    
    # Username is required for upload operations
    if not args.username:
        logger.error("Username is required for upload operations")
        return 1
    
    # Get photo list
    if args.retry:
        photos = read_todo_list()
        if not photos:
            logger.error(f"No pending uploads found in database. Exiting.")
            return 1
        logger.info(f"Found {len(photos)} pending uploads to process")
    else:
        photos = scan_directory(args.directory)
        if not photos:
            logger.error("No JPEG photos found to upload. Exiting.")
            return 1
        # Add new photos to todo list
        add_to_todo(photos)
        logger.info(f"Added {len(photos)} photos to todo list")
    
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
    stats = get_todo_stats()
    logger.info(f"Upload complete: {successful} successful, {failed} failed")
    if stats.get('pending', 0) > 0:
        logger.info(f"{stats['pending']} photos remaining to upload")
        logger.info(f"Run with --retry to attempt uploading remaining photos")
    else:
        logger.info("All photos have been uploaded successfully!")
        logger.info(f"Total completed uploads: {stats.get('completed', 0)}")
    
    return 0 if failed == 0 else 1

if __name__ == "__main__":
    sys.exit(main()) 