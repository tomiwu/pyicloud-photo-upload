# iCloud Photo Uploader

A Python utility to scan a directory for photos and upload them to iCloud.

## Features

- Scan directories recursively for JPEG photos
- Extract EXIF data to preserve original photo dates
- Upload photos to iCloud (either to Camera Roll or a specific album)
- Multi-threaded uploads for better performance
- Support for JPEG image formats (.jpg, .jpeg)
- Detailed logging

## Requirements

- Python 3.6+
- iCloud account
- Required Python packages (installed automatically with setup script)

## Installation

1. Clone this repository:
   ```
   git clone https://github.com/yourusername/icloud-photo-uploader.git
   cd icloud-photo-uploader
   ```

2. Use the setup script to create a virtual environment and install requirements:

   ```
   ./setup.sh
   ```

   This will:
   - Create a virtual environment
   - Install the required packages including the local pyicloud wheel from the lib directory
   - Set up everything needed to run the script

## Usage

Basic usage:

```
# Activate the virtual environment first
source venv/bin/activate

# Then run the script
python icloud_photo_uploader.py /path/to/photos --username your.email@icloud.com
```

### Command Line Arguments

- `directory`: Directory containing photos to upload (required, will be scanned recursively)
- `--username`, `-u`: iCloud username/email (required)
- `--password`, `-p`: iCloud password (if not provided, will prompt)
- `--album`, `-a`: iCloud album to upload to (if not specified, uploads to Camera Roll)
- `--threads`, `-t`: Number of upload threads (default: 5)
- `--verbose`, `-v`: Enable verbose logging

### Examples

Upload photos to a specific album:
```
python icloud_photo_uploader.py ~/Pictures/Vacation --username your.email@icloud.com --album "Summer Vacation 2023"
```

Specify number of threads:
```
python icloud_photo_uploader.py ~/Pictures/Vacation --username your.email@icloud.com --threads 10
```

## Authentication

The script handles two-factor authentication (2FA) if enabled on your iCloud account. When prompted, enter the verification code received on your trusted device.

## Notes

- Only JPEG files (.jpg, .jpeg) are supported for upload
- The directory is scanned recursively, so all JPEG files in subdirectories will be found
- For large uploads, the process may take time. The script provides a progress bar to track progress.
- If uploads fail, check the log file (icloud_upload.log) for details.

## License

MIT

## Disclaimer

This tool is not affiliated with Apple Inc. Use at your own risk. Always back up your photos before bulk operations. 