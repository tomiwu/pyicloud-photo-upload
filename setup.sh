#!/bin/bash
# setup.sh
# Script to set up a virtual environment and install required packages for iCloud Photo Uploader

echo "Setting up environment for iCloud Photo Uploader..."

# Determine the script's directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Check if Python 3 is installed
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is required but not installed. Please install Python 3 and try again."
    exit 1
fi

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    if [ $? -ne 0 ]; then
        echo "Error: Failed to create virtual environment. Please check your Python installation."
        exit 1
    fi
else
    echo "Using existing virtual environment."
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate
if [ $? -ne 0 ]; then
    echo "Error: Failed to activate virtual environment."
    exit 1
fi

# Update pip
echo "Updating pip..."
pip install --upgrade pip

# Install local pyicloud package from lib directory
echo "Installing pyicloud from local wheel file..."
if [ -f "lib/pyicloud-1.0.0.dev1-py3-none-any.whl" ]; then
    pip install lib/pyicloud-1.0.0.dev1-py3-none-any.whl
    if [ $? -ne 0 ]; then
        echo "Error: Failed to install pyicloud wheel file."
        exit 1
    fi
else
    echo "Error: pyicloud wheel file not found in lib directory."
    exit 1
fi

# Install other required packages
echo "Installing other required packages..."
pip install pillow tqdm python-dateutil

echo "Setup complete! You can now run the script with:"
echo "  source venv/bin/activate"
echo "  python icloud_photo_uploader.py --help"
echo ""
echo "Make sure to deactivate the virtual environment when done:"
echo "  deactivate" 