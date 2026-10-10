"""Phase 17 (S17.2-S17.3): weighted, explainable risk scoring.

Pure function :func:`assess_risk` maps a flattened list of findings to a
0-100 score, a ``low | medium | high | critical`` rating, per-category
sub-scores, and a traceable list of every contributing rule. The summary
generator turns the top contributors into plain-language sentences for
reports and AI-assistant prompts.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from core.risk_rules import CATEGORY_CEILINGS, CATEGORY_ORDER, RULES

# Score bands (documented in Phase_Plan S17.2). Deterministic: first matching
# band wins; the table is ordered highest-first.
RATING_BANDS: tuple[tuple[str, float], ...] = (
    ("critical", 75.0),
    ("high", 50.0),
    ("medium", 25.0),
    ("low", 0.0),
)

VERDICTS: dict[str, str] = {
    "critical": "immediate remediation required",
    "high": "significant weaknesses found",
    "medium": "moderate weaknesses found",
    "low": "low overall exposure",
}


def rating_for(score: float) -> str:
    for rating, threshold in RATING_BANDS:
        if score >= threshold:
            return rating
    return "low"


def _finding_key(finding: dict[str, Any]) -> str:
    payload = json.dumps(
        finding.get("data", {}), sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(payload).hexdigest()


@dataclass
class RiskReport:
    target: str
    score: float
    rating: str
    categories: dict[str, dict[str, Any]]
    rules: list[dict[str, Any]]
    summary: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "score": self.score,
            "rating": self.rating,
            "categories": self.categories,
            "rules": self.rules,
            "summary": self.summary,
        }


def assess_risk(findings: Sequence[dict[str, Any]], *, target: str) -> RiskReport:
    """Score ``findings`` (flattened engine findings) for ``target``.

    Every matched rule carries its id, category, weight, label, and the
    finding it fired on so the score is fully traceable.
    """
    matched: list[dict[str, Any]] = []
    for finding in findings:
        module = str(finding.get("module", ""))
        title = str(finding.get("title", ""))
        for rule in RULES:
            if rule.module != module or rule.title not in title:
                continue
            if rule.when is not None and not rule.when(finding):
                continue
            matched.append(
                {
                    "rule_id": rule.id,
                    "category": rule.category,
                    "label": rule.label,
                    "points": rule.weight,
                    "finding": {"module": module, "title": title},
                    "finding_key": _finding_key(finding),
                }
            )

    # De-duplicate identical (rule, finding) pairs, then order by contribution.
    seen: set[tuple[str, str, str, str]] = set()
    unique: list[dict[str, Any]] = []
    for item in matched:
        key = (
            item["rule_id"],
            item["finding"]["module"],
            item["finding"]["title"],
            item["finding_key"],
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    unique.sort(key=lambda item: (-item["points"], item["rule_id"]))

    categories: dict[str, dict[str, Any]] = {}
    total = 0.0
    for category in CATEGORY_ORDER:
        cat_rules = [item for item in unique if item["category"] == category]
        raw_score = round(sum(item["points"] for item in cat_rules), 1)
        categories[category] = {"score": raw_score, "rules": len(cat_rules)}
        total += min(raw_score, CATEGORY_CEILINGS[category])
    score = min(100.0, round(total, 1))
    rating = rating_for(score)

    summary = [
        (
            f"Overall risk: {rating.upper()} ({score:.0f}/100). "
            f"{VERDICTS[rating]}; {len(unique)} contributing finding(s)."
        ),
        *[
            f"[{item['category']}] {item['label']} (+{item['points']:.0f})"
            for item in unique[:8]
        ],
    ]
    if not unique:
        summary = ["Overall risk: LOW (0/100). No contributing risk findings."]

    return RiskReport(
        target=target,
        score=score,
        rating=rating,
        categories=categories,
        rules=[
            {key: value for key, value in item.items() if key != "finding_key"}
            for item in unique
        ],
        summary=summary,
    )


__all__ = ["RiskReport", "assess_risk", "rating_for"]
