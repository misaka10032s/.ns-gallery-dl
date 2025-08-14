@echo off
setlocal enabledelayedexpansion

set SCRIPT_VERSION=1.0.0
set VENV_DIR=venv
set INSTALL_FLAG=%VENV_DIR%\install.flag

echo [*] Script version: %SCRIPT_VERSION%

REM Check if the virtual environment directory exists
if not exist "%VENV_DIR%\Scripts\activate.bat" (
    echo [*] Creating virtual environment...
    python -m venv %VENV_DIR%
    if %errorlevel% neq 0 (
        echo [!] Failed to create virtual environment. Please ensure Python is installed and accessible.
        exit /b 1
    )
)

REM Activate the virtual environment
call "%VENV_DIR%\Scripts\activate.bat"

set "NEEDS_INSTALL="
if not exist "%INSTALL_FLAG%" (
    set NEEDS_INSTALL=true
) else (
    set /p INSTALLED_VERSION=<"%INSTALL_FLAG%"
    echo [*] Installed version: !INSTALLED_VERSION!
    echo [*] Script version: %SCRIPT_VERSION%
    if "!INSTALLED_VERSION!" neq "%SCRIPT_VERSION%" (
        set NEEDS_INSTALL=true
        set "MSG=[*] Installed version (!INSTALLED_VERSION!) is older than script version (%SCRIPT_VERSION%)."
        echo !MSG!
    )
)

if defined NEEDS_INSTALL (
    echo [*] Installing/updating dependencies...
    pip install -r requirements.txt --upgrade
    pip install gallery-dl --upgrade
    if %errorlevel% equ 0 (
        echo %SCRIPT_VERSION%>"%INSTALL_FLAG%"
    )
) else (
    echo [*] Dependencies are up to date.
)

REM Run the main script
echo [*] Running download script...
python dl.py %*

endlocal
pause