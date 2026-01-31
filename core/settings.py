"""
Settings management for PDF Consolidator.

Stores settings in a JSON file under the user's app data directory.
Designed to never store secrets; provides interface for future token storage.
"""
import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional, Dict, Any, List

from .sanitize import get_logger


# Application name for settings directory
APP_NAME = "PDFConsolidator"


def get_app_data_dir() -> Path:
    """
    Get the application data directory.

    Returns:
        Path to app data directory (created if doesn't exist)
    """
    if os.name == 'nt':  # Windows
        base = Path(os.environ.get('APPDATA', Path.home() / 'AppData' / 'Roaming'))
    else:  # Unix/Mac
        base = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config'))

    app_dir = base / APP_NAME
    app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir


def get_settings_path() -> Path:
    """Get path to settings file."""
    return get_app_data_dir() / "settings.json"


def get_log_path() -> Path:
    """Get path to log file."""
    return get_app_data_dir() / "app.log"


def get_logs_dir() -> Path:
    """Get path to logs directory."""
    logs_dir = get_app_data_dir() / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    return logs_dir


def get_reports_dir() -> Path:
    """Get path to reports directory."""
    reports_dir = get_app_data_dir() / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    return reports_dir


@dataclass
class AppSettings:
    """
    Application settings.

    All settings are non-sensitive and safe to store in plain JSON.
    IMPORTANT: Passwords are NEVER stored here.
    """

    # Output settings
    output_directory: str = ""  # Empty = same as first input file
    output_filename_template: str = "Merged_{timestamp}.pdf"
    open_folder_after_merge: bool = True

    # Processing settings
    sort_mode: str = "manual"  # manual, filename, modified_time
    include_subfolders: bool = False
    normalize_metadata: bool = True
    generate_summary_report: bool = True

    # Encryption handling (B feature)
    encryption_handling_mode: str = "skip"  # skip, prompt_each, single_password
    # Note: passwords are NEVER stored - only the mode is saved

    # Advanced settings
    enable_file_hashing: bool = False
    remove_duplicates_automatically: bool = False

    # Output safety (D feature)
    restrict_output_directories: bool = False
    allowed_output_directories: List[str] = field(default_factory=list)
    block_removable_drives: bool = False  # Windows only

    # UI settings
    window_width: int = 900
    window_height: int = 700
    show_advanced_options: bool = False

    # Recent paths (for convenience)
    recent_output_directories: List[str] = field(default_factory=list)
    max_recent_directories: int = 5

    # First run tracking
    first_run_shown: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AppSettings':
        """Create settings from dictionary."""
        # Filter to only known fields
        known_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known_fields}
        return cls(**filtered)

    def add_recent_directory(self, directory: str) -> None:
        """Add a directory to recent list."""
        if directory in self.recent_output_directories:
            self.recent_output_directories.remove(directory)
        self.recent_output_directories.insert(0, directory)
        self.recent_output_directories = self.recent_output_directories[:self.max_recent_directories]

    def add_allowed_directory(self, directory: str) -> None:
        """Add a directory to allowed output list."""
        if directory not in self.allowed_output_directories:
            self.allowed_output_directories.append(directory)

    def remove_allowed_directory(self, directory: str) -> None:
        """Remove a directory from allowed output list."""
        if directory in self.allowed_output_directories:
            self.allowed_output_directories.remove(directory)

    def is_output_allowed(self, output_path: Path) -> bool:
        """
        Check if output path is allowed.

        Returns True if:
        - restrict_output_directories is False, OR
        - output_path is within one of the allowed directories
        """
        if not self.restrict_output_directories:
            return True

        if not self.allowed_output_directories:
            return True  # No restrictions if list is empty

        output_resolved = output_path.resolve()
        for allowed in self.allowed_output_directories:
            allowed_path = Path(allowed).resolve()
            try:
                output_resolved.relative_to(allowed_path)
                return True
            except ValueError:
                continue

        return False


class SettingsManager:
    """
    Manages loading and saving application settings.

    Thread-safe for reading; writing should be done from main thread.
    """

    def __init__(self):
        self._settings: Optional[AppSettings] = None
        self._settings_path = get_settings_path()
        self._logger = get_logger()

    @property
    def settings(self) -> AppSettings:
        """Get current settings, loading from file if needed."""
        if self._settings is None:
            self._settings = self.load()
        return self._settings

    def load(self) -> AppSettings:
        """
        Load settings from file.

        Returns:
            Loaded settings, or defaults if file doesn't exist or is invalid
        """
        if not self._settings_path.exists():
            self._logger.info("No settings file found, using defaults")
            return AppSettings()

        try:
            with open(self._settings_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self._logger.info("Settings loaded from file")
            return AppSettings.from_dict(data)
        except (json.JSONDecodeError, IOError) as e:
            self._logger.warning(f"Failed to load settings: {e}, using defaults")
            return AppSettings()

    def save(self, settings: Optional[AppSettings] = None) -> bool:
        """
        Save settings to file.

        Args:
            settings: Settings to save (uses current if None)

        Returns:
            True if saved successfully
        """
        if settings is not None:
            self._settings = settings

        if self._settings is None:
            return False

        try:
            # Ensure directory exists
            self._settings_path.parent.mkdir(parents=True, exist_ok=True)

            with open(self._settings_path, 'w', encoding='utf-8') as f:
                json.dump(self._settings.to_dict(), f, indent=2)

            self._logger.info("Settings saved")
            return True
        except IOError as e:
            self._logger.error(f"Failed to save settings: {e}")
            return False

    def reset_to_defaults(self) -> AppSettings:
        """Reset settings to defaults."""
        self._settings = AppSettings()
        self.save()
        return self._settings


# Token storage interface for future Graph API integration
class TokenStorageInterface:
    """
    Interface for secure token storage (v2 feature).

    Implementation should use OS keychain:
    - Windows: Windows Credential Manager
    - macOS: Keychain
    - Linux: Secret Service API

    NOTE: Not implemented in MVP. This is a design placeholder.
    """

    def store_token(self, service: str, token: str) -> bool:
        """Store a token securely."""
        raise NotImplementedError("Token storage not implemented in MVP")

    def retrieve_token(self, service: str) -> Optional[str]:
        """Retrieve a stored token."""
        raise NotImplementedError("Token storage not implemented in MVP")

    def delete_token(self, service: str) -> bool:
        """Delete a stored token."""
        raise NotImplementedError("Token storage not implemented in MVP")


# Global settings manager instance
_settings_manager: Optional[SettingsManager] = None


def get_settings_manager() -> SettingsManager:
    """Get the global settings manager."""
    global _settings_manager
    if _settings_manager is None:
        _settings_manager = SettingsManager()
    return _settings_manager


def get_settings() -> AppSettings:
    """Get current application settings."""
    return get_settings_manager().settings
