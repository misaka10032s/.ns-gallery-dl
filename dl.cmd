@echo off
title NS Gallery DL Machine
setlocal enabledelayedexpansion

set SCRIPT_VERSION=1.0.2
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

REM if -u / -update is on, do `del "%INSTALL_FLAG%"`
if "%~1"=="-u"  (
    del "%INSTALL_FLAG%"
) else if "%~1"=="-update" (
    del "%INSTALL_FLAG%"
)

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

REM Show usage hint when -h / --help is passed
if "%~1"=="-h" goto :usage
if "%~1"=="--help" goto :usage

REM Set window title based on mode flags
set "HAS_S="
set "HAS_B="
for %%A in (%*) do (
    if /i "%%A"=="-s"       set "HAS_S=1"
    if /i "%%A"=="--server" set "HAS_S=1"
    if /i "%%A"=="-b"       set "HAS_B=1"
    if /i "%%A"=="--bot"    set "HAS_B=1"
)
if defined HAS_S (
    if defined HAS_B (
        title NS Gallery DL - Server + Bot
    ) else (
        title NS Gallery DL - Server
    )
) else if defined HAS_B (
    title NS Gallery DL - Bot
) else if /i "%~1"=="-u" (
    title NS Gallery DL - Update
) else if /i "%~1"=="--update" (
    title NS Gallery DL - Update
) else (
    title NS Gallery DL - Download
)

REM Run the main script
echo [*] Running download script...
python dl.py %*
goto :EOF

:usage
echo.
echo Usage: dl.cmd [mode]
echo.
echo   (no args)        Download URLs from dl.txt
echo   -s / --server    Start the Flask server (port 7601)
echo   -b / --bot       Start the Discord bot
echo   -s -b            Start Flask server AND Discord bot together
echo   -u / --update    Force-reinstall all dependencies
echo   -h / --help      Show this help message
echo.

endlocal
pause