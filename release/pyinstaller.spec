# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for PDF Consolidator.

This creates a ONEDIR distribution optimized for PySide6 on Windows.
Run with: pyinstaller release/pyinstaller.spec
"""

import sys
import os
from pathlib import Path

# Get the project root directory
spec_dir = os.path.dirname(os.path.abspath(SPEC))
project_root = os.path.dirname(spec_dir)

# Read version from version.py
version_file = os.path.join(project_root, 'core', 'version.py')
version_dict = {}
with open(version_file, 'r') as f:
    exec(f.read(), version_dict)
APP_VERSION = version_dict['__version__']

# Analysis configuration
a = Analysis(
    [os.path.join(project_root, 'app.py')],
    pathex=[project_root],
    binaries=[],
    datas=[],
    hiddenimports=[
        # PySide6 modules that may not be auto-detected
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        # pypdf modules
        'pypdf',
        'pypdf.generic',
        'pypdf._reader',
        'pypdf._writer',
        # Optional PyMuPDF (if installed)
        'fitz',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude unnecessary modules to reduce size
        'tkinter',
        'matplotlib',
        'numpy',
        'pandas',
        'scipy',
        'PIL',
        'cv2',
        'tensorflow',
        'torch',
        # Test frameworks
        'pytest',
        'unittest',
        # Development tools
        'IPython',
        'jupyter',
    ],
    noarchive=False,
    optimize=0,
)

# Filter out unnecessary PySide6 modules to reduce size
excluded_binaries = [
    'Qt6WebEngine',
    'Qt6Designer',
    'Qt6Quick',
    'Qt6Qml',
    'Qt6Network',  # We don't need network
    'Qt63D',
    'Qt6Multimedia',
    'opengl32sw.dll',
]

a.binaries = [b for b in a.binaries if not any(ex in b[0] for ex in excluded_binaries)]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='PDFConsolidator',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # No console window - windowed mode
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(spec_dir, 'assets', 'app.ico') if os.path.exists(os.path.join(spec_dir, 'assets', 'app.ico')) else None,
    version=os.path.join(spec_dir, 'assets', 'version_info.txt') if os.path.exists(os.path.join(spec_dir, 'assets', 'version_info.txt')) else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='PDFConsolidator',
)
