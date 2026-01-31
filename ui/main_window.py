"""
Main window for PDF Consolidator application.
"""
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Tuple

from PySide6.QtCore import (
    Qt, Signal, Slot, QThread, QObject, QModelIndex,
    QRunnable, QThreadPool
)
from PySide6.QtGui import QAction, QClipboard, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog, QMessageBox,
    QGroupBox, QLineEdit, QCheckBox, QComboBox, QSplitter, QFrame,
    QAbstractItemView, QApplication, QProgressBar, QToolButton, QMenu,
    QSizePolicy, QRadioButton, QButtonGroup, QDialog
)

from ..core.models import (
    QueuedPDF, FileStatus, MergeResult, MergeProgress,
    EncryptionHandlingMode, SortMode
)
from ..core.merge_service import MergeService, create_merge_service
from ..core.pdf_probe import validate_and_update_queued_pdf
from ..core.settings import (
    get_settings, get_settings_manager, AppSettings,
    get_log_path, get_app_data_dir
)
from ..core.utils import (
    generate_output_filename, find_pdfs_in_directory, normalize_path,
    compute_sha256, find_unique_path, is_removable_drive
)
from ..core.sanitize import get_logger, sanitize_path_for_log
from ..core.support_bundle import (
    create_support_bundle, BundleVerificationError
)
from ..core.version import __version__, get_full_app_title

from .widgets import (
    DropZone, ProgressDialog, SummaryDialog, PasswordDialog,
    LogViewerDialog, DuplicateDialog, OutputConflictDialog,
    AllowedDirectoriesDialog, SupportBundleDialog
)


logger = get_logger()


class MergeWorker(QObject):
    """
    Worker for running merge operations in a background thread.
    """

    progress = Signal(float, str, str)  # percent, status, current_file
    # Emit result data as primitives to avoid cross-thread object marshaling issues
    # (success, merged, skipped, errors, pages, size_bytes, duration, output_path, error_msg)
    finished = Signal(bool, int, int, int, int, int, float, str, str)
    error = Signal(str)
    password_requested = Signal(str)  # filename

    def __init__(
        self,
        service: MergeService,
        files: List[QueuedPDF],
        output_path: Path,
        passwords: Optional[Dict[str, str]] = None
    ):
        super().__init__()
        self.service = service
        self.files = files
        self.output_path = output_path
        self.passwords = passwords or {}
        self._pending_password_response = None

    @Slot()
    def run(self):
        """Run the merge operation."""
        try:
            def progress_callback(p: MergeProgress):
                self.progress.emit(p.percent_complete, p.status_message, p.current_file)

            logger.info("MergeWorker: Starting merge...")
            result = self.service.merge(
                self.files,
                self.output_path,
                progress_callback=progress_callback,
                passwords=self.passwords
            )
            logger.info(f"MergeWorker: Merge returned - success={result.success}, merged={result.merged_count}, pages={result.total_pages}")
            # Emit result data as primitives
            self.finished.emit(
                result.success,
                result.merged_count,
                result.skipped_count,
                result.error_count,
                result.total_pages,
                result.total_size_bytes,
                result.duration_seconds,
                str(result.output_path) if result.output_path else "",
                result.error_message
            )
            logger.info("MergeWorker: Signal emitted")
        except Exception as e:
            logger.exception("Merge worker error")
            self.error.emit(str(e))

    def cancel(self):
        """Request cancellation."""
        self.service.cancel()


class ValidationWorker(QObject):
    """
    Worker for validating files in background.
    """

    progress = Signal(int, int, str)  # current, total, filename
    file_validated = Signal(int, object)  # index, QueuedPDF
    finished = Signal()

    def __init__(self, files: List[QueuedPDF], skip_encrypted: bool = True):
        super().__init__()
        self.files = files
        self.skip_encrypted = skip_encrypted
        self._cancelled = False

    @Slot()
    def run(self):
        """Run validation."""
        total = len(self.files)
        for i, pdf in enumerate(self.files):
            if self._cancelled:
                break
            self.progress.emit(i + 1, total, pdf.file_name)
            validate_and_update_queued_pdf(pdf, self.skip_encrypted)
            self.file_validated.emit(i, pdf)
        self.finished.emit()

    def cancel(self):
        """Cancel validation."""
        self._cancelled = True


class PageCountRunnable(QRunnable):
    """
    Runnable for lazy page count detection.
    """

    class Signals(QObject):
        finished = Signal(int, int)  # index, page_count

    def __init__(self, index: int, file_path: Path):
        super().__init__()
        self.index = index
        self.file_path = file_path
        self.signals = self.Signals()
        self.setAutoDelete(True)

    def run(self):
        """Get page count for file."""
        try:
            from ..core.pdf_probe import probe_pdf
            is_valid, page_count, _ = probe_pdf(self.file_path, check_encryption=False)
            if is_valid and page_count is not None:
                self.signals.finished.emit(self.index, page_count)
        except Exception:
            pass  # Silently fail for page count


class MainWindow(QMainWindow):
    """
    Main application window for PDF Consolidator.
    """

    APP_NAME = "PDF Consolidator"
    APP_VERSION = __version__

    def __init__(self):
        super().__init__()
        self.setWindowTitle(get_full_app_title())
        self.queued_files: List[QueuedPDF] = []
        self.merge_thread: Optional[QThread] = None
        self.merge_worker: Optional[MergeWorker] = None
        self.validation_thread: Optional[QThread] = None
        self.page_count_pool = QThreadPool()
        self.page_count_pool.setMaxThreadCount(2)  # Low priority

        self._setup_ui()
        self._setup_shortcuts()
        self._load_settings()
        self._connect_signals()
        self._check_first_run()

        logger.info(f"{self.APP_NAME} v{self.APP_VERSION} started")

    def _setup_ui(self):
        """Set up the user interface."""
        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(16, 16, 16, 16)

        # Header
        header = self._create_header()
        main_layout.addWidget(header)

        # Drop zone
        self.drop_zone = DropZone()
        main_layout.addWidget(self.drop_zone)

        # Action buttons
        button_row = self._create_button_row()
        main_layout.addLayout(button_row)

        # File table
        self.file_table = self._create_file_table()
        main_layout.addWidget(self.file_table, stretch=1)

        # Output section
        output_group = self._create_output_section()
        main_layout.addWidget(output_group)

        # Advanced options (collapsible)
        self.advanced_group = self._create_advanced_options()
        main_layout.addWidget(self.advanced_group)

        # Bottom status bar
        self.status_bar = self.statusBar()
        self.status_bar.showMessage("Ready")

        # Apply window settings
        settings = get_settings()
        self.resize(settings.window_width, settings.window_height)

        # Apply styling
        self._apply_styles()

    def _setup_shortcuts(self):
        """Set up keyboard shortcuts."""
        # Ctrl+O: Add Files
        shortcut_add_files = QShortcut(QKeySequence("Ctrl+O"), self)
        shortcut_add_files.activated.connect(self._on_add_files)

        # Ctrl+Shift+O: Add Folder
        shortcut_add_folder = QShortcut(QKeySequence("Ctrl+Shift+O"), self)
        shortcut_add_folder.activated.connect(self._on_add_folder)

        # Delete: Remove selected
        shortcut_delete = QShortcut(QKeySequence.Delete, self)
        shortcut_delete.activated.connect(self._on_remove_selected)

        # Ctrl+M: Merge
        shortcut_merge = QShortcut(QKeySequence("Ctrl+M"), self)
        shortcut_merge.activated.connect(self._on_merge)

    def _create_header(self) -> QWidget:
        """Create header widget."""
        header = QWidget()
        layout = QHBoxLayout(header)
        layout.setContentsMargins(0, 0, 0, 8)

        # Title
        title = QLabel(self.APP_NAME)
        title.setStyleSheet("""
            font-size: 24px;
            font-weight: bold;
            color: #212529;
        """)
        layout.addWidget(title)

        layout.addStretch()

        # Version
        version = QLabel(f"v{self.APP_VERSION}")
        version.setStyleSheet("color: #6c757d;")
        layout.addWidget(version)

        # Support bundle button
        support_btn = QToolButton()
        support_btn.setText("📦")
        support_btn.setToolTip("Export Support Bundle")
        support_btn.clicked.connect(self._on_export_support_bundle)
        layout.addWidget(support_btn)

        # Log button
        log_btn = QToolButton()
        log_btn.setText("📋")
        log_btn.setToolTip("View Logs")
        log_btn.clicked.connect(self._show_logs)
        layout.addWidget(log_btn)

        return header

    def _create_button_row(self) -> QHBoxLayout:
        """Create action buttons row."""
        layout = QHBoxLayout()

        self.add_files_btn = QPushButton("Add Files")
        self.add_files_btn.setToolTip("Select PDF files to add (Ctrl+O)")
        layout.addWidget(self.add_files_btn)

        self.add_folder_btn = QPushButton("Add Folder")
        self.add_folder_btn.setToolTip("Add all PDFs from a folder (Ctrl+Shift+O)")
        layout.addWidget(self.add_folder_btn)

        layout.addStretch()

        self.move_up_btn = QPushButton("▲ Up")
        self.move_up_btn.setToolTip("Move selected file up")
        self.move_up_btn.setEnabled(False)
        layout.addWidget(self.move_up_btn)

        self.move_down_btn = QPushButton("▼ Down")
        self.move_down_btn.setToolTip("Move selected file down")
        self.move_down_btn.setEnabled(False)
        layout.addWidget(self.move_down_btn)

        layout.addStretch()

        self.clear_btn = QPushButton("Clear All")
        self.clear_btn.setToolTip("Remove all files from queue")
        layout.addWidget(self.clear_btn)

        self.merge_btn = QPushButton("  Merge PDFs  ")
        self.merge_btn.setToolTip("Merge all valid PDFs (Ctrl+M)")
        self.merge_btn.setStyleSheet("""
            QPushButton {
                background-color: #0d6efd;
                color: white;
                font-weight: bold;
                padding: 8px 16px;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #0b5ed7;
            }
            QPushButton:disabled {
                background-color: #6c757d;
            }
        """)
        layout.addWidget(self.merge_btn)

        return layout

    def _create_file_table(self) -> QTableWidget:
        """Create file list table."""
        table = QTableWidget()
        table.setColumnCount(6)
        table.setHorizontalHeaderLabels([
            "#", "File Name", "Source Path", "Size", "Pages", "Status"
        ])

        # Set column properties
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.Fixed)
        header.setSectionResizeMode(4, QHeaderView.Fixed)
        header.setSectionResizeMode(5, QHeaderView.Fixed)

        table.setColumnWidth(0, 40)
        table.setColumnWidth(3, 80)
        table.setColumnWidth(4, 60)
        table.setColumnWidth(5, 100)

        # Selection and drag behavior
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        table.setDragEnabled(True)
        table.setAcceptDrops(True)
        table.setDragDropMode(QAbstractItemView.InternalMove)
        table.setDefaultDropAction(Qt.MoveAction)

        # Alternating row colors
        table.setAlternatingRowColors(True)

        return table

    def _create_output_section(self) -> QGroupBox:
        """Create output configuration section."""
        group = QGroupBox("Output Settings")
        layout = QVBoxLayout(group)

        # Output folder row
        folder_row = QHBoxLayout()
        folder_row.addWidget(QLabel("Output Folder:"))

        self.output_folder_edit = QLineEdit()
        self.output_folder_edit.setPlaceholderText("Same as first input file")
        folder_row.addWidget(self.output_folder_edit, stretch=1)

        self.browse_output_btn = QPushButton("Browse...")
        folder_row.addWidget(self.browse_output_btn)

        layout.addLayout(folder_row)

        # Filename row
        filename_row = QHBoxLayout()
        filename_row.addWidget(QLabel("Filename:"))

        self.filename_edit = QLineEdit()
        self.filename_edit.setText("Merged_{timestamp}.pdf")
        self.filename_edit.setToolTip(
            "Use {timestamp}, {date}, or {time} as placeholders"
        )
        filename_row.addWidget(self.filename_edit, stretch=1)

        layout.addLayout(filename_row)

        # Open folder checkbox
        self.open_folder_check = QCheckBox("Open output folder after merge")
        self.open_folder_check.setChecked(True)
        layout.addWidget(self.open_folder_check)

        return group

    def _create_advanced_options(self) -> QGroupBox:
        """Create advanced options section."""
        group = QGroupBox("Advanced Options")
        group.setCheckable(True)
        group.setChecked(False)

        layout = QVBoxLayout(group)

        # Row 1: Sort mode with Sort Now button
        row1 = QHBoxLayout()

        row1.addWidget(QLabel("Sort files by:"))
        self.sort_combo = QComboBox()
        self.sort_combo.addItems(["Manual order", "Filename", "Modified time"])
        row1.addWidget(self.sort_combo)

        self.sort_now_btn = QPushButton("Sort Now")
        self.sort_now_btn.setToolTip("Apply sort immediately")
        self.sort_now_btn.setEnabled(False)
        row1.addWidget(self.sort_now_btn)

        row1.addSpacing(20)

        self.subfolders_check = QCheckBox("Include subfolders")
        row1.addWidget(self.subfolders_check)

        row1.addStretch()
        layout.addLayout(row1)

        # Row 2: Encryption handling
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Encrypted PDFs:"))

        self.encryption_group = QButtonGroup(self)
        self.encrypt_skip_radio = QRadioButton("Skip")
        self.encrypt_skip_radio.setChecked(True)
        self.encryption_group.addButton(self.encrypt_skip_radio, 0)
        row2.addWidget(self.encrypt_skip_radio)

        self.encrypt_prompt_radio = QRadioButton("Prompt each")
        self.encryption_group.addButton(self.encrypt_prompt_radio, 1)
        row2.addWidget(self.encrypt_prompt_radio)

        self.encrypt_single_radio = QRadioButton("Single password")
        self.encryption_group.addButton(self.encrypt_single_radio, 2)
        row2.addWidget(self.encrypt_single_radio)

        row2.addStretch()
        layout.addLayout(row2)

        # Row 3: Processing options
        row3 = QHBoxLayout()

        self.normalize_metadata_check = QCheckBox("Normalize metadata")
        self.normalize_metadata_check.setChecked(True)
        self.normalize_metadata_check.setToolTip("Remove author/producer from output")
        row3.addWidget(self.normalize_metadata_check)

        self.generate_report_check = QCheckBox("Generate summary report (.txt)")
        self.generate_report_check.setChecked(True)
        row3.addWidget(self.generate_report_check)

        self.hash_files_check = QCheckBox("Compute file hashes (SHA256)")
        self.hash_files_check.setToolTip("For audit purposes")
        row3.addWidget(self.hash_files_check)

        row3.addStretch()
        layout.addLayout(row3)

        # Row 4: Output safety
        row4 = QHBoxLayout()

        self.restrict_output_check = QCheckBox("Restrict output directories")
        self.restrict_output_check.setToolTip("Only allow saving to specified folders")
        row4.addWidget(self.restrict_output_check)

        self.manage_dirs_btn = QPushButton("Manage...")
        self.manage_dirs_btn.setEnabled(False)
        self.manage_dirs_btn.clicked.connect(self._on_manage_allowed_dirs)
        row4.addWidget(self.manage_dirs_btn)

        row4.addSpacing(20)

        self.block_removable_check = QCheckBox("Block removable drives")
        self.block_removable_check.setToolTip("Prevent saving to USB drives (Windows)")
        row4.addWidget(self.block_removable_check)

        row4.addStretch()

        # Open logs folder button
        self.open_logs_btn = QPushButton("Open Logs Folder")
        self.open_logs_btn.clicked.connect(self._on_open_logs_folder)
        row4.addWidget(self.open_logs_btn)

        layout.addLayout(row4)

        return group

    def _apply_styles(self):
        """Apply application-wide styles."""
        self.setStyleSheet("""
            QMainWindow {
                background-color: #ffffff;
            }
            QGroupBox {
                font-weight: bold;
                border: 1px solid #dee2e6;
                border-radius: 6px;
                margin-top: 12px;
                padding-top: 12px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 8px;
            }
            QTableWidget {
                border: 1px solid #dee2e6;
                border-radius: 4px;
                gridline-color: #e9ecef;
            }
            QTableWidget::item {
                padding: 4px;
            }
            QHeaderView::section {
                background-color: #f8f9fa;
                border: none;
                border-bottom: 1px solid #dee2e6;
                padding: 8px;
                font-weight: bold;
            }
            QPushButton {
                padding: 6px 12px;
                border: 1px solid #ced4da;
                border-radius: 4px;
                background-color: #ffffff;
            }
            QPushButton:hover {
                background-color: #e9ecef;
            }
            QPushButton:disabled {
                color: #adb5bd;
            }
            QLineEdit {
                padding: 6px;
                border: 1px solid #ced4da;
                border-radius: 4px;
            }
            QComboBox {
                padding: 6px;
                border: 1px solid #ced4da;
                border-radius: 4px;
            }
        """)

    def _connect_signals(self):
        """Connect UI signals to slots."""
        # Drop zone
        self.drop_zone.files_dropped.connect(self._on_files_dropped)
        self.drop_zone.folders_dropped.connect(self._on_folders_dropped)
        self.drop_zone.clicked.connect(self._on_add_files)

        # Buttons
        self.add_files_btn.clicked.connect(self._on_add_files)
        self.add_folder_btn.clicked.connect(self._on_add_folder)
        self.clear_btn.clicked.connect(self._on_clear)
        self.merge_btn.clicked.connect(self._on_merge)
        self.browse_output_btn.clicked.connect(self._on_browse_output)
        self.move_up_btn.clicked.connect(self._on_move_up)
        self.move_down_btn.clicked.connect(self._on_move_down)
        self.sort_now_btn.clicked.connect(self._on_sort_now)

        # Table selection
        self.file_table.itemSelectionChanged.connect(self._on_selection_changed)

        # Sort combo
        self.sort_combo.currentIndexChanged.connect(self._on_sort_mode_changed)

        # Output restriction toggle
        self.restrict_output_check.toggled.connect(
            lambda checked: self.manage_dirs_btn.setEnabled(checked)
        )

    def _check_first_run(self):
        """Show first-run information dialog if this is the first launch."""
        settings = get_settings()

        # Check if we've shown the first-run dialog before
        if getattr(settings, 'first_run_shown', False):
            return

        # Show the first-run information dialog
        app_data = get_app_data_dir()
        msg = QMessageBox(self)
        msg.setWindowTitle("Welcome to PDF Consolidator")
        msg.setIcon(QMessageBox.Information)
        msg.setText(
            "<b>Welcome to PDF Consolidator!</b><br><br>"
            "This application runs <b>100% offline</b>.<br>"
            "Your documents are never uploaded anywhere."
        )
        msg.setInformativeText(
            f"<b>Local Storage:</b><br>"
            f"Settings and logs are stored in:<br>"
            f"<code>{app_data}</code><br><br>"
            f"<b>Privacy:</b><br>"
            f"No telemetry, no network calls, no data collection.<br>"
            f"Passwords are never saved to disk."
        )
        msg.setStandardButtons(QMessageBox.Ok)

        # Add a button to view security notes
        security_btn = msg.addButton("View Security Notes", QMessageBox.ActionRole)

        msg.exec()

        if msg.clickedButton() == security_btn:
            self._show_security_notes()

        # Mark first run as shown
        try:
            settings_mgr = get_settings_manager()
            settings_mgr.settings.first_run_shown = True
            settings_mgr.save()
        except Exception:
            pass  # Don't fail if we can't save

    def _show_security_notes(self):
        """Show security notes dialog."""
        app_data = get_app_data_dir()
        notes = f"""
<h3>Security & Privacy Notes</h3>

<p><b>Offline Operation:</b><br>
This application makes NO network connections. Your documents are processed
entirely on your local computer.</p>

<p><b>Local Storage:</b><br>
Settings: <code>{app_data}\\settings.json</code><br>
Logs: <code>{app_data}\\app.log</code></p>

<p><b>What is NOT stored:</b></p>
<ul>
<li>Your PDF file contents</li>
<li>Passwords or credentials</li>
<li>Personal information</li>
<li>Network or location data</li>
</ul>

<p><b>Sanitized Logging:</b><br>
Usernames are automatically removed from logged file paths.</p>
"""
        msg = QMessageBox(self)
        msg.setWindowTitle("Security Notes")
        msg.setIcon(QMessageBox.Information)
        msg.setTextFormat(Qt.RichText)
        msg.setText(notes)
        msg.setStandardButtons(QMessageBox.Ok)
        msg.exec()

    def _load_settings(self):
        """Load saved settings."""
        settings = get_settings()

        self.output_folder_edit.setText(settings.output_directory)
        self.filename_edit.setText(settings.output_filename_template)
        self.open_folder_check.setChecked(settings.open_folder_after_merge)

        # Sort mode
        sort_modes = {"manual": 0, "filename": 1, "modified_time": 2}
        self.sort_combo.setCurrentIndex(sort_modes.get(settings.sort_mode, 0))
        self._on_sort_mode_changed(self.sort_combo.currentIndex())

        self.subfolders_check.setChecked(settings.include_subfolders)
        self.normalize_metadata_check.setChecked(settings.normalize_metadata)
        self.generate_report_check.setChecked(settings.generate_summary_report)
        self.hash_files_check.setChecked(settings.enable_file_hashing)

        # Encryption mode
        enc_modes = {"skip": 0, "prompt_each": 1, "single_password": 2}
        enc_mode = enc_modes.get(settings.encryption_handling_mode, 0)
        self.encryption_group.button(enc_mode).setChecked(True)

        # Output restrictions
        self.restrict_output_check.setChecked(settings.restrict_output_directories)
        self.manage_dirs_btn.setEnabled(settings.restrict_output_directories)
        self.block_removable_check.setChecked(settings.block_removable_drives)

        self.advanced_group.setChecked(settings.show_advanced_options)

    def _save_settings(self):
        """Save current settings."""
        manager = get_settings_manager()
        settings = manager.settings

        settings.output_directory = self.output_folder_edit.text()
        settings.output_filename_template = self.filename_edit.text()
        settings.open_folder_after_merge = self.open_folder_check.isChecked()

        sort_modes = {0: "manual", 1: "filename", 2: "modified_time"}
        settings.sort_mode = sort_modes.get(self.sort_combo.currentIndex(), "manual")

        settings.include_subfolders = self.subfolders_check.isChecked()
        settings.normalize_metadata = self.normalize_metadata_check.isChecked()
        settings.generate_summary_report = self.generate_report_check.isChecked()
        settings.enable_file_hashing = self.hash_files_check.isChecked()

        # Encryption mode
        enc_modes = {0: "skip", 1: "prompt_each", 2: "single_password"}
        settings.encryption_handling_mode = enc_modes.get(
            self.encryption_group.checkedId(), "skip"
        )

        # Output restrictions
        settings.restrict_output_directories = self.restrict_output_check.isChecked()
        settings.block_removable_drives = self.block_removable_check.isChecked()

        settings.show_advanced_options = self.advanced_group.isChecked()

        settings.window_width = self.width()
        settings.window_height = self.height()

        manager.save()

    def closeEvent(self, event):
        """Handle window close."""
        self._save_settings()
        logger.info("Application closed")
        event.accept()

    # === File Management ===

    def _add_files(self, file_paths: List[str]):
        """Add files to the queue."""
        new_files: List[QueuedPDF] = []
        existing_paths = {str(f.file_path) for f in self.queued_files}

        for path_str in file_paths:
            path = Path(path_str)
            if not path.exists():
                continue

            # Check for duplicates
            if str(path) in existing_paths:
                continue

            # Create queued item (page_count will be lazy loaded)
            queued = QueuedPDF(
                file_path=path,
                order_index=len(self.queued_files) + len(new_files)
            )
            new_files.append(queued)
            existing_paths.add(str(path))

        if new_files:
            self.queued_files.extend(new_files)
            self._refresh_table()
            self._validate_files(new_files)
            self._request_lazy_page_counts(new_files)

        self._update_status()

    def _validate_files(self, files: List[QueuedPDF]):
        """Validate files in background."""
        if not files:
            return

        skip_encrypted = self.encrypt_skip_radio.isChecked()

        # For small number of files, validate synchronously
        if len(files) <= 5:
            for pdf in files:
                validate_and_update_queued_pdf(pdf, skip_encrypted)
            self._refresh_table()
            return

        # For larger numbers, use background thread
        self.validation_thread = QThread()
        worker = ValidationWorker(files, skip_encrypted)
        worker.moveToThread(self.validation_thread)

        self.validation_thread.started.connect(worker.run)
        worker.file_validated.connect(self._on_file_validated)
        worker.finished.connect(self.validation_thread.quit)
        worker.finished.connect(worker.deleteLater)
        self.validation_thread.finished.connect(self.validation_thread.deleteLater)

        self.validation_thread.start()

    def _request_lazy_page_counts(self, files: List[QueuedPDF]):
        """Request page counts lazily in background."""
        for i, pdf in enumerate(files):
            if pdf.page_count is None:
                # Find index in main list
                try:
                    idx = self.queued_files.index(pdf)
                    runnable = PageCountRunnable(idx, pdf.file_path)
                    runnable.signals.finished.connect(self._on_page_count_ready)
                    self.page_count_pool.start(runnable)
                except ValueError:
                    pass

    @Slot(int, int)
    def _on_page_count_ready(self, index: int, page_count: int):
        """Handle lazy page count result."""
        if index < len(self.queued_files):
            self.queued_files[index].page_count = page_count
            # Update just the page count cell
            item = self.file_table.item(index, 4)
            if item:
                item.setText(str(page_count))
            self._update_status()

    def _refresh_table(self):
        """Refresh the file table display."""
        self.file_table.setRowCount(len(self.queued_files))

        for i, pdf in enumerate(self.queued_files):
            pdf.order_index = i + 1

            # Order number
            item = QTableWidgetItem(str(i + 1))
            item.setTextAlignment(Qt.AlignCenter)
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            self.file_table.setItem(i, 0, item)

            # File name
            item = QTableWidgetItem(pdf.file_name)
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            self.file_table.setItem(i, 1, item)

            # Source path (ellipsized)
            item = QTableWidgetItem(pdf.ellipsized_path(40))
            item.setToolTip(str(pdf.file_path.parent))
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            self.file_table.setItem(i, 2, item)

            # Size
            item = QTableWidgetItem(pdf.size_display)
            item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            self.file_table.setItem(i, 3, item)

            # Page count
            item = QTableWidgetItem(pdf.page_count_display)
            item.setTextAlignment(Qt.AlignCenter)
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            self.file_table.setItem(i, 4, item)

            # Status with color coding
            item = QTableWidgetItem(pdf.status_display)
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)

            if pdf.status == FileStatus.READY:
                item.setForeground(Qt.darkGreen)
            elif pdf.status in (FileStatus.ERROR, FileStatus.CORRUPT, FileStatus.NOT_PDF):
                item.setForeground(Qt.red)
            elif pdf.status == FileStatus.ENCRYPTED:
                item.setForeground(Qt.darkYellow)
            elif pdf.status == FileStatus.SKIPPED:
                item.setForeground(Qt.gray)

            self.file_table.setItem(i, 5, item)

    def _update_status(self):
        """Update status bar."""
        total = len(self.queued_files)
        valid = sum(1 for f in self.queued_files if f.is_valid_for_merge)
        total_pages = sum(f.page_count or 0 for f in self.queued_files if f.is_valid_for_merge)

        if total == 0:
            self.status_bar.showMessage("Ready - Add files to begin")
            self.merge_btn.setEnabled(False)
        else:
            self.status_bar.showMessage(
                f"{valid} of {total} files ready | ~{total_pages} pages"
            )
            self.merge_btn.setEnabled(valid > 0)

    def _check_duplicates(self) -> List[str]:
        """Check for duplicate files and return list of duplicates."""
        seen = set()
        duplicates = []
        for pdf in self.queued_files:
            normalized = str(normalize_path(pdf.file_path))
            if normalized in seen:
                duplicates.append(pdf.file_name)
            seen.add(normalized)
        return duplicates

    def _remove_duplicates(self):
        """Remove duplicate files from queue."""
        seen = set()
        unique = []
        for pdf in self.queued_files:
            normalized = str(normalize_path(pdf.file_path))
            if normalized not in seen:
                seen.add(normalized)
                unique.append(pdf)
        self.queued_files = unique
        self._refresh_table()
        self._update_status()

    def _sort_files(self):
        """Sort files according to current sort mode."""
        mode = self.sort_combo.currentIndex()

        if mode == 1:  # Filename
            self.queued_files.sort(key=lambda f: f.file_name.lower())
        elif mode == 2:  # Modified time
            self.queued_files.sort(
                key=lambda f: f.modified_time or datetime.min
            )
        # mode 0 = Manual, keep current order

        self._refresh_table()

    def _get_encryption_mode(self) -> EncryptionHandlingMode:
        """Get current encryption handling mode."""
        mode_id = self.encryption_group.checkedId()
        modes = {
            0: EncryptionHandlingMode.SKIP,
            1: EncryptionHandlingMode.PROMPT_EACH,
            2: EncryptionHandlingMode.SINGLE_PASSWORD
        }
        return modes.get(mode_id, EncryptionHandlingMode.SKIP)

    def _check_output_allowed(self, output_path: Path) -> Tuple[bool, str]:
        """Check if output path is allowed."""
        settings = get_settings()

        # Check directory restrictions
        if settings.restrict_output_directories:
            if not settings.is_output_allowed(output_path):
                allowed_list = "\n".join(f"  • {d}" for d in settings.allowed_output_directories)
                return False, (
                    f"Output directory not in allowed list.\n\n"
                    f"Allowed directories:\n{allowed_list}"
                )

        # Check removable drive (Windows)
        if settings.block_removable_drives:
            is_removable, drive_type = is_removable_drive(output_path)
            if is_removable:
                return False, (
                    f"Cannot save to removable drive ({drive_type}).\n"
                    f"Please select a fixed drive location."
                )

        return True, ""

    # === Slots ===

    @Slot(list)
    def _on_files_dropped(self, paths: List[str]):
        """Handle files dropped on drop zone."""
        logger.info(f"Files dropped: {len(paths)} items")
        pdf_paths = [p for p in paths if p.lower().endswith('.pdf')]
        if pdf_paths:
            self._add_files(pdf_paths)
        elif paths:
            QMessageBox.information(
                self,
                "No PDFs Found",
                "No PDF files were found in the dropped items."
            )

    @Slot(list)
    def _on_folders_dropped(self, paths: List[str]):
        """Handle folders dropped on drop zone."""
        logger.info(f"Folders dropped: {len(paths)} items")
        include_subfolders = self.subfolders_check.isChecked()

        all_pdfs = []
        for folder_path in paths:
            folder = Path(folder_path)
            pdfs = find_pdfs_in_directory(folder, include_subfolders)
            all_pdfs.extend([str(p) for p in pdfs])

        if all_pdfs:
            self._add_files(all_pdfs)
        else:
            QMessageBox.information(
                self,
                "No PDFs Found",
                "No PDF files were found in the dropped folder(s)."
            )

    @Slot()
    def _on_add_files(self):
        """Handle Add Files button click."""
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select PDF Files",
            "",
            "PDF Files (*.pdf);;All Files (*.*)"
        )
        if files:
            self._add_files(files)

    @Slot()
    def _on_add_folder(self):
        """Handle Add Folder button click."""
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Folder",
            "",
            QFileDialog.ShowDirsOnly
        )
        if folder:
            include_subfolders = self.subfolders_check.isChecked()
            pdfs = find_pdfs_in_directory(Path(folder), include_subfolders)
            if pdfs:
                self._add_files([str(p) for p in pdfs])
            else:
                QMessageBox.information(
                    self,
                    "No PDFs Found",
                    "No PDF files were found in the selected folder."
                )

    @Slot()
    def _on_clear(self):
        """Handle Clear button click."""
        if self.queued_files:
            result = QMessageBox.question(
                self,
                "Clear Queue",
                f"Remove all {len(self.queued_files)} files from the queue?",
                QMessageBox.Yes | QMessageBox.No
            )
            if result == QMessageBox.Yes:
                self.queued_files.clear()
                self._refresh_table()
                self._update_status()
                logger.info("Queue cleared")

    @Slot()
    def _on_remove_selected(self):
        """Remove selected files from queue."""
        selected_rows = set()
        for item in self.file_table.selectedItems():
            selected_rows.add(item.row())

        if selected_rows:
            # Remove in reverse order to maintain indices
            for row in sorted(selected_rows, reverse=True):
                if row < len(self.queued_files):
                    del self.queued_files[row]
            self._refresh_table()
            self._update_status()

    @Slot()
    def _on_browse_output(self):
        """Handle output folder browse button."""
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Output Folder",
            self.output_folder_edit.text()
        )
        if folder:
            self.output_folder_edit.setText(folder)

    @Slot()
    def _on_selection_changed(self):
        """Handle table selection change."""
        selected = self.file_table.selectedItems()
        has_selection = len(selected) > 0

        if has_selection:
            row = self.file_table.currentRow()
            self.move_up_btn.setEnabled(row > 0)
            self.move_down_btn.setEnabled(row < len(self.queued_files) - 1)
        else:
            self.move_up_btn.setEnabled(False)
            self.move_down_btn.setEnabled(False)

    @Slot()
    def _on_move_up(self):
        """Move selected file up in order."""
        row = self.file_table.currentRow()
        if row > 0:
            self.queued_files[row], self.queued_files[row - 1] = \
                self.queued_files[row - 1], self.queued_files[row]
            self._refresh_table()
            self.file_table.selectRow(row - 1)

    @Slot()
    def _on_move_down(self):
        """Move selected file down in order."""
        row = self.file_table.currentRow()
        if row < len(self.queued_files) - 1:
            self.queued_files[row], self.queued_files[row + 1] = \
                self.queued_files[row + 1], self.queued_files[row]
            self._refresh_table()
            self.file_table.selectRow(row + 1)

    @Slot(int)
    def _on_sort_mode_changed(self, index: int):
        """Handle sort mode change."""
        # Enable/disable Sort Now button based on mode
        self.sort_now_btn.setEnabled(index != 0)  # Disabled for Manual

    @Slot()
    def _on_sort_now(self):
        """Handle Sort Now button click."""
        if self.queued_files:
            self._sort_files()
            logger.info(f"Files sorted by {self.sort_combo.currentText()}")

    @Slot(int, object)
    def _on_file_validated(self, index: int, pdf: QueuedPDF):
        """Handle file validation complete."""
        if index < len(self.queued_files):
            self._refresh_table()
            self._update_status()

    @Slot()
    def _on_manage_allowed_dirs(self):
        """Show allowed directories manager."""
        settings = get_settings()
        dialog = AllowedDirectoriesDialog(
            self,
            settings.allowed_output_directories
        )
        if dialog.exec() == QDialog.Accepted:
            settings.allowed_output_directories = dialog.get_directories()
            get_settings_manager().save()

    @Slot()
    def _on_open_logs_folder(self):
        """Open logs folder in file explorer."""
        self._open_folder(get_app_data_dir())

    @Slot()
    def _on_export_support_bundle(self):
        """Export support bundle."""
        dialog = SupportBundleDialog(self)
        if dialog.exec() != QDialog.Accepted:
            return

        # Get save location
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"PDFConsolidator_Support_{timestamp}.zip"

        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Support Bundle",
            default_name,
            "ZIP Files (*.zip)"
        )

        if not save_path:
            return

        try:
            bundle_path = create_support_bundle(Path(save_path))
            QMessageBox.information(
                self,
                "Bundle Created",
                f"Support bundle saved to:\n{bundle_path}"
            )
            logger.info(f"Support bundle exported: {sanitize_path_for_log(bundle_path)}")
        except BundleVerificationError as e:
            QMessageBox.critical(
                self,
                "Bundle Error",
                f"Failed to create support bundle:\n\n{e}"
            )
            logger.error(f"Support bundle verification failed: {e}")
        except Exception as e:
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to create support bundle:\n\n{e}"
            )
            logger.exception("Support bundle creation failed")

    @Slot()
    def _on_merge(self):
        """Handle Merge button click."""
        # Check for valid files
        valid_files = [f for f in self.queued_files if f.is_valid_for_merge]
        if not valid_files:
            QMessageBox.warning(
                self,
                "No Valid Files",
                "There are no valid PDF files to merge."
            )
            return

        # Check for duplicates
        duplicates = self._check_duplicates()
        if duplicates:
            dialog = DuplicateDialog(self, duplicates)
            if dialog.exec() == QDialog.Accepted:
                if not dialog.keep_duplicates:
                    self._remove_duplicates()
                    valid_files = [f for f in self.queued_files if f.is_valid_for_merge]

        # Determine output path
        output_folder = self.output_folder_edit.text()
        if not output_folder:
            output_folder = str(self.queued_files[0].file_path.parent)

        output_path = generate_output_filename(
            template=self.filename_edit.text(),
            output_dir=Path(output_folder)
        )

        # Check output allowed
        allowed, reason = self._check_output_allowed(output_path)
        if not allowed:
            QMessageBox.warning(self, "Output Not Allowed", reason)
            return

        # Handle existing output file
        if output_path.exists():
            dialog = OutputConflictDialog(self, str(output_path))
            if dialog.exec() != QDialog.Accepted:
                return

            if dialog.choice == OutputConflictDialog.AUTO_RENAME:
                output_path = find_unique_path(output_path)
            elif dialog.choice == OutputConflictDialog.CANCEL:
                return
            # OVERWRITE: keep same path

        logger.info(f"Starting merge of {len(valid_files)} files")

        # Get encryption mode
        encryption_mode = self._get_encryption_mode()

        # Create merge service
        service = create_merge_service(
            normalize_metadata=self.normalize_metadata_check.isChecked(),
            encryption_mode=encryption_mode,
            generate_report=self.generate_report_check.isChecked(),
            compute_hashes=self.hash_files_check.isChecked()
        )

        # Handle single password mode - get password upfront
        if encryption_mode == EncryptionHandlingMode.SINGLE_PASSWORD:
            encrypted_files = [f for f in self.queued_files if f.is_encrypted]
            if encrypted_files:
                dialog = PasswordDialog(
                    self,
                    f"{len(encrypted_files)} encrypted file(s)",
                    show_use_for_all=False
                )
                result = dialog.exec()
                if result == PasswordDialog.RESULT_CANCEL:
                    return
                if result == PasswordDialog.RESULT_OK:
                    service.set_shared_password(dialog.get_password())

        # Show progress dialog
        self.progress_dialog = ProgressDialog(self, "Merging PDFs...")
        self.progress_dialog.cancelled.connect(self._on_merge_cancelled)

        # Create worker thread
        self.merge_thread = QThread()
        self.merge_worker = MergeWorker(
            service,
            self.queued_files,  # Pass ALL files for manifest
            output_path
        )
        self.merge_worker.moveToThread(self.merge_thread)

        # Connect signals
        self.merge_thread.started.connect(self.merge_worker.run)
        self.merge_worker.progress.connect(self._on_merge_progress)
        self.merge_worker.finished.connect(self._on_merge_finished)
        self.merge_worker.error.connect(self._on_merge_error)
        # Note: Don't connect deleteLater to finished - we'll clean up manually
        # after accessing the result in _on_merge_finished
        self.merge_worker.finished.connect(self.merge_thread.quit)
        self.merge_thread.finished.connect(self._cleanup_merge_thread)

        # Start merge
        self.merge_thread.start()
        self.progress_dialog.show()

    @Slot()
    def _cleanup_merge_thread(self):
        """Clean up merge thread and worker after completion."""
        if hasattr(self, 'merge_worker') and self.merge_worker:
            self.merge_worker.deleteLater()
            self.merge_worker = None
        if hasattr(self, 'merge_thread') and self.merge_thread:
            self.merge_thread.deleteLater()
            self.merge_thread = None

    @Slot()
    def _on_merge_cancelled(self):
        """Handle merge cancellation."""
        if self.merge_worker:
            self.merge_worker.cancel()
        logger.info("Merge cancelled by user")

    @Slot(float, str, str)
    def _on_merge_progress(self, percent: float, status: str, current_file: str):
        """Handle merge progress update."""
        if hasattr(self, 'progress_dialog'):
            self.progress_dialog.update_progress(percent, status, current_file)

    @Slot(bool, int, int, int, int, int, float, str, str)
    def _on_merge_finished(
        self,
        success: bool,
        merged_count: int,
        skipped_count: int,
        error_count: int,
        total_pages: int,
        total_size_bytes: int,
        duration_seconds: float,
        output_path_str: str,
        error_message: str
    ):
        """Handle merge completion."""
        logger.info(f"_on_merge_finished called: success={success}, merged={merged_count}, pages={total_pages}, path={output_path_str}")
        if hasattr(self, 'progress_dialog'):
            self.progress_dialog.close()

        # Refresh table with updated statuses
        self._refresh_table()
        self._update_status()

        # Show summary dialog
        output_size = f"{total_size_bytes / (1024*1024):.2f} MB"
        duration = f"{duration_seconds:.1f}s"
        output_path = Path(output_path_str) if output_path_str else None

        dialog = SummaryDialog(
            self,
            success=success,
            merged_count=merged_count,
            skipped_count=skipped_count,
            error_count=error_count,
            total_pages=total_pages,
            output_path=output_path_str,
            output_size=output_size,
            duration=duration
        )

        dialog.open_folder_requested.connect(
            lambda: self._open_folder(output_path.parent if output_path else None)
        )
        dialog.copy_path_requested.connect(
            lambda: self._copy_to_clipboard(output_path_str)
        )

        dialog.exec()

        # Open folder if requested
        if success and self.open_folder_check.isChecked() and output_path:
            self._open_folder(output_path.parent)

    @Slot(str)
    def _on_merge_error(self, error_message: str):
        """Handle merge error."""
        if hasattr(self, 'progress_dialog'):
            self.progress_dialog.close()

        QMessageBox.critical(
            self,
            "Merge Error",
            f"An error occurred during merge:\n\n{error_message}"
        )
        logger.error(f"Merge error: {error_message}")

    def _open_folder(self, folder_path: Optional[Path]):
        """Open folder in file explorer."""
        if not folder_path:
            return

        try:
            if sys.platform == 'win32':
                os.startfile(str(folder_path))
            elif sys.platform == 'darwin':
                subprocess.run(['open', str(folder_path)])
            else:
                subprocess.run(['xdg-open', str(folder_path)])
        except Exception as e:
            logger.warning(f"Failed to open folder: {e}")

    def _copy_to_clipboard(self, text: str):
        """Copy text to clipboard."""
        clipboard = QApplication.clipboard()
        clipboard.setText(text)
        self.status_bar.showMessage("Path copied to clipboard", 3000)

    def _show_logs(self):
        """Show log viewer dialog."""
        log_path = get_log_path()
        log_content = ""

        if log_path.exists():
            try:
                with open(log_path, 'r', encoding='utf-8') as f:
                    log_content = f.read()
            except Exception:
                log_content = "(Could not read log file)"
        else:
            log_content = "(No log file found)"

        dialog = LogViewerDialog(self, log_content)
        dialog.show()
