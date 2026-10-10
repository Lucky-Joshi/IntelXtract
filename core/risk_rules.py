"""Phase 17 (S17.1): deterministic, documented risk rule table.

Each :class:`RiskRule` identifies a finding pattern (module + title substring,
optionally gated by a predicate on the finding's ``data``) and contributes an
explicit weight toward one of four categories.

Weights are documented in the table below and in ``docs/Phase_Plan.md``
S17.1/S17.2. The scorer is pure: identical findings yield identical output.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

CATEGORY_TLS = "TLS"
CATEGORY_HEADERS = "HEADERS"
CATEGORY_DNS = "DNS"
CATEGORY_EXPOSURE = "EXPOSURE"

CATEGORY_ORDER = (CATEGORY_TLS, CATEGORY_HEADERS, CATEGORY_DNS, CATEGORY_EXPOSURE)

# Ceiling each category may contribute to the 0-100 total so a single
# weakness category (e.g. an entire TLS failure) cannot dominate the score.
CATEGORY_CEILINGS: dict[str, float] = {
    CATEGORY_TLS: 40.0,
    CATEGORY_HEADERS: 30.0,
    CATEGORY_DNS: 20.0,
    CATEGORY_EXPOSURE: 25.0,
}

FindingPredicate = Callable[[dict[str, Any]], bool]


@dataclass(frozen=True)
class RiskRule:
    id: str
    module: str
    title: str
    category: str
    weight: float
    label: str
    when: FindingPredicate | None = None


def _cookie_missing(finding: dict[str, Any], flag: str) -> bool:
    data: dict[str, Any] = finding.get("data") or {}
    missing = data.get("missing")
    if not isinstance(missing, list):
        return False
    return flag in missing


def _spf_is_allow_all(finding: dict[str, Any]) -> bool:
    data: dict[str, Any] = finding.get("data") or {}
    policy = data.get("all")
    return isinstance(policy, str) and policy == "+all"


def _dmarc_is_none(finding: dict[str, Any]) -> bool:
    data: dict[str, Any] = finding.get("data") or {}
    policy = data.get("policy")
    return isinstance(policy, str) and policy == "none"


RULES: tuple[RiskRule, ...] = (
    # TLS — weight by assurance impact (ceiling 40)
    RiskRule(
        id="tls_cert_expired",
        module="ssl",
        title="SSL: certificate expired",
        category=CATEGORY_TLS,
        weight=35.0,
        label="TLS certificate has expired",
    ),
    RiskRule(
        id="tls_self_signed",
        module="ssl",
        title="SSL: self-signed certificate",
        category=CATEGORY_TLS,
        weight=18.0,
        label="TLS certificate is self-signed",
    ),
    RiskRule(
        id="tls_no_https",
        module="http",
        title="HTTP: https unreachable",
        category=CATEGORY_TLS,
        weight=10.0,
        label="Service does not answer over HTTPS",
    ),
    # HEADERS — transport/web hardening (ceiling 30)
    RiskRule(
        id="headers_trace",
        module="http_methods",
        title="HTTP: TRACE enabled",
        category=CATEGORY_HEADERS,
        weight=15.0,
        label="TRACE method enabled (cross-site tracing risk)",
    ),
    RiskRule(
        id="headers_hsts",
        module="headers",
        title="Headers: strict-transport-security missing",
        category=CATEGORY_HEADERS,
        weight=9.0,
        label="Strict-Transport-Security header missing",
    ),
    RiskRule(
        id="headers_csp",
        module="headers",
        title="Headers: content-security-policy missing",
        category=CATEGORY_HEADERS,
        weight=9.0,
        label="Content-Security-Policy header missing",
    ),
    RiskRule(
        id="headers_cookie_no_secure",
        module="headers",
        title="Headers: insecure cookie",
        category=CATEGORY_HEADERS,
        weight=7.0,
        label="Cookie set without the Secure flag",
        when=lambda f: _cookie_missing(f, "Secure"),
    ),
    RiskRule(
        id="headers_xframe",
        module="headers",
        title="Headers: x-frame-options missing",
        category=CATEGORY_HEADERS,
        weight=4.0,
        label="X-Frame-Options header missing",
    ),
    RiskRule(
        id="headers_xcto",
        module="headers",
        title="Headers: x-content-type-options missing",
        category=CATEGORY_HEADERS,
        weight=3.0,
        label="X-Content-Type-Options header missing",
    ),
    RiskRule(
        id="headers_server",
        module="headers",
        title="Headers: server disclosure",
        category=CATEGORY_HEADERS,
        weight=4.0,
        label="Server software disclosed in headers",
    ),
    RiskRule(
        id="headers_referrer",
        module="headers",
        title="Headers: referrer-policy missing",
        category=CATEGORY_HEADERS,
        weight=2.0,
        label="Referrer-Policy header missing",
    ),
    RiskRule(
        id="headers_cookie_weak",
        module="headers",
        title="Headers: insecure cookie",
        category=CATEGORY_HEADERS,
        weight=2.0,
        label="Cookie missing HttpOnly/SameSite flags",
        when=lambda f: not _cookie_missing(f, "Secure"),
    ),
    RiskRule(
        id="headers_permissions",
        module="headers",
        title="Headers: permissions-policy missing",
        category=CATEGORY_HEADERS,
        weight=2.0,
        label="Permissions-Policy header missing",
    ),
    # DNS — mail/DNS hygiene (ceiling 20)
    RiskRule(
        id="dns_no_dmarc",
        module="dns",
        title="DNS: no DMARC record",
        category=CATEGORY_DNS,
        weight=6.0,
        label="No DMARC record published",
    ),
    RiskRule(
        id="dns_no_spf",
        module="dns",
        title="DNS: no SPF record",
        category=CATEGORY_DNS,
        weight=4.0,
        label="No SPF record published",
    ),
    RiskRule(
        id="dns_dnssec_absent",
        module="whois",
        title="RDAP: DNSSEC not signed",
        category=CATEGORY_DNS,
        weight=3.0,
        label="Domain DNSSEC not signed",
    ),
    RiskRule(
        id="dns_no_mx",
        module="email",
        title="Email: domain accepts no mail (no MX)",
        category=CATEGORY_DNS,
        weight=5.0,
        label="Domain has no MX records (cannot receive mail)",
    ),
    RiskRule(
        id="dns_spf_allow_all",
        module="email",
        title="Email: SPF policy",
        category=CATEGORY_DNS,
        weight=6.0,
        label="SPF policy allows unfiltered mail (+all)",
        when=_spf_is_allow_all,
    ),
    RiskRule(
        id="dns_dmarc_none",
        module="email",
        title="Email: DMARC policy",
        category=CATEGORY_DNS,
        weight=6.0,
        label="DMARC policy set to probing 'none'",
        when=_dmarc_is_none,
    ),
    # Exposure — sensitive data / account compromise surface (ceiling 25)
    RiskRule(
        id="exposure_breach",
        module="breach",
        title="Breach: address exposed in known breach(es)",
        category=CATEGORY_EXPOSURE,
        weight=20.0,
        label="Email exposed in known data breach(es)",
    ),
    RiskRule(
        id="exposure_gps",
        module="metadata",
        title="Metadata: GPS coordinates",
        category=CATEGORY_EXPOSURE,
        weight=10.0,
        label="Document publishes GPS coordinates in metadata",
    ),
    RiskRule(
        id="exposure_disposable",
        module="email",
        title="Email: disposable address",
        category=CATEGORY_EXPOSURE,
        weight=4.0,
        label="Uses a disposable email provider",
    ),
)

RULE_INDEX: dict[str, RiskRule] = {rule.id: rule for rule in RULES}

__all__ = [
    "CATEGORY_CEILINGS",
    "CATEGORY_DNS",
    "CATEGORY_EXPOSURE",
    "CATEGORY_HEADERS",
    "CATEGORY_ORDER",
    "CATEGORY_TLS",
    "RULES",
    "RiskRule",
]
