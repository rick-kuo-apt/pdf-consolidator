@echo off
REM PDF Consolidator - Source Distribution Launcher
REM ================================================
REM This script sets up a Python environment and runs the app.
REM Requires: Python 3.10+ installed on the system
REM
REM On first run, this will:
REM   1. Create a local .venv folder
REM   2. Install required packages (PySide6, pypdf)
REM   3. Launch the application
REM
REM Subsequent runs will just launch the app.

setlocal EnableDelayedExpansion

echo.
echo PDF Consolidator
echo ================
echo.

REM Get the directory where this script is located
set "SCRIPT_DIR=%~dp0"
set "VENV_DIR=%SCRIPT_DIR%.venv"
set "APP_DIR=%SCRIPT_DIR%pdf_consolidator"

REM Check if Python is available
where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo ERROR: Python is not installed or not on PATH.
    echo.
    echo Please install Python 3.10 or later from:
    echo   https://www.python.org/downloads/
    echo.
    echo During installation, check "Add Python to PATH"
    echo.
    pause
    exit /b 1
)

REM Check Python version
for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo Found Python %PYVER%

REM Check if venv exists
if exist "%VENV_DIR%\Scripts\python.exe" (
    echo Using existing virtual environment...
    goto :run_app
)

REM Create virtual environment
echo.
echo First-time setup: Creating virtual environment...
echo This may take a minute...
echo.

python -m venv "%VENV_DIR%"
if %ERRORLEVEL% neq 0 (
    echo ERROR: Failed to create virtual environment.
    echo.
    echo Possible causes:
    echo   - Python installation is incomplete
    echo   - Disk is full
    echo   - Antivirus blocking
    echo.
    pause
    exit /b 1
)

REM Activate and install dependencies
echo Installing dependencies...
echo.

call "%VENV_DIR%\Scripts\activate.bat"

REM Upgrade pip (suppress warnings)
python -m pip install --upgrade pip --quiet 2>nul

REM Install requirements
if exist "%SCRIPT_DIR%requirements.txt" (
    pip install -r "%SCRIPT_DIR%requirements.txt" --quiet
) else (
    pip install PySide6 pypdf --quiet
)

if %ERRORLEVEL% neq 0 (
    echo.
    echo ERROR: Failed to install dependencies.
    echo.
    echo Possible causes:
    echo   - No internet connection
    echo   - Corporate proxy blocking pip
    echo   - pip is blocked by policy
    echo.
    echo If behind a proxy, try:
    echo   set HTTPS_PROXY=http://proxy:port
    echo   %0
    echo.
    pause
    exit /b 1
)

echo Setup complete!
echo.

:run_app
REM Run the application
echo Starting PDF Consolidator...
echo.

"%VENV_DIR%\Scripts\python.exe" -m pdf_consolidator.app

if %ERRORLEVEL% neq 0 (
    echo.
    echo Application exited with error code %ERRORLEVEL%
    pause
)

endlocal
