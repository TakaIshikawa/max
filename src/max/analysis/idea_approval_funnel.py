"""Deterministic approval funnel analysis for generated ideas."""

from __future__ import annotations

import csv
import json
from collections import Counter
from collections.abc import Mapping
from io import StringIO
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store


SCHEMA_VERSION = "max.idea_approval_funnel.v1"
KIND = "max.idea_approval_funnel"
APPROVED_OUTCOMES = {"approved", "published"}
REJECTED_OUTCOMES = {"rejected", "abandoned"}
POSITIVE_RECOMMENDATIONS = {"yes", "strong_yes"}
CSV_COLUMNS = (
    "section",
    "key",
    "count",
    "generated",
    "evaluated",
    "recommended",
    "approved_or_published",
    "rejected",
    "publication_attempted",
    "conversion_risk",
)


def build_idea_approval_funnel(
    store: "Store",
    *,
    limit: int = 500,
    domain: str | None = None,
) -> dict[str, Any]:
    """Summarize ideas through evaluation, approval, rejection, and publication."""
    if limit < 1:
        raise ValueError("limit must be at least 1")

    units = store.get_buildable_units(limit=limit, domain=domain)
    rows = [_idea_row(store, unit) for unit in units]
    stages = _stage_counts(rows)
    summary = {
        **stages,
        "evaluation_rate": _rate(stages["evaluated"], stages["generated"]),
        "recommendation_rate": _rate(stages["recommended"], stages["evaluated"]),
        "approval_rate": _rate(stages["approved_or_published"], stages["recommended"]),
        "rejection_rate": _rate(stages["rejected"], stages["evaluated"]),
        "publication_attempt_rate": _rate(stages["publication_attempted"], stages["approved_or_published"]),
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "filters": {"limit": limit, "domain": domain},
        "summary": summary,
        "stages": stages,
        "category_breakdown": _breakdown(rows, "category"),
        "domain_breakdown": _breakdown(rows, "domain"),
        "next_actions": _next_actions(summary),
    }


def render_idea_approval_funnel(report: Mapping[str, Any], *, fmt: str = "json") -> str:
    """Render an idea approval funnel report as JSON, Markdown, or CSV."""
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt == "csv":
        return _render_csv(report)
    if fmt != "markdown":
        raise ValueError(f"Unsupported idea approval funnel format: {fmt}")

    summary = _mapping(report.get("summary"))
    lines = [
        "# Idea Approval Funnel",
        "",
        f"Schema: `{report.get('schema_version')}`",
        f"Generated: {summary.get('generated', 0)}",
        f"Evaluated: {summary.get('evaluated', 0)}",
        f"Recommended: {summary.get('recommended', 0)}",
        f"Approved/published: {summary.get('approved_or_published', 0)}",
        f"Rejected: {summary.get('rejected', 0)}",
        f"Publication attempted: {summary.get('publication_attempted', 0)}",
        "",
        "## Category Breakdown",
        "",
        "| Category | Generated | Evaluated | Recommended | Approved/Published | Rejected | Publication Attempted | Risk |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in _list_of_maps(report.get("category_breakdown")):
        lines.append(_breakdown_line(row, "category"))
    if not report.get("category_breakdown"):
        lines.append("| none | 0 | 0 | 0 | 0 | 0 | 0 | 0.000 |")

    lines.extend(["", "## Domain Breakdown", ""])
    lines.append("| Domain | Generated | Evaluated | Recommended | Approved/Published | Rejected | Publication Attempted | Risk |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for row in _list_of_maps(report.get("domain_breakdown")):
        lines.append(_breakdown_line(row, "domain"))
    if not report.get("domain_breakdown"):
        lines.append("| none | 0 | 0 | 0 | 0 | 0 | 0 | 0.000 |")

    lines.extend(["", "## Next Actions", ""])
    actions = report.get("next_actions")
    lines.extend(f"- {item}" for item in actions) if isinstance(actions, list) and actions else lines.append("- None")
    return "\n".join(lines).rstrip() + "\n"


def _render_csv(report: Mapping[str, Any]) -> str:
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for key, value in _mapping(report.get("summary")).items():
        writer.writerow({"section": "summary", "key": key, "count": value})
    for section, key_name in (("category", "category"), ("domain", "domain")):
        for row in _list_of_maps(report.get(f"{section}_breakdown")):
            writer.writerow({"section": section, "key": row.get(key_name) or "", **{k: row.get(k, "") for k in CSV_COLUMNS if k in row}})
    return output.getvalue()


def _idea_row(store: "Store", unit: Any) -> dict[str, Any]:
    evaluation = store.get_evaluation(unit.id)
    feedback = store.get_latest_feedback(unit.id)
    attempts = store.list_publication_attempts(unit.id)
    outcome = feedback.get("outcome") if feedback else None
    recommendation = evaluation.recommendation if evaluation else None
    return {
        "id": unit.id,
        "category": str(unit.category or "unknown"),
        "domain": str(unit.domain or "unspecified"),
        "generated": True,
        "evaluated": evaluation is not None or unit.status in {"evaluated", "approved", "published", "rejected"},
        "recommended": recommendation in POSITIVE_RECOMMENDATIONS,
        "approved_or_published": unit.status in {"approved", "published"} or outcome in APPROVED_OUTCOMES,
        "rejected": unit.status == "rejected" or outcome in REJECTED_OUTCOMES,
        "publication_attempted": bool(attempts),
    }


def _stage_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    keys = ("generated", "evaluated", "recommended", "approved_or_published", "rejected", "publication_attempted")
    return {key: sum(1 for row in rows if row[key]) for key in keys}


def _breakdown(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row.get(key) or "unknown"), []).append(row)

    result = []
    for value, group in grouped.items():
        counts = _stage_counts(group)
        risk = _conversion_risk(counts)
        result.append({key: value, **counts, "conversion_risk": risk})
    return sorted(result, key=lambda row: (-float(row["conversion_risk"]), -int(row["generated"]), str(row[key])))


def _conversion_risk(counts: Mapping[str, int]) -> float:
    generated = int(counts.get("generated", 0))
    approved = int(counts.get("approved_or_published", 0))
    if generated == 0:
        return 0.0
    return round(1.0 - approved / generated, 3)


def _next_actions(summary: Mapping[str, Any]) -> list[str]:
    if not summary.get("generated"):
        return ["Generate buildable units before running approval funnel analysis."]
    actions: list[str] = []
    if summary.get("evaluated", 0) < summary.get("generated", 0):
        actions.append("Evaluate unevaluated ideas before review prioritization.")
    if summary.get("recommended", 0) and summary.get("approved_or_published", 0) < summary.get("recommended", 0):
        actions.append("Review recommended ideas that have not received approval feedback.")
    if summary.get("approved_or_published", 0) and summary.get("publication_attempted", 0) < summary.get("approved_or_published", 0):
        actions.append("Attempt publication for approved ideas without publication history.")
    if summary.get("rejected", 0):
        actions.append("Review rejection reasons for recurring quality-loop improvements.")
    return actions or ["Continue monitoring approval and publication throughput."]


def _rate(part: int, whole: int) -> float:
    return round(part / whole, 3) if whole else 0.0


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list_of_maps(value: Any) -> list[Mapping[str, Any]]:
    return [item for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []


def _breakdown_line(row: Mapping[str, Any], key: str) -> str:
    return "| `{name}` | {generated} | {evaluated} | {recommended} | {approved} | {rejected} | {attempted} | {risk:.3f} |".format(
        name=row.get(key) or "unknown",
        generated=row.get("generated", 0),
        evaluated=row.get("evaluated", 0),
        recommended=row.get("recommended", 0),
        approved=row.get("approved_or_published", 0),
        rejected=row.get("rejected", 0),
        attempted=row.get("publication_attempted", 0),
        risk=float(row.get("conversion_risk") or 0.0),
    )
