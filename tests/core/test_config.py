"""Layered configuration tests."""

import json
from pathlib import Path
from typing import Any

import pytest

from core.config import DEFAULTS, Config
from core.exceptions import ConfigError


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


def test_defaults_loaded(tmp_path: Path) -> None:
    cfg = Config(tmp_path / "settings.json", use_env=False)
    assert cfg.get("scan.max_workers") == DEFAULTS["scan"]["max_workers"]
    assert cfg.get("logging.level") == "INFO"
    assert cfg.get("cache.enabled") is True


def test_missing_key_returns_default(tmp_path: Path) -> None:
    cfg = Config(tmp_path / "settings.json", use_env=False)
    assert cfg.get("does.not.exist") is None
    assert cfg.get("does.not.exist", 42) == 42


def test_file_layer_overrides_defaults(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    _write_json(path, {"scan": {"max_workers": 3}, "logging": {"level": "DEBUG"}})
    cfg = Config(path, use_env=False)
    assert cfg.get("scan.max_workers") == 3
    assert cfg.get("logging.level") == "DEBUG"
    # untouched defaults survive the merge
    assert cfg.get("scan.default_timeout") == DEFAULTS["scan"]["default_timeout"]


def test_env_layer_overrides_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "settings.json"
    _write_json(path, {"scan": {"max_workers": 3}})
    monkeypatch.setenv("INTELXTRACT_SCAN__MAX_WORKERS", "16")
    monkeypatch.setenv("INTELXTRACT_LOGGING__LEVEL", "DEBUG")
    cfg = Config(path)
    assert cfg.get("scan.max_workers") == 16
    assert cfg.get("logging.level") == "DEBUG"
    assert cfg.get("scan.default_timeout") == 30.0


def test_env_config_path_not_treated_as_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("INTELXTRACT_CONFIG_PATH", str(tmp_path / "other.json"))
    cfg = Config()
    assert cfg.get("config_path") is None
    assert cfg.path == tmp_path / "other.json"


def test_set_save_reload_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    cfg = Config(path, use_env=False)
    cfg.set("scan.max_workers", 12)
    cfg.set("network.user_agent", "TestUA/1.0")
    cfg.save()
    reloaded = Config(path, use_env=False)
    assert reloaded.get("scan.max_workers") == 12
    assert reloaded.get("network.user_agent") == "TestUA/1.0"


def test_set_coerces_string_to_existing_type(tmp_path: Path) -> None:
    cfg = Config(tmp_path / "settings.json", use_env=False)
    cfg.set("scan.max_workers", "6")
    assert cfg.get("scan.max_workers") == 6
    cfg.set("cache.enabled", "false")
    assert cfg.get("cache.enabled") is False


def test_unset(tmp_path: Path) -> None:
    cfg = Config(tmp_path / "settings.json", use_env=False)
    cfg.set("custom.flag", True)
    cfg.unset("custom.flag")
    assert cfg.get("custom.flag") is None
    with pytest.raises(ConfigError):
        cfg.unset("custom.flag")
    with pytest.raises(ConfigError):
        cfg.unset("never.existed")


def test_invalid_key_raises(tmp_path: Path) -> None:
    cfg = Config(tmp_path / "settings.json", use_env=False)
    with pytest.raises(ConfigError):
        cfg.get("..bad")
    with pytest.raises(ConfigError):
        cfg.set("", 1)


def test_section_and_as_dict_are_copies(tmp_path: Path) -> None:
    cfg = Config(tmp_path / "settings.json", use_env=False)
    section = cfg.section("scan")
    section["max_workers"] = 999
    assert cfg.get("scan.max_workers") != 999
    whole = cfg.as_dict()
    whole["scan"]["max_workers"] = 111
    assert cfg.get("scan.max_workers") != 111


def test_section_rejects_non_object(tmp_path: Path) -> None:
    cfg = Config(tmp_path / "settings.json", use_env=False)
    with pytest.raises(ConfigError):
        cfg.section("scan.max_workers")


def test_corrupt_file_raises_config_error(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ConfigError):
        Config(path, use_env=False)


def test_non_object_file_raises(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(ConfigError):
        Config(path, use_env=False)
