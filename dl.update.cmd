@echo off
setlocal

set VENV_DIR=venv
set INSTALL_FLAG=%VENV_DIR%\install.flag

if exist "%INSTALL_FLAG%" (
    echo [*] Removing installation flag to force an update on next run.
    del "%INSTALL_FLAG%"
) else (
    echo [*] Installation flag not found. No action needed.
    echo [*] The main script will install dependencies on its next run.
)

echo.
echo [*] Update flag set. Run dl.cmd to apply updates.

endlocal
pause