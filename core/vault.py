"""API-key vault: encrypted-at-rest secret storage (Phase 24, S24.1).

Secrets are encrypted with a Fernet key and stored as ciphertext in the
SQLite ``api_keys`` table; plaintext never touches config or disk. The Fernet
key itself comes from (in order of precedence):

1. ``INTELXTRACT_VAULT_KEY`` environment variable (explicit override),
2. the OS keyring (when the optional ``keyring`` package is importable),
3. a ``0600`` key file at ``vault.key_path`` (created on first use).

Runtime precedence for a provider key is:

    environment/``.env``  >  vault (encrypted DB)  >  config file  >  (none)

:func:`hydrate_api_keys` decrypts stored secrets into the in-memory config so
modules keep reading ``api_keys.<provider>`` unchanged, and migrates any
legacy plaintext ``api_keys`` entries out of the config file.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from core.config import Config
from core.exceptions import ConfigError, VaultError

ENV_VAULT_KEY = "INTELXTRACT_VAULT_KEY"
KEYRING_USERNAME = "vault-key"
_PROVIDER_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]*$")

try:  # optional dependency — absent keyring falls back to the key file
    import keyring as _keyring  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - exercised only without keyring
    _keyring = None


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def mask(value: str) -> str:
    """Render a secret without revealing it (``ab••••yz``)."""
    if not value:
        return ""
    if len(value) <= 4:
        return "••••"
    return f"{value[:2]}••••{value[-2:]}"


def validate_provider(name: str) -> str:
    """Normalize and validate a provider name."""
    provider = name.strip().lower()
    if not _PROVIDER_RE.match(provider):
        raise VaultError(f"invalid provider name: {name!r}")
    return provider


def _resolve_db(config: Config) -> Path | None:
    raw = str(config.get("paths.db_path", "")).strip()
    if not raw or raw == ":memory:":
        return None
    return Path(raw).expanduser()


def _require_db(config: Config) -> Path:
    path = _resolve_db(config)
    if path is None:
        raise VaultError("api-key vault requires a file-backed database")
    return path


def _key_path(config: Config) -> Path:
    raw = str(config.get("vault.key_path", "")).strip()
    if not raw:
        data_dir = str(config.get("paths.data_dir", "~/.local/share/intelxtract"))
        return Path(data_dir).expanduser() / "vault.key"
    return Path(raw).expanduser()


def _normalize_key(value: str) -> bytes:
    raw = value.strip().encode("ascii", "ignore")
    try:
        Fernet(raw)
    except (ValueError, TypeError) as exc:
        raise VaultError("vault key is not a valid Fernet key") from exc
    return raw


def _keyring_key(service: str) -> bytes | None:
    if _keyring is None:
        return None
    try:
        stored = _keyring.get_password(service, KEYRING_USERNAME)
    except Exception:
        return None
    if stored:
        return _normalize_key(str(stored))
    key = Fernet.generate_key()
    try:
        _keyring.set_password(service, KEYRING_USERNAME, key.decode("ascii"))
    except Exception:
        return None
    return key


def _write_private(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="ascii") as handle:
            handle.write(text)
    finally:
        try:
            os.chmod(path, 0o600)
        except OSError:  # pragma: no cover - best-effort on odd filesystems
            pass


def _file_key(path: Path) -> bytes:
    if path.is_file():
        try:
            content = path.read_text(encoding="ascii").strip()
        except OSError as exc:
            raise VaultError(f"cannot read vault key {path}: {exc}") from exc
        try:
            os.chmod(path, 0o600)
        except OSError:  # pragma: no cover - best-effort
            pass
        return _normalize_key(content)
    key = Fernet.generate_key()
    _write_private(path, key.decode("ascii"))
    return key


def resolve_key(config: Config) -> tuple[bytes, str]:
    """Resolve the Fernet key and report its source (env/keyring/file)."""
    env_key = os.environ.get(ENV_VAULT_KEY)
    if env_key:
        return _normalize_key(env_key), "env"
    service = str(config.get("vault.keyring_service", "intelxtract"))
    key = _keyring_key(service)
    if key is not None:
        return key, "keyring"
    return _file_key(_key_path(config)), "file"


class Vault:
    """Fernet-backed secret cipher."""

    def __init__(self, fernet: Fernet, *, source: str) -> None:
        self._fernet = fernet
        self.source = source

    @classmethod
    def from_config(cls, config: Config) -> Vault:
        """Build a vault from the configured/resolved key material."""
        key, source = resolve_key(config)
        return cls(Fernet(key), source=source)

    def encrypt(self, plaintext: str) -> str:
        """Encrypt ``plaintext`` into an opaque ASCII token."""
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt a stored token back to plaintext."""
        try:
            return self._fernet.decrypt(ciphertext.encode("ascii")).decode("utf-8")
        except (InvalidToken, ValueError) as exc:
            raise VaultError("stored API key could not be decrypted") from exc


_API_KEYS_DDL = (
    "CREATE TABLE IF NOT EXISTS api_keys ("
    " id INTEGER PRIMARY KEY AUTOINCREMENT,"
    " provider TEXT NOT NULL,"
    " ciphertext TEXT NOT NULL,"
    " hint TEXT NOT NULL DEFAULT '',"
    " created_at TEXT NOT NULL,"
    " updated_at TEXT NOT NULL)"
)
_API_KEYS_INDEX_DDL = (
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_api_keys_provider ON api_keys (provider)"
)


def _ensure_schema(conn: sqlite3.Connection) -> None:
    """Create the ``api_keys`` table when the vault owns a fresh database."""
    conn.execute(_API_KEYS_DDL)
    conn.execute(_API_KEYS_INDEX_DDL)


def _connect(path: Path, *, rw: bool) -> sqlite3.Connection | None:
    if not path.is_file():
        return None
    try:
        if rw:
            conn = sqlite3.connect(path, timeout=5.0)
        else:
            conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2.0)
    except sqlite3.Error:
        return None
    conn.row_factory = sqlite3.Row
    return conn


def list_stored(config: Config) -> list[dict[str, str]]:
    """Metadata (provider, hint, timestamps) for every stored key."""
    path = _resolve_db(config)
    if path is None:
        return []
    conn = _connect(path, rw=False)
    if conn is None:
        return []
    try:
        rows = conn.execute(
            "SELECT provider, ciphertext, hint, updated_at FROM api_keys"
            " ORDER BY provider"
        ).fetchall()
    except sqlite3.Error:
        return []
    finally:
        conn.close()
    return [
        {
            "provider": str(row["provider"]),
            "ciphertext": str(row["ciphertext"]),
            "hint": str(row["hint"]),
            "updated_at": str(row["updated_at"]),
        }
        for row in rows
    ]


def _upsert_sql() -> str:
    return (
        "INSERT INTO api_keys (provider, ciphertext, hint, created_at, updated_at)"
        " VALUES (?, ?, ?, ?, ?)"
        " ON CONFLICT(provider) DO UPDATE SET"
        " ciphertext = excluded.ciphertext,"
        " hint = excluded.hint,"
        " updated_at = excluded.updated_at"
    )


def _scrub_plaintext(config: Config, provider: str) -> None:
    """Remove a legacy plaintext key from the config file (never secrets)."""
    path = config.path
    if not path.is_file():
        return
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(raw, dict):
        return
    api_keys = raw.get("api_keys")
    if not isinstance(api_keys, dict) or provider not in api_keys:
        return
    del api_keys[provider]
    if not api_keys:
        raw.pop("api_keys", None)
    try:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(raw, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        tmp.replace(path)
    except OSError:
        pass


def store_key(config: Config, provider: str, value: str) -> str:
    """Encrypt and persist a key; returns the masked hint."""
    provider = validate_provider(provider)
    value = value.strip()
    if not value:
        raise VaultError("API key value must not be empty")
    path = _require_db(config)
    vault = Vault.from_config(config)
    now = _utc_now()
    hint = mask(value)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path, timeout=5.0)
    except (OSError, sqlite3.Error) as exc:
        raise VaultError(f"could not open database: {exc}") from exc
    try:
        _ensure_schema(conn)
        conn.execute(_upsert_sql(), (provider, vault.encrypt(value), hint, now, now))
        conn.commit()
    except sqlite3.Error as exc:
        raise VaultError(f"could not store key: {exc}") from exc
    finally:
        conn.close()
    _scrub_plaintext(config, provider)
    config.set(f"api_keys.{provider}", value)
    return hint


def get_key(config: Config, provider: str) -> str | None:
    """Return the decrypted secret for ``provider`` (``None`` if unset)."""
    provider = validate_provider(provider)
    path = _resolve_db(config)
    if path is None:
        return None
    conn = _connect(path, rw=False)
    if conn is None:
        return None
    try:
        row = conn.execute(
            "SELECT ciphertext FROM api_keys WHERE provider = ?", (provider,)
        ).fetchone()
    except sqlite3.Error:
        return None
    finally:
        conn.close()
    if row is None:
        return None
    return Vault.from_config(config).decrypt(str(row["ciphertext"]))


def delete_key(config: Config, provider: str) -> bool:
    """Remove a stored key; returns whether a row existed."""
    provider = validate_provider(provider)
    path = _resolve_db(config)
    if path is None:
        return False
    conn = _connect(path, rw=True)
    if conn is None:
        _scrub_plaintext(config, provider)
        return False
    try:
        cursor = conn.execute("DELETE FROM api_keys WHERE provider = ?", (provider,))
        conn.commit()
        existed = cursor.rowcount > 0
    except sqlite3.Error:
        existed = False
    finally:
        conn.close()
    try:
        config.unset(f"api_keys.{provider}")
    except ConfigError:
        pass
    _scrub_plaintext(config, provider)
    return existed


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    tmp.replace(path)


def _migrate_plaintext(config: Config) -> list[str]:
    path = config.path
    if not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(raw, dict):
        return []
    api_keys = raw.get("api_keys")
    if not isinstance(api_keys, dict):
        return []
    plaintext = {
        str(key): str(value)
        for key, value in api_keys.items()
        if isinstance(value, str) and value.strip()
    }
    if not plaintext:
        return []
    db = _resolve_db(config)
    if db is None or not db.is_file():
        return []
    try:
        vault = Vault.from_config(config)
    except VaultError:
        return []
    now = _utc_now()
    try:
        conn = sqlite3.connect(db, timeout=5.0)
    except sqlite3.Error:
        return []
    try:
        _ensure_schema(conn)
        for provider, value in plaintext.items():
            conn.execute(
                _upsert_sql(), (provider, vault.encrypt(value), mask(value), now, now)
            )
        conn.commit()
    except sqlite3.Error:
        return []
    finally:
        conn.close()
    for provider in plaintext:
        api_keys.pop(provider, None)
    if not api_keys:
        raw.pop("api_keys", None)
    try:
        _atomic_write(path, raw)
    except OSError:  # pragma: no cover - best-effort scrub
        pass
    return sorted(plaintext)


def hydrate_api_keys(config: Config) -> list[str]:
    """Load vault secrets into config and migrate any legacy plaintext keys.

    Environment/``.env`` values always win and are never overwritten. Returns
    the providers that were hydrated or migrated.
    """
    providers: set[str] = set()
    if bool(config.get("vault.migrate_plaintext", True)):
        providers.update(_migrate_plaintext(config))
    stored = list_stored(config)
    if not stored:
        return sorted(providers)
    try:
        vault = Vault.from_config(config)
    except VaultError:
        return sorted(providers)
    env_keys = config.env_keys()
    for row in stored:
        provider = row["provider"]
        if f"api_keys.{provider}" in env_keys:
            continue
        try:
            value = vault.decrypt(row["ciphertext"])
        except VaultError:
            continue
        config.set(f"api_keys.{provider}", value)
        providers.add(provider)
    return sorted(providers)


__all__ = [
    "ENV_VAULT_KEY",
    "Vault",
    "delete_key",
    "get_key",
    "hydrate_api_keys",
    "list_stored",
    "mask",
    "resolve_key",
    "store_key",
    "validate_provider",
]
