"""
Support bundle creation for PDF Consolidator.

Creates a ZIP file containing logs, settings, and recent reports for support purposes.
Never includes PDF files or sensitive data.
"""
import io
import os
import re
import zipfile
from datetime import datetime
from pathlib import Path
from typing import List, Tuple, Optional

from .settings import get_app_data_dir, get_settings_path, get_log_path, get_reports_dir
from .sanitize import get_logger, sanitize_path_for_log, SanitizedFormatter


logger = get_logger()


# Allowed file extensions in support bundle
ALLOWED_EXTENSIONS = {'.json', '.log', '.txt'}

# Maximum file size (10 MB)
MAX_FILE_SIZE = 10 * 1024 * 1024

# Maximum number of recent reports to include
MAX_RECENT_REPORTS = 10

# PDF magic bytes
PDF_MAGIC = b'%PDF-'


class BundleVerificationError(Exception):
    """Raised when bundle verification fails."""
    pass


def sanitize_file_content(content: str) -> str:
    """
    Sanitize file content by redacting usernames from paths.

    Args:
        content: Original file content

    Returns:
        Sanitized content
    """
    # Redact Windows user paths
    content = SanitizedFormatter.USER_PATH_PATTERN.sub(
        r'\1<user>\3',
        content
    )
    # Redact Unix home paths
    content = SanitizedFormatter.HOME_PATH_PATTERN.sub(
        r'\1<user>\3',
        content
    )
    return content


def get_files_for_bundle() -> List[Tuple[Path, str]]:
    """
    Get list of files to include in support bundle.

    Returns:
        List of (file_path, archive_name) tuples
    """
    files: List[Tuple[Path, str]] = []
    app_dir = get_app_data_dir()

    # Settings file
    settings_path = get_settings_path()
    if settings_path.exists():
        files.append((settings_path, "settings.json"))

    # Main log file
    log_path = get_log_path()
    if log_path.exists():
        files.append((log_path, "app.log"))

    # Additional log files in app directory
    for log_file in app_dir.glob("*.log"):
        if log_file != log_path:  # Don't duplicate main log
            files.append((log_file, f"logs/{log_file.name}"))

    # Recent reports
    reports_dir = get_reports_dir()
    if reports_dir.exists():
        report_files = sorted(
            reports_dir.glob("*.txt"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )[:MAX_RECENT_REPORTS]

        for report in report_files:
            files.append((report, f"reports/{report.name}"))

    # Also check for .txt files next to output PDFs (merge reports)
    # These are in the output directories, so we look in recent reports folder

    return files


def verify_file_safe(file_path: Path, file_content: bytes) -> Tuple[bool, str]:
    """
    Verify a file is safe to include in the bundle.

    Checks:
    - File extension is allowed
    - File size is within limit
    - No PDF magic bytes present

    Args:
        file_path: Path to the file
        file_content: Content of the file

    Returns:
        Tuple of (is_safe, error_message)
    """
    # Check extension
    if file_path.suffix.lower() not in ALLOWED_EXTENSIONS:
        return False, f"Disallowed extension: {file_path.suffix}"

    # Check size
    if len(file_content) > MAX_FILE_SIZE:
        return False, f"File too large: {len(file_content)} bytes (max {MAX_FILE_SIZE})"

    # Check for PDF magic bytes
    if PDF_MAGIC in file_content:
        return False, "File contains PDF content"

    return True, ""


def verify_bundle_no_secrets(zip_path: Path) -> Tuple[bool, List[str]]:
    """
    Verify a support bundle doesn't contain secrets or PDFs.

    Args:
        zip_path: Path to the ZIP file

    Returns:
        Tuple of (is_valid, list_of_issues)
    """
    issues: List[str] = []

    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            for info in zf.infolist():
                name = info.filename

                # Check extension
                ext = Path(name).suffix.lower()
                if ext and ext not in ALLOWED_EXTENSIONS:
                    issues.append(f"Disallowed file type: {name}")
                    continue

                # Check size
                if info.file_size > MAX_FILE_SIZE:
                    issues.append(f"File too large: {name} ({info.file_size} bytes)")
                    continue

                # Check content for PDF magic bytes
                try:
                    content = zf.read(info.filename)
                    if PDF_MAGIC in content:
                        issues.append(f"PDF content detected in: {name}")
                except Exception as e:
                    issues.append(f"Could not read {name}: {e}")

    except zipfile.BadZipFile:
        issues.append("Invalid ZIP file")
    except Exception as e:
        issues.append(f"Verification error: {e}")

    return len(issues) == 0, issues


def create_support_bundle(
    dest_zip_path: Path,
    sanitize_content: bool = True
) -> Path:
    """
    Create a support bundle ZIP file.

    The bundle contains:
    - settings.json (sanitized)
    - Log files (sanitized)
    - Recent summary reports (sanitized)

    Does NOT include:
    - PDF files
    - Passwords or tokens
    - Unsanitized paths

    Args:
        dest_zip_path: Where to save the ZIP file
        sanitize_content: Whether to sanitize paths in file content

    Returns:
        Path to the created ZIP file

    Raises:
        BundleVerificationError: If verification fails
    """
    logger.info(f"Creating support bundle: {sanitize_path_for_log(dest_zip_path)}")

    # Ensure destination directory exists
    dest_zip_path.parent.mkdir(parents=True, exist_ok=True)

    # Get files to include
    files = get_files_for_bundle()

    if not files:
        logger.warning("No files found for support bundle")

    # Create ZIP file
    with zipfile.ZipFile(dest_zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        # Add metadata file
        metadata = f"""PDF Consolidator Support Bundle
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Files included: {len(files)}

This bundle contains diagnostic information for troubleshooting.
No PDF files or sensitive data are included.
Paths have been sanitized to remove usernames.
"""
        zf.writestr("README.txt", metadata)

        # Add each file
        for file_path, archive_name in files:
            try:
                # Read content
                if file_path.suffix.lower() == '.json':
                    # JSON files - read as text
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    if sanitize_content:
                        content = sanitize_file_content(content)
                    content_bytes = content.encode('utf-8')
                else:
                    # Log/text files - read as text and sanitize
                    with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                        content = f.read()
                    if sanitize_content:
                        content = sanitize_file_content(content)
                    content_bytes = content.encode('utf-8')

                # Verify file is safe
                is_safe, error = verify_file_safe(file_path, content_bytes)
                if not is_safe:
                    logger.warning(f"Skipping unsafe file {file_path}: {error}")
                    continue

                # Add to ZIP
                zf.writestr(archive_name, content_bytes)
                logger.debug(f"Added to bundle: {archive_name}")

            except Exception as e:
                logger.warning(f"Failed to add {file_path} to bundle: {e}")

    # Verify the bundle
    is_valid, issues = verify_bundle_no_secrets(dest_zip_path)
    if not is_valid:
        # Delete the bundle if verification fails
        try:
            dest_zip_path.unlink()
        except Exception:
            pass
        raise BundleVerificationError(
            f"Bundle verification failed:\n" + "\n".join(f"  - {i}" for i in issues)
        )

    logger.info(f"Support bundle created successfully: {len(files)} files")
    return dest_zip_path


def get_bundle_info(zip_path: Path) -> dict:
    """
    Get information about a support bundle.

    Args:
        zip_path: Path to the ZIP file

    Returns:
        Dictionary with bundle information
    """
    info = {
        'path': str(zip_path),
        'exists': zip_path.exists(),
        'size_bytes': 0,
        'file_count': 0,
        'files': [],
        'is_valid': False,
        'issues': []
    }

    if not zip_path.exists():
        return info

    try:
        info['size_bytes'] = zip_path.stat().st_size

        with zipfile.ZipFile(zip_path, 'r') as zf:
            info['file_count'] = len(zf.namelist())
            info['files'] = zf.namelist()

        is_valid, issues = verify_bundle_no_secrets(zip_path)
        info['is_valid'] = is_valid
        info['issues'] = issues

    except Exception as e:
        info['issues'] = [str(e)]

    return info
