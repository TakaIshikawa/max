"""LLM prompt version adoption export report."""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any, Iterable

SCHEMA_VERSION = "max.llm_prompt_version_adoption_report.v1"
KIND = "max.llm_prompt_version_adoption_report"
DEFAULT_GENERATED_AT = "2026-05-31T00:00:00+00:00"


def generate_llm_prompt_version_adoption_report(current_versions: Iterable[dict[str, Any]], calls: Iterable[dict[str, Any]], *, old_version_traffic_threshold: int = 1, generated_at: str = DEFAULT_GENERATED_AT) -> dict[str, Any]:
    current = {_text(item.get("template") or item.get("prompt_template") or item.get("name")): _text(item.get("current_version") or item.get("version")) for item in current_versions}
    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for item in calls:
        template = _text(item.get("template") or item.get("prompt_template") or item.get("name")) or "default"
        version = _text(item.get("version") or item.get("prompt_version")) or "unknown"
        counts[template][version] += _int(item.get("call_count")) or 1
        current.setdefault(template, _text(item.get("current_version")) or version)
    rows = []
    for template in sorted(current):
        versions = dict(counts.get(template, {}))
        total = sum(versions.values())
        current_version = current[template] or "unknown"
        current_count = versions.get(current_version, 0)
        old_versions = {version: count for version, count in versions.items() if version != current_version and count >= old_version_traffic_threshold}
        adoption = round(current_count / total * 100, 2) if total else 0.0
        severity = "critical" if old_versions and adoption < 50 else ("warn" if old_versions else "ok")
        rows.append({"template": template, "current_version": current_version, "call_count": total, "current_version_call_count": current_count, "adoption_percent": adoption, "old_versions": old_versions, "severity": severity})
    rows.sort(key=lambda row: (row["adoption_percent"], row["template"]))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "generated_at": generated_at, "summary": {"template_count": len(rows), "flagged_template_count": sum(1 for row in rows if row["old_versions"]), "call_count": sum(row["call_count"] for row in rows)}, "rows": rows}


def render_llm_prompt_version_adoption_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_llm_prompt_version_adoption_report_markdown(report: dict[str, Any]) -> str:
    lines = ["# LLM Prompt Version Adoption Report", "", f"Flagged templates: {report.get('summary', {}).get('flagged_template_count', 0)}", ""]
    for row in report.get("rows") or []:
        old = ", ".join(f"{version}={count}" for version, count in sorted(row["old_versions"].items())) or "none"
        lines.append(f"- {row['template']} current {row['current_version']}: {row['adoption_percent']}% adoption; old traffic {old}")
    return "\n".join(lines).rstrip() + "\n"


def _int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
