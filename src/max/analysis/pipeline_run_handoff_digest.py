"""Action-oriented handoff digest for a completed pipeline run."""

from __future__ import annotations

import csv
import json
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from io import StringIO
from pathlib import Path
from typing import Any

from max.analysis.pipeline_run_export import (
    _budget_summary,
    _domain_name,
    _int_value,
    _profile_name,
    _run_status,
)
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit
from max.types.evaluation import UtilityEvaluation


SCHEMA_VERSION = "max.pipeline_run_handoff_digest.v1"
APPROVED_OUTCOMES = {"approved", "published"}
REJECTED_OUTCOMES = {"rejected", "abandoned"}
POSITIVE_RECOMMENDATIONS = {"strong_yes", "yes"}
CSV_COLUMNS = (
    "section",
    "ordinal",
    "key",
    "value",
    "run_id",
    "status",
    "profile",
    "domain",
    "started_at",
    "completed_at",
    "source_adapter",
    "idea_id",
    "title",
    "category",
    "score",
    "recommendation",
    "feedback_outcome",
    "approval_score",
    "publication_attempt_count",
    "latest_publication_status",
    "evidence_signal_count",
    "message",
)


@dataclass(frozen=True)
class PipelineRunHandoffDigestNotFound(Exception):
    """Raised when a requested pipeline run does not exist."""

    run_id: str


def build_pipeline_run_handoff_digest(
    store: Store,
    *,
    run_id: str,
    top_limit: int = 5,
) -> dict[str, Any]:
    """Build a JSON-ready downstream-agent handoff digest for one pipeline run."""
    run = store.get_pipeline_run(run_id)
    if run is None:
        raise PipelineRunHandoffDigestNotFound(run_id)

    domains = store.get_pipeline_run_domains(run_id)
    output_counts = store.get_pipeline_run_output_counts(run_id)
    candidate_ideas = _run_candidate_ideas(store, run, domains, run_id)
    idea_rows = [_idea_row(store, unit, run_id) for unit in candidate_ideas]
    feedback_counts = _feedback_counts(idea_rows, output_counts)
    source_mix = _source_mix(store, candidate_ideas)
    budget = _budget_summary(run)
    warnings = _warnings(run, idea_rows, source_mix, budget)
    next_actions = _next_actions(run, idea_rows, warnings)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "max.pipeline_run_handoff_digest",
        "run": {
            "id": run_id,
            "status": _run_status(run),
            "started_at": run["started_at"],
            "completed_at": run.get("completed_at"),
            "profile": _profile_name(run),
            "domain": _domain_name(run, domains),
            "config": run.get("config") or {},
        },
        "summary": {
            "idea_count": len(idea_rows),
            "evaluated_count": sum(1 for row in idea_rows if row["evaluation"] is not None),
            "approved_count": feedback_counts["approved"],
            "published_count": feedback_counts["published"],
            "approved_or_published_count": feedback_counts["approved_or_published"],
            "rejected_count": feedback_counts["rejected"],
            "feedback_count": feedback_counts["total"],
            "publication_attempt_count": sum(
                len(row["publication_attempts"]) for row in idea_rows
            ),
            "warning_count": len(warnings),
            "next_action_count": len(next_actions),
        },
        "stage_counts": {
            "signals_fetched": _int_value(run.get("signals_fetched")),
            "signals_new": _int_value(run.get("signals_new")),
            "insights_generated": _int_value(run.get("insights_generated")),
            "clusters_found": _int_value(run.get("clusters_found")),
            "gaps_detected": _int_value(run.get("gaps_detected")),
            "ideas_generated": _int_value(run.get("ideas_generated")),
            "ideas_evaluated": _int_value(run.get("ideas_evaluated")),
            "avg_idea_score": float(run.get("avg_idea_score") or 0.0),
        },
        "budget": budget,
        "source_mix": source_mix,
        "top_recommended_ideas": _top_ideas(idea_rows, top_limit=top_limit),
        "warnings": warnings,
        "next_actions": next_actions,
    }


def render_pipeline_run_handoff_digest(digest: Mapping[str, Any], *, fmt: str = "markdown") -> str:
    """Render a pipeline run handoff digest as Markdown, JSON, or CSV."""
    if fmt == "json":
        return json.dumps(digest, indent=2, sort_keys=True) + "\n"
    if fmt == "csv":
        return _render_csv(digest)
    if fmt != "markdown":
        raise ValueError(f"Unsupported pipeline run handoff digest format: {fmt}")

    run = _mapping(digest.get("run"))
    summary = _mapping(digest.get("summary"))
    budget = _mapping(digest.get("budget"))
    lines = [
        f"# Pipeline Run Handoff Digest: {run.get('id') or 'unknown'}",
        "",
        f"Schema: `{digest.get('schema_version')}`",
        f"Status: `{run.get('status') or 'unknown'}`",
        f"Profile: `{run.get('profile') or 'unknown'}`",
        f"Domain: `{run.get('domain') or 'mixed/unknown'}`",
        f"Started: {run.get('started_at') or 'unknown'}",
        f"Completed: {run.get('completed_at') or 'not completed'}",
        "",
        "## Summary",
        "",
        f"- Ideas: {summary.get('idea_count', 0)}",
        f"- Evaluated: {summary.get('evaluated_count', 0)}",
        f"- Approved/published: {summary.get('approved_or_published_count', 0)}",
        f"- Rejected: {summary.get('rejected_count', 0)}",
        f"- Publication attempts: {summary.get('publication_attempt_count', 0)}",
        "",
        "## Budget",
        "",
        f"- Model: {budget.get('model') or 'unknown'}",
        f"- Total tokens: {budget.get('total_tokens', 0)}",
        f"- Estimated cost USD: {float(budget.get('estimated_cost_usd') or 0.0):.6f}",
        "",
        "## Source Mix",
        "",
        "| Source | Ideas | Evidence Signals |",
        "| --- | ---: | ---: |",
    ]
    source_mix = digest.get("source_mix")
    if isinstance(source_mix, list) and source_mix:
        for source in source_mix:
            source_map = _mapping(source)
            lines.append(
                "| {source} | {ideas} | {signals} |".format(
                    source=f"`{source_map.get('source_adapter') or 'unknown'}`",
                    ideas=source_map.get("idea_count", 0),
                    signals=source_map.get("evidence_signal_count", 0),
                )
            )
    else:
        lines.append("| `none` | 0 | 0 |")

    lines.extend(
        [
            "",
            "## Top Recommended Ideas",
            "",
            "| Idea | Score | Recommendation | Feedback | Publications |",
            "| --- | ---: | --- | --- | ---: |",
        ]
    )
    top_ideas = digest.get("top_recommended_ideas")
    if isinstance(top_ideas, list) and top_ideas:
        for idea in top_ideas:
            idea_map = _mapping(idea)
            lines.append(
                "| {title} | {score:.1f} | `{recommendation}` | `{feedback}` | {pubs} |".format(
                    title=_escape_table(str(idea_map.get("title") or idea_map.get("id") or "")),
                    score=float(idea_map.get("score") or 0.0),
                    recommendation=idea_map.get("recommendation") or "unevaluated",
                    feedback=idea_map.get("feedback_outcome") or "none",
                    pubs=idea_map.get("publication_attempt_count", 0),
                )
            )
    else:
        lines.append("| None | 0.0 | `none` | `none` | 0 |")

    lines.extend(["", "## Warnings", ""])
    warnings = _string_list(digest.get("warnings"))
    lines.extend(f"- {warning}" for warning in warnings) if warnings else lines.append("- None")

    lines.extend(["", "## Next Actions", ""])
    next_actions = _string_list(digest.get("next_actions"))
    lines.extend(f"- {action}" for action in next_actions) if next_actions else lines.append("- None")

    return "\n".join(lines).rstrip() + "\n"


def _render_csv(digest: Mapping[str, Any]) -> str:
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()

    run = _mapping(digest.get("run"))
    common = {
        "run_id": run.get("id") or "",
        "status": run.get("status") or "",
        "profile": run.get("profile") or "",
        "domain": run.get("domain") or "",
        "started_at": run.get("started_at") or "",
        "completed_at": run.get("completed_at") or "",
    }

    def write_row(section: str, ordinal: int, **values: Any) -> None:
        row = {column: "" for column in CSV_COLUMNS}
        row.update(common)
        row.update({"section": section, "ordinal": ordinal})
        row.update(values)
        writer.writerow(row)

    metadata = (
        ("schema_version", digest.get("schema_version") or ""),
        ("kind", digest.get("kind") or ""),
        ("run_id", run.get("id") or ""),
        ("status", run.get("status") or ""),
        ("profile", run.get("profile") or ""),
        ("domain", run.get("domain") or ""),
        ("started_at", run.get("started_at") or ""),
        ("completed_at", run.get("completed_at") or ""),
    )
    for ordinal, (key, value) in enumerate(metadata, start=1):
        write_row("metadata", ordinal, key=key, value=value)

    for ordinal, (key, value) in enumerate(_mapping(digest.get("summary")).items(), start=1):
        write_row("summary", ordinal, key=key, value=value)

    for ordinal, key in enumerate(
        (
            "signals_fetched",
            "signals_new",
            "insights_generated",
            "clusters_found",
            "gaps_detected",
            "ideas_generated",
            "ideas_evaluated",
            "avg_idea_score",
        ),
        start=1,
    ):
        write_row(
            "stage_counts",
            ordinal,
            key=key,
            value=_mapping(digest.get("stage_counts")).get(key, 0),
        )

    budget = _mapping(digest.get("budget"))
    for ordinal, key in enumerate(
        ("model", "input_tokens", "output_tokens", "total_tokens", "estimated_cost_usd"),
        start=1,
    ):
        write_row("budget", ordinal, key=key, value=budget.get(key, 0 if key != "model" else ""))

    budget_stages = budget.get("stages")
    if isinstance(budget_stages, list):
        for offset, stage in enumerate(budget_stages, start=1):
            stage_map = _mapping(stage)
            write_row(
                "budget_stage",
                offset,
                key=str(stage_map.get("stage") or "unknown"),
                value=stage_map.get("total_tokens", ""),
                message=(
                    "input_tokens={input_tokens}; output_tokens={output_tokens}; "
                    "estimated_cost_usd={estimated_cost_usd}"
                ).format(
                    input_tokens=stage_map.get("input_tokens", 0),
                    output_tokens=stage_map.get("output_tokens", 0),
                    estimated_cost_usd=stage_map.get("estimated_cost_usd", 0.0),
                ),
            )

    source_mix = digest.get("source_mix")
    if isinstance(source_mix, list) and source_mix:
        for ordinal, source in enumerate(source_mix, start=1):
            source_map = _mapping(source)
            write_row(
                "source_mix",
                ordinal,
                key=str(source_map.get("source_adapter") or "unknown"),
                source_adapter=source_map.get("source_adapter") or "unknown",
                value=source_map.get("idea_count", 0),
                evidence_signal_count=source_map.get("evidence_signal_count", 0),
            )
    else:
        write_row(
            "source_mix",
            1,
            key="none",
            value=0,
            source_adapter="none",
            evidence_signal_count=0,
            message="No source mix is available.",
        )

    top_ideas = digest.get("top_recommended_ideas")
    if isinstance(top_ideas, list) and top_ideas:
        for ordinal, idea in enumerate(top_ideas, start=1):
            idea_map = _mapping(idea)
            write_row(
                "top_recommended_ideas",
                ordinal,
                key=str(idea_map.get("id") or ""),
                value=idea_map.get("score", 0.0),
                idea_id=idea_map.get("id") or "",
                title=idea_map.get("title") or "",
                category=idea_map.get("category") or "",
                score=idea_map.get("score", 0.0),
                recommendation=idea_map.get("recommendation") or "unevaluated",
                feedback_outcome=idea_map.get("feedback_outcome") or "none",
                approval_score=idea_map.get("approval_score") or "",
                publication_attempt_count=idea_map.get("publication_attempt_count", 0),
                latest_publication_status=idea_map.get("latest_publication_status") or "",
                evidence_signal_count=idea_map.get("evidence_signal_count", 0),
                message=idea_map.get("one_liner") or "",
            )
    else:
        write_row(
            "top_recommended_ideas",
            1,
            key="none",
            value=0,
            score=0.0,
            recommendation="none",
            feedback_outcome="none",
            publication_attempt_count=0,
            evidence_signal_count=0,
            message="No top recommended ideas are available.",
        )

    warnings = _string_list(digest.get("warnings"))
    if warnings:
        for ordinal, warning in enumerate(warnings, start=1):
            write_row("warnings", ordinal, key="warning", value=warning, message=warning)
    else:
        write_row("warnings", 1, key="none", value="", message="None")

    next_actions = _string_list(digest.get("next_actions"))
    if next_actions:
        for ordinal, action in enumerate(next_actions, start=1):
            write_row("next_actions", ordinal, key="action", value=action, message=action)
    else:
        write_row("next_actions", 1, key="none", value="", message="None")

    return output.getvalue()


def write_pipeline_run_handoff_digest(
    path: Path,
    digest: Mapping[str, Any],
    *,
    fmt: str = "markdown",
) -> None:
    """Write a rendered pipeline run handoff digest to disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_pipeline_run_handoff_digest(digest, fmt=fmt), encoding="utf-8")


def pipeline_run_handoff_digest_filename(run: Mapping[str, Any] | str, *, fmt: str = "markdown") -> str:
    """Return a stable filename for a pipeline run handoff digest."""
    run_id = run if isinstance(run, str) else str(run.get("id") or "pipeline-run")
    extension = "json" if fmt == "json" else "csv" if fmt == "csv" else "md"
    return f"{_filename_part(run_id)}-handoff-digest.{extension}"


def _run_candidate_ideas(
    store: Store,
    run: Mapping[str, Any],
    domains: list[dict[str, Any]],
    run_id: str,
) -> list[BuildableUnit]:
    domain_names = _domain_filter_values(run, domains)
    unit_by_id: dict[str, BuildableUnit] = {}

    for domain in domain_names or [None]:
        for unit in _iter_buildable_units(store, domain=domain):
            if _within_run_window(unit, run):
                unit_by_id[unit.id] = unit

    for unit_id in _feedback_unit_ids_for_run(store, run_id):
        unit = store.get_buildable_unit(unit_id)
        if unit is not None:
            unit_by_id[unit.id] = unit

    return sorted(unit_by_id.values(), key=lambda unit: (str(unit.created_at), unit.id))


def _iter_buildable_units(store: Store, *, domain: str | None) -> Iterable[BuildableUnit]:
    cursor: str | None = None
    while True:
        units, cursor = store.get_buildable_units_paginated(
            cursor=cursor,
            limit=100,
            domain=domain,
        )
        yield from units
        if cursor is None:
            break


def _domain_filter_values(run: Mapping[str, Any], domains: list[dict[str, Any]]) -> list[str]:
    values = {str(row.get("domain")) for row in domains if row.get("domain")}
    config = run.get("config")
    if isinstance(config, Mapping):
        for key in ("domain", "focus_domain"):
            if config.get(key):
                values.add(str(config[key]))
    return sorted(values)


def _within_run_window(unit: BuildableUnit, run: Mapping[str, Any]) -> bool:
    created_at = _parse_datetime(unit.created_at)
    started_at = _parse_datetime(run.get("started_at"))
    completed_at = _parse_datetime(run.get("completed_at"))
    if started_at and created_at and created_at < started_at:
        return False
    if completed_at and created_at and created_at > completed_at:
        return False
    return True


def _feedback_unit_ids_for_run(store: Store, run_id: str) -> list[str]:
    rows = store.conn.execute(
        """SELECT DISTINCT buildable_unit_id
           FROM feedback
           WHERE pipeline_run_id = ?
           ORDER BY buildable_unit_id""",
        (run_id,),
    ).fetchall()
    return [str(row["buildable_unit_id"]) for row in rows]


def _idea_row(store: Store, unit: BuildableUnit, run_id: str) -> dict[str, Any]:
    evaluation = store.get_evaluation(unit.id)
    feedback = _latest_feedback_for_run(store, unit.id, run_id) or store.get_latest_feedback(unit.id)
    publication_attempts = store.list_publication_attempts(unit.id)
    return {
        "unit": unit,
        "evaluation": evaluation,
        "feedback": feedback,
        "publication_attempts": publication_attempts,
    }


def _latest_feedback_for_run(store: Store, unit_id: str, run_id: str) -> dict[str, Any] | None:
    row = store.conn.execute(
        """SELECT buildable_unit_id, outcome, reason, approval_score, created_at
           FROM feedback
           WHERE buildable_unit_id = ? AND pipeline_run_id = ?
           ORDER BY created_at DESC, id DESC
           LIMIT 1""",
        (unit_id, run_id),
    ).fetchone()
    if row is None:
        return None
    return {
        "buildable_unit_id": row["buildable_unit_id"],
        "outcome": row["outcome"],
        "reason": row["reason"],
        "approval_score": row["approval_score"],
        "created_at": row["created_at"],
    }


def _feedback_counts(
    idea_rows: list[dict[str, Any]],
    output_counts: Mapping[str, int],
) -> dict[str, int]:
    counts = {
        "approved": _int_value(output_counts.get("approved")),
        "published": _int_value(output_counts.get("published")),
        "approved_or_published": _int_value(output_counts.get("approved_or_published")),
        "rejected": 0,
        "total": 0,
    }
    for row in idea_rows:
        feedback = row.get("feedback")
        if not isinstance(feedback, Mapping):
            continue
        outcome = str(feedback.get("outcome") or "")
        if outcome in REJECTED_OUTCOMES:
            counts["rejected"] += 1
        counts["total"] += 1
    if counts["approved_or_published"] == 0:
        counts["approved_or_published"] = sum(
            1
            for row in idea_rows
            if isinstance(row.get("feedback"), Mapping)
            and row["feedback"].get("outcome") in APPROVED_OUTCOMES
        )
    return counts


def _source_mix(store: Store, units: Iterable[BuildableUnit]) -> list[dict[str, Any]]:
    adapter_ideas: Counter[str] = Counter()
    adapter_signals: Counter[str] = Counter()

    for unit in units:
        seen_for_idea: set[str] = set()
        for signal_id in sorted(set(unit.evidence_signals)):
            signal = store.get_signal(signal_id)
            adapter = signal.source_adapter if signal is not None else "unknown"
            adapter_signals[adapter] += 1
            seen_for_idea.add(adapter)
        for adapter in seen_for_idea:
            adapter_ideas[adapter] += 1

    return [
        {
            "source_adapter": adapter,
            "idea_count": adapter_ideas[adapter],
            "evidence_signal_count": adapter_signals[adapter],
        }
        for adapter in sorted(adapter_signals, key=lambda item: (-adapter_signals[item], item))
    ]


def _top_ideas(idea_rows: list[dict[str, Any]], *, top_limit: int) -> list[dict[str, Any]]:
    ranked_rows = sorted(
        idea_rows,
        key=lambda row: (
            -_score(row.get("evaluation")),
            _feedback_rank(row.get("feedback")),
            _unit(row).title,
            _unit(row).id,
        ),
    )
    return [_top_idea_entry(row) for row in ranked_rows[: max(top_limit, 0)]]


def _top_idea_entry(row: dict[str, Any]) -> dict[str, Any]:
    unit = _unit(row)
    evaluation = row.get("evaluation")
    feedback = row.get("feedback")
    publications = row.get("publication_attempts")
    latest_publication = publications[0] if isinstance(publications, list) and publications else None
    return {
        "id": unit.id,
        "title": unit.title,
        "status": unit.status,
        "domain": unit.domain,
        "category": unit.category,
        "score": _score(evaluation),
        "recommendation": (
            evaluation.recommendation if isinstance(evaluation, UtilityEvaluation) else "unevaluated"
        ),
        "feedback_outcome": feedback.get("outcome") if isinstance(feedback, Mapping) else None,
        "approval_score": feedback.get("approval_score") if isinstance(feedback, Mapping) else None,
        "publication_attempt_count": len(publications) if isinstance(publications, list) else 0,
        "latest_publication_status": (
            latest_publication.get("status") if isinstance(latest_publication, Mapping) else None
        ),
        "one_liner": unit.one_liner,
        "evidence_signal_count": len(unit.evidence_signals),
    }


def _warnings(
    run: Mapping[str, Any],
    idea_rows: list[dict[str, Any]],
    source_mix: list[dict[str, Any]],
    budget: Mapping[str, Any],
) -> list[str]:
    warnings: list[str] = []
    if _run_status(run) not in {"completed", "success"}:
        warnings.append(f"Run status is {_run_status(run)}; review termination context before acting.")
    if run.get("error_message"):
        warnings.append(f"Run recorded an error: {run['error_message']}.")
    adapter_metrics = run.get("adapter_metrics")
    if isinstance(adapter_metrics, Mapping):
        failing_adapters = sorted(
            str(adapter)
            for adapter, raw_stats in adapter_metrics.items()
            if isinstance(raw_stats, Mapping) and raw_stats.get("status") not in (None, "ok")
        )
        if failing_adapters:
            warnings.append(
                "Adapters with non-ok status need source coverage review: "
                + ", ".join(failing_adapters)
                + "."
            )
    if not idea_rows and _int_value(run.get("ideas_generated")):
        warnings.append("Run reports generated ideas, but no matching idea records were found.")
    if not idea_rows:
        warnings.append("No generated ideas are available for downstream handoff.")
    if any(row.get("evaluation") is None for row in idea_rows):
        warnings.append("Some generated ideas do not have utility evaluations.")
    if not any(_score(row.get("evaluation")) > 0 for row in idea_rows):
        warnings.append("No scored recommendations are available.")
    if not source_mix and idea_rows:
        warnings.append("Ideas have no linked evidence signals, so source mix is unavailable.")
    if _int_value(budget.get("total_tokens")) == 0:
        warnings.append("No token usage was recorded for this run.")
    return warnings


def _next_actions(
    run: Mapping[str, Any],
    idea_rows: list[dict[str, Any]],
    warnings: list[str],
) -> list[str]:
    actions: list[str] = []
    positive = [
        row
        for row in idea_rows
        if isinstance(row.get("evaluation"), UtilityEvaluation)
        and row["evaluation"].recommendation in POSITIVE_RECOMMENDATIONS
    ]
    unreviewed_positive = [
        row for row in positive if not isinstance(row.get("feedback"), Mapping)
    ]
    unpub_approved = [
        row
        for row in idea_rows
        if isinstance(row.get("feedback"), Mapping)
        and row["feedback"].get("outcome") in APPROVED_OUTCOMES
        and not row.get("publication_attempts")
    ]

    if unreviewed_positive:
        actions.append("Review the highest-scoring recommended ideas and record approval feedback.")
    if unpub_approved:
        actions.append("Prepare publication or execution handoff for approved ideas without attempts.")
    if warnings:
        actions.append("Resolve digest warnings before replaying or changing profile settings.")
    if _run_status(run) in {"failed", "budget_exceeded"}:
        actions.append("Inspect run errors and budget usage before rerunning this pipeline.")
    if not actions and idea_rows:
        actions.append("Promote the top recommended idea into validation or publication planning.")
    if not actions:
        actions.append("Rerun the profile after checking source configuration and thresholds.")
    return actions


def _unit(row: Mapping[str, Any]) -> BuildableUnit:
    unit = row["unit"]
    if not isinstance(unit, BuildableUnit):
        raise TypeError("idea row does not contain a BuildableUnit")
    return unit


def _score(evaluation: Any) -> float:
    return float(evaluation.overall_score) if isinstance(evaluation, UtilityEvaluation) else 0.0


def _feedback_rank(feedback: Any) -> int:
    if not isinstance(feedback, Mapping):
        return 2
    outcome = feedback.get("outcome")
    if outcome in APPROVED_OUTCOMES:
        return 0
    if outcome in REJECTED_OUTCOMES:
        return 3
    return 1


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _escape_table(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _filename_part(value: str) -> str:
    clean = "".join(char.lower() if char.isalnum() else "-" for char in value)
    return "-".join(part for part in clean.split("-") if part) or "pipeline-run"


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None
