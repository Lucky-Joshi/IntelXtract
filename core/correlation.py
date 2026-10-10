"""Correlation engine: entities + relationships -> NetworkX graph (Phase 16).

Turns a scan's flat findings into a connected entity graph.  Node identity
comes from :mod:`core.entities`; edges carry a semantic type and a
confidence.  The graph is deterministic — the same findings always produce
the same JSON — so exports, persistence, and diffs are stable.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

import networkx as nx  # type: ignore[import-untyped]

from core.constants import TargetType
from core.entities import Entity, EntityBag, emit, extract_entities

EDGE_RESOLVES_TO = "resolves_to"
EDGE_REGISTERED_BY = "registered_by"
EDGE_ISSUED_TO = "issued_to"
EDGE_SAME_EMAIL = "same_email"
EDGE_PART_OF = "part_of"
EDGE_MENTIONS = "mentions"
EDGE_PROFILE = "profile"
EDGE_USES = "uses"

_IP4_RE = re.compile(r"\bip4:([0-9.]+)")

DEFAULT_TARGET_KIND = {
    TargetType.DOMAIN: "domain",
    TargetType.IP: "ip",
    TargetType.EMAIL: "email",
    TargetType.USERNAME: "username",
    TargetType.FILE: "document",
    TargetType.URL: "domain",
}


def is_subdomain(name: str, base: str) -> bool:
    """True when ``name`` is a strict subdomain of ``base``."""
    return name != base and name.endswith(f".{base}") and len(name) > len(base) + 1


def _clean_host(value: Any) -> str:
    return str(value or "").lower().rstrip(".").lstrip("*.")


def _entity(kind: str, value: Any) -> Entity | None:
    candidate = emit(kind, value)
    if candidate is None:
        return None
    return Entity(candidate[0], candidate[1])


def _flatten(value: Any) -> list[str]:
    """Coerce a string or iterable-of-strings into a list of text items."""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]


def _items(data: dict[str, Any], key: str) -> list[Any]:
    value = data.get(key)
    return value if isinstance(value, list) else []


@dataclass
class CorrelationGraph:
    """Wrapper around a :class:`networkx.MultiDiGraph` of entities and edges."""

    target: str
    target_type: TargetType
    graph: nx.MultiDiGraph = field(default_factory=nx.MultiDiGraph)

    def add_entity(self, entity: Entity) -> None:
        if self.graph.has_node(entity.id):
            node = self.graph.nodes[entity.id]
            node["count"] = int(node.get("count", 1)) + 1
            return
        self.graph.add_node(entity.id, kind=entity.kind, value=entity.value, count=1)

    def add_edge(
        self, source: Entity, target: Entity, edge_type: str, confidence: float
    ) -> None:
        self.add_entity(source)
        self.add_entity(target)
        key = (source.id, target.id, edge_type)
        if self.graph.has_edge(*key):
            current = float(self.graph.edges[key].get("confidence", 0.0))
            self.graph.edges[key]["confidence"] = max(current, confidence)
            return
        self.graph.add_edge(source.id, target.id, type=edge_type, confidence=confidence)

    def nodes_json(self) -> list[dict[str, Any]]:
        nodes = [
            {
                "id": node,
                "kind": data.get("kind", ""),
                "value": data.get("value", ""),
                "count": int(data.get("count", 1)),
            }
            for node, data in self.graph.nodes(data=True)
        ]
        return sorted(nodes, key=lambda item: item["id"])

    def edges_json(self) -> list[dict[str, Any]]:
        edges = [
            {
                "source": source,
                "target": target,
                "type": data.get("type", ""),
                "confidence": float(data.get("confidence", 0.0)),
            }
            for source, target, data in self.graph.edges(data=True)
        ]
        return sorted(
            edges, key=lambda item: (item["source"], item["target"], item["type"])
        )

    @property
    def component_count(self) -> int:
        try:
            return int(nx.number_weakly_connected_components(self.graph))
        except nx.NetworkXException:
            return 0

    def to_dict(self) -> dict[str, Any]:
        nodes = self.nodes_json()
        edges = self.edges_json()
        return {
            "target": self.target,
            "target_type": self.target_type.value,
            "entities": nodes,
            "edges": edges,
            "stats": {
                "entities": len(nodes),
                "edges": len(edges),
                "components": self.component_count,
            },
        }


def _target_entity(target: str, target_type: TargetType) -> Entity | None:
    kind = DEFAULT_TARGET_KIND.get(target_type, "domain")
    value = _clean_host(target) if kind == "domain" else str(target).strip()
    return _entity(kind, value)


def _link_name(
    graph: CorrelationGraph,
    base: Entity,
    host: str,
    target: str,
    confidence: float,
) -> None:
    """Attach a hostname to ``base`` as part_of, loose mention, or bare node."""
    name = _clean_host(host)
    if not name:
        return
    name_entity = _entity("domain", name)
    if name_entity is None:
        return
    if is_subdomain(name, base.value):
        graph.add_edge(base, name_entity, EDGE_PART_OF, confidence)
    elif name != base.value and name != _clean_host(target):
        graph.add_edge(base, name_entity, EDGE_MENTIONS, confidence)
    elif name == base.value:
        graph.add_entity(name_entity)


def _apply_dns(
    graph: CorrelationGraph, base: Entity, data: dict[str, Any], target: str
) -> None:
    record_type = str(data.get("type") or "").upper()
    if record_type in ("A", "AAAA"):
        for value in _items(data, "records"):
            ip_entity = _entity("ip", value)
            if ip_entity is not None:
                graph.add_edge(base, ip_entity, EDGE_RESOLVES_TO, 0.9)
    elif record_type == "CNAME":
        for value in _items(data, "records"):
            alias = _entity("domain", value)
            if alias is not None:
                graph.add_edge(base, alias, EDGE_RESOLVES_TO, 0.6)
    record = str(data.get("record") or "")
    for match in _IP4_RE.finditer(record):
        ip_entity = _entity("ip", match.group(1))
        if ip_entity is not None:
            graph.add_edge(base, ip_entity, EDGE_RESOLVES_TO, 0.4)


def _apply_whois(
    graph: CorrelationGraph, base: Entity, data: dict[str, Any], target: str
) -> None:
    registrar = data.get("registrar")
    if registrar:
        org = _entity("organization", registrar)
        if org is not None:
            graph.add_edge(base, org, EDGE_REGISTERED_BY, 0.9)
    email = data.get("email")
    if email and not str(email).startswith("***@"):
        address = _entity("email", email)
        if address is not None:
            graph.add_edge(base, address, EDGE_SAME_EMAIL, 0.8)


def _apply_ssl(
    graph: CorrelationGraph, base: Entity, data: dict[str, Any], target: str
) -> None:
    for issuer in _flatten(data.get("issuer")):
        org = _entity("organization", issuer)
        if org is not None:
            graph.add_edge(base, org, EDGE_ISSUED_TO, 0.7)
    for name in _items(data, "subject_alt_names"):
        _link_name(graph, base, _clean_host(name), target, 0.8)


def _apply_certificate(
    graph: CorrelationGraph, base: Entity, data: dict[str, Any], target: str
) -> None:
    serial = data.get("serial")
    if serial:
        certificate = Entity("certificate", serial)
        graph.add_edge(base, certificate, EDGE_ISSUED_TO, 0.9)
        issuer = data.get("issuer")
        if isinstance(issuer, dict):
            for key in ("organizationName", "organizationalUnitName", "O"):
                for text in _flatten(issuer.get(key)):
                    org = _entity("organization", text)
                    if org is not None:
                        graph.add_edge(certificate, org, EDGE_ISSUED_TO, 0.8)
    for name in _items(data, "subject_alt_names"):
        _link_name(graph, base, _clean_host(name), target, 0.8)
    for name in _items(data, "related_names"):
        _link_name(graph, base, _clean_host(name), target, 0.6)


def _apply_subdomain(
    graph: CorrelationGraph, base: Entity, data: dict[str, Any], target: str
) -> None:
    for name in _items(data, "subdomains"):
        _link_name(graph, base, _clean_host(name), target, 0.9)


def _apply_news(
    graph: CorrelationGraph, base: Entity, data: dict[str, Any], target: str
) -> None:
    for article in _items(data, "articles"):
        if not isinstance(article, dict):
            continue
        host = urlsplit(str(article.get("url") or "")).netloc.lower()
        if not host or host == _clean_host(target):
            continue
        publisher = _entity("domain", host)
        if publisher is not None:
            graph.add_edge(publisher, base, EDGE_MENTIONS, 0.4)


def _apply_tech(
    graph: CorrelationGraph, base: Entity, data: dict[str, Any], target: str
) -> None:
    technology = data.get("technology")
    if technology:
        tech = _entity("technology", technology)
        if tech is not None:
            graph.add_edge(base, tech, EDGE_USES, 0.8)


def _apply_username(
    graph: CorrelationGraph, base: Entity, data: dict[str, Any], target: str
) -> None:
    html_url = data.get("html_url")
    if html_url:
        profile = _entity("social_profile", html_url)
        if profile is not None:
            graph.add_edge(base, profile, EDGE_PROFILE, 0.9)


_APPLICATORS: dict[str, Any] = {
    "dns": _apply_dns,
    "whois": _apply_whois,
    "ssl": _apply_ssl,
    "certificate": _apply_certificate,
    "subdomain": _apply_subdomain,
    "news": _apply_news,
    "tech": _apply_tech,
    "username": _apply_username,
}


def _link_email_relationships(graph: CorrelationGraph, bag: EntityBag) -> None:
    usernames = {
        entity.value: entity
        for entity in bag.entities.values()
        if entity.kind == "username"
    }
    domains = {
        entity.value: entity
        for entity in bag.entities.values()
        if entity.kind == "domain"
    }
    for email_entity in (e for e in bag.entities.values() if e.kind == "email"):
        local, _, host = email_entity.value.partition("@")
        if host in domains:
            graph.add_edge(email_entity, domains[host], EDGE_SAME_EMAIL, 0.9)
        if local in usernames:
            graph.add_edge(email_entity, usernames[local], EDGE_SAME_EMAIL, 0.7)


def build_graph(
    findings: Iterable[dict[str, Any]],
    *,
    target: str,
    target_type: TargetType,
) -> CorrelationGraph | None:
    """Return a deterministic entity/edge graph, or ``None`` when empty."""
    findings = [finding for finding in findings if isinstance(finding, dict)]
    bag = extract_entities(findings)
    base = _target_entity(target, target_type)
    graph = CorrelationGraph(target=target, target_type=target_type)
    for entity in bag.sorted_entities():
        graph.add_entity(entity)
    if base is not None:
        graph.add_entity(base)

    if base is not None:
        for finding in findings:
            module = str(finding.get("module") or "")
            data = finding.get("data")
            if isinstance(data, dict):
                applicator = _APPLICATORS.get(module)
                if applicator is not None:
                    applicator(graph, base, data, target)

        _link_email_relationships(graph, bag)

    if graph.graph.number_of_nodes() == 0:
        return None
    return graph


def to_json_exports(nx_graph: nx.MultiDiGraph) -> dict[str, Any]:
    """Node-link JSON for external visualizers (deterministic ordering)."""
    nodes = sorted(nx_graph.nodes())
    edges = sorted(nx_graph.edges())
    return {
        "directed": True,
        "nodes": [{"id": node, **nx_graph.nodes[node]} for node in nodes],
        "links": [
            {"source": source, "target": target, **nx_graph.edges[(source, target)]}
            for source, target in edges
        ],
    }


__all__ = [
    "EDGE_ISSUED_TO",
    "EDGE_MENTIONS",
    "EDGE_PART_OF",
    "EDGE_PROFILE",
    "EDGE_REGISTERED_BY",
    "EDGE_RESOLVES_TO",
    "EDGE_SAME_EMAIL",
    "CorrelationGraph",
    "build_graph",
    "is_subdomain",
    "to_json_exports",
]
