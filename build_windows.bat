@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found. Please install Python 3.10+ and check "Add Python to PATH".
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" python -m venv .venv
call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

if exist "app_icon.ico" (
  python -m PyInstaller --noconfirm --windowed --onefile --icon app_icon.ico --name ScreenshotTranslator screenshot_translator_app.py
) else (
  python -m PyInstaller --noconfirm --windowed --onefile --name ScreenshotTranslator screenshot_translator_app.py
)

echo.
echo Build finished. Check dist\ScreenshotTranslator.exe
pause
