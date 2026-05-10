"""OKR document export for objectives and key results generation.

Generates structured OKR hierarchies with company, team, and individual levels.
Exports measurable key results with progress tracking baselines and target values
in markdown and JSON formats.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "max.okr_export.v1"
KIND = "max.okr_export"

# OKR levels
LEVEL_COMPANY = "company"
LEVEL_TEAM = "team"
LEVEL_INDIVIDUAL = "individual"

VALID_LEVELS = {LEVEL_COMPANY, LEVEL_TEAM, LEVEL_INDIVIDUAL}


def build_okr_document(
    objectives: list[dict[str, Any]],
    *,
    title: str = "OKR Document",
    period: str | None = None,
    owner: str | None = None,
) -> dict[str, Any]:
    """Build an OKR document from objectives data.

    Args:
        objectives: List of objective dicts, each containing:
            - title: str
            - level: one of "company", "team", "individual"
            - key_results: list of key result dicts
            - description: optional str
            - owner: optional str
        title: Document title
        period: Time period (e.g. "Q1 2026")
        owner: Document owner/author

    Returns:
        Structured OKR document dict with schema metadata.
    """
    validated = [_validate_objective(obj) for obj in objectives]

    # Group by level
    by_level: dict[str, list[dict[str, Any]]] = {
        LEVEL_COMPANY: [],
        LEVEL_TEAM: [],
        LEVEL_INDIVIDUAL: [],
    }
    for obj in validated:
        by_level[obj["level"]].append(obj)

    # Calculate summary stats
    total_objectives = len(validated)
    total_key_results = sum(len(obj["key_results"]) for obj in validated)
    avg_progress = _calculate_average_progress(validated)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "title": title,
        "period": period,
        "owner": owner,
        "summary": {
            "total_objectives": total_objectives,
            "total_key_results": total_key_results,
            "average_progress": avg_progress,
            "by_level": {
                level: len(objs) for level, objs in by_level.items()
            },
        },
        "objectives": {
            LEVEL_COMPANY: by_level[LEVEL_COMPANY],
            LEVEL_TEAM: by_level[LEVEL_TEAM],
            LEVEL_INDIVIDUAL: by_level[LEVEL_INDIVIDUAL],
        },
    }


def render_okr_markdown(document: dict[str, Any]) -> str:
    """Render OKR document as Markdown.

    Args:
        document: OKR document from build_okr_document

    Returns:
        Markdown formatted OKR document.
    """
    lines = [
        f"# {document['title']}",
        "",
        f"Schema: `{document['schema_version']}`",
        f"Kind: `{document['kind']}`",
        f"Generated: {document['generated_at']}",
    ]

    if document.get("period"):
        lines.append(f"Period: {document['period']}")
    if document.get("owner"):
        lines.append(f"Owner: {document['owner']}")

    lines.append("")

    # Summary
    summary = document["summary"]
    lines.extend([
        "## Summary",
        "",
        f"- Total objectives: {summary['total_objectives']}",
        f"- Total key results: {summary['total_key_results']}",
        f"- Average progress: {summary['average_progress']:.1f}%",
        "",
    ])

    # Render each level
    level_labels = {
        LEVEL_COMPANY: "Company Objectives",
        LEVEL_TEAM: "Team Objectives",
        LEVEL_INDIVIDUAL: "Individual Objectives",
    }

    objectives = document["objectives"]
    for level, label in level_labels.items():
        objs = objectives[level]
        if not objs:
            continue

        lines.extend([f"## {label}", ""])

        for i, obj in enumerate(objs, 1):
            lines.append(f"### {i}. {obj['title']}")
            lines.append("")

            if obj.get("description"):
                lines.append(f"{obj['description']}")
                lines.append("")

            if obj.get("owner"):
                lines.append(f"**Owner**: {obj['owner']}")
                lines.append("")

            # Key results
            if obj["key_results"]:
                lines.append("**Key Results:**")
                lines.append("")

                for j, kr in enumerate(obj["key_results"], 1):
                    progress = kr.get("progress", 0)
                    progress_bar = _render_progress_bar(progress)
                    lines.append(
                        f"{j}. {kr['title']} {progress_bar} {progress:.0f}%"
                    )

                    details = []
                    if kr.get("baseline") is not None:
                        details.append(f"Baseline: {kr['baseline']}")
                    if kr.get("target") is not None:
                        details.append(f"Target: {kr['target']}")
                    if kr.get("current") is not None:
                        details.append(f"Current: {kr['current']}")
                    if kr.get("unit"):
                        details.append(f"Unit: {kr['unit']}")

                    if details:
                        lines.append(f"   - {' | '.join(details)}")

                lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def render_okr_json(document: dict[str, Any]) -> str:
    """Render OKR document as formatted JSON.

    Args:
        document: OKR document from build_okr_document

    Returns:
        JSON formatted string.
    """
    return json.dumps(document, indent=2, default=str)


def _validate_objective(obj: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize an objective dict."""
    title = obj.get("title", "Untitled Objective")
    level = obj.get("level", LEVEL_TEAM)
    if level not in VALID_LEVELS:
        level = LEVEL_TEAM

    key_results = [_validate_key_result(kr) for kr in obj.get("key_results", [])]

    return {
        "title": title,
        "level": level,
        "description": obj.get("description", ""),
        "owner": obj.get("owner", ""),
        "key_results": key_results,
    }


def _validate_key_result(kr: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize a key result dict."""
    baseline = kr.get("baseline")
    target = kr.get("target")
    current = kr.get("current")

    # Calculate progress if baseline and target are numeric
    progress = kr.get("progress", 0)
    if (
        baseline is not None
        and target is not None
        and current is not None
        and isinstance(baseline, (int, float))
        and isinstance(target, (int, float))
        and isinstance(current, (int, float))
        and target != baseline
    ):
        progress = ((current - baseline) / (target - baseline)) * 100
        progress = max(0.0, min(100.0, progress))

    return {
        "title": kr.get("title", "Untitled Key Result"),
        "baseline": baseline,
        "target": target,
        "current": current,
        "progress": progress,
        "unit": kr.get("unit", ""),
    }


def _calculate_average_progress(objectives: list[dict[str, Any]]) -> float:
    """Calculate overall average progress across all key results."""
    all_progress: list[float] = []
    for obj in objectives:
        for kr in obj["key_results"]:
            all_progress.append(kr["progress"])

    if not all_progress:
        return 0.0
    return sum(all_progress) / len(all_progress)


def _render_progress_bar(progress: float, width: int = 10) -> str:
    """Render a text-based progress bar."""
    filled = int(progress / 100 * width)
    filled = max(0, min(width, filled))
    empty = width - filled
    return f"[{'█' * filled}{'░' * empty}]"
