@echo off
setlocal enabledelayedexpansion

:: �z�� Python �Ƿ��b
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] Python δ���b
    set /p choice="�Ƿ��ԄӰ��b Python? (y/n):" 
    if /i "!choice!"=="y" (
        echo [*] ���ڰ��b Python...
        powershell -Command "Invoke-WebRequest https://www.python.org/ftp/python/3.12.6/python-3.12.6-amd64.exe -OutFile python_installer.exe"
        python_installer.exe /quiet InstallAllUsers=1 PrependPath=1
        del python_installer.exe
    ) else (
        echo Ո���b Python ���و���
        pause
        exit /b
    )
)

:: �z�� gallery-dl �Ƿ��b
python -m pip show gallery-dl >nul 2>&1
if %errorlevel% neq 0 (
    echo [*] ���ڰ��b gallery-dl...
    python -m pip install --upgrade pip
    python -m pip install gallery-dl
)

:: ���� dl.py
python dl.py %*
pause
