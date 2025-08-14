#!/bin/bash

VENV_DIR="venv"
INSTALL_FLAG="$VENV_DIR/install.flag"

if [ -f "$INSTALL_FLAG" ]; then
    echo "[*] Removing installation flag to force an update on next run."
    rm "$INSTALL_FLAG"
else
    echo "[*] Installation flag not found. No action needed."
    echo "[*] The main script will install dependencies on its next run."
fi

echo ""
echo "[*] Update flag set. Run dl.sh to apply updates."

read -p "Press Enter to continue..."