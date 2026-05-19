"""Compliance questionnaire gap analysis export."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.compliance_questionnaire_gap.v1"
KIND = "max.compliance_questionnaire_gap"

_STATUS_ORDER = {"missing": 0, "partial": 1, "ready": 2}


def build_compliance_questionnaire_gap_export(store: Store, domain: str | None = None) -> dict[str, Any]:
    rows = [_row(unit) for unit in store.get_buildable_units(limit=1000, domain=domain)]
    rows.sort(key=lambda row: (_STATUS_ORDER[row["response_readiness"]], row["due_date"] or "9999-12-31", row["idea_id"]))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {"project": "max", "entity_type": "compliance_questionnaire_gap", "domain_filter": domain},
        "gap_rows": rows,
        "summary": _summary(rows),
        "missing_evidence": [item for row in rows for item in row["missing_evidence"]],
        "next_actions": _recommendations(rows),
    }


def render_compliance_questionnaire_gap_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_compliance_questionnaire_gap_markdown(report: dict[str, Any]) -> str:
    lines = ["# Compliance Questionnaire Gap Analysis", "", f"Schema: `{report['schema_version']}`", f"Generated: {report['generated_at']}", "", "## Requirements", ""]
    if report.get("gap_rows"):
        lines.extend(["| Idea | Requirement | Readiness | Score | Missing Evidence | Owner | Due | Action |", "|------|-------------|-----------|-------|------------------|-------|-----|--------|"])
        for row in report["gap_rows"]:
            lines.append(
                f"| {_md(row['title'])} | {_md(row['requirement'])} | {row['response_readiness']} | "
                f"{row['readiness_score']} | {_md(', '.join(item['artifact'] for item in row['missing_evidence']) or 'None')} | "
                f"{_md(row['owner'])} | {_md(row['due_date'] or 'Unknown')} | {_md(row['next_action'])} |"
            )
    else:
        lines.append("- No compliance questionnaire gap metadata available.")
    lines.extend(["", "## Next Actions", ""])
    lines.extend(f"- {item}" for item in report.get("next_actions", []))
    return "\n".join(lines).rstrip() + "\n"


def _row(unit: Any) -> dict[str, Any]:
    metadata = _metadata(unit)
    requirement = _text(metadata.get("requirement") or metadata.get("questionnaire_requirement") or getattr(unit, "title", "") or "Requirement")
    evidence = _list(metadata.get("available_evidence") or metadata.get("evidence"))
    required = _list(metadata.get("required_evidence") or metadata.get("required_artifacts"))
    missing = [artifact for artifact in required if artifact not in evidence]
    explicit_missing = _list(metadata.get("missing_evidence") or metadata.get("missing_artifacts"))
    for artifact in explicit_missing:
        if artifact not in missing:
            missing.append(artifact)
    owner = _text(metadata.get("owner") or metadata.get("evidence_owner") or "Unassigned")
    readiness = _readiness(evidence, required, missing)
    score = _readiness_score(evidence, required, missing)
    return {
        "idea_id": str(getattr(unit, "id", "")),
        "title": _text(getattr(unit, "title", "")) or "Untitled",
        "requirement": requirement,
        "requirement_coverage": {
            "required_artifacts": required,
            "available_evidence": evidence,
            "coverage_percent": score,
        },
        "missing_evidence": [{"artifact": artifact, "owner": owner} for artifact in missing],
        "owner": owner,
        "due_date": _text(metadata.get("due_date") or metadata.get("questionnaire_due_date")),
        "response_readiness": readiness,
        "readiness_score": score,
        "next_action": _next_action(readiness, owner, missing),
    }


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "requirement_count": len(rows),
        "readiness_score": round(sum(row["readiness_score"] for row in rows) / len(rows), 1) if rows else 0.0,
        "readiness_counts": {status: sum(1 for row in rows if row["response_readiness"] == status) for status in _STATUS_ORDER},
        "missing_evidence_count": sum(len(row["missing_evidence"]) for row in rows),
    }


def _recommendations(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return ["Capture questionnaire requirements, available evidence, missing artifacts, owners, and due dates."]
    recommendations = []
    if any(row["response_readiness"] == "missing" for row in rows):
        recommendations.append("Prioritize missing questionnaire evidence before customer response drafting.")
    if any(row["owner"] == "Unassigned" for row in rows):
        recommendations.append("Assign evidence owners for unowned compliance requirements.")
    if any(row["response_readiness"] == "partial" for row in rows):
        recommendations.append("Close partial evidence gaps and update response readiness.")
    return recommendations or ["Package ready evidence for questionnaire response review."]


def _readiness(evidence: list[str], required: list[str], missing: list[str]) -> str:
    if missing and not evidence:
        return "missing"
    if missing:
        return "partial"
    if required or evidence:
        return "ready"
    return "missing"


def _readiness_score(evidence: list[str], required: list[str], missing: list[str]) -> int:
    if required:
        return round(max(0, min(100, ((len(required) - len(missing)) / len(required)) * 100)))
    if evidence and not missing:
        return 100
    return 0


def _next_action(readiness: str, owner: str, missing: list[str]) -> str:
    if readiness == "ready":
        return "Prepare response for compliance review."
    if missing:
        return f"{owner} to provide {missing[0]}."
    return f"{owner} to define required evidence."


def _metadata(unit: Any) -> dict[str, Any]:
    metadata = getattr(unit, "metadata", None)
    return metadata if isinstance(metadata, dict) else {}


def _list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [part.strip() for part in value.replace(";", ",").split(",") if part.strip()]
    return [_text(item) for item in value if _text(item)] if isinstance(value, (list, tuple, set)) else [_text(value)]


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""


def _md(value: Any) -> str:
    return str(value).replace("|", "\\|")
