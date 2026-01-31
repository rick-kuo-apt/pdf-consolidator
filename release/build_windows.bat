@echo off
REM Build PDF Consolidator for Windows
REM This is a wrapper that calls the PowerShell build script.

echo.
echo PDF Consolidator - Windows Build
echo =================================
echo.

REM Check if PowerShell is available
where powershell >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo ERROR: PowerShell is required but not found on PATH.
    echo Please run from PowerShell directly: .\build_windows.ps1
    pause
    exit /b 1
)

REM Run the PowerShell script
powershell -ExecutionPolicy Bypass -File "%~dp0build_windows.ps1" %*

if %ERRORLEVEL% neq 0 (
    echo.
    echo Build failed with error code %ERRORLEVEL%
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo Build completed successfully.
pause
