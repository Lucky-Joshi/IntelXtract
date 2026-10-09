"""ip-api.org (Phase 9, S9.1) geolocation module tests."""

from __future__ import annotations

from pathlib import Path

from core.constants import Severity, TargetType
from core.engine import ModuleContext
from fakes import FakeHttpClient, HttpError, make_module_config, make_module_context
from fixtures import geo_payload
from modules.ip.geo import GeoModule

GEO_URL = "http://ip-api.com/json/1.1.1.1"


def _ctx(tmp_path: Path, *, client: FakeHttpClient) -> ModuleContext:
    cfg = make_module_config(tmp_path)
    return make_module_context(cfg, http=client, target_type=TargetType.IP)


async def test_geo_reports_location_and_network(tmp_path: Path) -> None:
    client = FakeHttpClient()
    client.stub(GEO_URL, body=geo_payload())
    ctx = _ctx(tmp_path, client=client)

    result = await GeoModule().run("1.1.1.1", ctx)

    assert result.data["state"] == "ok"
    assert result.data["country"] == "United States"
    assert result.data["region"] == "WA"
    assert result.data["city"] == "Seattle"
    assert result.data["asn"] == "AS13335 Cloudflare, Inc."
    assert result.data["data_source"] == "api"

    titles = {f.title for f in result.findings}
    assert "Geo: IP location" in titles
    assert "Geo: network" in titles
    assert all(f.severity is Severity.INFO for f in result.findings)


async def test_geo_serves_cached_lookup_without_second_request(
    tmp_path: Path,
) -> None:
    client = FakeHttpClient()
    client.stub(GEO_URL, body=geo_payload())
    ctx = _ctx(tmp_path, client=client)

    await GeoModule().run("1.1.1.1", ctx)
    second = await GeoModule().run("1.1.1.1", ctx)

    assert second.data["data_source"] == "cache"
    assert len(client.requests) == 1


async def test_geo_offline_degrades_to_low_finding(tmp_path: Path) -> None:
    client = FakeHttpClient()

    def refused(
        method: str, url: str, kwargs: dict
    ) -> tuple[int, dict[str, str], None]:
        raise HttpError(500, url)

    client.stub(GEO_URL, body=refused)
    ctx = _ctx(tmp_path, client=client)

    result = await GeoModule().run("1.1.1.1", ctx)

    assert result.data["state"] == "unavailable"
    finding = result.findings[0]
    assert finding.title == "Geo: lookup unavailable"
    assert finding.severity is Severity.LOW
    assert finding.confidence <= 0.7


async def test_geo_provider_failure_degrades_to_low_finding(tmp_path: Path) -> None:
    client = FakeHttpClient()
    client.stub(GEO_URL, body={"status": "fail", "message": "reserved range"})
    ctx = _ctx(tmp_path, client=client)

    result = await GeoModule().run("1.1.1.1", ctx)

    assert result.data["state"] == "unavailable"
    assert result.findings[0].title == "Geo: lookup unavailable"
    assert result.findings[0].severity is Severity.LOW
