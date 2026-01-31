<#
.SYNOPSIS
    Package PDF Consolidator into a publish-ready distribution.

.DESCRIPTION
    This script builds the application and creates a complete release package:
    - Standalone ZIP with all dependencies
    - SHA256 hash files for integrity verification
    - manifest.json with build metadata
    - RELEASE_NOTES.txt
    - All documentation for IT and end users

.PARAMETER SkipBuild
    Skip the build step (use existing dist folder).

.PARAMETER Clean
    Clean previous artifacts before building.

.EXAMPLE
    .\package_zip.ps1
    .\package_zip.ps1 -SkipBuild
    .\package_zip.ps1 -Clean
#>

param(
    [switch]$SkipBuild,
    [switch]$Clean
)

$ErrorActionPreference = "Stop"

# ============================================
# Configuration
# ============================================
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
if (-not (Test-Path "$ProjectRoot\pdf_consolidator")) {
    $ProjectRoot = Split-Path -Parent $PSScriptRoot
}
$ReleaseDir = $PSScriptRoot
$DistDir = Join-Path $ProjectRoot "dist"
$OutputDir = Join-Path $ProjectRoot "releases"
$TemplatesDir = Join-Path $ReleaseDir "templates"
$VenvDir = Join-Path $ProjectRoot ".venv_build"

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "PDF Consolidator - Publish-Ready Packaging" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# ============================================
# Read version from version.py
# ============================================
$VersionFile = Join-Path $ProjectRoot "core\version.py"
$AppVersion = "1.0.0"
if (Test-Path $VersionFile) {
    $VersionContent = Get-Content $VersionFile -Raw
    if ($VersionContent -match '__version__\s*=\s*[''"]([^''"]+)[''"]') {
        $AppVersion = $Matches[1]
    }
}
Write-Host "App Version: $AppVersion" -ForegroundColor Green

# Build timestamp
$BuildTime = Get-Date
$BuildTimeISO = $BuildTime.ToString("yyyy-MM-ddTHH:mm:ssZ")
$BuildTimeDisplay = $BuildTime.ToString("yyyy-MM-dd HH:mm")
$BuildDate = $BuildTime.ToString("yyyy-MM-dd")
Write-Host "Build Time:  $BuildTimeDisplay"
Write-Host ""

# Package naming
$PackageName = "PDFConsolidator_v$AppVersion"
$ReleaseOutputDir = Join-Path $OutputDir $PackageName
$PackageDir = Join-Path $OutputDir "${PackageName}_staging"
$ZipFileName = "${PackageName}_Windows.zip"
$ZipPath = Join-Path $ReleaseOutputDir $ZipFileName

# ============================================
# Clean previous artifacts
# ============================================
if (Test-Path $PackageDir) {
    Write-Host "Removing previous staging folder..." -ForegroundColor Yellow
    Remove-Item -Recurse -Force $PackageDir
}
if (Test-Path $ReleaseOutputDir) {
    Write-Host "Removing previous release folder..." -ForegroundColor Yellow
    Remove-Item -Recurse -Force $ReleaseOutputDir
}

# ============================================
# Step 1: Build application
# ============================================
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
} else {
    Write-Host "Step 1: Skipping build (using existing dist)..." -ForegroundColor Yellow
    Write-Host ""
}

# Verify dist folder exists
$DistAppDir = Join-Path $DistDir "PDFConsolidator"
if (-not (Test-Path $DistAppDir)) {
    Write-Host "ERROR: Distribution folder not found: $DistAppDir" -ForegroundColor Red
    Write-Host "Run without -SkipBuild flag" -ForegroundColor Red
    exit 1
}

# ============================================
# Step 2: Create package structure
# ============================================
Write-Host "Step 2: Creating package structure..." -ForegroundColor Cyan

# Create directories
New-Item -ItemType Directory -Path $ReleaseOutputDir -Force | Out-Null
New-Item -ItemType Directory -Path $PackageDir -Force | Out-Null

# Copy distribution files
Write-Host "  Copying application files..."
Copy-Item -Recurse "$DistAppDir\*" $PackageDir

# ============================================
# Step 3: Add documentation
# ============================================
Write-Host "Step 3: Adding documentation..." -ForegroundColor Cyan

$DocFiles = @(
    @{ Source = "README_USER.txt"; Dest = "README.txt" },
    @{ Source = "SECURITY_NOTES.txt"; Dest = "SECURITY_NOTES.txt" },
    @{ Source = "IT_ADMIN_NOTES.txt"; Dest = "IT_ADMIN_NOTES.txt" }
)

foreach ($doc in $DocFiles) {
    $SourcePath = Join-Path $TemplatesDir $doc.Source
    $DestPath = Join-Path $PackageDir $doc.Dest

    if (Test-Path $SourcePath) {
        $Content = Get-Content $SourcePath -Raw
        $Content = $Content -replace '\{VERSION\}', $AppVersion
        $Content = $Content -replace '\{DATE\}', $BuildDate
        Set-Content -Path $DestPath -Value $Content -NoNewline
        Write-Host "    Added: $($doc.Dest)"
    } else {
        Write-Host "    Warning: Template not found: $SourcePath" -ForegroundColor Yellow
    }
}

# ============================================
# Step 4: Create ZIP archive
# ============================================
Write-Host ""
Write-Host "Step 4: Creating ZIP archive..." -ForegroundColor Cyan

Add-Type -AssemblyName System.IO.Compression.FileSystem

[System.IO.Compression.ZipFile]::CreateFromDirectory(
    $PackageDir,
    $ZipPath,
    [System.IO.Compression.CompressionLevel]::Optimal,
    $true  # Include base directory name
)

if (-not (Test-Path $ZipPath)) {
    Write-Host "ERROR: Failed to create ZIP file" -ForegroundColor Red
    exit 1
}

$ZipSize = (Get-Item $ZipPath).Length
$ZipSizeMB = [math]::Round($ZipSize / 1MB, 2)
Write-Host "  ZIP created: $ZipFileName ($ZipSizeMB MB)"

# ============================================
# Step 5: Compute SHA256 hashes
# ============================================
Write-Host ""
Write-Host "Step 5: Computing SHA256 hashes..." -ForegroundColor Cyan

# Hash the ZIP
$ZipHash = (Get-FileHash -Path $ZipPath -Algorithm SHA256).Hash.ToLower()
$ZipHashFile = "$ZipPath.sha256"
"$ZipHash *$ZipFileName" | Set-Content -Path $ZipHashFile -NoNewline
Write-Host "  ZIP SHA256: $ZipHash"

# Hash the EXE
$ExePath = Join-Path $PackageDir "PDFConsolidator.exe"
$ExeHash = (Get-FileHash -Path $ExePath -Algorithm SHA256).Hash.ToLower()
$ExeHashFile = Join-Path $ReleaseOutputDir "PDFConsolidator.exe.sha256"
"$ExeHash *PDFConsolidator.exe" | Set-Content -Path $ExeHashFile -NoNewline
Write-Host "  EXE SHA256: $ExeHash"

# ============================================
# Step 6: Gather build metadata
# ============================================
Write-Host ""
Write-Host "Step 6: Gathering build metadata..." -ForegroundColor Cyan

# Get Python version
$PythonVersion = "unknown"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
if (Test-Path $VenvPython) {
    $PythonVersion = & $VenvPython --version 2>&1
    $PythonVersion = $PythonVersion -replace "Python ", ""
}

# Get PyInstaller version
$PyInstallerVersion = "unknown"
$VenvPip = Join-Path $VenvDir "Scripts\pip.exe"
if (Test-Path $VenvPip) {
    $pipShow = & $VenvPip show pyinstaller 2>&1
    if ($pipShow -match "Version:\s*(.+)") {
        $PyInstallerVersion = $Matches[1].Trim()
    }
}

# Get dependencies
$Dependencies = @()
if (Test-Path $VenvPip) {
    $freezeOutput = & $VenvPip freeze 2>&1
    $Dependencies = $freezeOutput -split "`n" | Where-Object { $_ -match "==" }
}

Write-Host "  Python: $PythonVersion"
Write-Host "  PyInstaller: $PyInstallerVersion"
Write-Host "  Dependencies: $($Dependencies.Count) packages"

# ============================================
# Step 7: Create manifest.json
# ============================================
Write-Host ""
Write-Host "Step 7: Creating manifest.json..." -ForegroundColor Cyan

$Manifest = @{
    app_name = "PDF Consolidator"
    version = $AppVersion
    build_time_iso = $BuildTimeISO
    build_date = $BuildDate
    python_version = $PythonVersion
    pyinstaller_version = $PyInstallerVersion
    dependencies = $Dependencies
    sha256_zip = $ZipHash
    sha256_exe = $ExeHash
    zip_size_bytes = $ZipSize

    # Security declarations
    no_network_calls = $true
    telemetry = "none"
    offline_only = $true

    # Storage paths (templates - actual paths use environment)
    settings_path = "%APPDATA%\PDFConsolidator\settings.json"
    logs_path = "%APPDATA%\PDFConsolidator\app.log"

    # Distribution info
    distribution_type = "standalone"
    platform = "windows-x64"
    requires_admin = $false
    requires_python = $false
}

$ManifestPath = Join-Path $ReleaseOutputDir "manifest.json"
$Manifest | ConvertTo-Json -Depth 10 | Set-Content -Path $ManifestPath
Write-Host "  Created: manifest.json"

# ============================================
# Step 8: Generate RELEASE_NOTES.txt
# ============================================
Write-Host ""
Write-Host "Step 8: Generating RELEASE_NOTES.txt..." -ForegroundColor Cyan

$ReleaseNotesTemplate = Join-Path $TemplatesDir "RELEASE_NOTES_TEMPLATE.txt"
$ReleaseNotesPath = Join-Path $ReleaseOutputDir "RELEASE_NOTES.txt"

if (Test-Path $ReleaseNotesTemplate) {
    $ReleaseNotes = Get-Content $ReleaseNotesTemplate -Raw
} else {
    # Default template if file doesn't exist
    $ReleaseNotes = @"
PDF Consolidator v{VERSION}
Release Date: {DATE} {TIME}
========================================

WHAT'S INCLUDED
---------------
- PDFConsolidator.exe (standalone, no Python required)
- All Qt and Python dependencies bundled
- README.txt - Quick start guide
- SECURITY_NOTES.txt - Privacy and security information
- IT_ADMIN_NOTES.txt - Deployment guidance for administrators

INTEGRITY VERIFICATION
----------------------
SHA256 (ZIP): {SHA256_ZIP}
SHA256 (EXE): {SHA256_EXE}

To verify on Windows PowerShell:
  Get-FileHash -Algorithm SHA256 {ZIP_FILENAME}

KNOWN LIMITATIONS
-----------------
- Not code-signed: Windows SmartScreen will show a warning on first run
  Click "More info" > "Run anyway" to proceed
- For organization-wide deployment, code signing is recommended

GETTING STARTED
---------------
1. Extract the ZIP to any local folder
2. Double-click PDFConsolidator.exe
3. Drag PDF files onto the window
4. Click "Merge PDFs"

SUPPORT
-------
If you encounter issues:
1. In the app, click Help > About / Support
2. Click "Export Support Bundle"
3. Share the generated ZIP file with your IT team

Build Information:
- Built with Python {PYTHON_VERSION}
- PyInstaller {PYINSTALLER_VERSION}
"@
}

# Replace placeholders
$ReleaseNotes = $ReleaseNotes -replace '\{VERSION\}', $AppVersion
$ReleaseNotes = $ReleaseNotes -replace '\{DATE\}', $BuildDate
$ReleaseNotes = $ReleaseNotes -replace '\{TIME\}', $BuildTime.ToString("HH:mm")
$ReleaseNotes = $ReleaseNotes -replace '\{SHA256_ZIP\}', $ZipHash
$ReleaseNotes = $ReleaseNotes -replace '\{SHA256_EXE\}', $ExeHash
$ReleaseNotes = $ReleaseNotes -replace '\{ZIP_FILENAME\}', $ZipFileName
$ReleaseNotes = $ReleaseNotes -replace '\{PYTHON_VERSION\}', $PythonVersion
$ReleaseNotes = $ReleaseNotes -replace '\{PYINSTALLER_VERSION\}', $PyInstallerVersion

Set-Content -Path $ReleaseNotesPath -Value $ReleaseNotes
Write-Host "  Created: RELEASE_NOTES.txt"

# ============================================
# Step 9: Copy documentation to release folder
# ============================================
Write-Host ""
Write-Host "Step 9: Copying documentation to release folder..." -ForegroundColor Cyan

foreach ($doc in $DocFiles) {
    $SourcePath = Join-Path $TemplatesDir $doc.Source
    $DestPath = Join-Path $ReleaseOutputDir $doc.Source

    if (Test-Path $SourcePath) {
        $Content = Get-Content $SourcePath -Raw
        $Content = $Content -replace '\{VERSION\}', $AppVersion
        $Content = $Content -replace '\{DATE\}', $BuildDate
        Set-Content -Path $DestPath -Value $Content -NoNewline
        Write-Host "    Copied: $($doc.Source)"
    }
}

# Copy rollout checklist if exists
$RolloutChecklist = Join-Path $TemplatesDir "ROLLOUT_CHECKLIST.txt"
if (Test-Path $RolloutChecklist) {
    $Content = Get-Content $RolloutChecklist -Raw
    $Content = $Content -replace '\{VERSION\}', $AppVersion
    $Content = $Content -replace '\{DATE\}', $BuildDate
    $Content = $Content -replace '\{SHA256_ZIP\}', $ZipHash
    Set-Content -Path (Join-Path $ReleaseOutputDir "ROLLOUT_CHECKLIST.txt") -Value $Content -NoNewline
    Write-Host "    Copied: ROLLOUT_CHECKLIST.txt"
}

# ============================================
# Step 10: Cleanup staging
# ============================================
Write-Host ""
Write-Host "Step 10: Cleaning up..." -ForegroundColor Cyan
Remove-Item -Recurse -Force $PackageDir
Write-Host "  Removed staging folder"

# ============================================
# Summary
# ============================================
Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "PACKAGING COMPLETE" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host ""
Write-Host "Release folder: $ReleaseOutputDir" -ForegroundColor White
Write-Host ""
Write-Host "Contents:"
Get-ChildItem $ReleaseOutputDir | ForEach-Object {
    $size = ""
    if (-not $_.PSIsContainer) {
        $size = " ($([math]::Round($_.Length / 1KB, 1)) KB)"
        if ($_.Length -gt 1MB) {
            $size = " ($([math]::Round($_.Length / 1MB, 2)) MB)"
        }
    }
    Write-Host "  $($_.Name)$size"
}

Write-Host ""
Write-Host "Integrity Hashes:" -ForegroundColor Yellow
Write-Host "  ZIP: $ZipHash"
Write-Host "  EXE: $ExeHash"

Write-Host ""
Write-Host "Next Steps:" -ForegroundColor Cyan
Write-Host "  1. Review RELEASE_NOTES.txt"
Write-Host "  2. Follow ROLLOUT_CHECKLIST.txt"
Write-Host "  3. Upload to SharePoint/Teams"
Write-Host "  4. Send announcement (see template in rollout checklist)"
Write-Host ""

# Open output folder
$OpenFolder = Read-Host "Open release folder? (Y/n)"
if ($OpenFolder -ne 'n' -and $OpenFolder -ne 'N') {
    Start-Process explorer.exe -ArgumentList $ReleaseOutputDir
}
