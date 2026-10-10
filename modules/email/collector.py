"""Phase 11 orchestrating collector: ``email``.

Combines S11.1 validation, S11.2 mail-domain DNS (MX/SPF/DMARC), and S11.3
Gravatar into one registered module.  Each network stage degrades to a
``state`` field plus a low-confidence finding instead of failing the run, so
a scan with no usable network still classifies the address.
"""

from __future__ import annotations

from typing import Any

from core.constants import Severity, TargetType
from core.engine import ModuleContext
from core.models import ModuleResult, make_finding
from modules.base import BaseModule
from modules.email import gravatar, mx, validation

DEFAULT_DNS_ENDPOINT = mx.DEFAULT_DNS_ENDPOINT


class EmailModule(BaseModule):
    """Classify an address and profile its mail infrastructure."""

    name = "email"
    target_types = (TargetType.EMAIL,)
    description = "Email validation, mail-domain MX/SPF/DMARC, Gravatar"
    timeout = 20.0

    def validate(self, target: str) -> bool:
        return validation.syntax_valid(target)

    async def run(self, target: str, ctx: ModuleContext) -> ModuleResult:
        normalized = validation.normalize_email(target)
        extra = ctx.config.get("email.disposable_extra", [])
        disposable_extra = extra if isinstance(extra, list) else []
        profile = validation.classify(normalized, disposable_extra)
        domain = profile["domain"]

        findings: list[Any] = []
        data: dict[str, Any] = {
            "target": normalized,
            "state": "ok",
            "syntax": profile["syntax"],
            "local": profile["local"],
            "domain": domain,
            "disposable": profile["disposable"],
        }

        if profile["disposable"]:
            findings.append(
                make_finding(
                    self.name,
                    "Email: disposable address",
                    {"domain": domain},
                    severity=Severity.MEDIUM,
                    confidence=0.9,
                    evidence=f"{domain} is a known disposable provider",
                )
            )

        if domain is None:
            data["state"] = "invalid"
            findings.append(
                make_finding(
                    self.name,
                    "Email: malformed address",
                    {"target": normalized},
                    severity=Severity.LOW,
                    confidence=0.8,
                    evidence="address failed syntax validation",
                )
            )
            return ModuleResult(data=data, findings=findings)

        try:
            mail = await mx.probe_mail_dns(ctx, domain)
        except Exception:
            data["state"] = "degraded"
            data["mail"] = {"state": "unavailable"}
            findings.append(
                make_finding(
                    self.name,
                    "Email: mail infrastructure check unavailable",
                    {"domain": domain},
                    severity=Severity.LOW,
                    confidence=0.4,
                    evidence="DNS-over-HTTPS probe failed",
                )
            )
        else:
            data["mail"] = mail
            findings.extend(self._mail_findings(domain, mail))

        try:
            gravatar_result = await gravatar.probe_gravatar(ctx, normalized)
        except Exception:
            gravatar_result = {"state": "unavailable"}
        data["gravatar"] = gravatar_result
        findings.extend(self._gravatar_findings(normalized, gravatar_result))

        return ModuleResult(data=data, findings=findings)

    def _mail_findings(self, domain: str, mail: dict[str, Any]) -> list[Any]:
        findings: list[Any] = []
        mx_records = mail.get("mx") or []
        if not mx_records:
            findings.append(
                make_finding(
                    self.name,
                    "Email: domain accepts no mail (no MX)",
                    {"domain": domain},
                    severity=Severity.MEDIUM,
                    confidence=0.9,
                    evidence="no MX records published",
                )
            )
        else:
            findings.append(
                make_finding(
                    self.name,
                    "Email: MX records",
                    {
                        "domain": domain,
                        "hosts": [record["host"] for record in mx_records],
                    },
                    severity=Severity.INFO,
                    confidence=0.9,
                    evidence=f"{len(mx_records)} MX host(s)",
                )
            )

        spf = mail.get("spf")
        if spf is None:
            findings.append(
                make_finding(
                    self.name,
                    "Email: no SPF record",
                    {"domain": domain},
                    severity=Severity.LOW,
                    confidence=0.8,
                    evidence="no v=spf1 TXT record",
                )
            )
        else:
            findings.append(
                make_finding(
                    self.name,
                    "Email: SPF policy",
                    {
                        "domain": domain,
                        "include": spf.get("include", []),
                        "all": spf.get("all"),
                    },
                    severity=Severity.INFO,
                    confidence=0.9,
                    evidence=f"SPF '{spf.get('all') or 'unset'}'",
                )
            )

        dmarc = mail.get("dmarc")
        if dmarc is None:
            findings.append(
                make_finding(
                    self.name,
                    "Email: no DMARC record",
                    {"domain": domain},
                    severity=Severity.LOW,
                    confidence=0.8,
                    evidence="no v=DMARC1 TXT record at _dmarc",
                )
            )
        else:
            policy = dmarc.get("policy")
            weak = policy == "none"
            findings.append(
                make_finding(
                    self.name,
                    "Email: DMARC policy",
                    {
                        "domain": domain,
                        "policy": policy,
                        "percent": dmarc.get("percent"),
                    },
                    severity=Severity.LOW if weak else Severity.INFO,
                    confidence=0.9,
                    evidence=dmarc.get("policy_note", "") or f"p={policy}",
                )
            )
        return findings

    def _gravatar_findings(self, email: str, result: dict[str, Any]) -> list[Any]:
        if result.get("exists") is True:
            return [
                make_finding(
                    self.name,
                    "Email: Gravatar profile",
                    {"hash": result.get("hash"), "url": result.get("url")},
                    severity=Severity.INFO,
                    confidence=0.9,
                    evidence=f"public profile for {email}",
                )
            ]
        if result.get("state") == "unavailable":
            return [
                make_finding(
                    self.name,
                    "Email: Gravatar lookup unavailable",
                    {"hash": result.get("hash")},
                    severity=Severity.LOW,
                    confidence=0.3,
                    evidence="avatar probe failed",
                )
            ]
        return []
