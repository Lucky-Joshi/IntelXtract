"""Entity model and per-module extractors (Phase 16, S16.1-S16.2).

Entities are the lowest common denominator across findings: an IP that shows
up in both a DNS A record and a certificate transparency entry is *one*
entity regardless of which module surfaced it.  Each module declares
extractors against ``Finding.data``; the correlation engine aggregates the
same entity's occurrences into a single node with counts and sources.
"""

from __future__ import annotations

import hashlib
import ipaddress
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

ENTITY_KINDS = (
    "domain",
    "subdomain",
    "email",
    "username",
    "ip",
    "organization",
    "certificate",
    "document",
    "social_profile",
    "technology",
)

_WHITESPACE_RE = re.compile(r"\s+")
_IP4_RE = re.compile(r"\bip4:([0-9.]+)")
_MAILTO_RE = re.compile(r"\bmailto:([A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})", re.I)


@dataclass(frozen=True)
class Entity:
    """A stable, normalized entity node (type + value)."""

    kind: str
    value: str

    @property
    def id(self) -> str:
        return entity_id(self.kind, self.value)


def _valid_domain(value: str) -> bool:
    if not value or len(value) > 253:
        return False
    if any(char in value for char in (" ", "'", '"', "/", "\\", "@", ":")):
        return False
    return "." in value


def normalize(kind: str, value: Any) -> str:
    """Canonical string form of an entity value for a given kind."""
    raw = str(value or "").strip()
    if kind == "email":
        return raw.lower()
    if kind == "ip":
        try:
            return str(ipaddress.ip_address(raw))
        except ValueError:
            return raw.lower()
    if kind == "phone":
        return re.sub(r"[^0-9+]", "", raw)[:20]
    if kind == "certificate":
        return " ".join(_WHITESPACE_RE.split(raw)).upper()
    if kind in ("domain", "subdomain"):
        return raw.lower().rstrip(".").rstrip("/").lstrip("*.")
    if kind == "username":
        return raw.lstrip("@").lower()
    if kind == "document":
        return raw.lower()
    if kind == "technology":
        return raw.lower()
    return " ".join(_WHITESPACE_RE.split(raw)).lower()


def entity_id(kind: str, value: Any) -> str:
    """Stable identifier: ``kind:n`` + 12 hex chars of the hash of the value."""
    digest = hashlib.sha256(normalize(kind, value).encode("utf-8")).hexdigest()
    return f"{kind}:{digest[:12]}"


def emit(kind: str, value: Any) -> tuple[str, str] | None:
    """Validate + normalize one candidate entity, or ``None`` for junk."""
    normalized = normalize(kind, value)
    if not normalized or len(normalized) > 512:
        return None
    if kind in ("domain", "subdomain") and not _valid_domain(normalized):
        return None
    if kind == "email" and "@" not in normalized:
        return None
    return kind, normalized


def _values(data: dict[str, Any], *keys: str) -> list[Any]:
    values: list[Any] = []
    for key in keys:
        value = data.get(key)
        if isinstance(value, list):
            values.extend(value)
        elif value is not None:
            values.append(value)
    return values


def _flatten_str(value: Any) -> Iterator[str]:
    if isinstance(value, (list, tuple)):
        for item in value:
            text = str(item).strip()
            if text:
                yield text
    else:
        text = str(value).strip()
        if text:
            yield text


def _extract_dns(data: dict[str, Any]) -> Iterator[tuple[str, str]]:
    record_type = str(data.get("type") or "").upper()
    if record_type in ("A", "AAAA"):
        for value in _values(data, "records"):
            candidate = emit("ip", value)
            if candidate:
                yield candidate
    elif record_type in ("CNAME", "NS", "MX"):
        for value in _values(data, "records"):
            candidate = emit("domain", value)
            if candidate:
                yield candidate
    record = str(data.get("record") or "")
    for match in _IP4_RE.finditer(record):
        candidate = emit("ip", match.group(1))
        if candidate:
            yield candidate
    for match in _MAILTO_RE.finditer(record):
        candidate = emit("email", match.group(1))
        if candidate:
            yield candidate


def _extract_whois(data: dict[str, Any]) -> Iterator[tuple[str, str]]:
    registrar = data.get("registrar")
    if registrar:
        candidate = emit("organization", registrar)
        if candidate:
            yield candidate
    for name in _values(data, "nameservers"):
        candidate = emit("domain", name)
        if candidate:
            yield candidate
    email = data.get("email")
    if email and not str(email).startswith("***@"):  # skip redacted RDAP contacts
        candidate = emit("email", email)
        if candidate:
            yield candidate
    org = data.get("org")
    if org:
        candidate = emit("organization", org)
        if candidate:
            yield candidate


def _extract_subdomain(data: dict[str, Any]) -> Iterator[tuple[str, str]]:
    for name in _values(data, "subdomains"):
        candidate = emit("domain", name)
        if candidate:
            yield candidate


def _extract_ssl(data: dict[str, Any]) -> Iterator[tuple[str, str]]:
    for subject in _flatten_str(data.get("subject_cn")):
        candidate = emit("domain", subject)
        if candidate:
            yield candidate
    for issuer in _flatten_str(data.get("issuer")):
        candidate = emit("organization", issuer)
        if candidate:
            yield candidate
    for name in _values(data, "subject_alt_names"):
        candidate = emit("domain", name)
        if candidate:
            yield candidate


def _extract_certificate(data: dict[str, Any]) -> Iterator[tuple[str, str]]:
    serial = data.get("serial")
    if serial:
        candidate = emit("certificate", serial)
        if candidate:
            yield candidate
    subject = data.get("subject")
    if isinstance(subject, dict):
        for key in ("organizationName", "organizationalUnitName", "O"):
            for text in _flatten_str(subject.get(key)):
                candidate = emit("organization", text)
                if candidate:
                    yield candidate
        cn = subject.get("CN") or subject.get("commonName")
        for text in _flatten_str(cn):
            candidate = emit("domain", text)
            if candidate:
                yield candidate
    issuer = data.get("issuer")
    if isinstance(issuer, dict):
        for key in ("organizationName", "organizationalUnitName", "O"):
            for text in _flatten_str(issuer.get(key)):
                candidate = emit("organization", text)
                if candidate:
                    yield candidate
    for name in _values(data, "subject_alt_names", "related_names"):
        candidate = emit("domain", name)
        if candidate:
            yield candidate
    for issuer in _values(data, "issuers"):
        candidate = emit("organization", issuer)
        if candidate:
            yield candidate


def _extract_geo(data: dict[str, Any]) -> Iterator[tuple[str, str]]:
    for key in ("organization", "isp"):
        value = data.get(key)
        if value:
            candidate = emit("organization", value)
            if candidate:
                yield candidate


def _extract_rdns(data: dict[str, Any]) -> Iterator[tuple[str, str]]:
    for name in _values(data, "records", "hostname", "matches"):
        candidate = emit("domain", name)
        if candidate:
            yield candidate


def _extract_email(data: dict[str, Any]) -> Iterator[tuple[str, str]]:
    domain = data.get("domain")
    if domain:
        candidate = emit("domain", domain)
        if candidate:
            yield candidate
    for host in _values(data, "hosts"):
        candidate = emit("domain", host)
        if candidate:
            yield candidate


def _extract_username(data: dict[str, Any]) -> Iterator[tuple[str, str]]:
    login = data.get("login")
    if login:
        candidate = emit("username", login)
        if candidate:
            yield candidate
    html_url = data.get("html_url")
    if html_url:
        candidate = emit("social_profile", html_url)
        if candidate:
            yield candidate


def _extract_metadata(data: dict[str, Any]) -> Iterator[tuple[str, str]]:
    filename = data.get("filename") or data.get("target")
    if filename:
        candidate = emit("document", filename)
        if candidate:
            yield candidate


def _extract_tech(data: dict[str, Any]) -> Iterator[tuple[str, str]]:
    technology = data.get("technology")
    if technology:
        candidate = emit("technology", technology)
        if candidate:
            yield candidate


def _extract_news(data: dict[str, Any]) -> Iterator[tuple[str, str]]:
    for article in _values(data, "articles"):
        if not isinstance(article, dict):
            continue
        host = urlsplit(str(article.get("url") or "")).netloc.lower()
        if host:
            candidate = emit("domain", host)
            if candidate:
                yield candidate


EXTRACTORS: dict[str, list[Any]] = {
    "dns": [_extract_dns],
    "whois": [_extract_whois],
    "subdomain": [_extract_subdomain],
    "ssl": [_extract_ssl],
    "certificate": [_extract_certificate],
    "geo": [_extract_geo],
    "rdns": [_extract_rdns],
    "email": [_extract_email],
    "username": [_extract_username],
    "metadata": [_extract_metadata],
    "tech": [_extract_tech],
    "news": [_extract_news],
}


@dataclass
class EntityBag:
    """Aggregated entity occurrences keyed by stable ID."""

    entities: dict[str, Entity] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)
    sources: dict[str, set[str]] = field(default_factory=dict)

    def add(self, kind: str, value: Any, source: str) -> None:
        candidate = emit(kind, value)
        if candidate is None:
            return
        normalized_kind, normalized_value = candidate
        identity = entity_id(normalized_kind, normalized_value)
        if identity not in self.entities:
            self.entities[identity] = Entity(normalized_kind, normalized_value)
        self.counts[identity] = self.counts.get(identity, 0) + 1
        self.sources.setdefault(identity, set()).add(source)

    def sorted_entities(self) -> list[Entity]:
        return sorted(self.entities.values(), key=lambda entity: entity.id)


def extract_entities(findings: Iterable[dict[str, Any]]) -> EntityBag:
    """Run every registered extractor over the scan's findings."""
    bag = EntityBag()
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        module = str(finding.get("module") or "")
        data = finding.get("data")
        if not isinstance(data, dict):
            continue
        for extractor in EXTRACTORS.get(module, []):
            for kind, value in extractor(data):
                bag.add(kind, value, module)
    return bag


__all__ = [
    "ENTITY_KINDS",
    "Entity",
    "EntityBag",
    "emit",
    "entity_id",
    "extract_entities",
    "normalize",
]
