"""Customer reference readiness export."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.customer_reference_readiness.v1"
KIND = "max.customer_reference_readiness"

_TIER_ORDER = {"tier_1": 0, "tier_2": 1, "not_ready": 2}


def build_customer_reference_readiness_export(store: Store, domain: str | None = None) -> dict[str, Any]:
    candidates = [_candidate_row(unit) for unit in store.get_buildable_units(limit=1000, domain=domain)]
    candidates.sort(key=lambda row: (_TIER_ORDER[row["candidate_tier"]], -row["readiness_score"], row["customer_name"], row["idea_id"]))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {"project": "max", "entity_type": "customer_reference_readiness", "domain_filter": domain},
        "summary": _summary(candidates),
        "candidates": candidates,
    }


def render_customer_reference_readiness_markdown(report: dict[str, Any]) -> str:
    lines = ["# Customer Reference Readiness", "", f"Schema: `{report['schema_version']}`", f"Generated: {report['generated_at']}", "", "## Candidates", ""]
    if report.get("candidates"):
        lines.extend(["| Customer | Score | Tier | Disqualifiers | Recommendation |", "|----------|-------|------|---------------|----------------|"])
        for row in report["candidates"]:
            lines.append(f"| {_md(row['customer_name'])} | {row['readiness_score']:.0f} | {row['candidate_tier']} | {_md(', '.join(row['disqualifiers']) or 'None')} | {_md(row['outreach_recommendation'])} |")
    else:
        lines.append("- No customer candidates available.")
    return "\n".join(lines).rstrip() + "\n"


def render_customer_reference_readiness_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str)


def _candidate_row(unit: Any) -> dict[str, Any]:
    metadata = getattr(unit, "metadata", None) if isinstance(getattr(unit, "metadata", None), dict) else {}
    score = 40.0
    supporting: list[str] = []
    disqualifiers: list[str] = []
    for key, label in (("adoption", "Adoption"), ("satisfaction", "Satisfaction"), ("renewal_status", "Renewal"), ("strategic_fit", "Strategic fit")):
        delta = _score_signal(metadata.get(key))
        score += delta
        if delta > 0:
            supporting.append(label)
        elif delta < 0:
            disqualifiers.append(f"Weak {label.lower()}")
    support = _text(metadata.get("support_burden") or metadata.get("open_escalations") or metadata.get("escalations")).lower()
    if any(word in support for word in ("open", "high", "escalation", "sev")):
        score -= 35
        disqualifiers.append("Open escalations")
    elif any(word in support for word in ("low", "none", "healthy")):
        score += 15
        supporting.append("Low support burden")
    score = round(max(0.0, min(100.0, score)), 1)
    tier = "tier_1" if score >= 80 and not disqualifiers else "tier_2" if score >= 55 and "Open escalations" not in disqualifiers else "not_ready"
    return {
        "idea_id": str(getattr(unit, "id", "")),
        "customer_name": _text(metadata.get("customer") or metadata.get("account") or getattr(unit, "title", "Untitled")),
        "readiness_score": score,
        "candidate_tier": tier,
        "disqualifiers": disqualifiers,
        "supporting_evidence": _list(metadata.get("evidence_references") or metadata.get("evidence")) + supporting,
        "outreach_recommendation": _recommendation(tier, disqualifiers),
    }


def _summary(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    return {"candidate_count": len(candidates), "average_readiness_score": round(sum(row["readiness_score"] for row in candidates) / len(candidates), 1) if candidates else 0.0, "tier_counts": {tier: sum(1 for row in candidates if row["candidate_tier"] == tier) for tier in ("tier_1", "tier_2", "not_ready")}}


def _score_signal(value: Any) -> float:
    text = _text(value).lower()
    if any(word in text for word in ("high", "strong", "healthy", "promoter", "renewed", "strategic")):
        return 15.0
    if any(word in text for word in ("low", "weak", "detractor", "risk", "churn")):
        return -15.0
    return 0.0


def _recommendation(tier: str, disqualifiers: list[str]) -> str:
    if tier == "tier_1":
        return "Proceed with reference outreach."
    if disqualifiers:
        return f"Do not request a reference until {disqualifiers[0].lower()} is resolved."
    return "Nurture before requesting a public reference."


def _list(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return [_text(item) for item in value if _text(item)]
    return [_text(value)] if _text(value) else []


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""


def _md(value: Any) -> str:
    return str(value).replace("|", "\\|")
