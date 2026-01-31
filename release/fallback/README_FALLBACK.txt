PDF Consolidator - Source Distribution
======================================

This is the source distribution for environments where the
standalone executable cannot be used.

REQUIREMENTS
------------
  - Windows 10/11
  - Python 3.10 or later
  - Internet access (first run only, for pip install)

INSTALLATION
------------
1. Install Python from https://www.python.org/downloads/
   - Check "Add Python to PATH" during installation

2. Extract this ZIP to any folder

3. Double-click run.bat
   - First run will set up dependencies (~1-2 minutes)
   - Subsequent runs start immediately

OFFLINE INSTALLATION
--------------------
If pip is blocked or no internet is available:

1. On a machine WITH internet, run:
   pip download PySide6 pypdf -d packages/

2. Copy the 'packages' folder to the target machine

3. Modify run.bat to use:
   pip install --no-index --find-links=packages PySide6 pypdf

PROXY CONFIGURATION
-------------------
If behind a corporate proxy:

1. Set environment variables before running:
   set HTTPS_PROXY=http://proxy.company.com:8080
   set HTTP_PROXY=http://proxy.company.com:8080

2. Or configure pip permanently:
   pip config set global.proxy http://proxy.company.com:8080

EMBEDDED PYTHON (ADVANCED)
--------------------------
For fully portable distribution without Python installation:

1. Download Python embeddable package:
   https://www.python.org/ftp/python/3.11.x/python-3.11.x-embed-amd64.zip

2. Extract to 'python' folder in this directory

3. Create 'python311._pth' file with:
   python311.zip
   .
   Lib\site-packages

4. Install pip:
   python\python.exe get-pip.py

5. Install dependencies:
   python\python.exe -m pip install PySide6 pypdf

6. Modify run.bat to use:
   "%~dp0python\python.exe" -m pdf_consolidator.app

TROUBLESHOOTING
---------------
1. "Python is not recognized"
   - Reinstall Python with "Add to PATH" checked
   - Or use full path: C:\Python311\python.exe

2. "pip is not recognized"
   - Run: python -m ensurepip
   - Then: python -m pip install --upgrade pip

3. Proxy errors
   - See PROXY CONFIGURATION above

4. Permission errors
   - Don't extract to Program Files
   - Use Documents, Desktop, or Downloads
