@echo off
cd /d "%~dp0"
python -m pip show pygame >nul 2>&1
if errorlevel 1 goto install
rem pygame and pygame-ce share the same import files. Remove the old package first.
python -m pip uninstall -y pygame
if errorlevel 1 goto failed
python -m pip install --user --only-binary=:all: --force-reinstall pygame-ce==2.5.8
if errorlevel 1 goto failed
:install
python -m pip install --user --only-binary=pygame-ce,Pillow -r requirements.txt
if errorlevel 1 goto failed
echo Installation complete. Use start-target.bat or start-host.bat.
pause
exit /b 0
:failed
echo Installation failed. Check the error above; device restrictions may need administrator help.
pause
exit /b 1
