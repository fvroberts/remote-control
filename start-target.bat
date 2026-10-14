@echo off
cd /d "%~dp0"
python target.py %*
if errorlevel 1 (
    echo If dependencies are missing, run install.bat once on this device.
    pause
    exit /b 1
)
