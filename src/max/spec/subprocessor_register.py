"""Generate deterministic subprocessor registers for TactSpec previews."""

from __future__ import annotations

import csv
from io import StringIO
from typing import Any

SCHEMA_VERSION = "max.spec.subprocessor_register.v1"
SUBPROCESSOR_REGISTER_SCHEMA_VERSION = SCHEMA_VERSION
KIND = "max.spec.subprocessor_register"
CSV_COLUMNS = ("vendor_id", "name", "purpose", "data_category", "region", "risk_level", "contract_status", "review_cadence", "action")
_VENDORS = {"openai": ("OpenAI", "AI processing", "prompt and workflow content"), "slack": ("Slack", "workflow notifications", "message payloads"), "stripe": ("Stripe", "payment processing", "payment and billing data"), "github": ("GitHub", "source and CI/CD", "repository and deployment metadata"), "postgres": ("Postgres provider", "database hosting", "application records"), "aws": ("AWS", "cloud hosting", "application and operational data"), "gcp": ("Google Cloud", "cloud hosting", "application and operational data"), "azure": ("Azure", "cloud hosting", "application and operational data")}


def generate_subprocessor_register(tact_spec: dict[str, Any]) -> dict[str, Any]:
    ctx = _context(tact_spec)
    subprocessors = _subprocessors(ctx["text"])
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "source": _source(tact_spec), "summary": {"title": ctx["title"], "workflow_context": ctx["workflow"], "subprocessor_count": len(subprocessors), "high_risk_count": sum(1 for item in subprocessors if item["risk_level"] == "high")}, "subprocessors": subprocessors, "recommendations": _recommendations(subprocessors)}


def render_subprocessor_register_markdown(register: dict[str, Any]) -> str:
    title = register.get("summary", {}).get("title") or "TactSpec"
    lines = [f"# {title} Subprocessor Register", "", f"- Schema version: {register.get('schema_version')}", "", "## Subprocessors", ""]
    if register.get("subprocessors"):
        lines.extend(["| Vendor | Purpose | Data Category | Region | Risk | Contract | Review | Action |", "|--------|---------|---------------|--------|------|----------|--------|--------|"])
        for row in register["subprocessors"]:
            lines.append(f"| {row['name']} | {row['purpose']} | {row['data_category']} | {row['region']} | {row['risk_level']} | {row['contract_status']} | {row['review_cadence']} | {row['action']} |")
    else:
        lines.append("- No subprocessors inferred.")
    return "\n".join(lines).rstrip() + "\n"


def render_subprocessor_register_csv(register: dict[str, Any]) -> str:
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in register.get("subprocessors", []):
        writer.writerow({field: row.get(field) for field in CSV_COLUMNS})
    return output.getvalue()


def _subprocessors(text: str) -> list[dict[str, str]]:
    lowered = text.lower()
    rows = []
    for key, (name, purpose, data_category) in sorted(_VENDORS.items()):
        if key in lowered:
            sensitive = any(term in lowered for term in ("payment", "customer", "personal", "privacy", "health", "email"))
            risk = "high" if sensitive and key in {"openai", "slack", "stripe"} else "medium"
            rows.append({"vendor_id": key, "name": name, "purpose": purpose, "data_category": data_category, "region": "unknown", "risk_level": risk, "contract_status": "needs_review", "review_cadence": "quarterly" if risk == "high" else "semiannual", "action": "Confirm DPA, region, retention, and security review before launch."})
    if not rows:
        rows.append({"vendor_id": "unknown_vendor", "name": "Unknown vendor", "purpose": "to be confirmed", "data_category": "to be confirmed", "region": "unknown", "risk_level": "medium", "contract_status": "missing", "review_cadence": "before launch", "action": "Identify subprocessors from stack and integration metadata."})
    return rows


def _recommendations(rows: list[dict[str, str]]) -> list[str]:
    if any(row["contract_status"] in {"missing", "needs_review"} for row in rows):
        return ["Confirm contract status, DPA coverage, processing region, and review cadence for each subprocessor."]
    return ["Maintain the register during vendor and integration changes."]


def _context(spec: dict[str, Any]) -> dict[str, str]:
    spec = spec if isinstance(spec, dict) else {}
    project = spec.get("project") if isinstance(spec.get("project"), dict) else {}
    return {"title": _text(project.get("title")) or "Untitled TactSpec", "workflow": _text(project.get("workflow_context") or project.get("summary")) or "primary workflow", "text": str(spec)}


def _source(spec: dict[str, Any]) -> dict[str, Any]:
    source = spec.get("source") if isinstance(spec.get("source"), dict) else {}
    return {"system": source.get("system") or "max", "type": source.get("type") or "tact_spec_preview", "idea_id": source.get("idea_id"), "status": source.get("status"), "domain": source.get("domain"), "category": source.get("category"), "tact_spec_schema_version": spec.get("schema_version"), "tact_spec_kind": spec.get("kind")}


def _text(value: Any) -> str:
    return " ".join(str(value).split()) if value not in (None, "") else ""
