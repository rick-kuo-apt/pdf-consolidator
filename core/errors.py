"""
Custom exceptions and error codes for PDF Consolidator.
"""
from enum import Enum, auto
from typing import Optional


class ErrorCode(Enum):
    """Error codes for structured error handling."""
    UNKNOWN = auto()
    FILE_NOT_FOUND = auto()
    NOT_A_PDF = auto()
    PDF_ENCRYPTED = auto()
    PDF_CORRUPT = auto()
    PDF_UNREADABLE = auto()
    PERMISSION_DENIED = auto()
    OUTPUT_WRITE_FAILED = auto()
    MERGE_FAILED = auto()
    INVALID_PASSWORD = auto()
    DUPLICATE_FILE = auto()


class PDFConsolidatorError(Exception):
    """Base exception for PDF Consolidator."""

    def __init__(
        self,
        message: str,
        code: ErrorCode = ErrorCode.UNKNOWN,
        file_path: Optional[str] = None
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.file_path = file_path

    def __str__(self) -> str:
        if self.file_path:
            return f"[{self.code.name}] {self.message} (file: {self.file_path})"
        return f"[{self.code.name}] {self.message}"


class PDFValidationError(PDFConsolidatorError):
    """Raised when PDF validation fails."""
    pass


class PDFEncryptedError(PDFConsolidatorError):
    """Raised when a PDF is encrypted and cannot be read."""

    def __init__(self, file_path: str, message: str = "PDF is encrypted"):
        super().__init__(message, ErrorCode.PDF_ENCRYPTED, file_path)


class PDFCorruptError(PDFConsolidatorError):
    """Raised when a PDF is corrupt or unreadable."""

    def __init__(self, file_path: str, message: str = "PDF is corrupt or unreadable"):
        super().__init__(message, ErrorCode.PDF_CORRUPT, file_path)


class MergeError(PDFConsolidatorError):
    """Raised when merging fails."""

    def __init__(self, message: str, file_path: Optional[str] = None):
        super().__init__(message, ErrorCode.MERGE_FAILED, file_path)


class OutputWriteError(PDFConsolidatorError):
    """Raised when output file cannot be written."""

    def __init__(self, message: str, file_path: str):
        super().__init__(message, ErrorCode.OUTPUT_WRITE_FAILED, file_path)
