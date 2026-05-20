"""Security review exports for persisted design briefs."""

from __future__ import annotations

import csv
import json
from io import StringIO
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.design_brief.security_review.v1"
KIND = "max.design_brief.security_review"

CSV_COLUMNS: tuple[str, ...] = (
    "review_id",
    "brief_id",
    "brief_title",
    "threat_model",
    "security_controls",
    "compliance_requirements",
    "risk_assessment",
)


def build_design_brief_security_review(store: Store, brief_id: str) -> dict[str, Any] | None:
    """Build a deterministic security review artifact from a persisted design brief."""
    design_brief = store.get_design_brief(brief_id)
    if not design_brief:
        return None

    review_id = _text(design_brief.get("security_review_id")) or f"{design_brief['id']}-security-review"
    threat_model = _text(
        design_brief.get("threat_model")
        or design_brief.get("security_threat_model")
        or design_brief.get("merged_product_concept")
        or design_brief.get("title")
    )
    controls = _string_list(design_brief.get("security_controls"))
    if not controls:
        controls = _default_controls(design_brief)
    compliance = _string_list(design_brief.get("compliance_requirements") or design_brief.get("compliance"))
    risks = _string_list(design_brief.get("risk_assessment") or design_brief.get("security_risks") or design_brief.get("risks"))
    risk_level = _risk_level(risks, controls, compliance)

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
            "title": design_brief.get("title", "Untitled design brief"),
            "domain": design_brief.get("domain", ""),
            "design_status": design_brief.get("design_status", ""),
            "readiness_score": float(design_brief.get("readiness_score") or 0.0),
        },
        "review": {
            "id": review_id,
            "threat_model": threat_model or "Not specified",
            "security_controls": controls,
            "compliance_requirements": compliance,
            "risk_assessment": risks,
            "risk_level": risk_level,
        },
        "summary": {
            "security_control_count": len(controls),
            "compliance_requirement_count": len(compliance),
            "risk_count": len(risks),
            "risk_level": risk_level,
        },
    }


def render_design_brief_security_review(report: dict[str, Any], fmt: str = "json") -> str:
    """Render a security review as JSON, Markdown, or CSV."""
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt == "csv":
        return render_design_brief_security_review_csv(report)
    if fmt != "markdown":
        raise ValueError(f"Unsupported security review format: {fmt}")
    return _render_markdown(report)


def render_design_brief_security_review_csv(report: dict[str, Any]) -> str:
    """Render security review artifact fields as a deterministic CSV."""
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerow(_csv_row(report))
    return output.getvalue()


def security_review_filename(design_brief: dict[str, Any], *, fmt: str = "markdown") -> str:
    extension = {"csv": "csv", "json": "json"}.get(fmt, "md")
    return f"{_filename_part(str(design_brief.get('id') or 'design-brief'))}-security-review.{extension}"


def _render_markdown(report: dict[str, Any]) -> str:
    brief = _dict_value(report.get("design_brief"))
    review = _dict_value(report.get("review"))
    lines = [
        f"# Security Review: {_text(brief.get('title'), 'Untitled design brief')}",
        "",
        f"Schema: `{_text(report.get('schema_version'), 'unknown')}`",
        f"Design brief: `{_text(brief.get('id'), 'unknown')}`",
        f"Review ID: `{_text(review.get('id'), 'unknown')}`",
        "",
        "## Threat Model",
        "",
        f"- {_text(review.get('threat_model'), 'Not specified')}",
        "",
        "## Security Controls",
        "",
    ]
    lines.extend(f"- {item}" for item in _string_list(review.get("security_controls")) or ["None"])
    lines.extend(["", "## Compliance Requirements", ""])
    lines.extend(f"- {item}" for item in _string_list(review.get("compliance_requirements")) or ["None"])
    lines.extend(["", "## Risk Assessment", ""])
    lines.extend(f"- {item}" for item in _string_list(review.get("risk_assessment")) or ["None"])
    lines.append(f"- Risk level: {_text(review.get('risk_level'), 'unknown')}")
    return "\n".join(lines).rstrip() + "\n"


def _csv_row(report: dict[str, Any]) -> dict[str, str]:
    brief = _dict_value(report.get("design_brief"))
    review = _dict_value(report.get("review"))
    row = {
        "review_id": review.get("id"),
        "brief_id": brief.get("id"),
        "brief_title": brief.get("title"),
        "threat_model": review.get("threat_model"),
        "security_controls": review.get("security_controls"),
        "compliance_requirements": review.get("compliance_requirements"),
        "risk_assessment": review.get("risk_assessment"),
    }
    return {column: _csv_text(row.get(column)) for column in CSV_COLUMNS}


def _default_controls(design_brief: dict[str, Any]) -> list[str]:
    controls = ["Confirm authentication, authorization, and audit logging before build."]
    text = " ".join(_string_list(design_brief.get("risks")) + _string_list(design_brief.get("tech_approach"))).lower()
    if any(keyword in text for keyword in ("privacy", "pii", "customer data", "telemetry")):
        controls.append("Validate data minimization and retention handling.")
    if any(keyword in text for keyword in ("oauth", "token", "credential", "api")):
        controls.append("Review credential storage and least-privilege scopes.")
    return controls


def _risk_level(risks: list[str], controls: list[str], compliance: list[str]) -> str:
    risk_text = " ".join(risks).lower()
    if any(keyword in risk_text for keyword in ("critical", "credential", "oauth", "pii", "privacy", "security")):
        return "high"
    if risks or compliance or len(controls) > 1:
        return "medium"
    return "low"


def _csv_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return _text(value)
    if isinstance(value, (list, tuple, set)):
        return "; ".join(item for item in (_text(item) for item in value) if item)
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    return _text(value)


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, dict):
        return [f"{key}: {item}" for key, item in value.items() if _text(key) or _text(item)]
    if isinstance(value, (list, tuple, set)):
        return [_text(item) for item in value if _text(item)]
    return [_text(value)] if _text(value) else []


def _dict_value(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: Any, default: str = "") -> str:
    return " ".join(str(value).strip().split()) if value is not None and str(value).strip() else default


def _filename_part(value: str) -> str:
    cleaned = "".join(char if char.isalnum() else "-" for char in value).strip("-")
    return "-".join(part for part in cleaned.split("-") if part) or "design-brief"
