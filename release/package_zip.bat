@echo off
REM Package PDF Consolidator for distribution
REM This is a wrapper that calls the PowerShell packaging script.

echo.
echo PDF Consolidator - Package for Distribution
echo ============================================
echo.

REM Check if PowerShell is available
where powershell >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo ERROR: PowerShell is required but not found on PATH.
    echo Please run from PowerShell directly: .\package_zip.ps1
    pause
    exit /b 1
)

REM Run the PowerShell script
powershell -ExecutionPolicy Bypass -File "%~dp0package_zip.ps1" %*

if %ERRORLEVEL% neq 0 (
    echo.
    echo Packaging failed with error code %ERRORLEVEL%
    pause
    exit /b %ERRORLEVEL%
)

pause
