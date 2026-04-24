"""Export persisted pipeline runs as review-friendly records and markdown."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from max import config
from max.analysis.budget_usage import _stage_usage_from_mapping
from max.llm.client import estimate_token_cost_usd, token_counts_from_usage
from max.store.db import Store


@dataclass(frozen=True)
class PipelineRunExportNotFound(Exception):
    """Raised when a requested pipeline run does not exist."""

    run_id: str


def _int_value(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _float_value(value: object) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def _profile_name(run: Mapping[str, object]) -> str | None:
    run_config = run.get("config")
    if not isinstance(run_config, Mapping):
        return None
    value = run_config.get("profile") or run_config.get("profile_name")
    return str(value) if value else None


def _domain_name(run: Mapping[str, object], domains: list[dict[str, object]]) -> str | None:
    run_config = run.get("config")
    if isinstance(run_config, Mapping):
        value = run_config.get("domain") or run_config.get("focus_domain")
        if value:
            return str(value)
    if len(domains) == 1:
        return str(domains[0]["domain"])
    return None


def _run_status(run: Mapping[str, object]) -> str:
    status = run.get("status")
    if isinstance(status, str) and status:
        return status
    return "completed" if run.get("completed_at") else "running"


def _budget_summary(run: Mapping[str, object]) -> dict[str, object]:
    token_usage = run.get("token_usage") if isinstance(run.get("token_usage"), Mapping) else {}
    run_config = run.get("config")
    configured_model = run_config.get("model") if isinstance(run_config, Mapping) else None
    model = str(configured_model or config.MODEL)
    input_tokens, output_tokens = token_counts_from_usage(token_usage)
    stored_cost = _float_value(token_usage.get("estimated_cost_usd"))
    cost = (
        stored_cost
        if stored_cost is not None
        else estimate_token_cost_usd(input_tokens, output_tokens, model=model)
    )
    return {
        "model": model or config.MODEL,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "estimated_cost_usd": cost,
        "stages": _stage_usage_from_mapping(token_usage, model=model or config.MODEL),
        "token_usage": dict(token_usage),
    }


def _stage_counts(run: Mapping[str, object], outputs: Mapping[str, int]) -> dict[str, int | float]:
    return {
        "signals_fetched": _int_value(run.get("signals_fetched")),
        "signals_new": _int_value(run.get("signals_new")),
        "insights_generated": _int_value(run.get("insights_generated")),
        "clusters_found": _int_value(run.get("clusters_found")),
        "gaps_detected": _int_value(run.get("gaps_detected")),
        "ideas_generated": _int_value(run.get("ideas_generated")),
        "ideas_evaluated": _int_value(run.get("ideas_evaluated")),
        "approved": _int_value(outputs.get("approved")),
        "published": _int_value(outputs.get("published")),
        "approved_or_published": _int_value(outputs.get("approved_or_published")),
        "avg_idea_score": float(run.get("avg_idea_score") or 0.0),
    }


def _adapter_stats(run: Mapping[str, object]) -> list[dict[str, object]]:
    metrics = run.get("adapter_metrics")
    if not isinstance(metrics, Mapping):
        return []

    rows: list[dict[str, object]] = []
    for adapter, raw_stats in sorted(metrics.items()):
        stats = raw_stats if isinstance(raw_stats, Mapping) else {}
        rows.append(
            {
                "adapter": str(adapter),
                "status": stats.get("status"),
                "signal_count": _int_value(stats.get("signal_count")),
                "duration_ms": _int_value(stats.get("duration_ms")),
                "error_message": stats.get("error_message"),
                "metrics": dict(stats),
            }
        )
    return rows


def _domain_stats(domains: list[dict[str, object]]) -> list[dict[str, object]]:
    return [
        {
            "domain": str(row.get("domain") or ""),
            "signals_fetched": _int_value(row.get("signals_fetched")),
            "insights_generated": _int_value(row.get("insights_generated")),
            "ideas_generated": _int_value(row.get("ideas_generated")),
            "ideas_evaluated": _int_value(row.get("ideas_evaluated")),
            "avg_score": float(row.get("avg_score") or 0.0),
        }
        for row in domains
    ]


def _recommendations(
    *,
    run: Mapping[str, object],
    stage_counts: Mapping[str, int | float],
    adapters: list[dict[str, object]],
    budget: Mapping[str, object],
) -> list[str]:
    recommendations: list[str] = []
    error_message = str(run.get("error_message") or "")
    status = _run_status(run)

    if status in {"failed", "budget_exceeded"}:
        recommendations.append(f"Review run termination context before replaying: {error_message or status}.")
    if any(adapter.get("status") not in (None, "ok") for adapter in adapters):
        recommendations.append("Inspect adapters with non-ok status before trusting source coverage.")
    if stage_counts["signals_fetched"] == 0:
        recommendations.append("Check source configuration because the run fetched no signals.")
    if stage_counts["ideas_generated"] == 0 and stage_counts["signals_fetched"]:
        recommendations.append("Review insight and ideation thresholds because fetched signals produced no ideas.")
    if _int_value(budget.get("total_tokens")) == 0:
        recommendations.append("No token usage was recorded; verify tracker configuration for cost review.")
    if not recommendations:
        recommendations.append("Compare against adjacent runs for trend changes before changing pipeline settings.")
    return recommendations


def summarize_pipeline_run(store: Store, run: dict) -> dict[str, object]:
    """Return a JSON-ready review summary for one persisted run."""
    run_id = str(run["id"])
    domains = store.get_pipeline_run_domains(run_id)
    outputs = store.get_pipeline_run_output_counts(run_id)
    stage_counts = _stage_counts(run, outputs)
    adapters = _adapter_stats(run)
    budget = _budget_summary(run)

    return {
        "id": run_id,
        "started_at": run["started_at"],
        "finished_at": run.get("completed_at"),
        "status": _run_status(run),
        "profile": _profile_name(run),
        "domain": _domain_name(run, domains),
        "config": run.get("config") or {},
        "stage_counts": stage_counts,
        "adapter_stats": adapters,
        "budget": budget,
        "domains": _domain_stats(domains),
        "errors": {
            "run": run.get("error_message") or None,
            "adapters": [
                {
                    "adapter": adapter["adapter"],
                    "status": adapter.get("status"),
                    "error_message": adapter.get("error_message"),
                }
                for adapter in adapters
                if adapter.get("error_message") or adapter.get("status") not in (None, "ok")
            ],
        },
        "follow_up_recommendations": _recommendations(
            run=run,
            stage_counts=stage_counts,
            adapters=adapters,
            budget=budget,
        ),
    }


def export_recent_pipeline_runs(store: Store, *, limit: int = 10) -> dict[str, object]:
    """Return recent pipeline runs as JSON-ready export records."""
    runs = store.get_pipeline_runs(limit=limit)
    records = [summarize_pipeline_run(store, run) for run in runs]
    return {"limit": limit, "run_count": len(records), "runs": records}


def export_pipeline_run(store: Store, *, run_id: str) -> dict[str, object]:
    """Return one pipeline run export record, or raise when absent."""
    run = store.get_pipeline_run(run_id)
    if run is None:
        raise PipelineRunExportNotFound(run_id)
    return summarize_pipeline_run(store, run)


def render_pipeline_runs_markdown(records: list[dict[str, object]], *, title: str) -> str:
    """Render pipeline run export records as markdown for human review."""
    lines = [f"# {title}", "", f"Run count: {len(records)}", ""]
    if not records:
        lines.extend(["No pipeline runs found.", ""])
        return "\n".join(lines)

    for record in records:
        stage_counts = record["stage_counts"] if isinstance(record["stage_counts"], Mapping) else {}
        budget = record["budget"] if isinstance(record["budget"], Mapping) else {}
        lines.extend(
            [
                f"## Run {record['id']}",
                "",
                f"- Status: {record['status']}",
                f"- Started: {record['started_at']}",
                f"- Finished: {record.get('finished_at') or 'not finished'}",
                f"- Profile: {record.get('profile') or 'unknown'}",
                f"- Domain: {record.get('domain') or 'mixed/unknown'}",
                "",
                "### Stage Counts",
                "",
                "| Stage | Count |",
                "| --- | ---: |",
            ]
        )
        for key in (
            "signals_fetched",
            "signals_new",
            "insights_generated",
            "clusters_found",
            "gaps_detected",
            "ideas_generated",
            "ideas_evaluated",
            "approved",
            "published",
            "approved_or_published",
            "avg_idea_score",
        ):
            lines.append(f"| {key} | {stage_counts.get(key, 0)} |")

        lines.extend(
            [
                "",
                "### Budget",
                "",
                f"- Model: {budget.get('model') or 'unknown'}",
                f"- Input tokens: {budget.get('input_tokens', 0)}",
                f"- Output tokens: {budget.get('output_tokens', 0)}",
                f"- Total tokens: {budget.get('total_tokens', 0)}",
                f"- Estimated cost USD: {float(budget.get('estimated_cost_usd') or 0.0):.6f}",
                "",
            ]
        )
        stages = budget.get("stages")
        if isinstance(stages, list) and stages:
            lines.extend(["#### Token Stages", "", "| Stage | Input | Output | Cost USD |", "| --- | ---: | ---: | ---: |"])
            for stage in stages:
                if not isinstance(stage, Mapping):
                    continue
                lines.append(
                    "| {stage} | {input} | {output} | {cost:.6f} |".format(
                        stage=stage.get("stage"),
                        input=stage.get("input_tokens", 0),
                        output=stage.get("output_tokens", 0),
                        cost=float(stage.get("estimated_cost_usd") or 0.0),
                    )
                )
            lines.append("")

        adapters = record.get("adapter_stats")
        lines.extend(["### Adapter Stats", ""])
        if isinstance(adapters, list) and adapters:
            lines.extend(["| Adapter | Status | Signals | Duration ms | Error |", "| --- | --- | ---: | ---: | --- |"])
            for adapter in adapters:
                if not isinstance(adapter, Mapping):
                    continue
                lines.append(
                    f"| {adapter.get('adapter')} | {adapter.get('status') or 'unknown'} | "
                    f"{adapter.get('signal_count', 0)} | {adapter.get('duration_ms', 0)} | "
                    f"{adapter.get('error_message') or ''} |"
                )
        else:
            lines.append("No adapter metrics recorded.")
        lines.append("")

        domains = record.get("domains")
        if isinstance(domains, list) and domains:
            lines.extend(["### Domains", "", "| Domain | Signals | Insights | Ideas | Evaluated | Avg score |", "| --- | ---: | ---: | ---: | ---: | ---: |"])
            for domain in domains:
                if not isinstance(domain, Mapping):
                    continue
                lines.append(
                    f"| {domain.get('domain')} | {domain.get('signals_fetched', 0)} | "
                    f"{domain.get('insights_generated', 0)} | {domain.get('ideas_generated', 0)} | "
                    f"{domain.get('ideas_evaluated', 0)} | {domain.get('avg_score', 0.0)} |"
                )
            lines.append("")

        errors = record.get("errors") if isinstance(record.get("errors"), Mapping) else {}
        lines.extend(["### Errors", ""])
        if errors.get("run"):
            lines.append(f"- Run: {errors['run']}")
        adapter_errors = errors.get("adapters")
        if isinstance(adapter_errors, list):
            for adapter_error in adapter_errors:
                if not isinstance(adapter_error, Mapping):
                    continue
                lines.append(
                    f"- Adapter {adapter_error.get('adapter')}: "
                    f"{adapter_error.get('status') or 'unknown'}"
                    f" {adapter_error.get('error_message') or ''}".rstrip()
                )
        if not errors.get("run") and not adapter_errors:
            lines.append("No errors recorded.")
        lines.extend(["", "### Follow-up Recommendations", ""])
        for recommendation in record.get("follow_up_recommendations", []):
            lines.append(f"- {recommendation}")
        lines.append("")

    return "\n".join(lines)
