#!/bin/bash

# Set the name of the virtual environment directory
VENV_DIR="venv"

# Check if the virtual environment directory exists
if [ ! -d "$VENV_DIR" ]; then
    echo "[!] Virtual environment not found. Please run dl.sh first to create it."
    exit 1
fi

# Activate the virtual environment
source "$VENV_DIR/bin/activate"

# Upgrade pip
echo "[*] Upgrading pip..."
pip install --upgrade pip

# Upgrade gallery-dl
echo "[*] Upgrading gallery-dl..."
pip install --upgrade gallery-dl

echo "[*] Update process finished."

# Deactivate the virtual environment
deactivate

read -p "Press Enter to continue..."
