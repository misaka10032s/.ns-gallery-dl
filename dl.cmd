@echo off
setlocal

REM Set the name of the virtual environment directory
set VENV_DIR=venv
set INSTALL_FLAG=%VENV_DIR%\install.flag

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

REM Install dependencies if the flag file doesn't exist
if not exist "%INSTALL_FLAG%" (
    echo [*] Installing dependencies...
    pip install -r requirements.txt
    pip install gallery-dl
    if %errorlevel% equ 0 (
        echo. > "%INSTALL_FLAG%"
    )
)

REM Run the main script
echo [*] Running download script...
python dl.py %*

endlocal
pause
