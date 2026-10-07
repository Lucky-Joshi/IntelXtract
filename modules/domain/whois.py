"""RDAP-based WHOIS facts for a domain (Phase 8, S8.1).

Queries the RDAP bootstrap service (``whois.endpoint``) over the shared
HTTP client — no raw port-43 sockets — and normalizes registrar, dates,
nameservers, contacts (with an email-redaction option) and DNSSEC status.
"""

from __future__ import annotations

import re
from typing import Any

from core.constants import Severity, TargetType
from core.engine import ModuleContext
from core.models import ModuleResult, make_finding
from modules.base import BaseModule

_EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
_CONTACT_ROLES = ("registrant", "administrative", "technical", "abuse")


def _mask_email(match: re.Match[str]) -> str:
    email = match.group(0)
    _, _, host = email.rpartition("@")
    return f"***@{host}"


def redact_email(value: str) -> str:
    """Replace the local part of every email address found in ``value``."""
    return _EMAIL_RE.sub(_mask_email, value)


def _vcard_field(payload: Any, field: str) -> str | None:
    """Pull a named vCard entry (``vcardArray``) string value, if any."""
    if not isinstance(payload, list) or len(payload) != 2 or payload[0] != "vcard":
        return None
    entries = payload[1] if isinstance(payload[1], list) else []
    for entry in entries:
        if (
            isinstance(entry, list)
            and len(entry) >= 4
            and entry[0] == field
            and isinstance(entry[3], str)
        ):
            return entry[3]
    return None


def _entities(entities: Any) -> list[dict[str, str]]:
    """Extract role/org/email triads from the RDAP ``entities`` list."""
    contacts: list[dict[str, str]] = []
    if not isinstance(entities, list):
        return contacts
    for entity in entities:
        if not isinstance(entity, dict):
            continue
        roles = entity.get("roles")
        if not isinstance(roles, list):
            continue
        vcard = entity.get("vcardArray")
        org = _vcard_field(vcard, "fn") or _vcard_field(vcard, "org") or ""
        email = _vcard_field(vcard, "email") or ""
        for role in roles:
            if isinstance(role, str) and role in _CONTACT_ROLES:
                contacts.append({"role": role, "org": org, "email": email})
    return contacts


def _event_dates(events: Any) -> dict[str, str | None]:
    """Map RDAP ``events`` onto registration/expiration/last-changed dates."""
    dates: dict[str, str | None] = {
        "registration": None,
        "expiration": None,
        "last_changed": None,
    }
    if not isinstance(events, list):
        return dates
    for event in events:
        if not isinstance(event, dict):
            continue
        action = event.get("eventAction")
        date = event.get("eventDate")
        if isinstance(date, str):
            if action == "registration":
                dates["registration"] = date
            elif action == "expiration":
                dates["expiration"] = date
            elif action == "last changed":
                dates["last_changed"] = date
    return dates


def _nameservers(payload: Any) -> list[str]:
    value = payload.get("nameservers") if isinstance(payload, dict) else None
    if not isinstance(value, list):
        return []
    names: list[str] = []
    for ns in value:
        if isinstance(ns, dict) and isinstance(ns.get("ldhName"), str):
            names.append(ns["ldhName"])
    return names


def _registrar(payload: Any) -> str | None:
    value = payload.get("registrar")
    if isinstance(value, list):
        for entry in value:
            if isinstance(entry, dict):
                name = entry.get("ldhName")
                if isinstance(name, str):
                    return name
    elif isinstance(value, dict):
        name = value.get("ldhName")
        if isinstance(name, str):
            return name
    return None


class WhoisModule(BaseModule):
    """RDAP WHOIS facts: registrar, dates, nameservers, contacts, DNSSEC."""

    name = "whois"
    target_types = (TargetType.DOMAIN,)
    description = "RDAP whois facts for a domain (registrar, dates, contacts)"

    async def run(self, target: str, ctx: ModuleContext) -> ModuleResult:
        endpoint = str(ctx.config.get("whois.endpoint", "https://rdap.org/domain/"))
        url = f"{endpoint.rstrip('/')}/{target}"
        payload = await self.http_get_json(ctx, url)
        return self._build(target, url, payload, ctx)

    def _build(
        self,
        target: str,
        url: str,
        payload: Any,
        ctx: ModuleContext,
    ) -> ModuleResult:
        registrar = _registrar(payload)
        dates = _event_dates(
            payload.get("events") if isinstance(payload, dict) else None
        )
        nameservers = _nameservers(payload)
        flags: list[str] = []
        if isinstance(payload, dict):
            statuses = payload.get("status")
            if isinstance(statuses, list):
                flags = [flag for flag in statuses if isinstance(flag, str)]
        signed = False
        secure = payload.get("secureDNS") if isinstance(payload, dict) else None
        if isinstance(secure, dict):
            signed = bool(secure.get("delegationSigned"))

        redact = bool(ctx.config.get("whois.redact_emails", True))
        contacts = _entities(
            payload.get("entities") if isinstance(payload, dict) else None
        )
        if redact:
            for contact in contacts:
                contact["email"] = redact_email(contact["email"])

        findings = [
            make_finding(
                self.name,
                "RDAP: registrar",
                {"registrar": registrar, "registration": dates["registration"]},
                severity=Severity.INFO,
                confidence=0.9,
                evidence=str(registrar),
            ),
            make_finding(
                self.name,
                "RDAP: registration dates",
                {
                    "registration": dates["registration"],
                    "expiration": dates["expiration"],
                },
                severity=Severity.INFO,
                confidence=0.9,
                evidence=f"expires {dates['expiration'] or 'unknown'}",
            ),
        ]
        if nameservers:
            findings.append(
                make_finding(
                    self.name,
                    "RDAP: nameservers",
                    {"nameservers": nameservers},
                    severity=Severity.INFO,
                    confidence=0.9,
                    evidence=", ".join(nameservers),
                )
            )
        if flags:
            findings.append(
                make_finding(
                    self.name,
                    "RDAP: status flags",
                    {"flags": flags},
                    severity=Severity.INFO,
                    confidence=0.9,
                    evidence="; ".join(flags),
                )
            )
        findings.append(
            make_finding(
                self.name,
                "RDAP: DNSSEC signed" if signed else "RDAP: DNSSEC not signed",
                {"delegation_signed": signed},
                severity=Severity.INFO if signed else Severity.LOW,
                confidence=0.9,
                evidence=f"delegation_signature={'signed' if signed else 'none'}",
            )
        )
        for contact in contacts:
            findings.append(
                make_finding(
                    self.name,
                    f"RDAP: {contact['role']} contact",
                    dict(contact),
                    severity=Severity.INFO,
                    confidence=0.7,
                    evidence=f"{contact['role']}: {contact['email']}",
                )
            )

        data: dict[str, Any] = {
            "target": target,
            "source": url,
            "registrar": registrar,
            "dates": dates,
            "nameservers": nameservers,
            "status": flags,
            "dnssec": {"delegation_signed": signed},
            "contacts": contacts,
        }
        return ModuleResult(data=data, findings=findings, meta={"source": url})
