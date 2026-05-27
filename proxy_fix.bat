@echo off
chcp 65001 >nul
echo Clearing Python/pip proxy settings for this user...
set HTTP_PROXY=
set HTTPS_PROXY=
set ALL_PROXY=
set http_proxy=
set https_proxy=
set all_proxy=
python -m pip config unset global.proxy >nul 2>nul
python -m pip config unset user.proxy >nul 2>nul
echo Done. If pip still connects to 127.0.0.1, close this terminal and run run_windows.bat again.
pause
