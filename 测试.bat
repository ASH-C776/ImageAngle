@echo off
cd /d "%~dp0"

set "PYEXE=py"
where py >nul 2>nul || set "PYEXE=python"

rem Run tests with the offscreen platform so no window flashes up.
set QT_QPA_PLATFORM=offscreen

echo ============================================
echo   ImageAngle - run unit tests
echo ============================================
echo.

"%PYEXE%" -m pytest tests -q

echo.
pause
