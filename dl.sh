#!/bin/bash

SCRIPT_VERSION="1.0.0"
VENV_DIR="venv"
INSTALL_FLAG="$VENV_DIR/install.flag"

echo "[*] Script version: $SCRIPT_VERSION"

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

# if -u / -update is on, remove "$INSTALL_FLAG"
if [[ "$1" == "-u" || "$1" == "-update" ]]; then
    rm -f "$INSTALL_FLAG"
fi

NEEDS_INSTALL=false
if [ ! -f "$INSTALL_FLAG" ]; then
    NEEDS_INSTALL=true
else
    INSTALLED_VERSION=$(cat "$INSTALL_FLAG")
    if [ "$INSTALLED_VERSION" != "$SCRIPT_VERSION" ]; then
        NEEDS_INSTALL=true
        echo "[*] Installed version ($INSTALLED_VERSION) is older than script version ($SCRIPT_VERSION)."
    fi
fi

if [ "$NEEDS_INSTALL" = true ]; then
    echo "[*] Installing/updating dependencies..."
    pip install -r requirements.txt --upgrade
    pip install gallery-dl --upgrade
    if [ $? -eq 0 ]; then
        echo "$SCRIPT_VERSION" > "$INSTALL_FLAG"
    fi
else
    echo "[*] Dependencies are up to date."
fi

# Run the main script
echo "[*] Running download script..."
python3 dl.py "$@"

# Deactivate the virtual environment
deactivate

read -p "Press Enter to continue..."