#!/usr/bin/env python3
"""
iCloud Media Lister

This script lists all photos and videos in your iCloud account,
sorted by size. It can help identify large media files and manage storage.
"""

import os
import sys
import argparse
import getpass
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Tuple

from pyicloud import PyiCloudService
from tqdm import tqdm

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def format_size(size_bytes: int) -> str:
    """Convert bytes to human readable format."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.2f} TB"

def get_password(username: str, password: str = None) -> str:
    """Get the password either from args or user input."""
    if password:
        return password
    
    return getpass.getpass(f"Enter iCloud password for {username}: ")

def authenticate_icloud(username: str, password: str = None) -> PyiCloudService:
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

def get_media_info(api: PyiCloudService, media_type: str = 'all') -> List[Dict]:
    """
    Get information about photos and videos in iCloud.
    Uses smart folders for efficient filtering when possible.
    """
    logger.info("Fetching media information from iCloud...")
    
    all_media = []
    
    try:
        if media_type == 'videos':
            # Use Videos smart folder for efficiency
            logger.info("Using Videos smart folder for efficient video fetching")
            photos_to_process = api.photos.albums['Videos']
        else:
            # For all media or just photos, we need to process everything
            # because the Photos smart folder might miss some images in other albums
            photos_to_process = api.photos.all
        
        with tqdm(desc=f"Fetching {media_type}") as pbar:
            for photo in photos_to_process:
                try:
                    # Determine if it's a video based on duration attribute
                    is_video = hasattr(photo, 'duration')
                    
                    # Skip if we're only looking for photos and this is a video
                    if media_type == 'photos' and is_video:
                        continue
                    
                    # Skip if we're only looking for videos and this is a photo
                    if media_type == 'videos' and not is_video:
                        continue
                    
                    media_info = {
                        'filename': photo.filename,
                        'size': photo.size,
                        'created': photo.created.strftime('%Y-%m-%d %H:%M:%S'),
                        'type': 'video' if is_video else 'photo'
                    }
                    
                    # Add duration for videos
                    if is_video:
                        media_info['duration'] = photo.duration
                    
                    all_media.append(media_info)
                    pbar.update(1)
                except Exception as e:
                    logger.error(f"Error processing {photo.filename}: {e}")
                    continue
                
    except KeyError:
        logger.warning("Videos smart folder not available, falling back to processing all media")
        # Fallback to processing all media if smart folder is not available
        return get_media_info(api, 'all')
    
    return all_media

def print_media_summary(media_list: List[Dict], total_count: int = None) -> None:
    """Print summary of media files."""
    # Calculate total sizes
    total_size = sum(m['size'] for m in media_list)
    photo_size = sum(m['size'] for m in media_list if m['type'] == 'photo')
    video_size = sum(m['size'] for m in media_list if m['type'] == 'video')
    
    photo_count = sum(1 for m in media_list if m['type'] == 'photo')
    video_count = sum(1 for m in media_list if m['type'] == 'video')
    
    print("\nMedia Summary:")
    if total_count and total_count > len(media_list):
        print(f"Showing {len(media_list)} of {total_count} total files (sorted by size)")
    else:
        print(f"Total files: {len(media_list)}")
    print(f"Photos: {photo_count} ({format_size(photo_size)})")
    print(f"Videos: {video_count} ({format_size(video_size)})")
    print(f"Total size: {format_size(total_size)}")
    
    # Print video durations if any videos are present
    if video_count > 0:
        total_duration = sum(m.get('duration', 0) for m in media_list if m['type'] == 'video')
        hours = total_duration // 3600
        minutes = (total_duration % 3600) // 60
        seconds = total_duration % 60
        print(f"Total video duration: {hours:02d}:{minutes:02d}:{seconds:02d}")

def main():
    """Main function to parse arguments and run the lister."""
    parser = argparse.ArgumentParser(
        description='List photos and videos in iCloud account sorted by size.'
    )
    
    parser.add_argument('--username', '-u', required=True,
                       help='iCloud username/email')
    parser.add_argument('--password', '-p',
                       help='iCloud password (if not provided, will prompt)')
    parser.add_argument('--min-size', '-m', type=float,
                       help='Minimum size in MB to include in the listing')
    parser.add_argument('--type', '-t', choices=['all', 'photos', 'videos'],
                       default='all', help='Type of media to list (default: all)')
    parser.add_argument('--limit', '-n', type=int,
                       help='Limit the number of records displayed')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Enable verbose logging')
    
    args = parser.parse_args()
    
    if args.verbose:
        logger.setLevel(logging.DEBUG)
    
    # Authenticate with iCloud
    api = authenticate_icloud(args.username, args.password)
    if not api:
        logger.error("Authentication failed. Exiting.")
        return 1
    
    # Get media information using smart folders when possible
    media_list = get_media_info(api, args.type)
    total_count = len(media_list)
    
    # Filter by minimum size if specified
    if args.min_size:
        min_bytes = args.min_size * 1024 * 1024  # Convert MB to bytes
        media_list = [m for m in media_list if m['size'] >= min_bytes]
    
    # Sort by size (largest first)
    media_list.sort(key=lambda x: x['size'], reverse=True)
    
    # Apply limit if specified
    if args.limit and args.limit > 0:
        original_count = len(media_list)
        media_list = media_list[:args.limit]
        if args.verbose:
            logger.debug(f"Showing {len(media_list)} of {original_count} matching files")
    
    # Print summary
    print_media_summary(media_list, total_count)
    
    # Print detailed listing
    print("\nDetailed Media Listing (sorted by size):")
    if any(m['type'] == 'video' for m in media_list):
        print(f"{'Size':>10} {'Type':>8} {'Duration':>8} {'Created':>19} Filename")
    else:
        print(f"{'Size':>10} {'Type':>8} {'Created':>19} Filename")
    print("-" * 80)
    
    for media in media_list:
        if media['type'] == 'video':
            duration = media.get('duration', 0)
            minutes = duration // 60
            seconds = duration % 60
            duration_str = f"{minutes:02d}:{seconds:02d}"
            print(f"{format_size(media['size']):>10} {media['type']:>8} {duration_str:>8} {media['created']} {media['filename']}")
        else:
            print(f"{format_size(media['size']):>10} {media['type']:>8} {'':>8} {media['created']} {media['filename']}")
    
    return 0

if __name__ == "__main__":
    sys.exit(main()) 