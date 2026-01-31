"""
PDF merging service for PDF Consolidator.

Handles the core merge logic without any Qt dependencies for testability.
"""
import shutil
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Callable, Dict

from pypdf import PdfWriter, PdfReader
from pypdf.errors import PdfReadError

from .errors import MergeError, OutputWriteError, ErrorCode
from .models import (
    QueuedPDF, FileStatus, MergeResult, MergeProgress,
    MergeManifestEntry, EncryptionHandlingMode
)
from .pdf_probe import validate_and_update_queued_pdf, HAS_PYMUPDF
from .sanitize import get_logger, sanitize_path_for_log
from .utils import generate_output_filename, find_unique_path, compute_sha256


logger = get_logger()


# Progress callback type
ProgressCallback = Callable[[MergeProgress], None]

# Password request callback: (filename) -> (password, use_for_all, cancelled)
PasswordRequestCallback = Callable[[str], tuple]


class MergeService:
    """
    Service for merging PDF files.

    This class is designed to be UI-agnostic and can be used from
    command line, tests, or Qt applications.
    """

    def __init__(
        self,
        normalize_metadata: bool = True,
        encryption_mode: EncryptionHandlingMode = EncryptionHandlingMode.SKIP,
        generate_report: bool = True,
        compute_hashes: bool = False
    ):
        """
        Initialize merge service.

        Args:
            normalize_metadata: Remove author/producer from output
            encryption_mode: How to handle encrypted PDFs
            generate_report: Generate summary report file
            compute_hashes: Compute SHA256 hashes for audit
        """
        self.normalize_metadata = normalize_metadata
        self.encryption_mode = encryption_mode
        self.generate_report = generate_report
        self.compute_hashes = compute_hashes
        self._cancelled = False
        self._shared_password: Optional[str] = None

    def cancel(self) -> None:
        """Request cancellation of current merge operation."""
        self._cancelled = True

    def reset(self) -> None:
        """Reset cancellation flag and shared password."""
        self._cancelled = False
        self._shared_password = None

    def set_shared_password(self, password: str) -> None:
        """Set password to use for all encrypted PDFs."""
        self._shared_password = password

    def validate_files(
        self,
        files: List[QueuedPDF],
        progress_callback: Optional[ProgressCallback] = None
    ) -> List[QueuedPDF]:
        """
        Validate all files in the queue.

        Args:
            files: List of QueuedPDF objects
            progress_callback: Optional callback for progress updates

        Returns:
            List of updated QueuedPDF objects with validation results
        """
        total = len(files)
        skip_encrypted = self.encryption_mode == EncryptionHandlingMode.SKIP

        for i, queued_pdf in enumerate(files):
            if self._cancelled:
                break

            if progress_callback:
                progress_callback(MergeProgress(
                    current_file=queued_pdf.file_name,
                    current_index=i + 1,
                    total_files=total,
                    percent_complete=(i / total) * 100,
                    status_message=f"Validating {queued_pdf.file_name}..."
                ))

            validate_and_update_queued_pdf(queued_pdf, skip_encrypted)

        return files

    def merge(
        self,
        files: List[QueuedPDF],
        output_path: Path,
        progress_callback: Optional[ProgressCallback] = None,
        passwords: Optional[Dict[str, str]] = None,
        password_request_callback: Optional[PasswordRequestCallback] = None
    ) -> MergeResult:
        """
        Merge PDF files into a single output file.

        Args:
            files: List of QueuedPDF objects to merge
            output_path: Path for output file
            progress_callback: Optional callback for progress updates
            passwords: Optional dict mapping file paths to passwords
            password_request_callback: Callback to request password from user

        Returns:
            MergeResult with details of the operation
        """
        self._cancelled = False
        start_time = time.time()
        passwords = passwords or {}
        manifest_entries: List[MergeManifestEntry] = []

        safe_output = sanitize_path_for_log(output_path)
        logger.info(f"Starting merge of {len(files)} files to {safe_output}")

        # Filter to valid files only
        valid_files = [f for f in files if f.is_valid_for_merge]

        if not valid_files:
            return MergeResult(
                success=False,
                error_message="No valid PDF files to merge",
                skipped_count=len(files)
            )

        result = MergeResult(
            success=False,
            output_path=output_path
        )

        # Create writer
        writer = PdfWriter()
        total_pages = 0
        merged_count = 0
        skipped_count = 0
        error_count = 0

        # Process each file in order
        total = len(files)
        for i, queued_pdf in enumerate(files):
            if self._cancelled:
                logger.info("Merge cancelled by user")
                result.error_message = "Merge cancelled"
                return result

            safe_path = sanitize_path_for_log(queued_pdf.file_path)

            if progress_callback:
                progress_callback(MergeProgress(
                    current_file=queued_pdf.file_name,
                    current_index=i + 1,
                    total_files=total,
                    percent_complete=((i + 1) / total) * 80,  # Reserve 20% for writing
                    status_message=f"Merging {queued_pdf.file_name}..."
                ))

            # Compute hash if enabled
            if self.compute_hashes:
                try:
                    queued_pdf.sha256_hash = compute_sha256(queued_pdf.file_path)
                except Exception as e:
                    logger.warning(f"Failed to compute hash for {safe_path}: {e}")

            # Skip files that aren't valid for merge
            if not queued_pdf.is_valid_for_merge:
                manifest_entries.append(self._create_manifest_entry(
                    i + 1, queued_pdf
                ))
                if queued_pdf.status not in (FileStatus.PENDING, FileStatus.READY):
                    skipped_count += 1
                continue

            try:
                queued_pdf.status = FileStatus.PROCESSING

                # Open and read PDF
                reader = PdfReader(queued_pdf.file_path)

                # Handle encryption
                if reader.is_encrypted:
                    queued_pdf.is_encrypted = True
                    password = self._get_password_for_file(
                        queued_pdf,
                        passwords,
                        password_request_callback
                    )

                    if password is None:
                        # Skip - no password available
                        queued_pdf.status = FileStatus.ENCRYPTED
                        queued_pdf.skip_reason = "skipped"
                        queued_pdf.status_message = "Skipped"
                        skipped_count += 1
                        manifest_entries.append(self._create_manifest_entry(
                            i + 1, queued_pdf
                        ))
                        logger.info(f"Skipped encrypted file: {safe_path}")
                        continue

                    # Try to decrypt
                    try:
                        decrypt_result = reader.decrypt(password)
                        if not decrypt_result:
                            queued_pdf.status = FileStatus.ENCRYPTED
                            queued_pdf.skip_reason = "password failed"
                            queued_pdf.status_message = "Wrong password"
                            skipped_count += 1
                            manifest_entries.append(self._create_manifest_entry(
                                i + 1, queued_pdf
                            ))
                            logger.info(f"Password failed for: {safe_path}")
                            continue
                        queued_pdf.password_provided = True
                    except Exception as e:
                        queued_pdf.status = FileStatus.ENCRYPTED
                        queued_pdf.skip_reason = "decrypt error"
                        queued_pdf.status_message = "Decrypt failed"
                        skipped_count += 1
                        manifest_entries.append(self._create_manifest_entry(
                            i + 1, queued_pdf
                        ))
                        logger.warning(f"Decrypt error for {safe_path}: {e}")
                        continue

                # Add pages to writer
                pages_added = 0
                for page in reader.pages:
                    writer.add_page(page)
                    pages_added += 1
                    total_pages += 1

                queued_pdf.status = FileStatus.MERGED
                queued_pdf.page_count = pages_added
                queued_pdf.status_message = ""
                queued_pdf.skip_reason = ""
                merged_count += 1

                manifest_entries.append(self._create_manifest_entry(
                    i + 1, queued_pdf
                ))
                logger.info(f"Merged {pages_added} pages from {safe_path}")

            except PdfReadError as e:
                queued_pdf.status = FileStatus.CORRUPT
                queued_pdf.status_message = "Corrupt or unreadable"
                queued_pdf.skip_reason = "corrupt"
                error_count += 1
                manifest_entries.append(self._create_manifest_entry(
                    i + 1, queued_pdf
                ))
                logger.warning(f"Failed to read PDF {safe_path}: {e}")

            except Exception as e:
                queued_pdf.status = FileStatus.ERROR
                queued_pdf.status_message = str(e)[:50]
                queued_pdf.skip_reason = "error"
                error_count += 1
                manifest_entries.append(self._create_manifest_entry(
                    i + 1, queued_pdf
                ))
                logger.error(f"Error processing {safe_path}: {e}")

        # Check if we have anything to write
        if merged_count == 0:
            result.error_message = "No files could be merged"
            result.skipped_count = skipped_count
            result.error_count = error_count
            result.manifest_entries = manifest_entries
            return result

        # Normalize metadata if requested
        if self.normalize_metadata:
            writer.add_metadata({
                '/Producer': 'PDF Consolidator',
                '/Creator': 'PDF Consolidator',
                '/Author': '',
                '/Title': output_path.stem,
            })

        # Write output atomically (to temp file, then rename)
        try:
            if progress_callback:
                progress_callback(MergeProgress(
                    current_file="",
                    current_index=total,
                    total_files=total,
                    percent_complete=90,
                    status_message="Writing output file..."
                ))

            # Ensure output directory exists
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Write to temp file first
            temp_fd, temp_path = tempfile.mkstemp(suffix='.pdf')
            temp_path = Path(temp_path)

            try:
                with open(temp_path, 'wb') as f:
                    writer.write(f)

                # Move to final location
                shutil.move(str(temp_path), str(output_path))
                logger.info(f"Output written to {safe_output}")

            except Exception as e:
                # Clean up temp file on error
                if temp_path.exists():
                    temp_path.unlink()
                raise OutputWriteError(f"Failed to write output: {e}", str(output_path))

        except Exception as e:
            result.error_message = f"Failed to write output: {e}"
            result.manifest_entries = manifest_entries
            logger.error(f"Write error: {e}")
            return result

        # Generate summary report with manifest
        if self.generate_report:
            self._write_summary_report(
                output_path,
                files,
                manifest_entries,
                merged_count,
                skipped_count,
                error_count,
                total_pages
            )

        # Calculate final result
        duration = time.time() - start_time
        output_size = output_path.stat().st_size if output_path.exists() else 0

        result.success = True
        result.merged_count = merged_count
        result.skipped_count = skipped_count
        result.error_count = error_count
        result.total_pages = total_pages
        result.total_size_bytes = output_size
        result.duration_seconds = duration
        result.manifest_entries = manifest_entries

        if progress_callback:
            progress_callback(MergeProgress(
                current_file="",
                current_index=total,
                total_files=total,
                percent_complete=100,
                status_message="Complete!"
            ))

        logger.info(
            f"Merge complete: {merged_count} merged, {skipped_count} skipped, "
            f"{error_count} errors, {total_pages} pages, {duration:.1f}s"
        )

        return result

    def _get_password_for_file(
        self,
        queued_pdf: QueuedPDF,
        passwords: Dict[str, str],
        password_request_callback: Optional[PasswordRequestCallback]
    ) -> Optional[str]:
        """
        Get password for an encrypted file based on encryption mode.

        Returns None if file should be skipped.
        """
        file_key = str(queued_pdf.file_path)

        # Check if we already have a password for this file
        if file_key in passwords:
            return passwords[file_key]

        # Handle based on encryption mode
        if self.encryption_mode == EncryptionHandlingMode.SKIP:
            return None

        elif self.encryption_mode == EncryptionHandlingMode.SINGLE_PASSWORD:
            # Use shared password if set
            if self._shared_password is not None:
                return self._shared_password
            # Request password once
            if password_request_callback:
                password, use_for_all, cancelled = password_request_callback(
                    queued_pdf.file_name
                )
                if cancelled:
                    return None
                if use_for_all:
                    self._shared_password = password
                return password
            return None

        elif self.encryption_mode == EncryptionHandlingMode.PROMPT_EACH:
            # Request password for each file
            if password_request_callback:
                password, _, cancelled = password_request_callback(
                    queued_pdf.file_name
                )
                if cancelled:
                    return None
                return password
            return None

        return None

    def _create_manifest_entry(
        self,
        index: int,
        queued_pdf: QueuedPDF
    ) -> MergeManifestEntry:
        """Create a manifest entry for a queued PDF."""
        return MergeManifestEntry(
            index=index,
            file_name=queued_pdf.file_name,
            full_path=str(queued_pdf.file_path),
            size_bytes=queued_pdf.size_bytes,
            page_count=queued_pdf.page_count,
            status=queued_pdf.manifest_status,
            sha256_hash=queued_pdf.sha256_hash
        )

    def _write_summary_report(
        self,
        output_path: Path,
        files: List[QueuedPDF],
        manifest_entries: List[MergeManifestEntry],
        merged_count: int,
        skipped_count: int,
        error_count: int,
        total_pages: int
    ) -> None:
        """Write a summary report with merge manifest alongside the output PDF."""
        report_path = output_path.with_suffix('.txt')

        try:
            with open(report_path, 'w', encoding='utf-8') as f:
                f.write("=" * 70 + "\n")
                f.write("PDF Consolidator - Merge Summary Report\n")
                f.write("=" * 70 + "\n\n")

                f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Output file: {output_path.name}\n")
                f.write(f"Output path: {output_path}\n\n")

                f.write("-" * 70 + "\n")
                f.write("SUMMARY\n")
                f.write("-" * 70 + "\n")
                f.write(f"  Files merged:  {merged_count}\n")
                f.write(f"  Files skipped: {skipped_count}\n")
                f.write(f"  Errors:        {error_count}\n")
                f.write(f"  Total pages:   {total_pages}\n")
                if output_path.exists():
                    output_size = output_path.stat().st_size
                    f.write(f"  Output size:   {output_size:,} bytes ({output_size/1024/1024:.2f} MB)\n")
                f.write("\n")

                # Merge Manifest section
                f.write("=" * 70 + "\n")
                f.write("MERGE MANIFEST\n")
                f.write("(Files listed in exact merge order)\n")
                f.write("=" * 70 + "\n\n")

                for entry in manifest_entries:
                    f.write(entry.to_manifest_line(include_hash=self.compute_hashes))
                    f.write("\n")

                f.write("-" * 70 + "\n")
                f.write("End of Report\n")

            logger.info(f"Summary report written to {sanitize_path_for_log(report_path)}")

        except Exception as e:
            logger.warning(f"Failed to write summary report: {e}")


def create_merge_service(
    normalize_metadata: bool = True,
    encryption_mode: EncryptionHandlingMode = EncryptionHandlingMode.SKIP,
    generate_report: bool = True,
    compute_hashes: bool = False
) -> MergeService:
    """
    Factory function to create a MergeService instance.

    Args:
        normalize_metadata: Remove author/producer from output
        encryption_mode: How to handle encrypted PDFs
        generate_report: Generate summary report file
        compute_hashes: Compute SHA256 hashes for audit

    Returns:
        Configured MergeService instance
    """
    return MergeService(
        normalize_metadata=normalize_metadata,
        encryption_mode=encryption_mode,
        generate_report=generate_report,
        compute_hashes=compute_hashes
    )
