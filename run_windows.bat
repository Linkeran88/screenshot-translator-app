@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
echo Starting Screenshot Translator...
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found. Please install Python 3.10+ and check "Add Python to PATH".
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment...
  python -m venv .venv
  if errorlevel 1 (
    echo Failed to create virtual environment.
    pause
    exit /b 1
  )
)

call ".venv\Scripts\activate.bat"
echo Installing dependencies...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo Failed to install dependencies.
  pause
  exit /b 1
)

echo Launching app...
python screenshot_translator_app.py
if errorlevel 1 (
  echo.
  echo App exited with an error.
  pause
  exit /b 1
)

pause
