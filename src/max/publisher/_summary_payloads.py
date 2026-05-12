"""Rendering helpers for outbound publisher payload previews."""

from __future__ import annotations

import re
from typing import Any

from max.publisher._tact_spec_publish import dict_value, join_list, optional_text, score_text, source_id, text_or_placeholder, title


def is_design_brief_payload(payload: dict[str, Any]) -> bool:
    return isinstance(payload.get("design_brief"), dict)


def summary_title(payload: dict[str, Any], *, fallback: str = "Max summary") -> str:
    if is_design_brief_payload(payload):
        brief = dict_value(payload, "design_brief")
        return optional_text(brief.get("title")) or optional_text(brief.get("id")) or "Max design brief"
    return title(payload, fallback=fallback)


def summary_markdown(payload: dict[str, Any]) -> str:
    if is_design_brief_payload(payload):
        brief = dict_value(payload, "design_brief")
        return "\n".join(
            [
                f"# {summary_title(payload)}",
                "",
                text_or_placeholder(brief.get("summary")),
                "",
                f"Brief ID: {text_or_placeholder(brief.get('id'))}",
                f"Readiness score: {score_text(brief.get('readiness_score'))}",
                f"Recommendation: {text_or_placeholder(brief.get('recommendation'))}",
                f"Status: {text_or_placeholder(brief.get('design_status'))}",
                f"Lead idea: {text_or_placeholder(brief.get('lead_idea_id'))}",
                f"Source ideas: {join_list(brief.get('source_idea_ids'))}",
                "",
                text_or_placeholder(brief.get("markdown") or brief.get("validation_plan")),
            ]
        )

    source = dict_value(payload, "source")
    project = dict_value(payload, "project")
    execution = dict_value(payload, "execution")
    evidence = dict_value(payload, "evidence")
    evaluation = dict_value(payload, "evaluation")
    quality = dict_value(payload, "quality")
    return "\n".join(
        [
            f"# {summary_title(payload, fallback='Max idea')}",
            "",
            text_or_placeholder(project.get("summary")),
            "",
            f"Idea ID: {text_or_placeholder(source.get('idea_id'))}",
            f"Status: {text_or_placeholder(source.get('status'))}",
            f"Domain: {text_or_placeholder(source.get('domain'))}",
            f"Category: {text_or_placeholder(source.get('category'))}",
            f"Score: {score_text(evaluation.get('overall_score') or quality.get('quality_score'))}",
            f"Recommendation: {text_or_placeholder(evaluation.get('recommendation'))}",
            f"Evidence: insights={join_list(evidence.get('insight_ids'))}; signals={join_list(evidence.get('signal_ids'))}",
            f"Source ideas: {join_list(evidence.get('source_idea_ids'))}",
            f"Validation plan: {text_or_placeholder(execution.get('validation_plan'))}",
        ]
    )


def summary_metadata(payload: dict[str, Any], *, publisher: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    if is_design_brief_payload(payload):
        brief = dict_value(payload, "design_brief")
        data: dict[str, Any] = {
            "publisher": publisher,
            "source_type": "design_brief",
            "design_brief_id": brief.get("id"),
            "source_id": brief.get("id"),
            "source_idea_ids": brief.get("source_idea_ids"),
        }
    else:
        source = dict_value(payload, "source")
        data = {
            "publisher": publisher,
            "source_system": source.get("system", "max"),
            "source_type": source.get("type") or "idea",
            "source_id": source_id(source),
            "idea_id": source.get("idea_id"),
            "design_brief_id": source.get("design_brief_id"),
            "schema_version": payload.get("schema_version"),
            "kind": payload.get("kind"),
        }
    if extra:
        data.update(extra)
    return data


def deterministic_filename(payload: dict[str, Any], *, extension: str = "md") -> str:
    name = summary_title(payload, fallback="max-summary").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", name).strip("-") or "max-summary"
    return f"{slug}.{extension.lstrip('.')}"
