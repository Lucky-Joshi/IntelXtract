"""Logging setup: console + rotating file handler with secret redaction.

Handlers are attached to the ``intelxtract`` logger namespace; modules obtain
loggers via :func:`get_logger`.  Scan identifiers are bound with
:func:`set_scan_context` and rendered in every record.
"""

from __future__ import annotations

import logging
import re
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from logging.handlers import RotatingFileHandler
from pathlib import Path

from core.config import Config

ROOT_LOGGER_NAME = "intelxtract"
_FORMAT = "%(asctime)s %(levelname)-7s %(name)s [scan=%(scan_id)s] %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"

_scan_id: ContextVar[str] = ContextVar("scan_id", default="-")
_setup_lock = threading.Lock()
_is_setup = False

_REDACTION_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._~+/-]+=?"), r"\1 ***REDACTED***"),
    (
        re.compile(
            r"(?i)\b(api[_-]?key|apikey|token|secret|password|passwd|authorization)"
            r"(\s*[=:]\s*)(\S+(?:\s+\S+)?)"
        ),
        r"\1\2***REDACTED***",
    ),
)


class _RedactingFormatter(logging.Formatter):
    """Formatter that masks credential-looking substrings."""

    def format(self, record: logging.LogRecord) -> str:
        rendered = super().format(record)
        for pattern, replacement in _REDACTION_RULES:
            rendered = pattern.sub(replacement, rendered)
        return rendered


class _ScanContextFilter(logging.Filter):
    """Injects the current scan id into every record."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "scan_id"):
            record.scan_id = _scan_id.get()
        return True


def set_scan_context(scan_id: str) -> Token[str]:
    """Bind ``scan_id`` to the current context; returns a reset token."""
    return _scan_id.set(scan_id)


def reset_scan_context(token: Token[str]) -> None:
    """Restore the scan context to its previous value."""
    _scan_id.reset(token)


@contextmanager
def scan_context(scan_id: str) -> Iterator[None]:
    """Context manager form of :func:`set_scan_context`."""
    token = set_scan_context(scan_id)
    try:
        yield
    finally:
        reset_scan_context(token)


def get_logger(name: str) -> logging.Logger:
    """Return a logger under the ``intelxtract`` namespace.

    ``get_logger(__name__)`` from ``core.engine`` yields
    ``intelxtract.core.engine``.
    """
    clean = name.removeprefix(ROOT_LOGGER_NAME).lstrip(".")
    return logging.getLogger(f"{ROOT_LOGGER_NAME}.{clean}")


def setup_logging(config: Config, *, force: bool = False) -> None:
    """Configure console and file handlers from config (idempotent).

    Set ``force=True`` to reconfigure (used by tests and ``doctor``).
    """
    global _is_setup

    with _setup_lock:
        root = logging.getLogger(ROOT_LOGGER_NAME)
        if _is_setup and not force:
            return
        for handler in list(root.handlers):
            root.removeHandler(handler)
            handler.close()

        level_name = str(config.get("logging.level", "INFO")).upper()
        level = getattr(logging, level_name, logging.INFO)
        root.setLevel(level)
        root.propagate = False

        formatter = _RedactingFormatter(_FORMAT, datefmt=_DATEFMT)
        context_filter = _ScanContextFilter()

        if config.get("logging.console", True):
            stream = logging.StreamHandler()
            stream.setFormatter(formatter)
            stream.addFilter(context_filter)
            root.addHandler(stream)

        file_setting = config.get("logging.file")
        if file_setting:
            file_path = Path(str(file_setting)).expanduser()
            try:
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_handler = RotatingFileHandler(
                    file_path,
                    maxBytes=int(config.get("logging.max_bytes", 1_048_576)),
                    backupCount=int(config.get("logging.backup_count", 3)),
                    encoding="utf-8",
                )
            except OSError:
                root.error("cannot open log file %s; file logging disabled", file_path)
            else:
                file_handler.setFormatter(formatter)
                file_handler.addFilter(context_filter)
                root.addHandler(file_handler)

        _is_setup = True


def shutdown_logging() -> None:
    """Close and detach all handlers (used by tests and app shutdown)."""
    global _is_setup
    with _setup_lock:
        root = logging.getLogger(ROOT_LOGGER_NAME)
        for handler in list(root.handlers):
            root.removeHandler(handler)
            handler.close()
        _is_setup = False
