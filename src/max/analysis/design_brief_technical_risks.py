"""Deterministic technical risks analysis for persisted design briefs."""

from __future__ import annotations

import json
from typing import Any

from max.store.db import Store

KIND = "max.design_brief.technical_risks"
SCHEMA_VERSION = "max.design_brief.technical_risks.v1"


def build_design_brief_technical_risks(
    store: Store, brief_id: str
) -> dict[str, Any] | None:
    """Build technical risks analysis from a persisted design brief."""
    design_brief = store.get_design_brief(brief_id)
    if not design_brief:
        return None

    source_ideas = _source_ideas(store, design_brief)
    lead_idea = next((idea for idea in source_ideas if idea.get("role") == "lead"), None)
    source_idea_ids = [idea["id"] for idea in source_ideas if not idea.get("missing")]
    if not source_idea_ids:
        source_idea_ids = list(design_brief.get("source_idea_ids") or [])

    risks = _technical_risks(design_brief, source_ideas, lead_idea)
    risks = _prioritize_risks(risks)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": {
            "project": "max",
            "entity_type": "design_brief",
            "id": design_brief["id"],
            "generated_at": design_brief.get("updated_at") or design_brief.get("created_at"),
        },
        "design_brief": {
            "id": design_brief["id"],
            "title": design_brief["title"],
            "domain": design_brief.get("domain", ""),
            "theme": design_brief.get("theme", ""),
            "readiness_score": float(design_brief.get("readiness_score") or 0.0),
            "design_status": design_brief.get("design_status", ""),
            "lead_idea_id": design_brief.get("lead_idea_id", ""),
            "source_idea_ids": source_idea_ids,
        },
        "summary": {
            "risk_count": len(risks),
            "critical_risk_count": sum(1 for r in risks if r["severity"] == "critical"),
            "high_risk_count": sum(1 for r in risks if r["severity"] == "high"),
            "medium_risk_count": sum(1 for r in risks if r["severity"] == "medium"),
            "low_risk_count": sum(1 for r in risks if r["severity"] == "low"),
        },
        "technical_risks": risks,
        "source_ideas": source_ideas,
    }


def render_design_brief_technical_risks(
    report: dict[str, Any], fmt: str = "json"
) -> str:
    """Render technical risks analysis as JSON or Markdown."""
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt != "markdown":
        raise ValueError(f"Unsupported technical risks format: {fmt}")

    brief = report.get("design_brief") or {}
    summary = report.get("summary") or {}
    risks = _markdown_dicts(report.get("technical_risks"))
    title = _compact(brief.get("title")) or "Untitled design brief"
    brief_id = _compact(brief.get("id")) or "unknown"
    source_idea_ids = _csv_items(brief.get("source_idea_ids"))

    lines = [
        f"# Technical Risks: {title}",
        "",
        f"Schema: `{report.get('schema_version') or SCHEMA_VERSION}`",
        f"Design brief: `{brief_id}`",
        f"Status: {brief.get('design_status') or 'unknown'}",
        f"Readiness: {float(brief.get('readiness_score') or 0.0):.1f}/100",
        f"Source ideas: {_inline_ids(source_idea_ids) if source_idea_ids else 'design brief'}",
        "",
        "## Risk Summary",
        "",
        f"- Total risks: {summary.get('risk_count', 0)}",
        f"- Critical: {summary.get('critical_risk_count', 0)}",
        f"- High: {summary.get('high_risk_count', 0)}",
        f"- Medium: {summary.get('medium_risk_count', 0)}",
        f"- Low: {summary.get('low_risk_count', 0)}",
        "",
        "## Technical Risks",
        "",
    ]

    if not risks:
        lines.extend(["- None", ""])
    else:
        for risk in risks:
            risk_id = _markdown_text(risk.get("id"), "?")
            category = _markdown_text(risk.get("category"), "uncategorized")
            severity = _markdown_text(risk.get("severity"), "unknown")
            likelihood = _markdown_text(risk.get("likelihood"), "unknown")
            description = _markdown_text(risk.get("description"), "No description")
            mitigation = _markdown_text(risk.get("mitigation_strategy"), "No mitigation strategy")
            owner = _markdown_text(risk.get("owner"), "unassigned")

            lines.extend(
                [
                    f"### {risk_id}: {category}",
                    "",
                    f"- **Severity**: {severity}",
                    f"- **Likelihood**: {likelihood}",
                    f"- **Description**: {description}",
                    f"- **Mitigation strategy**: {mitigation}",
                    f"- **Owner**: {owner}",
                    "",
                ]
            )

    return "\n".join(lines)


def _source_ideas(store: Store, design_brief: dict[str, Any]) -> list[dict[str, Any]]:
    """Retrieve source ideas for the design brief."""
    ideas: list[dict[str, Any]] = []
    lead_id = design_brief.get("lead_idea_id")
    source_ids = design_brief.get("source_idea_ids") or []

    if lead_id:
        unit = store.get_buildable_unit(lead_id)
        if unit:
            data = unit.model_dump(mode="json")
            ideas.append({**data, "role": "lead"})
        else:
            ideas.append({"id": lead_id, "role": "lead", "missing": True})

    for idea_id in source_ids:
        if idea_id == lead_id:
            continue
        unit = store.get_buildable_unit(idea_id)
        if unit:
            data = unit.model_dump(mode="json")
            ideas.append({**data, "role": "member"})
        else:
            ideas.append({"id": idea_id, "role": "member", "missing": True})

    return ideas


def _technical_risks(
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
    lead_idea: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Extract and structure technical risks from design brief and source ideas."""
    risks: list[dict[str, Any]] = []

    # Extract risks from design brief risks field
    brief_risks = design_brief.get("risks") or []
    if isinstance(brief_risks, list):
        for idx, risk_text in enumerate(brief_risks, start=1):
            if _compact(risk_text):
                risks.append(
                    _risk(
                        risk_id=f"RISK-{idx:02d}",
                        category="domain",
                        severity=_infer_severity(risk_text),
                        likelihood=_infer_likelihood(risk_text),
                        description=_compact(risk_text),
                        mitigation_strategy="Review with domain experts before implementation",
                        owner="product_owner",
                        source="design_brief.risks",
                    )
                )

    # Extract risks from lead idea if available
    if lead_idea and not lead_idea.get("missing"):
        idea_risks = lead_idea.get("domain_risks") or []
        if isinstance(idea_risks, list):
            for idx, risk_text in enumerate(idea_risks, start=len(risks) + 1):
                if _compact(risk_text):
                    risks.append(
                        _risk(
                            risk_id=f"RISK-{idx:02d}",
                            category="implementation",
                            severity=_infer_severity(risk_text),
                            likelihood=_infer_likelihood(risk_text),
                            description=_compact(risk_text),
                            mitigation_strategy="Address during technical design phase",
                            owner="engineering_lead",
                            source=f"lead_idea.{lead_idea['id']}.domain_risks",
                        )
                    )

    # Add default risk if none found
    if not risks:
        risks.append(
            _risk(
                risk_id="RISK-01",
                category="general",
                severity="medium",
                likelihood="medium",
                description="No explicit technical risks documented; review before implementation",
                mitigation_strategy="Conduct technical risk assessment workshop with stakeholders",
                owner="product_owner",
                source="fallback",
            )
        )

    return risks


def _risk(
    *,
    risk_id: str,
    category: str,
    severity: str,
    likelihood: str,
    description: str,
    mitigation_strategy: str,
    owner: str,
    source: str,
) -> dict[str, Any]:
    """Create a structured risk record."""
    return {
        "id": risk_id,
        "category": category,
        "severity": severity,
        "likelihood": likelihood,
        "description": description,
        "mitigation_strategy": mitigation_strategy,
        "owner": owner,
        "source": source,
    }


def _prioritize_risks(risks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sort risks by severity and likelihood, then reassign IDs."""
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    likelihood_order = {"very_high": 0, "high": 1, "medium": 2, "low": 3, "very_low": 4}

    sorted_risks = sorted(
        risks,
        key=lambda r: (
            severity_order.get(r["severity"], 99),
            likelihood_order.get(r["likelihood"], 99),
            r["category"],
        ),
    )

    return [
        {**risk, "id": f"RISK-{idx:02d}"}
        for idx, risk in enumerate(sorted_risks, start=1)
    ]


def _infer_severity(risk_text: str) -> str:
    """Infer severity from risk description keywords."""
    text_lower = risk_text.lower()
    if any(term in text_lower for term in ["critical", "blocking", "severe", "catastrophic"]):
        return "critical"
    if any(term in text_lower for term in ["high", "major", "significant"]):
        return "high"
    if any(term in text_lower for term in ["low", "minor", "trivial"]):
        return "low"
    return "medium"


def _infer_likelihood(risk_text: str) -> str:
    """Infer likelihood from risk description keywords."""
    text_lower = risk_text.lower()
    if any(term in text_lower for term in ["certain", "definite", "guaranteed"]):
        return "very_high"
    if any(term in text_lower for term in ["likely", "probable", "expected"]):
        return "high"
    if any(term in text_lower for term in ["unlikely", "rare", "improbable"]):
        return "low"
    if any(term in text_lower for term in ["very unlikely", "almost impossible"]):
        return "very_low"
    return "medium"


def _markdown_dicts(value: Any) -> list[dict[str, Any]]:
    """Extract list of dicts from value."""
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _markdown_text(value: Any, fallback: str = "") -> str:
    """Convert value to markdown-safe text."""
    if value is None:
        return fallback
    text = str(value).strip()
    return text if text else fallback


def _compact(value: Any) -> str:
    """Compact whitespace in value."""
    if value is None:
        return ""
    return " ".join(str(value).split())


def _csv_items(value: Any) -> list[str]:
    """Convert value to list of strings."""
    if value is None:
        return []
    if isinstance(value, list):
        return [_compact(item) for item in value if _compact(item)]
    if isinstance(value, str):
        return [_compact(value)] if _compact(value) else []
    return []


def _inline_ids(ids: list[str]) -> str:
    """Format IDs as inline code list."""
    if not ids:
        return "none"
    return ", ".join(f"`{id_}`" for id_ in ids)
