"""Generate deterministic evaluation benchmark refresh plans."""

from __future__ import annotations

from datetime import date
from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._planning_common import compact
from max.spec._review_plan_common import base, row, source_summary, unique_records


SCHEMA_VERSION = "max.spec.evaluation_benchmark_refresh_plan.v1"
KIND = "max.spec.evaluation_benchmark_refresh_plan"
DEFAULT_STALE_AFTER_DAYS = 180


def generate_evaluation_benchmark_refresh_plan(spec_like: Any) -> dict[str, Any]:
    spec, ctx, metadata_hints, evidence_ids = base(spec_like, "evaluation_benchmark_refresh")
    hints = metadata_hints or (spec if isinstance(spec, dict) else {})
    stale_after_days = _int(hints.get("stale_after_days"), DEFAULT_STALE_AFTER_DAYS)
    benchmarks = unique_records(
        named(
            hints.get("benchmark_inventory") or hints.get("benchmarks") or hints.get("evaluation_benchmarks"),
            ("benchmark", "dataset", "source"),
        ),
        [{"name": "evaluation benchmark", "owner": "evaluation_owner", "age_days": stale_after_days}],
    )
    inventory = [
        _benchmark_item("EBI", index, record, stale_after_days, evidence_ids)
        for index, record in enumerate(benchmarks, start=1)
    ]
    stale = sorted(
        (record for record in inventory if record["is_stale"]),
        key=lambda record: (-_int(record.get("age_days"), 0), compact(record.get("name")).casefold()),
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "title": "Evaluation Benchmark Refresh Plan",
        "summary": source_summary(
            ctx,
            benchmark_count=len(inventory),
            stale_benchmark_count=len(stale),
            stale_after_days=stale_after_days,
        ),
        "benchmark_inventory": inventory,
        "stale_benchmarks": [
            row(
                "EBS",
                index,
                record["name"],
                record["owner"],
                f"Refresh {record['name']} because age {record.get('age_days', 'unknown')} days meets stale threshold {stale_after_days}.",
                evidence_ids,
                severity="high" if _int(record.get("age_days"), 0) >= stale_after_days * 2 else "medium",
                age_days=record.get("age_days"),
                stale_after_days=stale_after_days,
            )
            for index, record in enumerate(stale, start=1)
        ],
        "refresh_candidates": section(
            hints,
            ("refresh_candidates", "candidates", "replacement_candidates"),
            "EBC",
            "evaluation_owner",
            "Prepare benchmark refresh candidate",
            evidence_ids,
            [record["name"] for record in stale] or ["source fresh benchmark examples"],
            extra_keys=("source", "slice", "sample_size"),
        ),
        "validation_sampling": section(
            hints,
            ("validation_sampling", "sampling", "sampling_plan"),
            "EBV",
            "evaluation_owner",
            "Validate refreshed benchmark sample",
            evidence_ids,
            ["stratified sample by task, difficulty, language, source, and expected model capability"],
        ),
        "approval_gates": section(
            hints,
            ("approval_gates", "approvers", "approvals"),
            "EBA",
            "approval_owner",
            "Approve benchmark refresh",
            evidence_ids,
            ["evaluation owner, data governance, model owner, and release manager approval"],
        ),
        "rollout_steps": section(
            hints,
            ("rollout_steps", "rollout", "deployment_steps"),
            "EBR",
            "evaluation_owner",
            "Roll out refreshed benchmark",
            evidence_ids,
            ["version benchmark, rerun baseline, compare score deltas, publish changelog, and archive prior version"],
        ),
        "rollback_criteria": section(
            hints,
            ("rollback_criteria", "rollback", "backout"),
            "EBK",
            "evaluation_owner",
            "Define benchmark refresh rollback criteria",
            evidence_ids,
            ["rollback if validation sample fails, baseline variance exceeds tolerance, or approval is revoked"],
        ),
        "evidence_references": ctx["evidence_references"],
    }


def _benchmark_item(prefix: str, index: int, record: dict[str, Any], stale_after_days: int, evidence_ids: list[str]) -> dict[str, Any]:
    data = item(
        prefix,
        index,
        record,
        "evaluation_owner",
        evidence_ids,
        "Inventory evaluation benchmark",
        name_keys=("name", "benchmark", "dataset", "source"),
        extra_keys=("source", "slice", "last_refreshed_at", "as_of"),
    )
    age_days = _age_days(record)
    data["age_days"] = age_days
    data["stale_after_days"] = stale_after_days
    data["is_stale"] = age_days >= stale_after_days
    return data


def _age_days(record: dict[str, Any]) -> int:
    explicit = _int(record.get("age_days"), -1)
    if explicit >= 0:
        return explicit
    refreshed = _date(record.get("last_refreshed_at") or record.get("refreshed_at"))
    as_of = _date(record.get("as_of"))
    if refreshed and as_of:
        return max((as_of - refreshed).days, 0)
    return 0


def _date(value: Any) -> date | None:
    text = compact(value)
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _int(value: Any, fallback: int) -> int:
    try:
        return int(float(compact(value)))
    except (TypeError, ValueError):
        return fallback
