#!/bin/bash

# Set the name of the virtual environment directory
VENV_DIR="venv"
INSTALL_FLAG="$VENV_DIR/install.flag"

# Check if the virtual environment directory exists
if [ ! -d "$VENV_DIR" ]; then
    echo "[*] Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
    if [ $? -ne 0 ]; then
        echo "[!] Failed to create virtual environment. Please ensure Python is installed and accessible."
        exit 1
    fi
fi

# Activate the virtual environment
source "$VENV_DIR/bin/activate"

# Install dependencies if the flag file doesn't exist
if [ ! -f "$INSTALL_FLAG" ]; then
    echo "[*] Installing dependencies..."
    pip install -r requirements.txt
    pip install gallery-dl
    if [ $? -eq 0 ]; then
        touch "$INSTALL_FLAG"
    fi
fi

# Run the main script
echo "[*] Running download script..."
python3 dl.py "$@"

# Deactivate the virtual environment
deactivate

read -p "Press Enter to continue..."
