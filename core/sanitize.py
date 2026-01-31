"""
Log sanitization helpers for PDF Consolidator.

Ensures sensitive information is not logged while maintaining useful debugging info.
"""
import logging
import re
from pathlib import Path
from typing import Any, Dict, Optional


class SanitizedFormatter(logging.Formatter):
    """
    Custom log formatter that sanitizes sensitive information.

    - Redacts potential usernames from paths
    - Never logs file contents
    - Limits path depth in logs
    """

    # Pattern to match Windows user paths
    USER_PATH_PATTERN = re.compile(
        r'([A-Za-z]:\\Users\\)([^\\]+)(\\.*)',
        re.IGNORECASE
    )

    # Pattern to match Unix home paths
    HOME_PATH_PATTERN = re.compile(
        r'(/home/)([^/]+)(/.*)',
        re.IGNORECASE
    )

    def __init__(
        self,
        fmt: Optional[str] = None,
        datefmt: Optional[str] = None,
        redact_usernames: bool = True
    ):
        super().__init__(fmt, datefmt)
        self.redact_usernames = redact_usernames

    def format(self, record: logging.LogRecord) -> str:
        """Format and sanitize log record."""
        # Make a copy of the message to sanitize
        original_msg = record.getMessage()
        sanitized_msg = self._sanitize_message(original_msg)

        # Temporarily replace the message
        record.msg = sanitized_msg
        record.args = ()

        result = super().format(record)

        # Restore original (for other handlers)
        record.msg = original_msg

        return result

    def _sanitize_message(self, message: str) -> str:
        """Sanitize a log message."""
        if self.redact_usernames:
            # Redact Windows user paths
            message = self.USER_PATH_PATTERN.sub(
                r'\1<user>\3',
                message
            )
            # Redact Unix home paths
            message = self.HOME_PATH_PATTERN.sub(
                r'\1<user>\3',
                message
            )

        return message


def setup_logging(
    log_level: int = logging.INFO,
    log_file: Optional[Path] = None,
    redact_usernames: bool = True
) -> logging.Logger:
    """
    Set up application logging with sanitization.

    Args:
        log_level: Logging level
        log_file: Optional file to write logs to
        redact_usernames: Whether to redact usernames from paths

    Returns:
        Configured logger
    """
    logger = logging.getLogger("pdf_consolidator")
    logger.setLevel(log_level)

    # Clear existing handlers
    logger.handlers.clear()

    # Create sanitized formatter
    formatter = SanitizedFormatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        redact_usernames=redact_usernames
    )

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler (if specified)
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


def sanitize_path_for_log(path: Path) -> str:
    """
    Sanitize a path for logging.

    Args:
        path: Path to sanitize

    Returns:
        Sanitized path string
    """
    path_str = str(path)

    # Redact Windows user paths
    path_str = SanitizedFormatter.USER_PATH_PATTERN.sub(
        r'\1<user>\3',
        path_str
    )

    # Redact Unix home paths
    path_str = SanitizedFormatter.HOME_PATH_PATTERN.sub(
        r'\1<user>\3',
        path_str
    )

    return path_str


def safe_log_dict(data: Dict[str, Any], exclude_keys: Optional[set] = None) -> Dict[str, Any]:
    """
    Create a safe copy of a dictionary for logging.

    Args:
        data: Dictionary to sanitize
        exclude_keys: Keys to exclude from output

    Returns:
        Sanitized dictionary
    """
    if exclude_keys is None:
        exclude_keys = {'content', 'data', 'bytes', 'password', 'token', 'secret'}

    result = {}
    for key, value in data.items():
        if key.lower() in exclude_keys:
            result[key] = '<redacted>'
        elif isinstance(value, Path):
            result[key] = sanitize_path_for_log(value)
        elif isinstance(value, str) and len(value) > 1000:
            result[key] = f'<string of length {len(value)}>'
        elif isinstance(value, bytes):
            result[key] = f'<bytes of length {len(value)}>'
        elif isinstance(value, dict):
            result[key] = safe_log_dict(value, exclude_keys)
        else:
            result[key] = value

    return result


# Global logger instance
_logger: Optional[logging.Logger] = None


def get_logger() -> logging.Logger:
    """Get the application logger, initializing if needed."""
    global _logger
    if _logger is None:
        _logger = setup_logging()
    return _logger
