"""Enterprise security questionnaire export."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.enterprise_security_questionnaire.v1"
KIND = "max.enterprise_security_questionnaire"

_SECTIONS = {
    "security": ["encryption", "sso", "mfa", "vulnerability_management"],
    "privacy": ["privacy_policy", "subprocessors", "data_subject_requests"],
    "compliance": ["soc2", "iso27001", "hipaa", "gdpr"],
    "availability": ["uptime_sla", "backup", "disaster_recovery", "incident_response"],
    "data_handling": ["data_residency", "retention", "deletion", "data_classification"],
}


def build_enterprise_security_questionnaire_export(store: Store, domain: str | None = None) -> dict[str, Any]:
    units = store.get_buildable_units(limit=1000, domain=domain)
    evidence = _merge_metadata(units)
    sections = [_section(name, questions, evidence) for name, questions in _SECTIONS.items()]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {"project": "max", "entity_type": "enterprise_security_questionnaire", "domain_filter": domain},
        "summary": _summary(sections),
        "sections": sections,
    }


def render_enterprise_security_questionnaire_markdown(report: dict[str, Any]) -> str:
    lines = ["# Enterprise Security Questionnaire", "", f"Schema: `{report['schema_version']}`", f"Generated: {report['generated_at']}", ""]
    for section in report.get("sections", []):
        lines.extend([f"## {section['section_label']}", "", "| Question | Answer | Evidence |", "|----------|--------|----------|"])
        for answer in section["answers"]:
            lines.append(f"| {_md(answer['question'])} | {_md(answer['answer'])} | {_md(', '.join(answer['evidence_references']) or 'Unknown')} |")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_enterprise_security_questionnaire_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str)


def _section(name: str, questions: list[str], evidence: dict[str, Any]) -> dict[str, Any]:
    answers = []
    for question in questions:
        item = evidence.get(question, {})
        answer = _text(item.get("answer")) if isinstance(item, dict) else _text(item)
        refs = item.get("evidence_references", []) if isinstance(item, dict) else []
        answers.append({
            "question_key": question,
            "question": question.replace("_", " ").title(),
            "answer": answer or "Unknown",
            "answer_status": "known" if answer else "unknown",
            "evidence_references": _list(refs),
        })
    return {"section": name, "section_label": name.replace("_", " ").title(), "answers": answers}


def _summary(sections: list[dict[str, Any]]) -> dict[str, Any]:
    answers = [answer for section in sections for answer in section["answers"]]
    return {
        "section_count": len(sections),
        "answer_count": len(answers),
        "known_answer_count": sum(1 for answer in answers if answer["answer_status"] == "known"),
        "unknown_answer_count": sum(1 for answer in answers if answer["answer_status"] == "unknown"),
    }


def _merge_metadata(units: list[Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for unit in units:
        metadata = getattr(unit, "metadata", None)
        if not isinstance(metadata, dict):
            continue
        for container in (metadata, metadata.get("security_questionnaire", {}), metadata.get("security", {}), metadata.get("compliance", {})):
            if isinstance(container, dict):
                merged.update(container)
    return merged


def _list(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return [_text(item) for item in value if _text(item)]
    return [_text(value)] if _text(value) else []


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""


def _md(value: Any) -> str:
    return str(value).replace("|", "\\|")
