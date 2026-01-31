"""
Version information for PDF Consolidator.

This is the single source of truth for the application version.
"""

__version__ = "1.1.0"
__app_name__ = "PDF Consolidator"
__author__ = "Your Organization"
__description__ = "Enterprise-ready desktop application for merging PDF files"


def get_version_tuple():
    """Return version as a tuple of integers."""
    return tuple(int(x) for x in __version__.split("."))


def get_version_string():
    """Return formatted version string."""
    return f"v{__version__}"


def get_full_app_title():
    """Return full application title with version."""
    return f"{__app_name__} {get_version_string()}"
