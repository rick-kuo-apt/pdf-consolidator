"""
Reusable UI widgets for PDF Consolidator.
"""
from pathlib import Path
from typing import Optional, List

from PySide6.QtCore import Qt, Signal, QMimeData
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QPainter, QColor, QPen, QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QDialog, QDialogButtonBox, QTextEdit, QLineEdit, QFormLayout,
    QMessageBox, QProgressBar, QFrame, QSizePolicy, QRadioButton,
    QButtonGroup, QGroupBox, QListWidget, QListWidgetItem, QCheckBox
)


class DropZone(QFrame):
    """
    A widget that accepts drag-and-drop of files and folders.

    Emits signals when files or folders are dropped.
    """

    files_dropped = Signal(list)  # List of file paths
    folders_dropped = Signal(list)  # List of folder paths
    clicked = Signal()  # Emitted when zone is clicked

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setMinimumHeight(120)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._setup_ui()
        self._dragging = False

    def _setup_ui(self):
        """Set up the drop zone appearance."""
        self.setStyleSheet("""
            DropZone {
                background-color: #f8f9fa;
                border: 2px dashed #dee2e6;
                border-radius: 8px;
            }
            DropZone:hover {
                border-color: #6c757d;
                background-color: #e9ecef;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)

        # Icon/label
        self.icon_label = QLabel("📄")
        self.icon_label.setStyleSheet("font-size: 32px; border: none; background: transparent;")
        self.icon_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.icon_label)

        # Main text
        self.main_label = QLabel("Drop PDF files here")
        self.main_label.setStyleSheet("""
            font-size: 16px;
            font-weight: bold;
            color: #495057;
            border: none;
            background: transparent;
        """)
        self.main_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.main_label)

        # Sub text
        self.sub_label = QLabel("or click to browse")
        self.sub_label.setStyleSheet("""
            font-size: 12px;
            color: #6c757d;
            border: none;
            background: transparent;
        """)
        self.sub_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.sub_label)

    def mousePressEvent(self, event):
        """Handle mouse click to trigger file browser."""
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent):
        """Handle drag enter events."""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._dragging = True
            self.setStyleSheet("""
                DropZone {
                    background-color: #e7f5ff;
                    border: 2px dashed #339af0;
                    border-radius: 8px;
                }
            """)
            self.main_label.setText("Release to add files")

    def dragLeaveEvent(self, event):
        """Handle drag leave events."""
        self._dragging = False
        self._setup_ui()
        self.main_label.setText("Drop PDF files here")

    def dropEvent(self, event: QDropEvent):
        """Handle drop events."""
        self._dragging = False
        self._setup_ui()
        self.main_label.setText("Drop PDF files here")

        files: List[Path] = []
        folders: List[Path] = []

        for url in event.mimeData().urls():
            path = Path(url.toLocalFile())
            if path.is_dir():
                folders.append(path)
            elif path.is_file():
                files.append(path)

        if files:
            self.files_dropped.emit([str(f) for f in files])
        if folders:
            self.folders_dropped.emit([str(f) for f in folders])

        event.acceptProposedAction()


class ProgressDialog(QDialog):
    """
    Progress dialog for merge operations.
    """

    cancelled = Signal()

    def __init__(self, parent: Optional[QWidget] = None, title: str = "Processing..."):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(400)
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowContextHelpButtonHint
        )
        self._setup_ui()

    def _setup_ui(self):
        """Set up the dialog UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Status label
        self.status_label = QLabel("Preparing...")
        self.status_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(self.status_label)

        # File label
        self.file_label = QLabel("")
        self.file_label.setStyleSheet("color: #666;")
        layout.addWidget(self.file_label)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        # Cancel button
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self._on_cancel)
        button_layout.addWidget(self.cancel_button)
        layout.addLayout(button_layout)

    def _on_cancel(self):
        """Handle cancel button click."""
        self.cancel_button.setEnabled(False)
        self.cancel_button.setText("Cancelling...")
        self.cancelled.emit()

    def update_progress(self, percent: float, status: str, current_file: str = ""):
        """Update the progress display."""
        self.progress_bar.setValue(int(percent))
        self.status_label.setText(status)
        if current_file:
            # Truncate long filenames
            if len(current_file) > 50:
                current_file = "..." + current_file[-47:]
            self.file_label.setText(current_file)

    def set_complete(self):
        """Mark operation as complete."""
        self.progress_bar.setValue(100)
        self.status_label.setText("Complete!")
        self.cancel_button.setText("Close")
        self.cancel_button.setEnabled(True)
        self.cancel_button.clicked.disconnect()
        self.cancel_button.clicked.connect(self.accept)


class SummaryDialog(QDialog):
    """
    Dialog showing merge operation summary.
    """

    open_folder_requested = Signal()
    copy_path_requested = Signal()

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        success: bool = True,
        merged_count: int = 0,
        skipped_count: int = 0,
        error_count: int = 0,
        total_pages: int = 0,
        output_path: str = "",
        output_size: str = "",
        duration: str = ""
    ):
        super().__init__(parent)
        self.setWindowTitle("Merge Complete" if success else "Merge Failed")
        self.setModal(True)
        self.setMinimumWidth(450)
        self.output_path = output_path
        self._setup_ui(
            success, merged_count, skipped_count, error_count,
            total_pages, output_path, output_size, duration
        )

    def _setup_ui(
        self,
        success: bool,
        merged_count: int,
        skipped_count: int,
        error_count: int,
        total_pages: int,
        output_path: str,
        output_size: str,
        duration: str
    ):
        """Set up the dialog UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        # Header
        if success:
            icon = "✅"
            title = "Merge Successful"
            header_color = "#28a745"
        else:
            icon = "❌"
            title = "Merge Failed"
            header_color = "#dc3545"

        header = QLabel(f"{icon}  {title}")
        header.setStyleSheet(f"""
            font-size: 18px;
            font-weight: bold;
            color: {header_color};
        """)
        layout.addWidget(header)

        # Stats
        stats_text = f"""
        <table style="margin-left: 10px;">
            <tr><td style="padding-right: 20px;">Files merged:</td><td><b>{merged_count}</b></td></tr>
            <tr><td>Files skipped:</td><td>{skipped_count}</td></tr>
            <tr><td>Errors:</td><td>{error_count}</td></tr>
            <tr><td>Total pages:</td><td>{total_pages}</td></tr>
            <tr><td>Output size:</td><td>{output_size}</td></tr>
            <tr><td>Duration:</td><td>{duration}</td></tr>
        </table>
        """
        stats_label = QLabel(stats_text)
        stats_label.setTextFormat(Qt.RichText)
        layout.addWidget(stats_label)

        # Output path
        if output_path:
            path_group = QFrame()
            path_group.setStyleSheet("""
                QFrame {
                    background-color: #f8f9fa;
                    border: 1px solid #dee2e6;
                    border-radius: 4px;
                    padding: 8px;
                }
            """)
            path_layout = QVBoxLayout(path_group)
            path_layout.setContentsMargins(8, 8, 8, 8)

            path_title = QLabel("Output file:")
            path_title.setStyleSheet("font-weight: bold; border: none; background: transparent;")
            path_layout.addWidget(path_title)

            # Truncate path for display
            display_path = output_path
            if len(display_path) > 60:
                display_path = "..." + display_path[-57:]

            path_value = QLabel(display_path)
            path_value.setStyleSheet("color: #495057; border: none; background: transparent;")
            path_value.setWordWrap(True)
            path_layout.addWidget(path_value)

            layout.addWidget(path_group)

        # Buttons
        button_layout = QHBoxLayout()

        if success and output_path:
            open_folder_btn = QPushButton("Open Folder")
            open_folder_btn.clicked.connect(self._on_open_folder)
            button_layout.addWidget(open_folder_btn)

            copy_path_btn = QPushButton("Copy Path")
            copy_path_btn.clicked.connect(self._on_copy_path)
            button_layout.addWidget(copy_path_btn)

        button_layout.addStretch()

        close_btn = QPushButton("Close")
        close_btn.setDefault(True)
        close_btn.clicked.connect(self.accept)
        button_layout.addWidget(close_btn)

        layout.addLayout(button_layout)

    def _on_open_folder(self):
        """Handle open folder button click."""
        self.open_folder_requested.emit()

    def _on_copy_path(self):
        """Handle copy path button click."""
        self.copy_path_requested.emit()


class PasswordDialog(QDialog):
    """
    Dialog for entering PDF password.
    """

    RESULT_OK = QDialog.Accepted
    RESULT_CANCEL = QDialog.Rejected
    RESULT_SKIP = 2

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        filename: str = "",
        show_use_for_all: bool = False
    ):
        super().__init__(parent)
        self.setWindowTitle("Password Required")
        self.setModal(True)
        self.setMinimumWidth(350)
        self.use_for_all = False
        self._setup_ui(filename, show_use_for_all)

    def _setup_ui(self, filename: str, show_use_for_all: bool):
        """Set up the dialog UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Header
        header = QLabel("🔒  This PDF is password protected")
        header.setStyleSheet("font-weight: bold;")
        layout.addWidget(header)

        # Filename
        if filename:
            file_label = QLabel(f"File: {filename}")
            file_label.setStyleSheet("color: #666;")
            file_label.setWordWrap(True)
            layout.addWidget(file_label)

        # Password input
        form = QFormLayout()
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setPlaceholderText("Enter password")
        form.addRow("Password:", self.password_input)
        layout.addLayout(form)

        # Use for all checkbox
        if show_use_for_all:
            self.use_for_all_check = QCheckBox("Use this password for all encrypted PDFs")
            layout.addWidget(self.use_for_all_check)
        else:
            self.use_for_all_check = None

        # Buttons
        button_layout = QHBoxLayout()

        skip_btn = QPushButton("Skip File")
        skip_btn.clicked.connect(self._on_skip)
        button_layout.addWidget(skip_btn)

        button_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        ok_btn = QPushButton("OK")
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self.accept)
        button_layout.addWidget(ok_btn)

        layout.addLayout(button_layout)

        # Connect enter key
        self.password_input.returnPressed.connect(self.accept)

    def _on_skip(self):
        """Handle skip button."""
        self.done(self.RESULT_SKIP)

    def accept(self):
        """Handle OK button."""
        if self.use_for_all_check:
            self.use_for_all = self.use_for_all_check.isChecked()
        super().accept()

    def get_password(self) -> str:
        """Get the entered password."""
        return self.password_input.text()


class LogViewerDialog(QDialog):
    """
    Dialog for viewing and copying logs.
    """

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        log_content: str = ""
    ):
        super().__init__(parent)
        self.setWindowTitle("Application Logs")
        self.setModal(False)
        self.setMinimumSize(600, 400)
        self.log_content = log_content
        self._setup_ui()

    def _setup_ui(self):
        """Set up the dialog UI."""
        layout = QVBoxLayout(self)

        # Log text area
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 9))
        self.log_text.setPlainText(self.log_content)
        layout.addWidget(self.log_text)

        # Buttons
        button_layout = QHBoxLayout()

        copy_btn = QPushButton("Copy to Clipboard")
        copy_btn.clicked.connect(self._on_copy)
        button_layout.addWidget(copy_btn)

        button_layout.addStretch()

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        button_layout.addWidget(close_btn)

        layout.addLayout(button_layout)

    def _on_copy(self):
        """Copy logs to clipboard."""
        from PySide6.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        clipboard.setText(self.log_content)
        QMessageBox.information(self, "Copied", "Logs copied to clipboard.")

    def set_log_content(self, content: str):
        """Update log content."""
        self.log_content = content
        self.log_text.setPlainText(content)


class DuplicateDialog(QDialog):
    """
    Dialog for handling duplicate files.
    """

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        duplicates: List[str] = None
    ):
        super().__init__(parent)
        self.setWindowTitle("Duplicate Files Found")
        self.setModal(True)
        self.setMinimumWidth(400)
        self.duplicates = duplicates or []
        self.keep_duplicates = False
        self._setup_ui()

    def _setup_ui(self):
        """Set up the dialog UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Header
        header = QLabel(f"⚠️  {len(self.duplicates)} duplicate file(s) detected")
        header.setStyleSheet("font-weight: bold;")
        layout.addWidget(header)

        # Description
        desc = QLabel(
            "The following files appear more than once in the queue.\n"
            "Would you like to keep or remove the duplicates?"
        )
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # File list
        if len(self.duplicates) <= 5:
            for dup in self.duplicates:
                label = QLabel(f"  • {dup}")
                label.setStyleSheet("color: #666;")
                layout.addWidget(label)
        else:
            label = QLabel(f"  • {self.duplicates[0]}")
            label.setStyleSheet("color: #666;")
            layout.addWidget(label)
            more = QLabel(f"  ... and {len(self.duplicates) - 1} more")
            more.setStyleSheet("color: #999;")
            layout.addWidget(more)

        # Buttons
        button_layout = QHBoxLayout()

        keep_btn = QPushButton("Keep Duplicates")
        keep_btn.clicked.connect(self._on_keep)
        button_layout.addWidget(keep_btn)

        remove_btn = QPushButton("Remove Duplicates")
        remove_btn.setDefault(True)
        remove_btn.clicked.connect(self._on_remove)
        button_layout.addWidget(remove_btn)

        layout.addLayout(button_layout)

    def _on_keep(self):
        """Keep duplicates."""
        self.keep_duplicates = True
        self.accept()

    def _on_remove(self):
        """Remove duplicates."""
        self.keep_duplicates = False
        self.accept()


class OutputConflictDialog(QDialog):
    """
    Dialog for handling output file conflicts.
    """

    OVERWRITE = 1
    AUTO_RENAME = 2
    CANCEL = 0

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        output_path: str = ""
    ):
        super().__init__(parent)
        self.setWindowTitle("Output File Exists")
        self.setModal(True)
        self.setMinimumWidth(450)
        self.choice = self.CANCEL
        self._setup_ui(output_path)

    def _setup_ui(self, output_path: str):
        """Set up the dialog UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Header
        header = QLabel("⚠️  Output file already exists")
        header.setStyleSheet("font-weight: bold;")
        layout.addWidget(header)

        # Path display
        if output_path:
            path_label = QLabel(f"File: {Path(output_path).name}")
            path_label.setStyleSheet("color: #666;")
            layout.addWidget(path_label)

        # Description
        desc = QLabel("What would you like to do?")
        layout.addWidget(desc)

        # Buttons
        button_layout = QHBoxLayout()

        overwrite_btn = QPushButton("Overwrite")
        overwrite_btn.clicked.connect(self._on_overwrite)
        button_layout.addWidget(overwrite_btn)

        rename_btn = QPushButton("Auto-rename (_01, _02...)")
        rename_btn.setDefault(True)
        rename_btn.clicked.connect(self._on_rename)
        button_layout.addWidget(rename_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        layout.addLayout(button_layout)

    def _on_overwrite(self):
        """Handle overwrite choice."""
        self.choice = self.OVERWRITE
        self.accept()

    def _on_rename(self):
        """Handle auto-rename choice."""
        self.choice = self.AUTO_RENAME
        self.accept()


class AllowedDirectoriesDialog(QDialog):
    """
    Dialog for managing allowed output directories.
    """

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        directories: List[str] = None
    ):
        super().__init__(parent)
        self.setWindowTitle("Allowed Output Directories")
        self.setModal(True)
        self.setMinimumSize(500, 300)
        self.directories = list(directories) if directories else []
        self._setup_ui()

    def _setup_ui(self):
        """Set up the dialog UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Description
        desc = QLabel(
            "When enabled, merged PDFs can only be saved to these directories.\n"
            "Leave empty to allow all directories."
        )
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # List widget
        self.list_widget = QListWidget()
        for d in self.directories:
            self.list_widget.addItem(d)
        layout.addWidget(self.list_widget)

        # Add/Remove buttons
        btn_row = QHBoxLayout()

        add_btn = QPushButton("Add Folder...")
        add_btn.clicked.connect(self._on_add)
        btn_row.addWidget(add_btn)

        remove_btn = QPushButton("Remove Selected")
        remove_btn.clicked.connect(self._on_remove)
        btn_row.addWidget(remove_btn)

        btn_row.addStretch()
        layout.addLayout(btn_row)

        # Dialog buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_add(self):
        """Add a directory."""
        from PySide6.QtWidgets import QFileDialog
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Allowed Directory"
        )
        if folder and folder not in self.directories:
            self.directories.append(folder)
            self.list_widget.addItem(folder)

    def _on_remove(self):
        """Remove selected directory."""
        current = self.list_widget.currentRow()
        if current >= 0:
            self.directories.pop(current)
            self.list_widget.takeItem(current)

    def get_directories(self) -> List[str]:
        """Get the list of allowed directories."""
        return self.directories


class SupportBundleDialog(QDialog):
    """
    Dialog for creating and exporting support bundles.
    """

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        bundle_info: dict = None
    ):
        super().__init__(parent)
        self.setWindowTitle("Export Support Bundle")
        self.setModal(True)
        self.setMinimumWidth(450)
        self.bundle_info = bundle_info or {}
        self._setup_ui()

    def _setup_ui(self):
        """Set up the dialog UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Header
        header = QLabel("📦  Create Support Bundle")
        header.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(header)

        # Description
        desc = QLabel(
            "Creates a ZIP file containing:\n"
            "  • Application settings\n"
            "  • Log files (sanitized)\n"
            "  • Recent merge reports\n\n"
            "This bundle does NOT include:\n"
            "  • PDF files\n"
            "  • Passwords or sensitive data\n"
            "  • Unsanitized file paths"
        )
        desc.setStyleSheet("color: #666;")
        layout.addWidget(desc)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        export_btn = QPushButton("Export Bundle...")
        export_btn.setDefault(True)
        export_btn.clicked.connect(self.accept)
        button_layout.addWidget(export_btn)

        layout.addLayout(button_layout)


class AboutDialog(QDialog):
    """
    About / Support dialog showing app info and quick actions.
    """

    open_logs_requested = Signal()
    open_settings_requested = Signal()
    export_bundle_requested = Signal()

    def __init__(
        self,
        parent: Optional[QWidget],
        version: str,
        settings_path: str,
        logs_path: str,
        build_info: Optional[str] = None
    ):
        super().__init__(parent)
        self.setWindowTitle("About PDF Consolidator")
        self.setFixedWidth(480)
        self._setup_ui(version, settings_path, logs_path, build_info)

    def _setup_ui(
        self,
        version: str,
        settings_path: str,
        logs_path: str,
        build_info: Optional[str]
    ):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        # Header
        header = QLabel(f"<h2>PDF Consolidator</h2>")
        header.setAlignment(Qt.AlignCenter)
        layout.addWidget(header)

        version_label = QLabel(f"<b>Version {version}</b>")
        version_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(version_label)

        # Description
        desc = QLabel(
            "Merge multiple PDF files into a single document.\n"
            "100% offline - no data is uploaded anywhere."
        )
        desc.setAlignment(Qt.AlignCenter)
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #555; margin: 8px 0;")
        layout.addWidget(desc)

        # Separator
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("background-color: #ddd;")
        layout.addWidget(line)

        # Storage info section
        storage_group = QGroupBox("Local Storage")
        storage_layout = QFormLayout(storage_group)
        storage_layout.setSpacing(8)

        settings_label = QLabel(f"<code>{settings_path}</code>")
        settings_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        settings_label.setWordWrap(True)
        storage_layout.addRow("Settings:", settings_label)

        logs_label = QLabel(f"<code>{logs_path}</code>")
        logs_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        logs_label.setWordWrap(True)
        storage_layout.addRow("Logs:", logs_label)

        layout.addWidget(storage_group)

        # Privacy note
        privacy = QLabel(
            "<b>Privacy:</b> No telemetry, no network calls. "
            "Passwords are never saved to disk."
        )
        privacy.setWordWrap(True)
        privacy.setStyleSheet("color: #2e7d32; padding: 8px; background: #e8f5e9; border-radius: 4px;")
        layout.addWidget(privacy)

        # Build info (if available)
        if build_info:
            build_label = QLabel(f"<small>{build_info}</small>")
            build_label.setAlignment(Qt.AlignCenter)
            build_label.setStyleSheet("color: #888;")
            layout.addWidget(build_label)

        # Action buttons
        actions_group = QGroupBox("Support")
        actions_layout = QVBoxLayout(actions_group)

        btn_row1 = QHBoxLayout()

        logs_btn = QPushButton("Open Logs Folder")
        logs_btn.clicked.connect(self._on_open_logs)
        btn_row1.addWidget(logs_btn)

        settings_btn = QPushButton("Open Settings Folder")
        settings_btn.clicked.connect(self._on_open_settings)
        btn_row1.addWidget(settings_btn)

        actions_layout.addLayout(btn_row1)

        bundle_btn = QPushButton("Export Support Bundle...")
        bundle_btn.setStyleSheet("font-weight: bold;")
        bundle_btn.clicked.connect(self._on_export_bundle)
        actions_layout.addWidget(bundle_btn)

        bundle_note = QLabel(
            "<small>Creates a ZIP with sanitized logs for troubleshooting. "
            "No PDFs or passwords included.</small>"
        )
        bundle_note.setWordWrap(True)
        bundle_note.setStyleSheet("color: #666;")
        actions_layout.addWidget(bundle_note)

        layout.addWidget(actions_group)

        # Close button
        close_btn = QPushButton("Close")
        close_btn.setDefault(True)
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignCenter)

    def _on_open_logs(self):
        self.open_logs_requested.emit()

    def _on_open_settings(self):
        self.open_settings_requested.emit()

    def _on_export_bundle(self):
        self.export_bundle_requested.emit()
        self.accept()
