@echo off
setlocal
rem Keep the console open even if a command or the batch file itself fails.
if defined REMOTE_CONTROL_LAUNCHER goto run
set "REMOTE_CONTROL_LAUNCHER=1"
"%ComSpec%" /d /k call "%~f0" %*
exit /b

:run
cd /d "%~dp0"
if errorlevel 1 goto folder_error
set "REMOTE_CONTROL_PYTHON=python"
python -c "import sys; assert sys.version_info >= (3, 10)" >nul 2>&1
if not errorlevel 1 goto launch
set "REMOTE_CONTROL_PYTHON=py -3"
py -3 -c "import sys; assert sys.version_info >= (3, 10)" >nul 2>&1
if not errorlevel 1 goto launch
echo Python 3.10 or newer could not be started.
echo Check python --version or py -3 --version in Command Prompt.
echo If Python is blocked by device policy, ask your administrator for help.
exit /b 1

:folder_error
echo Could not open the project folder: %~dp0
exit /b 1

:launch
%REMOTE_CONTROL_PYTHON% target.py %*
if errorlevel 1 goto failed
echo Session ended. You can close this window.
exit /b 0

:failed
echo.
echo Target failed. Read the error above.
echo If packages are missing, run install.bat once on this device.
echo If batch files are blocked, run python target.py from Command Prompt.
exit /b 1
