# Settings & Secret Storage

IntelXtract resolves configuration from four layers. When the same dotted key
appears in more than one layer, the higher layer wins:

| Priority | Source | Notes |
|----------|--------|-------|
| 1 (highest) | Environment variables / `.env` | `INTELXTRACT_<KEY>`, nested keys use `__` |
| 2 | Encrypted vault | `api_keys.<provider>` only (see below) |
| 3 | Config file | `config/settings.json` (path override: `INTELXTRACT_CONFIG_PATH`) |
| 4 (lowest) | Built-in defaults | `core/config.DEFAULTS` |

Nested keys map environment names by upper-casing and replacing `.` with `__`:

```
INTELXTRACT_API_KEYS__HIBP     -> api_keys.hibp
INTELXTRACT_NETWORK__PROXY     -> network.proxy
INTELXTRACT_GUI__THEME         -> gui.theme
INTELXTRACT_SCAN__MAX_WORKERS  -> scan.max_workers
```

`Config.env_keys()` exposes the set of dotted keys supplied by the
environment/`.env`, which is how the vault knows not to override them.

## API-key vault

API keys are **never** stored in plaintext. `intelxtract key set <provider>`
encrypts the value with Fernet and writes only the ciphertext (plus a masked
hint) to the `api_keys` table in the database. There are three ways to obtain
the Fernet key, in order of precedence:

1. `INTELXTRACT_VAULT_KEY` — an explicit key (portable across machines).
   Generate one with:

   ```bash
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```

2. The OS keyring — used automatically when the optional `keyring` package is
   installed.

3. A key file at `vault.key_path` (default
   `~/.local/share/intelxtract/vault.key`), created on first use with `0600`
   permissions.

At startup (CLI and GUI) `core.vault.hydrate_api_keys()` decrypts stored keys
into the in-memory config so modules keep reading `api_keys.<provider>`
unchanged. Environment/`.env` values always win and are never overwritten.
Legacy plaintext `api_keys` entries already in `settings.json` are migrated
into the vault on the next load, and the config file is scrubbed.

Because secrets live in the vault, `Config.save()` deliberately omits the
`api_keys` section — saving settings can never write a key back to disk.

### CLI

```bash
intelxtract key set shodan            # prompts (hidden input)
intelxtract key set shodan --value X  # non-interactive
intelxtract key list                  # provider + masked hint
intelxtract key get shodan            # masked
intelxtract key get shodan --reveal   # decrypted
intelxtract key delete shodan --yes
```

`config set api_keys.*` is rejected (use `key set`); `config list` masks any
`api_keys.*` values it renders.

## Network settings

Consumed by `core.http_client.HttpClient`:

| Key | Default | Meaning |
|-----|---------|---------|
| `network.proxy` | `""` | Proxy URL applied to every request (blank = direct) |
| `network.rate_limit` | `0.0` | Max requests/second (0 disables pacing) |
| `network.timeout` | `30.0` | Request timeout in seconds |
| `network.retries` | `2` | Transient-failure retries |

## App settings

| Key | Default | Meaning |
|-----|---------|---------|
| `app.telemetry` | `false` | Always off; not user-configurable |
| `gui.theme` | `dark` | Dark only for now |
| `gui.language` | `en` | UI language |
| `cache.enabled` | `true` | Disable to make the response cache a no-op |
| `cache.ttl` / `cache.max_size` | `300.0` / `1024` | Cache lifetime and LRU bound |
| `logging.level` / `logging.file` | `INFO` / `logs/intelxtract.log` | Logging target |
| `logging.max_bytes` / `logging.backup_count` | `1048576` / `3` | Log rotation |

All of these are editable from the GUI **Settings** page (except telemetry,
which is fixed off).
