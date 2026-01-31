"""
PDF validation and probing for PDF Consolidator.

Provides safe PDF validation without loading full file content into memory.
Uses pypdf as primary library, with optional PyMuPDF for better page count detection.
"""
from pathlib import Path
from typing import Optional, Tuple

from .errors import (
    PDFValidationError,
    PDFEncryptedError,
    PDFCorruptError,
    ErrorCode
)
from .models import QueuedPDF, FileStatus
from .sanitize import get_logger, sanitize_path_for_log

# Check for PyMuPDF availability
try:
    import fitz  # PyMuPDF
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False

# pypdf is required
from pypdf import PdfReader
from pypdf.errors import PdfReadError, FileNotDecryptedError


logger = get_logger()


def is_pdf_file(file_path: Path) -> bool:
    """
    Quick check if a file appears to be a PDF based on magic bytes.

    Args:
        file_path: Path to file to check

    Returns:
        True if file starts with PDF magic bytes
    """
    try:
        with open(file_path, 'rb') as f:
            header = f.read(8)
            return header.startswith(b'%PDF-')
    except (IOError, OSError):
        return False


def probe_pdf(file_path: Path, check_encryption: bool = True) -> Tuple[bool, Optional[int], str]:
    """
    Probe a PDF file to check validity and get page count.

    Args:
        file_path: Path to PDF file
        check_encryption: Whether to check for encryption

    Returns:
        Tuple of (is_valid, page_count, error_message)
        page_count is None if couldn't be determined
    """
    safe_path = sanitize_path_for_log(file_path)

    # Check file exists
    if not file_path.exists():
        return False, None, "File not found"

    # Check if it's actually a PDF
    if not is_pdf_file(file_path):
        return False, None, "Not a PDF file"

    # Try to get page count with PyMuPDF first (faster and more robust)
    if HAS_PYMUPDF:
        try:
            doc = fitz.open(file_path)
            if doc.is_encrypted and not doc.authenticate(""):
                doc.close()
                return False, None, "PDF is encrypted"
            page_count = doc.page_count
            doc.close()
            logger.debug(f"Probed PDF with PyMuPDF: {safe_path}, pages={page_count}")
            return True, page_count, ""
        except Exception as e:
            # Fall through to pypdf
            logger.debug(f"PyMuPDF failed, falling back to pypdf: {e}")

    # Fall back to pypdf
    try:
        reader = PdfReader(file_path)

        # Check encryption
        if check_encryption and reader.is_encrypted:
            # Try empty password
            try:
                if not reader.decrypt(""):
                    return False, None, "PDF is encrypted"
            except Exception:
                return False, None, "PDF is encrypted"

        page_count = len(reader.pages)
        logger.debug(f"Probed PDF with pypdf: {safe_path}, pages={page_count}")
        return True, page_count, ""

    except FileNotDecryptedError:
        return False, None, "PDF is encrypted"
    except PdfReadError as e:
        logger.warning(f"PDF read error for {safe_path}: {e}")
        return False, None, "PDF is corrupt or unreadable"
    except Exception as e:
        logger.warning(f"Unexpected error probing {safe_path}: {e}")
        return False, None, f"Error reading PDF: {type(e).__name__}"


def validate_and_update_queued_pdf(
    queued_pdf: QueuedPDF,
    skip_encrypted: bool = True
) -> QueuedPDF:
    """
    Validate a queued PDF and update its status.

    Args:
        queued_pdf: QueuedPDF to validate
        skip_encrypted: Whether to mark encrypted PDFs as skipped

    Returns:
        Updated QueuedPDF with status and page count
    """
    safe_path = sanitize_path_for_log(queued_pdf.file_path)

    # Check file exists
    if not queued_pdf.file_path.exists():
        queued_pdf.status = FileStatus.ERROR
        queued_pdf.status_message = "File not found"
        logger.info(f"File not found: {safe_path}")
        return queued_pdf

    # Check if it's a PDF
    if not is_pdf_file(queued_pdf.file_path):
        queued_pdf.status = FileStatus.NOT_PDF
        queued_pdf.status_message = "Not a valid PDF"
        logger.info(f"Not a PDF: {safe_path}")
        return queued_pdf

    # Probe the PDF
    is_valid, page_count, error_message = probe_pdf(
        queued_pdf.file_path,
        check_encryption=True
    )

    if is_valid:
        queued_pdf.status = FileStatus.READY
        queued_pdf.page_count = page_count
        queued_pdf.status_message = ""
        logger.info(f"PDF validated: {safe_path}, pages={page_count}")
    elif "encrypted" in error_message.lower():
        queued_pdf.status = FileStatus.ENCRYPTED
        queued_pdf.status_message = "Password protected"
        if skip_encrypted:
            logger.info(f"Skipping encrypted PDF: {safe_path}")
        else:
            logger.info(f"Encrypted PDF found: {safe_path}")
    elif "corrupt" in error_message.lower() or "unreadable" in error_message.lower():
        queued_pdf.status = FileStatus.CORRUPT
        queued_pdf.status_message = error_message
        logger.warning(f"Corrupt PDF: {safe_path}")
    else:
        queued_pdf.status = FileStatus.ERROR
        queued_pdf.status_message = error_message
        logger.warning(f"PDF error: {safe_path} - {error_message}")

    return queued_pdf


def try_decrypt_pdf(file_path: Path, password: str) -> Tuple[bool, Optional[int]]:
    """
    Try to decrypt a PDF with a password.

    Args:
        file_path: Path to encrypted PDF
        password: Password to try

    Returns:
        Tuple of (success, page_count)
    """
    safe_path = sanitize_path_for_log(file_path)

    # Try PyMuPDF first
    if HAS_PYMUPDF:
        try:
            doc = fitz.open(file_path)
            if doc.authenticate(password):
                page_count = doc.page_count
                doc.close()
                logger.info(f"Successfully decrypted PDF with PyMuPDF: {safe_path}")
                return True, page_count
            doc.close()
        except Exception:
            pass

    # Fall back to pypdf
    try:
        reader = PdfReader(file_path)
        if reader.decrypt(password):
            page_count = len(reader.pages)
            logger.info(f"Successfully decrypted PDF with pypdf: {safe_path}")
            return True, page_count
    except Exception as e:
        logger.debug(f"Decrypt failed for {safe_path}: {e}")

    return False, None


def get_pdf_metadata(file_path: Path) -> dict:
    """
    Get metadata from a PDF file.

    Args:
        file_path: Path to PDF

    Returns:
        Dictionary of metadata (may be empty)
    """
    try:
        reader = PdfReader(file_path)
        if reader.is_encrypted:
            reader.decrypt("")
        metadata = reader.metadata
        if metadata:
            return {
                'title': metadata.get('/Title', ''),
                'author': metadata.get('/Author', ''),
                'subject': metadata.get('/Subject', ''),
                'creator': metadata.get('/Creator', ''),
                'producer': metadata.get('/Producer', ''),
            }
    except Exception:
        pass
    return {}
