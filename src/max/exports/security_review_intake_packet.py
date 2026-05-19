"""Security review intake packet export."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.security_review_intake_packet.v1"
KIND = "max.security_review_intake_packet"


def build_security_review_intake_packet_export(store: Store, domain: str | None = None) -> dict[str, Any]:
    rows = [_row(unit) for unit in store.get_buildable_units(limit=1000, domain=domain)]
    rows.sort(key=lambda row: (-len(row["unanswered_questions"]), row["owner"], row["idea_id"]))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {"project": "max", "entity_type": "security_review_intake_packet", "domain_filter": domain},
        "packet_rows": rows,
        "summary": _summary(rows),
        "evidence_inventory": _evidence_inventory(rows),
        "open_questions": [question for row in rows for question in row["unanswered_questions"]],
        "recommendations": _recommendations(rows),
    }


def render_security_review_intake_packet_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_security_review_intake_packet_markdown(report: dict[str, Any]) -> str:
    lines = ["# Security Review Intake Packet", "", f"Schema: `{report['schema_version']}`", f"Generated: {report['generated_at']}", "", "## Intake Rows", ""]
    if report.get("packet_rows"):
        lines.extend(["| Idea | Frameworks | Data Classes | Deployment | Owners | Questions |", "|------|------------|--------------|------------|--------|-----------|"])
        for row in report["packet_rows"]:
            lines.append(f"| {_md(row['title'])} | {_md(', '.join(row['compliance_frameworks']) or 'None')} | {_md(', '.join(row['data_classes']) or 'None')} | {_md(row['deployment_model'])} | {_md(', '.join(row['owners']))} | {len(row['unanswered_questions'])} |")
    else:
        lines.append("- No security review intake metadata available.")
    lines.extend(["", "## Evidence", ""])
    if report.get("evidence_inventory"):
        for item in report["evidence_inventory"]:
            lines.append(f"- {_md(item['evidence_url'])}: {item['idea_count']} idea(s)")
    else:
        lines.append("- No security evidence links provided.")
    lines.extend(["", "## Unanswered Questions", ""])
    if report.get("open_questions"):
        lines.extend(f"- {_md(question)}" for question in report["open_questions"])
    else:
        lines.append("- No unanswered security questions.")
    lines.extend(["", "## Implementation/Security Ownership", ""])
    if report.get("packet_rows"):
        for row in report["packet_rows"]:
            lines.append(f"- {_md(row['title'])}: owner {_md(row['owner'])}; security owner {_md(row['security_owner'])}.")
    else:
        lines.append("- No ownership routing available.")
    lines.extend(["", "## Recommendations", ""])
    lines.extend(f"- {item}" for item in report.get("recommendations", []))
    return "\n".join(lines).rstrip() + "\n"


def _row(unit: Any) -> dict[str, Any]:
    metadata = _metadata(unit)
    owners = _list(metadata.get("owners") or metadata.get("owner"))
    owner = owners[0] if owners else "Unassigned"
    security_owner = _text(metadata.get("security_owner") or metadata.get("security_reviewer") or "Security team")
    controls = _list(metadata.get("security_controls") or metadata.get("controls"))
    frameworks = _list(metadata.get("compliance_frameworks") or metadata.get("frameworks"))
    data_classes = _list(metadata.get("data_classes") or metadata.get("data_classification"))
    evidence = _list(metadata.get("evidence_urls") or metadata.get("evidence_links") or metadata.get("evidence"))
    questions = _questions(metadata, controls, frameworks, data_classes, evidence)
    return {
        "idea_id": str(getattr(unit, "id", "")),
        "title": _text(getattr(unit, "title", "")) or "Untitled",
        "security_controls": controls,
        "compliance_frameworks": frameworks,
        "data_classes": data_classes,
        "subprocessors": _list(metadata.get("subprocessors")),
        "deployment_model": _text(metadata.get("deployment_model") or metadata.get("hosting_model") or "unknown"),
        "evidence_urls": evidence,
        "unanswered_questions": questions,
        "owners": owners or [owner],
        "owner": owner,
        "security_owner": security_owner,
    }


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "packet_count": len(rows),
        "evidence_link_count": sum(len(row["evidence_urls"]) for row in rows),
        "open_question_count": sum(len(row["unanswered_questions"]) for row in rows),
    }


def _evidence_inventory(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    urls = sorted({url for row in rows for url in row["evidence_urls"]})
    return [{"evidence_url": url, "idea_count": sum(1 for row in rows if url in row["evidence_urls"])} for url in urls]


def _recommendations(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return ["Capture security controls, frameworks, data classes, evidence links, deployment model, and owners for review intake."]
    if any(row["unanswered_questions"] for row in rows):
        return ["Resolve unanswered security intake questions before enterprise handoff."]
    return ["Route the packet to implementation and security owners for final review."]


def _questions(metadata: dict[str, Any], controls: list[str], frameworks: list[str], data_classes: list[str], evidence: list[str]) -> list[str]:
    provided = _list(metadata.get("unanswered_questions") or metadata.get("open_questions"))
    questions = list(provided)
    if not controls:
        questions.append("Which security controls apply?")
    if not frameworks:
        questions.append("Which compliance frameworks are in scope?")
    if not data_classes:
        questions.append("Which customer data classes are processed?")
    if not evidence:
        questions.append("Which security evidence links support the review?")
    if not _text(metadata.get("deployment_model") or metadata.get("hosting_model")):
        questions.append("What deployment model will be used?")
    return sorted(dict.fromkeys(questions))


def _metadata(unit: Any) -> dict[str, Any]:
    metadata = getattr(unit, "metadata", None)
    return metadata if isinstance(metadata, dict) else {}


def _list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [part.strip() for part in value.replace(";", ",").split(",") if part.strip()]
    if isinstance(value, dict):
        return [f"{key}: {value[key]}" for key in sorted(value) if _text(value[key])]
    return sorted({_text(item) for item in value if _text(item)}) if isinstance(value, (list, tuple, set)) else [_text(value)]


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""


def _md(value: Any) -> str:
    return str(value).replace("|", "\\|")
