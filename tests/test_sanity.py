"""Smoke tests for the toolchain and repository layout (Phase 1 gate)."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

REQUIRED_DIRS = (
    "app",
    "assets",
    "cache",
    "cli",
    "config",
    "core",
    "database",
    "docs",
    "docs/brand",
    "examples",
    "exports",
    "gui",
    "logs",
    "modules",
    "modules/archive",
    "modules/domain",
    "modules/email",
    "modules/ip",
    "modules/metadata",
    "modules/news",
    "modules/username",
    "modules/website",
    "plugins",
    "reports",
    "scripts",
    "templates",
    "tests",
)

REQUIRED_FILES = (
    "README.md",
    "LICENSE",
    "CONTRIBUTING.md",
    "CODE_OF_CONDUCT.md",
    "CHANGELOG.md",
    "SECURITY.md",
    "ROADMAP.md",
    "pyproject.toml",
    "requirements.txt",
    "requirements-dev.txt",
    ".gitignore",
    "docs/Phase_Plan.md",
    "docs/Development_Plan.md",
    "docs/brand/BRAND.md",
    "docs/coding_standards.md",
    "docs/git_workflow.md",
    "docs/threat_model.md",
    "docs/privacy.md",
    "assets/logo.svg",
    "assets/icon.svg",
)


def test_python_version() -> None:
    """The project targets Python 3.13 or newer."""
    assert sys.version_info >= (3, 13), (
        f"Python 3.13+ required, running "
        f"{sys.version_info.major}.{sys.version_info.minor}"
    )


def test_repo_layout() -> None:
    """The folder architecture from Phase 0 is intact."""
    missing = [d for d in REQUIRED_DIRS if not (REPO_ROOT / d).is_dir()]
    assert not missing, f"Missing directories: {missing}"


def test_required_files_present() -> None:
    """Foundation documents and assets from Phases 0-1 exist and are non-empty."""
    missing = [
        f
        for f in REQUIRED_FILES
        if not (REPO_ROOT / f).is_file() or (REPO_ROOT / f).stat().st_size == 0
    ]
    assert not missing, f"Missing or empty files: {missing}"


def test_license_is_gpl3() -> None:
    """The repository license is GNU GPL v3 (Phase 1 decision)."""
    license_text = (REPO_ROOT / "LICENSE").read_text(encoding="utf-8", errors="ignore")
    assert "GNU GENERAL PUBLIC LICENSE" in license_text
    assert "Version 3, 29 June 2007" in license_text
