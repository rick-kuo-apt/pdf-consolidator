#!/usr/bin/env python3
"""
PDF Consolidator - Enterprise PDF Merging Application

A desktop application for merging multiple PDF files into a single
consolidated document with a clean, modern UI.

Usage:
    python app.py

Author: PDF Consolidator Team
License: MIT
"""
import sys
import logging
from pathlib import Path

# Ensure the package can be imported when running directly
if __name__ == "__main__":
    # Add parent directory to path for direct execution
    parent = Path(__file__).parent.parent
    if str(parent) not in sys.path:
        sys.path.insert(0, str(parent))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QPalette, QColor

from pdf_consolidator.core.sanitize import setup_logging
from pdf_consolidator.core.settings import get_app_data_dir, get_log_path
from pdf_consolidator.ui.main_window import MainWindow


def configure_high_dpi():
    """Configure high DPI settings for crisp rendering."""
    # Enable high DPI scaling
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )


def configure_logging():
    """Set up application logging."""
    log_path = get_log_path()

    # Ensure log directory exists
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Configure logging with sanitization
    logger = setup_logging(
        log_level=logging.INFO,
        log_file=log_path,
        redact_usernames=True
    )

    return logger


def create_application() -> QApplication:
    """Create and configure the Qt application."""
    app = QApplication(sys.argv)

    # Set application metadata
    app.setApplicationName("PDF Consolidator")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("PDFConsolidator")
    app.setOrganizationDomain("pdfconsolidator.local")

    # Set default font
    font = QFont("Segoe UI", 10)
    app.setFont(font)

    # Apply modern styling
    app.setStyle("Fusion")

    return app


def main():
    """Main entry point for the application."""
    # Configure high DPI before creating application
    configure_high_dpi()

    # Set up logging
    logger = configure_logging()
    logger.info("=" * 50)
    logger.info("PDF Consolidator starting...")
    logger.info(f"Python version: {sys.version}")
    logger.info(f"App data directory: {get_app_data_dir()}")

    # Create Qt application
    app = create_application()

    # Create and show main window
    window = MainWindow()
    window.show()

    logger.info("Main window displayed")

    # Run event loop
    try:
        exit_code = app.exec()
    except Exception as e:
        logger.exception("Unhandled exception in event loop")
        exit_code = 1

    logger.info(f"Application exiting with code {exit_code}")
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
