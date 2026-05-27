@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
if "%~1"=="" (
  echo Drag a .argosmodel file onto this bat file to install it.
  echo Or run: install_argos_model_file.bat path\to\model.argosmodel
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  python -m venv .venv
)
call ".venv\Scripts\activate.bat"
python -m pip install -r requirements_offline.txt
python install_argos_models.py "%~1"
pause
