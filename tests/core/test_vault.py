"""API-key vault tests (Phase 24, S24.1/S24.5)."""

from __future__ import annotations

import json
import stat
from pathlib import Path
from typing import Any

import pytest
from cryptography.fernet import Fernet

from core.config import Config
from core.exceptions import VaultError
from core.vault import (
    Vault,
    delete_key,
    get_key,
    hydrate_api_keys,
    list_stored,
    mask,
    resolve_key,
    store_key,
    validate_provider,
)


def _config(tmp_path: Path, *, use_env: bool = False) -> Config:
    cfg = Config(tmp_path / "settings.json", use_env=use_env)
    cfg.set("paths.db_path", str(tmp_path / "vault.db"))
    cfg.set("vault.key_path", str(tmp_path / "vault.key"))
    return cfg


def test_store_get_roundtrip_encrypts_ciphertext(tmp_path: Path) -> None:
    cfg = _config(tmp_path)
    hint = store_key(cfg, "shodan", "supersecretvalue")

    assert hint == "su••••ue"
    assert cfg.get("api_keys.shodan") == "supersecretvalue"
    assert get_key(cfg, "shodan") == "supersecretvalue"

    row = list_stored(cfg)[0]
    assert row["provider"] == "shodan"
    assert row["hint"] == "su••••ue"
    assert "supersecretvalue" not in row["ciphertext"]
    assert row["ciphertext"] != "supersecretvalue"


def test_store_key_writes_private_key_file(tmp_path: Path) -> None:
    cfg = _config(tmp_path)
    store_key(cfg, "shodan", "value")
    key_file = Path(cfg.get("vault.key_path"))
    assert key_file.is_file()
    assert stat.S_IMODE(key_file.stat().st_mode) == 0o600


def test_key_file_is_reused_across_vaults(tmp_path: Path) -> None:
    cfg = _config(tmp_path)
    store_key(cfg, "shodan", "value")
    vault = Vault.from_config(cfg)
    assert vault.source == "file"

    other = _config(tmp_path)
    assert get_key(other, "shodan") == "value"


def test_delete_key_removes_row(tmp_path: Path) -> None:
    cfg = _config(tmp_path)
    store_key(cfg, "shodan", "value")
    assert delete_key(cfg, "shodan") is True
    assert delete_key(cfg, "shodan") is False
    assert get_key(cfg, "shodan") is None
    assert cfg.get("api_keys.shodan") is None
    assert list_stored(cfg) == []


def test_invalid_provider_and_empty_value_rejected(tmp_path: Path) -> None:
    cfg = _config(tmp_path)
    with pytest.raises(VaultError):
        store_key(cfg, "bad provider!", "value")
    with pytest.raises(VaultError):
        store_key(cfg, "shodan", "   ")
    with pytest.raises(VaultError):
        validate_provider("")


def test_vault_requires_file_backed_database(tmp_path: Path) -> None:
    cfg = Config(tmp_path / "settings.json", use_env=False)
    cfg.set("paths.db_path", ":memory:")
    with pytest.raises(VaultError):
        store_key(cfg, "shodan", "value")


def test_env_key_resolution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    key = Fernet.generate_key().decode("ascii")
    monkeypatch.setenv("INTELXTRACT_VAULT_KEY", key)
    cfg = _config(tmp_path)
    resolved, source = resolve_key(cfg)
    assert source == "env"
    assert resolved == key.encode("ascii")


def test_invalid_env_key_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("INTELXTRACT_VAULT_KEY", "not-a-fernet-key")
    cfg = _config(tmp_path)
    with pytest.raises(VaultError):
        resolve_key(cfg)


class _FakeKeyring:
    def __init__(self) -> None:
        self.store: dict[tuple[str, str], str] = {}
        self.fail_get = False

    def get_password(self, service: str, username: str) -> str | None:
        if self.fail_get:
            raise RuntimeError("keyring unavailable")
        return self.store.get((service, username))

    def set_password(self, service: str, username: str, value: str) -> None:
        self.store[(service, username)] = value


def test_keyring_source_used_when_available(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("INTELXTRACT_VAULT_KEY", raising=False)
    fake = _FakeKeyring()
    monkeypatch.setattr("core.vault._keyring", fake)
    cfg = _config(tmp_path)
    resolved, source = resolve_key(cfg)
    assert source == "keyring"
    assert resolved  # a fresh key was generated
    assert fake.store  # a fresh key was persisted to the keyring backend
    assert not Path(cfg.get("vault.key_path")).exists()

    store_key(cfg, "shodan", "value")
    assert get_key(cfg, "shodan") == "value"


def test_keyring_failure_falls_back_to_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("INTELXTRACT_VAULT_KEY", raising=False)
    fake = _FakeKeyring()
    fake.fail_get = True
    monkeypatch.setattr("core.vault._keyring", fake)
    cfg = _config(tmp_path)
    assert Vault.from_config(cfg).source == "file"


def test_store_key_scrubs_legacy_plaintext(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"api_keys": {"shodan": "legacy"}}), encoding="utf-8")
    cfg = _config(tmp_path)
    store_key(cfg, "shodan", "newsecret")

    raw = json.loads(path.read_text(encoding="utf-8"))
    assert "shodan" not in raw.get("api_keys", {})
    assert get_key(cfg, "shodan") == "newsecret"


def test_hydrate_loads_vault_into_config(tmp_path: Path) -> None:
    cfg = _config(tmp_path)
    store_key(cfg, "censys", "fromvault")

    fresh = _config(tmp_path)
    assert fresh.get("api_keys.censys") is None
    hydrated = hydrate_api_keys(fresh)
    assert hydrated == ["censys"]
    assert fresh.get("api_keys.censys") == "fromvault"


def test_hydrate_env_wins_over_vault(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = _config(tmp_path)
    cfg.save()
    store_key(cfg, "shodan", "vaultvalue")

    monkeypatch.setenv("INTELXTRACT_DOTENV", str(tmp_path / "none.env"))
    monkeypatch.setenv("INTELXTRACT_PATHS__DB_PATH", str(tmp_path / "vault.db"))
    monkeypatch.setenv("INTELXTRACT_API_KEYS__SHODAN", "envvalue")
    env_cfg = Config(tmp_path / "settings.json", use_env=True)
    hydrate_api_keys(env_cfg)
    assert env_cfg.get("api_keys.shodan") == "envvalue"


def test_hydrate_migrates_legacy_plaintext(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"api_keys": {"hibp": "legacyhibp"}}), encoding="utf-8")
    cfg = _config(tmp_path)
    store_key(cfg, "shodan", "seed")  # create the DB + schema
    assert get_key(cfg, "shodan") == "seed"

    migrated = hydrate_api_keys(cfg)
    assert "hibp" in migrated
    assert get_key(cfg, "hibp") == "legacyhibp"
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert "api_keys" not in raw


def test_mask_shapes() -> None:
    assert mask("") == ""
    assert mask("abcd") == "••••"
    assert mask("abcde") == "ab••••de"
    assert mask("supersecretvalue") == "su••••ue"


def test_decrypt_rejects_wrong_key(tmp_path: Path) -> None:
    cfg = _config(tmp_path)
    token = Vault.from_config(cfg).encrypt("value")
    other_key = Fernet.generate_key()
    with pytest.raises(VaultError):
        Vault(Fernet(other_key), source="env").decrypt(token)


def test_vault_never_persists_plaintext_to_config(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    cfg = _config(tmp_path)
    store_key(cfg, "shodan", "supersecretvalue")
    cfg.save()
    text: Any = path.read_text(encoding="utf-8")
    assert "supersecretvalue" not in text
