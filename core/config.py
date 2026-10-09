"""Layered configuration.

Precedence (lowest to highest):

1. Built-in defaults (:data:`DEFAULTS`)
2. JSON file (``config/settings.json`` by default)
3. ``.env`` file (see :func:`load_env_file`) and environment variables
   prefixed with ``INTELXTRACT_``

Nested keys use dotted paths (``scan.max_workers``).  Environment variables
map ``__`` to nesting levels: ``INTELXTRACT_SCAN__MAX_WORKERS=16`` sets
``scan.max_workers``.  The ``.env`` file is the documented way to keep API
keys and other secrets out of the repository.
"""

from __future__ import annotations

import json
import os
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any

from core.exceptions import ConfigError

ENV_PREFIX = "INTELXTRACT_"
ENV_CONFIG_PATH = f"{ENV_PREFIX}CONFIG_PATH"
ENV_DOTENV_PATH = f"{ENV_PREFIX}DOTENV"

DEFAULTS: dict[str, Any] = {
    "app": {
        "name": "IntelXtract",
        "version": "0.1.0a0",
    },
    "paths": {
        "data_dir": "~/.local/share/intelxtract",
        "logs_dir": "logs",
        "cache_dir": "cache",
        "exports_dir": "exports",
        "db_path": "~/.local/share/intelxtract/intelxtract.db",
        "plugins_dir": "plugins",
    },
    "scan": {
        "default_mode": "quick",
        "default_timeout": 30.0,
        "max_workers": 8,
    },
    "cache": {
        "enabled": True,
        "ttl": 300.0,
        "max_size": 1024,
    },
    "logging": {
        "level": "INFO",
        "file": "logs/intelxtract.log",
        "max_bytes": 1_048_576,
        "backup_count": 3,
        "console": True,
    },
    "network": {
        "user_agent": "IntelXtract/0.1 (OSINT research tool)",
        "timeout": 30.0,
        "retries": 2,
    },
    "http": {
        "timeout": 30.0,
        "retries": 2,
    },
    "whois": {
        "endpoint": "https://rdap.org/domain/",
        "redact_emails": True,
    },
    "dns": {
        "endpoint": "https://cloudflare-dns.com/dns-query",
        "selectors": [
            "default",
            "google",
            "selector1",
            "selector2",
            "selector3",
            "dkim",
            "mail",
            "s1",
            "s2",
            "s3",
            "2020",
            "2021",
            "pacman",
        ],
    },
    "ssl": {
        "timeout": 10.0,
    },
    "subdomain": {
        "endpoint": "https://crt.sh",
        "max_results": 500,
    },
    "geo": {
        "endpoint": "http://ip-api.com/json/",
        "cache_ttl": 86400.0,
    },
    "rdns": {
        "endpoint": "https://cloudflare-dns.com/dns-query",
    },
    "reputation": {
        "endpoint": "https://cloudflare-dns.com/dns-query",
        "dnsbl_zone": "zen.spamhaus.org",
        "abuseipdb_endpoint": "https://api.abuseipdb.com/api/v2/check",
    },
}


def _coerce_env(value: str) -> Any:
    """Parse an environment string as JSON when possible, else keep it."""
    try:
        return json.loads(value)
    except (json.JSONDecodeError, ValueError):
        return value


def _parse_dotenv(text: str) -> dict[str, str]:
    """Parse simple ``KEY=VALUE`` lines (blank lines, ``#`` comments, quotes)."""
    pairs: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        if key:
            pairs[key] = value
    return pairs


def load_env_file(path: Path | str | None = None) -> Path | None:
    """Load ``KEY=VALUE`` pairs from a ``.env`` file into ``os.environ``.

    Resolution: explicit ``path`` > ``INTELXTRACT_DOTENV`` > ``.env`` in the
    current directory.  Existing environment variables always win and are
    never overwritten.  Returns the loaded file path, or ``None`` when the
    file is absent.
    """
    if path is None:
        path = os.environ.get(ENV_DOTENV_PATH, ".env")
    env_path = Path(path)
    if not env_path.is_file():
        return None
    try:
        pairs = _parse_dotenv(env_path.read_text(encoding="utf-8"))
    except OSError:
        return None
    for key, value in pairs.items():
        if key not in os.environ:
            os.environ[key] = value
    return env_path


def _coerce_to_current(value: Any, current: Any) -> Any:
    """Coerce a string value to the type of the value it replaces."""
    if not isinstance(value, str) or not isinstance(current, (int, float, bool)):
        return value
    if isinstance(current, bool) and value.lower() in {"true", "false"}:
        return value.lower() == "true"
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, ValueError):
        return value
    if isinstance(current, bool):
        return parsed if isinstance(parsed, bool) else value
    if (
        isinstance(current, int)
        and isinstance(parsed, int)
        and not isinstance(parsed, bool)
    ):
        return parsed
    if isinstance(current, float) and isinstance(parsed, (int, float)):
        return float(parsed)
    return value


def _split_key(key: str) -> list[str]:
    parts = [p.strip() for p in key.lower().split(".")]
    if not parts or any(not p for p in parts):
        raise ConfigError(f"invalid config key: {key!r}")
    return parts


def _get_dotted(source: dict[str, Any], key: str, default: Any = None) -> Any:
    node: Any = source
    for part in _split_key(key):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node


def _set_dotted(target: dict[str, Any], key: str, value: Any) -> None:
    parts = _split_key(key)
    node = target
    for part in parts[:-1]:
        child = node.get(part)
        if not isinstance(child, dict):
            child = {}
            node[part] = child
        node = child
    node[parts[-1]] = value


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


class Config:
    """Thread-safe, layered configuration store."""

    def __init__(
        self,
        path: Path | str | None = None,
        *,
        use_env: bool = True,
    ) -> None:
        if path is not None:
            self._path = Path(path)
        else:
            self._path = Path(os.environ.get(ENV_CONFIG_PATH, "config/settings.json"))
        self._use_env = use_env
        self._lock = threading.RLock()
        self._data: dict[str, Any] = {}
        if use_env:
            load_env_file()
        self.reload()

    @property
    def path(self) -> Path:
        """Path of the backing JSON file."""
        return self._path

    def reload(self) -> None:
        """Rebuild the effective configuration from all layers."""
        data = deepcopy(DEFAULTS)
        if self._path.is_file():
            try:
                raw = json.loads(self._path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ConfigError(
                    f"cannot read config file {self._path}: {exc}"
                ) from exc
            if not isinstance(raw, dict):
                raise ConfigError(
                    f"config file {self._path} must contain a JSON object"
                )
            data = _deep_merge(data, raw)
        if self._use_env:
            for name, value in os.environ.items():
                if not name.startswith(ENV_PREFIX) or name == ENV_CONFIG_PATH:
                    continue
                dotted = name[len(ENV_PREFIX) :].lower().replace("__", ".")
                _set_dotted(data, dotted, _coerce_env(value))
        with self._lock:
            self._data = data

    def get(self, key: str, default: Any = None) -> Any:
        """Return the value for a dotted key, or ``default`` when unset."""
        with self._lock:
            value = _get_dotted(self._data, key, default)
        return deepcopy(value) if isinstance(value, dict) else value

    def set(self, key: str, value: Any) -> None:
        """Set a dotted key in memory (call :meth:`save` to persist)."""
        with self._lock:
            current = _get_dotted(self._data, key, _MISSING)
            if current is not _MISSING:
                value = _coerce_to_current(value, current)
            _set_dotted(self._data, key, value)

    def unset(self, key: str) -> None:
        """Remove a dotted key (raises :class:`ConfigError` when absent)."""
        parts = _split_key(key)
        with self._lock:
            node: Any = self._data
            for part in parts[:-1]:
                node = node.get(part) if isinstance(node, dict) else None
                if node is None:
                    raise ConfigError(f"config key not set: {key!r}")
            if not isinstance(node, dict) or parts[-1] not in node:
                raise ConfigError(f"config key not set: {key!r}")
            del node[parts[-1]]

    def section(self, name: str) -> dict[str, Any]:
        """Return a deep copy of a top-level (or dotted) section."""
        value = self.get(name, {})
        if not isinstance(value, dict):
            raise ConfigError(f"config section is not an object: {name!r}")
        return value

    def as_dict(self) -> dict[str, Any]:
        """Return a deep copy of the effective configuration."""
        with self._lock:
            return deepcopy(self._data)

    def save(self) -> None:
        """Persist the current configuration to the JSON file atomically."""
        with self._lock:
            payload = json.dumps(self._data, indent=2, sort_keys=True) + "\n"
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(self._path.suffix + ".tmp")
            tmp.write_text(payload, encoding="utf-8")
            tmp.replace(self._path)
        except OSError as exc:
            raise ConfigError(f"cannot write config file {self._path}: {exc}") from exc


class _Missing:
    """Sentinel for 'key not present' lookups."""


_MISSING = _Missing()


def load_config(path: Path | str | None = None) -> Config:
    """Convenience factory used by CLI and GUI entry points."""
    return Config(path)
