# PDF Consolidator

A professional, enterprise-ready desktop application for merging multiple PDF files into a single consolidated document.

## Features

### Core Functionality
- **Drag & Drop Support**: Simply drag PDF files or folders onto the application
- **Folder Import**: Add all PDFs from a folder (with optional subfolder scanning)
- **File Reordering**: Drag to reorder or use Up/Down buttons
- **Multiple Sort Modes**: Sort by filename, modified date, or manual order with "Sort Now" button
- **Progress Tracking**: Real-time progress with file-by-file status
- **Error Handling**: Graceful handling of encrypted, corrupt, or non-PDF files
- **Summary Reports**: Detailed text report with merge manifest alongside output
- **Metadata Normalization**: Remove author/producer info from output

### Enterprise Hardening Features

#### A) Determinism & Manifest
- **Merge Manifest**: Every summary report includes a detailed manifest showing:
  - File index (merge order)
  - Base filename and full path
  - Size in bytes
  - Page count
  - Status (Merged/Skipped with reason)
- **Sort Mode Behavior**: "Sort Now" button applies sorting immediately
- **Deterministic Output Naming**: `Merged_YYYYMMDD_HHMM.pdf` with conflict handling:
  - Overwrite existing
  - Auto-rename (_01, _02, etc.)
  - Cancel

#### B) Encrypted PDF Handling
Three modes for handling encrypted PDFs:
- **Skip** (default): Automatically skip all encrypted files
- **Prompt Each**: Ask for password for each encrypted file
- **Single Password**: Enter one password to try for all encrypted files

Security guarantees:
- Passwords are NEVER stored in settings
- Passwords are NEVER logged
- Failed decryption shows clear status ("Encrypted - password failed")

#### C) Support Bundle Export
Export diagnostic information for troubleshooting:
- Click the 📦 button in the header
- Creates a ZIP file containing:
  - Application settings (sanitized)
  - Log files (sanitized - no usernames in paths)
  - Recent merge reports
- Verification ensures:
  - No PDF files included
  - Only allowed extensions (.json, .log, .txt)
  - No files exceed 10MB
  - No PDF magic bytes in content

#### D) Output Safety Controls
- **Directory Restrictions**: Limit output to a list of allowed folders
- **Removable Drive Blocking**: Prevent saving to USB drives (Windows)
- Warning messages when restrictions are violated

#### E) UX Polish
- **Keyboard Shortcuts**:
  - `Ctrl+O`: Add Files
  - `Ctrl+Shift+O`: Add Folder
  - `Delete`: Remove selected files
  - `Ctrl+M`: Merge
- **Multi-select**: Select multiple rows with Ctrl/Shift+click
- **Open Logs Folder**: Quick access button in Advanced Options

#### F) Performance
- **Lazy Page Counting**: Page counts load in background for responsiveness
- **Background Validation**: Large file sets validated without blocking UI
- **Thread Pool**: Low-priority workers for non-critical tasks
- Handles 500+ PDFs smoothly

## Requirements

- Python 3.9 or later
- Windows 10/11 (also works on macOS/Linux)

## Installation

### 1. Create Virtual Environment (Recommended)

```bash
# Create venv
python -m venv venv

# Activate (Windows)
venv\Scripts\activate

# Activate (macOS/Linux)
source venv/bin/activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. (Optional) Install PyMuPDF for Better Page Detection

```bash
pip install PyMuPDF
```

PyMuPDF provides faster and more reliable page count detection.

## Running the Application

```bash
# From the project root directory
python -m pdf_consolidator.app

# Or directly
python pdf_consolidator/app.py
```

## Usage

1. **Add Files**:
   - Drag & drop PDF files onto the drop zone
   - Click "Add Files" to browse (Ctrl+O)
   - Click "Add Folder" to add all PDFs from a directory (Ctrl+Shift+O)

2. **Organize**:
   - Drag rows to reorder
   - Use Up/Down buttons
   - Select sort mode and click "Sort Now"

3. **Configure Output**:
   - Set output folder (defaults to first file's location)
   - Customize filename template using `{timestamp}`, `{date}`, `{time}`
   - Enable/disable "Open folder after merge"

4. **Merge**:
   - Click "Merge PDFs" (Ctrl+M)
   - Watch progress
   - Review summary with manifest

## Support Bundle

If you need help troubleshooting:

1. Click the 📦 (package) icon in the header
2. Click "Export Bundle..."
3. Choose a save location
4. Share the ZIP file with support

The bundle contains:
- Sanitized settings and logs
- Recent merge reports
- NO PDF files or passwords

## Configuration

Settings are stored in:
- **Windows**: `%APPDATA%\PDFConsolidator\settings.json`
- **macOS**: `~/Library/Application Support/PDFConsolidator/settings.json`
- **Linux**: `~/.config/PDFConsolidator/settings.json`

Logs are stored in the same directory as `app.log`.

## Building Standalone Executable

### PyInstaller (Windows)

```bash
# Install PyInstaller
pip install pyinstaller

# One-file build (simpler distribution)
pyinstaller --name "PDF Consolidator" ^
            --windowed ^
            --onefile ^
            --icon=icon.ico ^
            pdf_consolidator/app.py

# One-directory build (faster startup)
pyinstaller --name "PDF Consolidator" ^
            --windowed ^
            --onedir ^
            --icon=icon.ico ^
            pdf_consolidator/app.py
```

### Recommended: One-Directory Build

The one-directory build is recommended for enterprise deployment:
- Faster application startup
- Easier to update individual components
- Better compatibility with antivirus software

### Adding Version Info (Windows)

Create a `version.txt` file:
```
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=(1, 1, 0, 0),
    prodvers=(1, 1, 0, 0),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
  ),
  kids=[
    StringFileInfo([
      StringTable('040904B0', [
        StringStruct('CompanyName', 'Your Company'),
        StringStruct('FileDescription', 'PDF Consolidator'),
        StringStruct('FileVersion', '1.1.0'),
        StringStruct('ProductName', 'PDF Consolidator'),
        StringStruct('ProductVersion', '1.1.0'),
      ])
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
```

Then build with:
```bash
pyinstaller --version-file=version.txt ...
```

### Application Icon

Create an `.ico` file for Windows:
- Recommended sizes: 16x16, 32x32, 48x48, 256x256
- Use tools like GIMP or online ICO converters

## Security Notes

### Offline Only
- No network calls in the application
- No external API dependencies
- Works in air-gapped environments

### No Telemetry
- No data collection
- No analytics or tracking
- No "phone home" functionality

### Passwords Not Stored
- PDF passwords entered at runtime only
- Never saved to disk or settings
- Never written to logs

### Sanitized Logging
- Usernames redacted from file paths
- No file contents logged
- Safe for enterprise audit

### Output Safety
- Optional directory restrictions
- Optional removable drive blocking
- Never modifies original files

## v2 Roadmap: SharePoint Integration

Future version will include SharePoint/OneDrive integration via Microsoft Graph API:

### Planned Features

1. **Device Code Authentication**
   - Secure OAuth 2.0 flow
   - Works with organizational accounts

2. **Browse SharePoint Sites**
   - List accessible sites and document libraries
   - Navigate folder structure

3. **Download & Merge**
   - Download selected PDFs locally
   - Merge locally (no cloud processing)
   - Optionally upload result

4. **Token Storage**
   - OS keychain integration:
     - Windows: Credential Manager
     - macOS: Keychain
     - Linux: Secret Service API

## Distribution to Colleagues

### Quick Start (For Developers)

To create a distributable ZIP file:

```powershell
# From the pdf_consolidator directory
cd release
.\package_zip.ps1
```

This creates `releases/PDFConsolidator_vX.Y.Z_Windows.zip` ready for distribution.

### Mode A: Standalone Executable (Recommended)

**What colleagues receive:**
- Single ZIP file (~80-150 MB)
- No Python installation required
- No admin rights required

**How to distribute:**
1. Run `release\package_zip.bat` (or `.ps1`)
2. Share the generated ZIP via:
   - Network share
   - SharePoint/OneDrive
   - Email
   - Software Center

**Colleague instructions:**
1. Extract ZIP anywhere (Desktop, Documents, etc.)
2. Double-click `PDFConsolidator.exe`
3. Done!

### Mode B: Source Distribution (Fallback)

If PyInstaller is blocked, use the source distribution:

**Requirements:** Python 3.10+ installed

**Files to distribute:**
- `pdf_consolidator/` folder
- `requirements.txt`
- `release/fallback/run.bat`

**Colleague instructions:**
1. Extract ZIP anywhere
2. Double-click `run.bat`
3. First run installs dependencies automatically

### SmartScreen Warning

The standalone executable is not code-signed, so Windows will show:
> "Windows protected your PC"

**For users:** Click "More info" → "Run anyway"

**For IT:** See `IT_ADMIN_NOTES.txt` for code signing recommendations.

### Build Scripts Reference

| Script | Purpose |
|--------|---------|
| `release/build_windows.ps1` | Build standalone exe |
| `release/build_windows.bat` | Wrapper for double-click |
| `release/package_zip.ps1` | Create distribution ZIP |
| `release/package_zip.bat` | Wrapper for double-click |
| `release/fallback/run.bat` | Source distribution launcher |

### Versioning

Version is defined in `core/version.py`. Update this file before building a new release:

```python
__version__ = "1.2.0"  # Update this
```

The version automatically propagates to:
- Window title bar
- ZIP filename
- Windows exe properties

## License

MIT License - Free for personal and commercial use.

## Contributing

Contributions welcome! Please ensure:
- Code follows existing style
- All tests pass
- No sensitive information in commits
- Documentation updated for new features

## Test Checklist

### Manual Testing Steps

1. **Basic Merge**
   - [ ] Add 3+ PDF files via drag & drop
   - [ ] Verify page counts load
   - [ ] Click Merge
   - [ ] Verify output file created
   - [ ] Verify .txt report has manifest

2. **Sort Functionality**
   - [ ] Add files in random order
   - [ ] Select "Filename" sort mode
   - [ ] Click "Sort Now"
   - [ ] Verify order changed

3. **Encrypted PDF Handling**
   - [ ] Add encrypted PDF
   - [ ] With "Skip" mode: verify skipped
   - [ ] With "Single Password": enter password
   - [ ] Verify decrypted file merged

4. **Output Conflict**
   - [ ] Merge to existing filename
   - [ ] Test "Overwrite" option
   - [ ] Test "Auto-rename" option

5. **Support Bundle**
   - [ ] Click 📦 button
   - [ ] Export bundle
   - [ ] Verify ZIP contains only allowed files
   - [ ] Verify no PDFs in bundle

6. **Output Restrictions**
   - [ ] Enable "Restrict output directories"
   - [ ] Add allowed directory
   - [ ] Try to merge to non-allowed location
   - [ ] Verify warning shown

7. **Keyboard Shortcuts**
   - [ ] Ctrl+O opens file dialog
   - [ ] Ctrl+Shift+O opens folder dialog
   - [ ] Delete removes selected
   - [ ] Ctrl+M starts merge

8. **Performance**
   - [ ] Add 100+ PDFs
   - [ ] Verify UI remains responsive
   - [ ] Page counts load progressively
