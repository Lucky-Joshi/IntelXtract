"""S12.1 — site pattern registry loading and rendering (private module).

Reads the bundled ``sites.json``, merges operator-supplied patterns from
``username.sites_extra`` (and an optional ``username.sites_path`` override),
validates each entry, and renders ``{username}`` URLs.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from core.config import Config

_TEMPLATE_RE = re.compile(r"\{username\}")
_VALID_RULE_KEYS = frozenset(
    {"exists", "missing", "unknown", "exists_marker", "missing_marker"}
)
_SUPPORTED_HTTP_STATUSES = {200, 301, 302, 303, 307, 308, 403, 404, 410, 429, 451}


class SitePatternError(ValueError):
    """Raised when a username site pattern is malformed."""


def load_bundled() -> list[dict[str, Any]]:
    """Load the package's bundled site registry."""
    path = Path(__file__).with_name("sites.json")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SitePatternError(f"cannot read bundled sites.json: {exc}") from exc
    sites = raw.get("sites") if isinstance(raw, dict) else None
    if not isinstance(sites, list):
        raise SitePatternError("bundled sites.json must contain a 'sites' list")
    return [validate_site(site) for site in sites]


def load_sites(config: Config) -> list[dict[str, Any]]:
    """Load bundled sites plus a config override/extra patterns."""
    override = config.get("username.sites_path", None)
    if isinstance(override, str) and override:
        return _load_path(override)
    sites = load_bundled()
    extra = config.get("username.sites_extra", [])
    if isinstance(extra, list):
        for entry in extra:
            sites.append(validate_site(entry))
    return sites


def _load_path(path: str) -> list[dict[str, Any]]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SitePatternError(
            f"cannot read username.sites_path {path!r}: {exc}"
        ) from exc
    sites = data.get("sites") if isinstance(data, dict) else None
    if not isinstance(sites, list):
        raise SitePatternError(f"username.sites_path {path!r} must be a 'sites' list")
    return [validate_site(site) for site in sites]


def validate_site(site: Any) -> dict[str, Any]:
    """Validate a single site entry and normalize its rule."""
    if not isinstance(site, dict):
        raise SitePatternError(
            f"site entry must be an object, got {type(site).__name__}"
        )
    name = site.get("name")
    url = site.get("url")
    if not isinstance(name, str) or not name.strip():
        raise SitePatternError(f"site entry missing a non-empty 'name': {site!r}")
    if not isinstance(url, str) or _TEMPLATE_RE.search(url) is None:
        raise SitePatternError(
            f"site {name!r} url must contain {{{{username}}}}: {url!r}"
        )

    rule = site.get("rule", {})
    if not isinstance(rule, dict):
        raise SitePatternError(f"site {name!r} rule must be an object")
    unknown = set(rule) - _VALID_RULE_KEYS
    if unknown:
        raise SitePatternError(
            f"site {name!r} rule has unknown keys: {sorted(unknown)}"
        )
    statuses: dict[str, list[int]] = {}
    for key in ("exists", "missing", "unknown"):
        values = rule.get(key, [])
        if not isinstance(values, list) or not all(
            isinstance(v, int) and v in _SUPPORTED_HTTP_STATUSES for v in values
        ):
            raise SitePatternError(
                f"site {name!r} rule.{key} must be a status-code list"
            )
        statuses[key] = [v for v in values]

    markers: dict[str, str] = {}
    for key in ("exists_marker", "missing_marker"):
        value = rule.get(key, "")
        if not isinstance(value, str):
            raise SitePatternError(f"site {name!r} rule.{key} must be a string")
        markers[key] = value

    return {
        "name": name,
        "url": url,
        "rule": {**statuses, **markers},
    }


def render_url(site: Mapping[str, Any], username: str) -> str:
    """Fill the ``{{username}}`` template (usernames are URL-safe by validation)."""
    template = site["url"]
    return str(template).replace("{username}", username)
