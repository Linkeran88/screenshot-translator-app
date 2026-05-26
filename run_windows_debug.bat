@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
echo Writing debug_log.txt...
call run_windows.bat > debug_log.txt 2>&1
type debug_log.txt
echo.
echo Debug log saved to debug_log.txt
pause
