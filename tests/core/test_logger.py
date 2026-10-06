"""Logging setup, redaction, and scan-context tests."""

import logging
from collections.abc import Iterator
from pathlib import Path

import pytest

from core.config import Config
from core.logger import (
    ROOT_LOGGER_NAME,
    get_logger,
    scan_context,
    setup_logging,
    shutdown_logging,
)


@pytest.fixture(autouse=True)
def _clean_logging() -> Iterator[None]:
    shutdown_logging()
    yield
    shutdown_logging()


def _config(tmp_path: Path, **overrides: object) -> Config:
    cfg = Config(tmp_path / "settings.json", use_env=False)
    cfg.set("logging.file", str(tmp_path / "logs" / "ix.log"))
    cfg.set("logging.console", False)
    for key, value in overrides.items():
        cfg.set(key, value)
    return cfg


def test_file_logging(tmp_path: Path) -> None:
    cfg = _config(tmp_path)
    setup_logging(cfg)
    get_logger("tests").info("hello world")
    log_file = tmp_path / "logs" / "ix.log"
    content = log_file.read_text(encoding="utf-8")
    assert "hello world" in content
    assert "INFO" in content
    assert "[scan=-]" in content


def test_secret_redaction_in_file(tmp_path: Path) -> None:
    cfg = _config(tmp_path)
    setup_logging(cfg)
    log = get_logger("tests")
    log.info("connecting with api_key=sk-abc123secret")
    log.info("header Authorization: Bearer eyJhbGciOi.payload")
    log.info("password: hunter2 leaked")
    content = (tmp_path / "logs" / "ix.log").read_text(encoding="utf-8")
    assert "sk-abc123secret" not in content
    assert "eyJhbGciOi.payload" not in content
    assert "hunter2" not in content
    assert "***REDACTED***" in content


def test_scan_context_binding(tmp_path: Path) -> None:
    cfg = _config(tmp_path)
    setup_logging(cfg)
    log = get_logger("tests")
    with scan_context("abc123def456"):
        log.info("inside scan")
    log.info("outside scan")
    content = (tmp_path / "logs" / "ix.log").read_text(encoding="utf-8")
    lines = [line for line in content.splitlines() if "scan=" in line]
    inside = [line for line in lines if "inside scan" in line]
    outside = [line for line in lines if "outside scan" in line]
    assert all("[scan=abc123def456]" in line for line in inside)
    assert all("[scan=-]" in line for line in outside)


def test_setup_is_idempotent_without_force(tmp_path: Path) -> None:
    cfg = _config(tmp_path)
    setup_logging(cfg)
    setup_logging(cfg)  # second call is a no-op
    root = logging.getLogger(ROOT_LOGGER_NAME)
    assert len(root.handlers) <= 1


def test_force_reconfigure(tmp_path: Path) -> None:
    cfg = _config(tmp_path, **{"logging.level": "INFO"})
    setup_logging(cfg)
    cfg.set("logging.level", "DEBUG")
    setup_logging(cfg, force=True)
    root = logging.getLogger(ROOT_LOGGER_NAME)
    assert root.level == logging.DEBUG
    assert len(root.handlers) == 1


def test_level_from_config(tmp_path: Path) -> None:
    cfg = _config(tmp_path, **{"logging.level": "WARNING"})
    setup_logging(cfg)
    log = get_logger("tests")
    log.info("suppressed")
    log.warning("kept")
    content = (tmp_path / "logs" / "ix.log").read_text(encoding="utf-8")
    assert "suppressed" not in content
    assert "kept" in content


def test_get_logger_namespacing() -> None:
    assert get_logger("core.engine").name == "intelxtract.core.engine"
    assert get_logger("__main__").name == "intelxtract.__main__"
    assert get_logger("intelxtract.core.engine").name == "intelxtract.core.engine"
