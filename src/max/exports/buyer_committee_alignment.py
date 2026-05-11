"""Buyer committee alignment export for sales readiness."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.buyer_committee_alignment.v1"
KIND = "max.buyer_committee_alignment"

REQUIRED_BUYER_ROLES = [
    "economic_buyer",
    "champion",
    "technical_evaluator",
    "legal_security",
    "end_user",
]

ROLE_LABELS = {
    "economic_buyer": "Economic buyer",
    "champion": "Champion",
    "technical_evaluator": "Technical evaluator",
    "legal_security": "Legal/security",
    "end_user": "End user",
}

_ROLE_ALIASES = {
    "economic_buyer": [
        "economic buyer",
        "budget owner",
        "budget holder",
        "executive sponsor",
        "exec sponsor",
        "decision maker",
        "cfo",
        "vp finance",
    ],
    "champion": ["champion", "internal champion", "advocate", "sponsor", "power user"],
    "technical_evaluator": [
        "technical evaluator",
        "technical buyer",
        "technical reviewer",
        "architect",
        "engineering lead",
        "it evaluator",
        "it buyer",
        "cto",
    ],
    "legal_security": [
        "legal",
        "security",
        "legal/security",
        "legal security",
        "compliance",
        "procurement",
        "risk",
        "infosec",
        "privacy",
        "dpo",
    ],
    "end_user": ["end user", "end-user", "user", "users", "operator", "practitioner", "admin"],
}


def build_buyer_committee_alignment_export(store: Store, domain: str | None = None) -> dict[str, Any]:
    """Build buyer committee alignment from buildable unit metadata."""
    units = store.get_buildable_units(limit=1000, domain=domain)
    rows = [_build_unit_alignment(unit) for unit in units]
    rows.sort(key=lambda row: (row["alignment_score"], row["title"], row["idea_id"]))

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "project": "max",
            "entity_type": "buyer_committee_alignment",
            "domain_filter": domain,
        },
        "required_buyer_roles": [
            {"role": role, "label": ROLE_LABELS[role]} for role in REQUIRED_BUYER_ROLES
        ],
        "unit_count": len(rows),
        "units": rows,
        "summary": _build_summary(rows),
        "recommendations": _build_recommendations(rows),
    }


def render_buyer_committee_alignment_markdown(report: dict[str, Any]) -> str:
    """Render buyer committee alignment report as Markdown."""
    summary = report.get("summary", {})
    lines = [
        "# Buyer Committee Alignment",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Generated: {report['generated_at']}",
        f"Units analyzed: {report.get('unit_count', 0)}",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Average alignment score | {summary.get('average_alignment_score', 0.0):.1f} |",
        f"| Fully covered units | {summary.get('fully_covered_units', 0)} |",
        f"| Units with gaps | {summary.get('units_with_gaps', 0)} |",
        "",
        "## Alignment",
        "",
    ]

    if report.get("units"):
        lines.extend(
            [
                "| Unit | Domain | Score | Covered Roles | Missing Roles | Next Action |",
                "|------|--------|-------|---------------|---------------|-------------|",
            ]
        )
        for row in report["units"]:
            covered = _labels(row.get("covered_roles", []))
            missing = _labels(row.get("missing_roles", []))
            lines.append(
                f"| {row['title']} | {row['domain']} | {row['alignment_score']:.1f} | "
                f"{covered or '-'} | {missing or '-'} | {row['recommended_next_action']} |"
            )
    else:
        lines.append(
            "- No buildable units available. Add buyer_roles, stakeholders, proof_points, "
            "objections, or decision_criteria metadata to assess committee coverage."
        )

    lines.extend(["", "## Role Coverage", "", "| Role | Covered Units | Missing Units |", "|------|---------------|---------------|"])
    for role in REQUIRED_BUYER_ROLES:
        role_summary = summary.get("role_coverage", {}).get(role, {})
        lines.append(
            f"| {ROLE_LABELS[role]} | {role_summary.get('covered_units', 0)} | "
            f"{role_summary.get('missing_units', 0)} |"
        )

    lines.extend(["", "## Recommendations", ""])
    for recommendation in report.get("recommendations", []):
        lines.append(f"- {recommendation}")

    return "\n".join(lines).rstrip() + "\n"


def render_buyer_committee_alignment_json(report: dict[str, Any]) -> str:
    """Render buyer committee alignment report as stable formatted JSON."""
    return json.dumps(report, indent=2, sort_keys=True, default=str)


def _build_unit_alignment(unit: Any) -> dict[str, Any]:
    metadata = _metadata(unit)
    role_evidence = {
        role: _evidence_for_role(role, metadata)
        for role in REQUIRED_BUYER_ROLES
    }
    covered_roles = [role for role in REQUIRED_BUYER_ROLES if role_evidence[role]]
    missing_roles = [role for role in REQUIRED_BUYER_ROLES if role not in covered_roles]
    alignment_score = round((len(covered_roles) / len(REQUIRED_BUYER_ROLES)) * 100, 1)

    return {
        "idea_id": str(getattr(unit, "id", "")),
        "title": str(getattr(unit, "title", "Untitled")),
        "domain": str(getattr(unit, "domain", "") or "general"),
        "alignment_score": alignment_score,
        "covered_roles": covered_roles,
        "missing_roles": missing_roles,
        "role_evidence": role_evidence,
        "recommended_next_action": _next_action(missing_roles),
    }


def _build_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    role_coverage = {
        role: {
            "covered_units": sum(1 for row in rows if role in row["covered_roles"]),
            "missing_units": sum(1 for row in rows if role in row["missing_roles"]),
        }
        for role in REQUIRED_BUYER_ROLES
    }
    return {
        "unit_count": len(rows),
        "average_alignment_score": round(
            sum(row["alignment_score"] for row in rows) / len(rows), 1
        )
        if rows
        else 0.0,
        "fully_covered_units": sum(1 for row in rows if not row["missing_roles"]),
        "units_with_gaps": sum(1 for row in rows if row["missing_roles"]),
        "role_coverage": role_coverage,
    }


def _build_recommendations(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return [
            "Add buyer committee metadata to buildable units before running alignment review.",
            "Capture at least one proof point or decision criterion for each required buyer role.",
        ]

    recommendations = []
    missing_counts = {
        role: sum(1 for row in rows if role in row["missing_roles"])
        for role in REQUIRED_BUYER_ROLES
    }
    for role, count in sorted(missing_counts.items(), key=lambda item: (-item[1], ROLE_LABELS[item[0]])):
        if count:
            recommendations.append(f"Close {ROLE_LABELS[role].lower()} gaps on {count} unit(s).")

    low_alignment = [row for row in rows if row["alignment_score"] < 60]
    if low_alignment:
        recommendations.append(
            f"Prioritize committee discovery for {len(low_alignment)} unit(s) below 60 alignment."
        )
    if not recommendations:
        recommendations.append("Maintain role-specific proof points for every committee member.")
    return recommendations


def _evidence_for_role(role: str, metadata: dict[str, Any]) -> list[str]:
    evidence: set[str] = set()
    fields = {
        "buyer_roles": metadata.get("buyer_roles"),
        "stakeholders": metadata.get("stakeholders"),
        "proof_points": metadata.get("proof_points"),
        "objections": metadata.get("objections"),
        "decision_criteria": metadata.get("decision_criteria"),
    }
    for field_name, value in fields.items():
        for text in _flatten_metadata(value):
            if _matches_role(role, text):
                evidence.add(field_name)
                break
    return sorted(evidence)


def _flatten_metadata(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, dict):
        flattened: list[str] = []
        for key, item in value.items():
            flattened.extend(_flatten_metadata(key))
            flattened.extend(_flatten_metadata(item))
        return flattened
    if isinstance(value, (list, tuple, set)):
        flattened = []
        for item in value:
            flattened.extend(_flatten_metadata(item))
        return flattened
    return [str(value)]


def _matches_role(role: str, text: str) -> bool:
    normalized = _normalize(text)
    return any(_contains_alias(normalized, alias) for alias in _ROLE_ALIASES[role])


def _contains_alias(normalized_text: str, alias: str) -> bool:
    normalized_alias = _normalize(alias)
    return bool(re.search(rf"\b{re.escape(normalized_alias)}\b", normalized_text))


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", value.lower())).strip()


def _next_action(missing_roles: list[str]) -> str:
    if not missing_roles:
        return "Maintain committee-specific proof points"
    if "economic_buyer" in missing_roles:
        return "Validate budget owner value metrics"
    if "champion" in missing_roles:
        return "Identify and enable an internal champion"
    if "technical_evaluator" in missing_roles:
        return "Add technical evaluation criteria and proof"
    if "legal_security" in missing_roles:
        return "Prepare security, legal, and compliance responses"
    return "Document end-user workflow impact"


def _labels(roles: list[str]) -> str:
    return ", ".join(ROLE_LABELS.get(role, role) for role in roles)


def _metadata(unit: Any) -> dict[str, Any]:
    metadata = getattr(unit, "metadata", None)
    return metadata if isinstance(metadata, dict) else {}
