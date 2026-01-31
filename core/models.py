"""
Data models for PDF Consolidator.
"""
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Optional, List
from datetime import datetime


class FileStatus(Enum):
    """Status of a queued PDF file."""
    PENDING = auto()      # Not yet processed
    READY = auto()        # Validated and ready for merge
    PROCESSING = auto()   # Currently being processed
    MERGED = auto()       # Successfully merged
    SKIPPED = auto()      # Skipped (duplicate, user choice)
    ENCRYPTED = auto()    # Encrypted and cannot be read
    CORRUPT = auto()      # Corrupt or unreadable
    NOT_PDF = auto()      # Not a valid PDF file
    ERROR = auto()        # Other error


class EncryptionHandlingMode(Enum):
    """How to handle encrypted PDFs."""
    SKIP = auto()              # Skip all encrypted PDFs
    PROMPT_EACH = auto()       # Prompt for password for each encrypted file
    SINGLE_PASSWORD = auto()   # Use one password for all encrypted files


class SortMode(Enum):
    """Sort modes for file list."""
    MANUAL = auto()
    FILENAME = auto()
    MODIFIED_TIME = auto()


@dataclass
class QueuedPDF:
    """Represents a PDF file in the merge queue."""

    file_path: Path
    order_index: int = 0
    file_name: str = ""
    size_bytes: int = 0
    page_count: Optional[int] = None
    status: FileStatus = FileStatus.PENDING
    status_message: str = ""
    skip_reason: str = ""  # Detailed reason when skipped
    modified_time: Optional[datetime] = None
    sha256_hash: Optional[str] = None
    is_encrypted: bool = False
    password_provided: bool = False  # True if user provided password

    def __post_init__(self):
        """Initialize computed fields."""
        if not self.file_name:
            self.file_name = self.file_path.name
        if self.size_bytes == 0 and self.file_path.exists():
            try:
                self.size_bytes = self.file_path.stat().st_size
            except OSError:
                pass
        if self.modified_time is None and self.file_path.exists():
            try:
                mtime = self.file_path.stat().st_mtime
                self.modified_time = datetime.fromtimestamp(mtime)
            except OSError:
                pass

    @property
    def size_mb(self) -> float:
        """Get file size in megabytes."""
        return self.size_bytes / (1024 * 1024)

    @property
    def size_display(self) -> str:
        """Get human-readable file size."""
        if self.size_bytes < 1024:
            return f"{self.size_bytes} B"
        elif self.size_bytes < 1024 * 1024:
            return f"{self.size_bytes / 1024:.1f} KB"
        else:
            return f"{self.size_mb:.2f} MB"

    @property
    def page_count_display(self) -> str:
        """Get page count display string."""
        if self.page_count is None:
            return "—"
        return str(self.page_count)

    @property
    def status_display(self) -> str:
        """Get human-readable status."""
        status_names = {
            FileStatus.PENDING: "Pending",
            FileStatus.READY: "Ready",
            FileStatus.PROCESSING: "Processing...",
            FileStatus.MERGED: "Merged",
            FileStatus.SKIPPED: "Skipped",
            FileStatus.ENCRYPTED: "Encrypted",
            FileStatus.CORRUPT: "Corrupt",
            FileStatus.NOT_PDF: "Not a PDF",
            FileStatus.ERROR: "Error",
        }
        base = status_names.get(self.status, "Unknown")
        if self.status_message:
            return f"{base}: {self.status_message}"
        return base

    @property
    def manifest_status(self) -> str:
        """Get status for merge manifest (more detailed)."""
        if self.status == FileStatus.MERGED:
            return "Merged"
        elif self.status == FileStatus.SKIPPED:
            return f"Skipped - {self.skip_reason or 'user choice'}"
        elif self.status == FileStatus.ENCRYPTED:
            if self.skip_reason:
                return f"Encrypted - {self.skip_reason}"
            return "Encrypted - skipped"
        elif self.status == FileStatus.CORRUPT:
            return "Skipped - corrupt/unreadable"
        elif self.status == FileStatus.NOT_PDF:
            return "Skipped - not a PDF"
        elif self.status == FileStatus.ERROR:
            return f"Error - {self.status_message or 'unknown'}"
        elif self.status in (FileStatus.PENDING, FileStatus.READY):
            return "Pending"
        return self.status_display

    @property
    def is_valid_for_merge(self) -> bool:
        """Check if file can be included in merge."""
        return self.status in (FileStatus.PENDING, FileStatus.READY)

    def ellipsized_path(self, max_length: int = 50) -> str:
        """Get ellipsized path for display."""
        path_str = str(self.file_path.parent)
        if len(path_str) <= max_length:
            return path_str
        return "..." + path_str[-(max_length - 3):]


@dataclass
class MergeManifestEntry:
    """Entry in the merge manifest for audit trail."""
    index: int
    file_name: str
    full_path: str
    size_bytes: int
    page_count: Optional[int]
    status: str
    sha256_hash: Optional[str] = None

    def to_manifest_line(self, include_hash: bool = False) -> str:
        """Format as a line for the manifest."""
        pages = str(self.page_count) if self.page_count else "?"
        line = f"{self.index:4}. {self.file_name}\n"
        line += f"      Path: {self.full_path}\n"
        line += f"      Size: {self.size_bytes:,} bytes | Pages: {pages} | Status: {self.status}\n"
        if include_hash and self.sha256_hash:
            line += f"      SHA256: {self.sha256_hash}\n"
        return line


@dataclass
class MergeResult:
    """Result of a merge operation."""

    success: bool
    output_path: Optional[Path] = None
    merged_count: int = 0
    skipped_count: int = 0
    error_count: int = 0
    total_pages: int = 0
    total_size_bytes: int = 0
    error_message: str = ""
    duration_seconds: float = 0.0
    manifest_entries: List[MergeManifestEntry] = field(default_factory=list)

    @property
    def summary(self) -> str:
        """Get summary text for display."""
        if self.success:
            return (
                f"Successfully merged {self.merged_count} PDF(s)\n"
                f"Total pages: {self.total_pages}\n"
                f"Output size: {self.total_size_bytes / (1024*1024):.2f} MB\n"
                f"Duration: {self.duration_seconds:.1f}s"
            )
        return f"Merge failed: {self.error_message}"


@dataclass
class MergeProgress:
    """Progress update during merge operation."""

    current_file: str = ""
    current_index: int = 0
    total_files: int = 0
    percent_complete: float = 0.0
    status_message: str = ""

    @property
    def progress_text(self) -> str:
        """Get progress text for display."""
        if self.total_files == 0:
            return self.status_message
        return f"Processing {self.current_index}/{self.total_files}: {self.current_file}"


@dataclass
class OutputConflictChoice(Enum):
    """User choice when output file already exists."""
    OVERWRITE = auto()
    AUTO_RENAME = auto()
    CANCEL = auto()
