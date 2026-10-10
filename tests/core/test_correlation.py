"""Correlation engine tests (Phase 16, S16.5): entity/edge detection + determinism."""

from __future__ import annotations

import hashlib
from typing import Any

from core.constants import TargetType
from core.correlation import (
    EDGE_ISSUED_TO,
    EDGE_MENTIONS,
    EDGE_PART_OF,
    EDGE_REGISTERED_BY,
    EDGE_RESOLVES_TO,
    EDGE_SAME_EMAIL,
    build_graph,
    is_subdomain,
)
from core.entities import Entity, entity_id, extract_entities, normalize

DNS_A_DATA: dict[str, Any] = {"type": "A", "records": ["93.184.216.34", "invalid-ip"]}
DNS_SPF_DATA: dict[str, Any] = {"record": "v=spf1 ip4:10.0.0.1 -all"}

WHOIS_REGISTRAR_DATA: dict[str, Any] = {"registrar": "Example Registrar LLC"}
WHOIS_CONTACT_DATA: dict[str, Any] = {
    "role": "registrant",
    "org": "Acme Corp",
    "email": "hostmaster@example.com",
}

CERT_DATA: dict[str, Any] = {
    "serial": "01:2B:3C",
    "subject": {"organizationName": "Acme Corp", "CN": "example.com"},
    "issuer": {"organizationName": "Example CA"},
    "subject_alt_names": ["example.com", "www.example.com", "api.example.com"],
}

NEWS_DATA: dict[str, Any] = {
    "target": "example.com",
    "articles": [
        {
            "title": "Example.com story",
            "url": "https://publisher.example/story",
            "source": "Publisher",
            "published": "2024-03-01T00:00:00+00:00",
            "guid": "g1",
        }
    ],
}

EMAIL_MX_DATA: dict[str, Any] = {
    "domain": "example.com",
    "hosts": ["mail1.example.com"],
}

USERNAME_DATA: dict[str, Any] = {
    "login": "hostmaster",
    "html_url": "https://github.com/hostmaster",
}


def _findings() -> list[dict[str, Any]]:
    return [
        {"module": "dns", "title": "DNS: A records", "data": DNS_A_DATA},
        {"module": "dns", "title": "DNS: SPF record", "data": DNS_SPF_DATA},
        {"module": "whois", "title": "RDAP: registrar", "data": WHOIS_REGISTRAR_DATA},
        {
            "module": "whois",
            "title": "RDAP: registrant contact",
            "data": WHOIS_CONTACT_DATA,
        },
        {
            "module": "certificate",
            "title": "Certificate: chain details",
            "data": CERT_DATA,
        },
        {"module": "news", "title": "News: timeline", "data": NEWS_DATA},
        {"module": "email", "title": "Email: MX records", "data": EMAIL_MX_DATA},
        {
            "module": "username",
            "title": "Username: GitHub profile",
            "data": USERNAME_DATA,
        },
    ]


def test_normalize_and_stable_ids() -> None:
    assert normalize("domain", "Example.COM.") == "example.com"
    assert normalize("domain", "*.API.example.com") == "api.example.com"
    assert normalize("email", "  Bob@Example.COM ") == "bob@example.com"
    assert normalize("username", "@hostmaster") == "hostmaster"
    assert normalize("certificate", "01:2b:3c") == "01:2B:3C"
    assert entity_id("domain", "example.com") == entity_id("domain", "EXAMPLE.COM")
    assert entity_id("domain", "example.com") != entity_id("domain", "other.org")

    digest = hashlib.sha256(b"example.com").hexdigest()[:12]
    assert entity_id("domain", "example.com") == f"domain:{digest}"


def test_is_subdomain() -> None:
    assert is_subdomain("www.example.com", "example.com")
    assert not is_subdomain("example.com", "example.com")
    assert not is_subdomain("example.com", "org")


def test_extract_entities_aggregates_across_modules() -> None:
    bag = extract_entities(_findings())

    domains = [e.value for e in bag.entities.values() if e.kind == "domain"]
    ips = [e.value for e in bag.entities.values() if e.kind == "ip"]
    organizations = [e.value for e in bag.entities.values() if e.kind == "organization"]
    assert "example.com" in domains
    assert "93.184.216.34" in ips
    assert "example registrar llc" in organizations
    assert "acme corp" in organizations
    assert any(
        entity.kind == "certificate" and entity.value == "01:2B:3C"
        for entity in bag.entities.values()
    )

    ids = list(bag.entities)
    assert len(ids) == len(set(ids))  # no duplicate ids
    assert Entity("domain", "example.com").id in bag.entities


def test_build_graph_produces_expected_entities_and_edges() -> None:
    graph = build_graph(
        _findings(), target="example.com", target_type=TargetType.DOMAIN
    )
    assert graph is not None

    entities_by_kind: dict[str, list[str]] = {}
    for item in graph.nodes_json():
        entities_by_kind.setdefault(item["kind"], []).append(item["value"])
    assert "example.com" in entities_by_kind["domain"]
    assert "93.184.216.34" in entities_by_kind["ip"]
    assert "01:2B:3C" in entities_by_kind["certificate"]
    assert "hostmaster@example.com" in entities_by_kind["email"]
    assert "example registrar llc" in entities_by_kind["organization"]

    edge_types = {
        (edge["source"], edge["target"]): edge["type"] for edge in graph.edges_json()
    }
    domain_id = entity_id("domain", "example.com")
    ip_id = entity_id("ip", "93.184.216.34")
    org_id = entity_id("organization", "Example Registrar LLC")
    cert_id = entity_id("certificate", "01:2B:3C")

    assert edge_types[(domain_id, ip_id)] == EDGE_RESOLVES_TO
    assert edge_types[(domain_id, org_id)] == EDGE_REGISTERED_BY
    assert edge_types[(domain_id, cert_id)] == EDGE_ISSUED_TO

    # whois contact email links back to its domain
    email_id = entity_id("email", "hostmaster@example.com")
    assert edge_types[(domain_id, email_id)] == EDGE_SAME_EMAIL

    # SAN subdomain gets a part_of edge
    www_id = entity_id("domain", "www.example.com")
    assert edge_types[(domain_id, www_id)] == EDGE_PART_OF


def test_build_graph_is_deterministic() -> None:
    first = build_graph(
        _findings(), target="example.com", target_type=TargetType.DOMAIN
    )
    second = build_graph(
        _findings(), target="example.com", target_type=TargetType.DOMAIN
    )
    assert first is not None and second is not None
    assert first.to_dict() == second.to_dict()

    # Reordering findings does not change the graph.
    shuffled = list(reversed(_findings()))
    third = build_graph(shuffled, target="example.com", target_type=TargetType.DOMAIN)
    assert third is not None
    assert third.to_dict() == first.to_dict()


def test_build_graph_components_for_news_mention() -> None:
    graph = build_graph(
        _findings(), target="example.com", target_type=TargetType.DOMAIN
    )
    assert graph is not None

    import networkx as nx  # type: ignore[import-untyped]

    publisher_id = entity_id("domain", "publisher.example")
    edge_types = {
        (edge["source"], edge["target"]): edge["type"] for edge in graph.edges_json()
    }
    target_id = entity_id("domain", "example.com")
    assert edge_types[(publisher_id, target_id)] == EDGE_MENTIONS

    target_component = next(
        component
        for component in nx.weakly_connected_components(graph.graph)
        if target_id in component
    )
    ip_id = entity_id("ip", "93.184.216.34")
    cert_id = entity_id("certificate", "01:2B:3C")
    email_id = entity_id("email", "hostmaster@example.com")
    assert {ip_id, cert_id, email_id, publisher_id} <= target_component


def test_empty_findings_seed_only_the_target() -> None:
    graph = build_graph([], target="example.com", target_type=TargetType.DOMAIN)
    assert graph is not None
    assert graph.graph.number_of_nodes() == 1

    sparse = build_graph(
        [{"module": "dns", "data": {}}],
        target="example.com",
        target_type=TargetType.DOMAIN,
    )
    assert sparse is not None
    assert sparse.graph.number_of_nodes() == 1

    assert (
        build_graph(
            [{"no_module": True}], target="not-a-domain", target_type=TargetType.DOMAIN
        )
        is None
    )
