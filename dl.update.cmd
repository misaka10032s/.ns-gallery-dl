@echo off
setlocal

REM Set the name of the virtual environment directory
set VENV_DIR=venv

REM Check if the virtual environment directory exists
if not exist "%VENV_DIR%\Scripts\activate.bat" (
    echo [!] Virtual environment not found. Please run dl.cmd first to create it.
    exit /b 1
)

REM Activate the virtual environment
call "%VENV_DIR%\Scripts\activate.bat"

REM Upgrade pip
echo [*] Upgrading pip...
python -m pip install --upgrade pip

REM Upgrade gallery-dl
echo [*] Upgrading gallery-dl...
pip install --upgrade gallery-dl

echo [*] Update process finished.

endlocal
pause
