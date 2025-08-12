@echo off
setlocal enabledelayedexpansion

:: 檢查 Python 是否安裝
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] Python 未安裝
    set /p choice="是否自動安裝 Python? (y/n):" 
    if /i "!choice!"=="y" (
        echo [*] 正在安裝 Python...
        powershell -Command "Invoke-WebRequest https://www.python.org/ftp/python/3.12.6/python-3.12.6-amd64.exe -OutFile python_installer.exe"
        python_installer.exe /quiet InstallAllUsers=1 PrependPath=1
        del python_installer.exe
    ) else (
        echo 請安裝 Python 後再執行
        pause
        exit /b
    )
)

:: 檢查 gallery-dl 是否安裝
python -m pip show gallery-dl >nul 2>&1
if %errorlevel% neq 0 (
    echo [*] 正在安裝 gallery-dl...
    python -m pip install --upgrade pip
    python -m pip install gallery-dl
)

:: 執行 dl.py
python dl.py %*
pause
