#!/bin/bash#!/bin/bash
echo -ne "\033]0;NS Gallery DL Machine\007"

SCRIPT_VERSION="1.0.2"
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

# Show usage when -h / --help is passed
if [[ "$1" == "-h" || "$1" == "--help" ]]; then
    echo ""
    echo "Usage: ./dl.sh [mode]"
    echo ""
    echo "  (no args)        Download URLs from dl.txt"
    echo "  -s / --server    Start the Flask server (port 7601)"
    echo "  -b / --bot       Start the Discord bot"
    echo "  -s -b            Start Flask server AND Discord bot together"
    echo "  -u / --update    Force-reinstall all dependencies"
    echo "  -h / --help      Show this help message"
    echo ""
    deactivate
    exit 0
fi

# Set terminal title based on mode flags
HAS_S=false; HAS_B=false
for arg in "$@"; do
    case "$arg" in
        -s|--server) HAS_S=true ;;
        -b|--bot)    HAS_B=true ;;
    esac
done
if $HAS_S && $HAS_B; then
    echo -ne "\033]0;NS Gallery DL - Server + Bot\007"
elif $HAS_S; then
    echo -ne "\033]0;NS Gallery DL - Server\007"
elif $HAS_B; then
    echo -ne "\033]0;NS Gallery DL - Bot\007"
elif [[ "$1" == "-u" || "$1" == "--update" ]]; then
    echo -ne "\033]0;NS Gallery DL - Update\007"
else
    echo -ne "\033]0;NS Gallery DL - Download\007"
fi

# Run the main script
echo "[*] Running download script..."
python3 dl.py "$@"

# Deactivate the virtual environment
deactivate

read -p "Press Enter to continue..."