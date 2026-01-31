<#
.SYNOPSIS
    Package PDF Consolidator into a distributable ZIP file.

.DESCRIPTION
    This script builds the application (if needed) and packages it into
    a versioned ZIP file ready for distribution to colleagues.

.PARAMETER SkipBuild
    Skip the build step (use existing dist folder).

.PARAMETER Clean
    Clean previous artifacts before building.

.EXAMPLE
    .\package_zip.ps1
    .\package_zip.ps1 -SkipBuild
#>

param(
    [switch]$SkipBuild,
    [switch]$Clean
)

$ErrorActionPreference = "Stop"

# Configuration
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
if (-not (Test-Path "$ProjectRoot\pdf_consolidator")) {
    $ProjectRoot = Split-Path -Parent $PSScriptRoot
}
$ReleaseDir = $PSScriptRoot
$DistDir = Join-Path $ProjectRoot "dist"
$OutputDir = Join-Path $ProjectRoot "releases"
$TemplatesDir = Join-Path $ReleaseDir "templates"

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "PDF Consolidator - Package for Distribution" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# Read version from version.py
$VersionFile = Join-Path $ProjectRoot "core\version.py"
$AppVersion = "1.0.0"  # Default
if (Test-Path $VersionFile) {
    $VersionContent = Get-Content $VersionFile -Raw
    if ($VersionContent -match '__version__\s*=\s*[''"]([^''"]+)[''"]') {
        $AppVersion = $Matches[1]
    }
}
Write-Host "App Version: $AppVersion" -ForegroundColor Green
Write-Host ""

# Package naming
$PackageName = "PDFConsolidator_v$AppVersion"
$PackageDir = Join-Path $OutputDir $PackageName
$ZipFileName = "${PackageName}_Windows.zip"
$ZipPath = Join-Path $OutputDir $ZipFileName

# Clean previous package
if (Test-Path $PackageDir) {
    Write-Host "Removing previous package folder..." -ForegroundColor Yellow
    Remove-Item -Recurse -Force $PackageDir
}
if (Test-Path $ZipPath) {
    Write-Host "Removing previous zip file..." -ForegroundColor Yellow
    Remove-Item -Force $ZipPath
}

# Build if needed
if (-not $SkipBuild) {
    Write-Host "Step 1: Building application..." -ForegroundColor Cyan
    Write-Host ""

    $BuildScript = Join-Path $ReleaseDir "build_windows.ps1"

    if ($Clean) {
        & $BuildScript -Clean
    } else {
        & $BuildScript
    }

    if (-not $?) {
        Write-Host "ERROR: Build failed" -ForegroundColor Red
        exit 1
    }
    Write-Host ""
}

# Verify dist folder exists
$DistAppDir = Join-Path $DistDir "PDFConsolidator"
if (-not (Test-Path $DistAppDir)) {
    Write-Host "ERROR: Distribution folder not found: $DistAppDir" -ForegroundColor Red
    Write-Host "Run build_windows.ps1 first or remove -SkipBuild flag" -ForegroundColor Red
    exit 1
}

# Create output directory
Write-Host "Step 2: Creating package structure..." -ForegroundColor Cyan

if (-not (Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir | Out-Null
}
New-Item -ItemType Directory -Path $PackageDir | Out-Null

# Copy distribution files
Write-Host "  Copying application files..."
Copy-Item -Recurse "$DistAppDir\*" $PackageDir

# Copy documentation templates
Write-Host "  Adding documentation..."

$DocFiles = @(
    @{ Source = "README_USER.txt"; Dest = "README.txt" },
    @{ Source = "SECURITY_NOTES.txt"; Dest = "SECURITY_NOTES.txt" },
    @{ Source = "IT_ADMIN_NOTES.txt"; Dest = "IT_ADMIN_NOTES.txt" }
)

foreach ($doc in $DocFiles) {
    $SourcePath = Join-Path $TemplatesDir $doc.Source
    $DestPath = Join-Path $PackageDir $doc.Dest

    if (Test-Path $SourcePath) {
        # Replace version placeholder
        $Content = Get-Content $SourcePath -Raw
        $Content = $Content -replace '\{VERSION\}', $AppVersion
        $Content = $Content -replace '\{DATE\}', (Get-Date -Format "yyyy-MM-dd")
        Set-Content -Path $DestPath -Value $Content -NoNewline
        Write-Host "    Added: $($doc.Dest)"
    } else {
        Write-Host "    Warning: Template not found: $SourcePath" -ForegroundColor Yellow
    }
}

# Create ZIP file
Write-Host ""
Write-Host "Step 3: Creating ZIP archive..." -ForegroundColor Cyan

# Use .NET compression for better compatibility
Add-Type -AssemblyName System.IO.Compression.FileSystem

# Remove existing zip if it exists
if (Test-Path $ZipPath) {
    Remove-Item $ZipPath -Force
}

[System.IO.Compression.ZipFile]::CreateFromDirectory(
    $PackageDir,
    $ZipPath,
    [System.IO.Compression.CompressionLevel]::Optimal,
    $true  # Include base directory name in zip
)

if (-not (Test-Path $ZipPath)) {
    Write-Host "ERROR: Failed to create ZIP file" -ForegroundColor Red
    exit 1
}

$ZipSize = (Get-Item $ZipPath).Length / 1MB

# Summary
Write-Host ""
Write-Host "==========================================" -ForegroundColor Green
Write-Host "PACKAGING COMPLETE" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Package created:"
Write-Host "  Folder: $PackageDir"
Write-Host "  ZIP:    $ZipPath"
Write-Host "  Size:   $([math]::Round($ZipSize, 2)) MB"
Write-Host ""
Write-Host "Distribution checklist:" -ForegroundColor Yellow
Write-Host "  [x] PDFConsolidator.exe included"
Write-Host "  [x] All Qt/Python dependencies included"
Write-Host "  [x] README.txt included"
Write-Host "  [x] SECURITY_NOTES.txt included"
Write-Host "  [x] IT_ADMIN_NOTES.txt included"
Write-Host ""
Write-Host "To distribute:"
Write-Host "  1. Share: $ZipPath"
Write-Host "  2. Colleagues: Unzip anywhere, double-click PDFConsolidator.exe"
Write-Host ""
Write-Host "Note: First run may trigger Windows SmartScreen."
Write-Host "See IT_ADMIN_NOTES.txt for code signing recommendations."
Write-Host ""

# Open output folder
$OpenFolder = Read-Host "Open releases folder? (Y/n)"
if ($OpenFolder -ne 'n' -and $OpenFolder -ne 'N') {
    Start-Process explorer.exe -ArgumentList $OutputDir
}
