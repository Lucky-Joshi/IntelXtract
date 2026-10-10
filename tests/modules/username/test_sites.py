"""Phase 12 S12.1: bundled site registry, validation, URL rendering."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from core.config import Config
from fakes import make_module_config
from modules.username.sites import (
    SitePatternError,
    load_sites,
    render_url,
    validate_site,
)


@pytest.fixture(scope="module")
def bundled(
    tmp_path_factory: pytest.TempPathFactory,
) -> list[dict[str, Any]]:
    cfg = make_module_config(
        tmp_path_factory.mktemp("cfg") / "settings.json", secret=None
    )
    return load_sites(cfg)


def test_bundled_has_30plus_sites(bundled: list[dict[str, Any]]) -> None:
    assert len(bundled) >= 30
    names = [site["name"] for site in bundled]
    assert len(names) == len(set(names))
    assert "GitHub" in names
    assert "Instagram" in names


def test_bundled_entries_are_valid(bundled: list[dict[str, Any]]) -> None:
    for site in bundled:
        assert "{username}" in site["url"]
        rule = site["rule"]
        assert isinstance(rule["exists"], list) and rule["exists"]
        assert isinstance(rule["missing"], list)

        # statuses that can never mean "exists" must not be claimed
        assert set(rule["missing"]) & set(rule["exists"]) == set()


def test_render_url_fills_template() -> None:
    site = validate_site(
        {
            "name": "GitHub",
            "url": "https://github.com/{username}",
            "rule": {"exists": [200], "missing": [404]},
        }
    )
    assert render_url(site, "octocat") == "https://github.com/octocat"


def test_validate_rejects_malformed_entries() -> None:
    with pytest.raises(SitePatternError):
        validate_site(
            {"url": "https://example.com/{username}", "rule": {"exists": [200]}}
        )
    with pytest.raises(SitePatternError):
        validate_site(
            {
                "name": "X",
                "url": "https://example.com/static",
                "rule": {"exists": [200]},
            }
        )
    with pytest.raises(SitePatternError):
        validate_site(
            {
                "name": "X",
                "url": "https://e.com/{username}",
                "rule": {"exists": [200], "bogus": [300]},
            }
        )
    with pytest.raises(SitePatternError):
        validate_site(
            {"name": "X", "url": "https://e.com/{username}", "rule": {"exists": ["ok"]}}
        )


def test_load_sites_merges_extra_and_path(
    tmp_path: Path, bundled: list[dict[str, Any]]
) -> None:
    cfg: Config = make_module_config(tmp_path / "c.json", secret=None)
    cfg.set(
        "username.sites_extra",
        [
            {
                "name": "AcmeNet",
                "url": "https://acme.tld/{username}",
                "rule": {"exists": [200], "missing": [404]},
            }
        ],
    )
    merged = load_sites(cfg)
    assert len(merged) == len(bundled) + 1
    assert any(s["name"] == "AcmeNet" for s in merged)

    override = tmp_path / "override.json"
    override.write_text(
        json.dumps(
            {
                "sites": [
                    {
                        "name": "OnlySite",
                        "url": "https://only.tld/{username}",
                        "rule": {"exists": [200], "missing": [404]},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    cfg.set("username.sites_path", str(override))
    only = load_sites(cfg)
    assert [s["name"] for s in only] == ["OnlySite"]
