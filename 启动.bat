@echo off
cd /d "%~dp0"

set "PYEXE=py"
where py >nul 2>nul || set "PYEXE=python"

echo ============================================
echo   ImageAngle - starting
echo   folder : %CD%
echo   python : %PYEXE%
echo ============================================
echo.

"%PYEXE%" -m app.main

if errorlevel 1 (
  echo.
  echo [ERROR] Start failed. Please send the messages above.
  pause
)
