"""
Utility functions for PDF Consolidator.
"""
import hashlib
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Tuple


def generate_output_filename(
    template: str = "Merged_{timestamp}.pdf",
    output_dir: Optional[Path] = None
) -> Path:
    """
    Generate output filename from template.

    Supported placeholders:
        {timestamp} - YYYYMMDD_HHMM format
        {date} - YYYYMMDD format
        {time} - HHMM format

    Args:
        template: Filename template with placeholders
        output_dir: Output directory (defaults to current directory)

    Returns:
        Full path to output file
    """
    now = datetime.now()
    timestamp = now.strftime("%Y%m%d_%H%M")
    date = now.strftime("%Y%m%d")
    time = now.strftime("%H%M")

    filename = template.format(
        timestamp=timestamp,
        date=date,
        time=time
    )

    # Ensure .pdf extension
    if not filename.lower().endswith('.pdf'):
        filename += '.pdf'

    # Sanitize filename
    filename = sanitize_filename(filename)

    if output_dir is None:
        output_dir = Path.cwd()

    return output_dir / filename


def sanitize_filename(filename: str) -> str:
    """
    Sanitize a filename by removing invalid characters.

    Args:
        filename: Original filename

    Returns:
        Sanitized filename safe for Windows/Unix
    """
    # Remove or replace invalid characters
    invalid_chars = r'[<>:"/\\|?*]'
    sanitized = re.sub(invalid_chars, '_', filename)

    # Remove leading/trailing spaces and dots
    sanitized = sanitized.strip(' .')

    # Ensure not empty
    if not sanitized:
        sanitized = "output.pdf"

    return sanitized


def compute_sha256(file_path: Path, chunk_size: int = 8192) -> str:
    """
    Compute SHA256 hash of a file.

    Args:
        file_path: Path to file
        chunk_size: Read chunk size in bytes

    Returns:
        Hex digest of SHA256 hash
    """
    sha256 = hashlib.sha256()
    with open(file_path, 'rb') as f:
        while chunk := f.read(chunk_size):
            sha256.update(chunk)
    return sha256.hexdigest()


def find_pdfs_in_directory(
    directory: Path,
    include_subfolders: bool = False,
    max_depth: int = 10
) -> List[Path]:
    """
    Find all PDF files in a directory.

    Args:
        directory: Directory to search
        include_subfolders: Whether to search subdirectories
        max_depth: Maximum recursion depth

    Returns:
        List of paths to PDF files
    """
    pdf_files: List[Path] = []

    if not directory.is_dir():
        return pdf_files

    pattern = "**/*.pdf" if include_subfolders else "*.pdf"

    try:
        for path in directory.glob(pattern):
            if path.is_file():
                pdf_files.append(path)
    except PermissionError:
        pass  # Skip directories we can't access

    return sorted(pdf_files)


def normalize_path(path: Path) -> Path:
    """
    Normalize a path for consistent comparison.

    Args:
        path: Path to normalize

    Returns:
        Normalized absolute path
    """
    return path.resolve()


def find_unique_path(base_path: Path) -> Path:
    """
    Find a unique path by appending numbers if file exists.

    Uses format: name_01.pdf, name_02.pdf, etc.

    Args:
        base_path: Desired path

    Returns:
        Unique path that doesn't exist
    """
    if not base_path.exists():
        return base_path

    stem = base_path.stem
    suffix = base_path.suffix
    parent = base_path.parent

    counter = 1
    while True:
        new_path = parent / f"{stem}_{counter:02d}{suffix}"
        if not new_path.exists():
            return new_path
        counter += 1
        if counter > 1000:  # Safety limit
            raise ValueError("Could not find unique filename")


def format_duration(seconds: float) -> str:
    """Format duration in human-readable form."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = int(seconds // 60)
    secs = seconds % 60
    return f"{minutes}m {secs:.0f}s"


def truncate_path(path: Path, max_length: int = 60) -> str:
    """
    Truncate a path for display, keeping the filename visible.

    Args:
        path: Path to truncate
        max_length: Maximum display length

    Returns:
        Truncated path string
    """
    path_str = str(path)
    if len(path_str) <= max_length:
        return path_str

    filename = path.name
    if len(filename) >= max_length - 4:
        return "..." + filename[-(max_length - 3):]

    remaining = max_length - len(filename) - 4  # 4 for "...\"
    parent = str(path.parent)

    if remaining > 0:
        return "..." + parent[-remaining:] + "\\" + filename
    return "...\\" + filename


def is_removable_drive(path: Path) -> Tuple[bool, str]:
    """
    Check if a path is on a removable drive (Windows only).

    Args:
        path: Path to check

    Returns:
        Tuple of (is_removable, drive_type_description)
    """
    if sys.platform != 'win32':
        return False, "Not Windows"

    try:
        import ctypes
        from ctypes import wintypes

        # Get drive letter
        drive = str(path.resolve()).split(':')[0] + ':'

        # GetDriveTypeW returns:
        # 0 = DRIVE_UNKNOWN
        # 1 = DRIVE_NO_ROOT_DIR
        # 2 = DRIVE_REMOVABLE
        # 3 = DRIVE_FIXED
        # 4 = DRIVE_REMOTE
        # 5 = DRIVE_CDROM
        # 6 = DRIVE_RAMDISK

        kernel32 = ctypes.windll.kernel32
        drive_type = kernel32.GetDriveTypeW(drive + '\\')

        drive_types = {
            0: "Unknown",
            1: "No Root Dir",
            2: "Removable",
            3: "Fixed",
            4: "Remote/Network",
            5: "CD-ROM",
            6: "RAM Disk"
        }

        type_name = drive_types.get(drive_type, "Unknown")

        # Consider removable: USB drives, CD-ROMs
        is_removable = drive_type in (2, 5)

        return is_removable, type_name

    except Exception as e:
        # If detection fails, return False with error
        return False, f"Detection failed: {e}"


def is_path_within_directory(path: Path, directory: Path) -> bool:
    """
    Check if a path is within a directory (or is the directory itself).

    Args:
        path: Path to check
        directory: Directory to check against

    Returns:
        True if path is within directory
    """
    try:
        path.resolve().relative_to(directory.resolve())
        return True
    except ValueError:
        return False


def get_file_info(file_path: Path) -> dict:
    """
    Get basic file information.

    Args:
        file_path: Path to file

    Returns:
        Dictionary with size, modified time, etc.
    """
    info = {
        'exists': False,
        'size_bytes': 0,
        'modified_time': None,
        'is_file': False,
        'is_dir': False
    }

    if file_path.exists():
        info['exists'] = True
        info['is_file'] = file_path.is_file()
        info['is_dir'] = file_path.is_dir()

        if file_path.is_file():
            try:
                stat = file_path.stat()
                info['size_bytes'] = stat.st_size
                info['modified_time'] = datetime.fromtimestamp(stat.st_mtime)
            except OSError:
                pass

    return info


def ensure_directory_exists(directory: Path) -> bool:
    """
    Ensure a directory exists, creating it if necessary.

    Args:
        directory: Directory path

    Returns:
        True if directory exists or was created
    """
    try:
        directory.mkdir(parents=True, exist_ok=True)
        return True
    except OSError:
        return False


def is_valid_pdf_extension(file_path: Path) -> bool:
    """Check if file has a PDF extension."""
    return file_path.suffix.lower() == '.pdf'


def has_pdf_magic_bytes(file_path: Path) -> bool:
    """
    Check if file starts with PDF magic bytes.

    Args:
        file_path: Path to file

    Returns:
        True if file starts with %PDF-
    """
    try:
        with open(file_path, 'rb') as f:
            header = f.read(8)
            return header.startswith(b'%PDF-')
    except (IOError, OSError):
        return False
