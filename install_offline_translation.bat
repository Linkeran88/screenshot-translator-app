@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
echo Installing offline translation engine: Argos Translate...
echo.
set HTTP_PROXY=
set HTTPS_PROXY=
set ALL_PROXY=
set http_proxy=
set https_proxy=
set all_proxy=

where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found. Please install Python 3.10+.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment...
  python -m venv .venv
)
call ".venv\Scripts\activate.bat"
python -m pip config unset global.proxy >nul 2>nul
python -m pip install --upgrade pip
python -m pip install -r requirements_offline.txt
if errorlevel 1 (
  echo.
  echo Failed to install Argos Translate.
  echo Please check network or download wheels manually.
  pause
  exit /b 1
)

echo Installing Chinese-English offline models...
python install_argos_models.py
pause
