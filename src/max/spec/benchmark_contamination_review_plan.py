"""Generate deterministic benchmark contamination review plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._planning_common import compact
from max.spec._review_plan_common import base, row, source_summary, unique_records


SCHEMA_VERSION = "max.spec.benchmark_contamination_review_plan.v1"
KIND = "max.spec.benchmark_contamination_review_plan"


def generate_benchmark_contamination_review_plan(spec_like: Any) -> dict[str, Any]:
    spec, ctx, metadata_hints, evidence_ids = base(spec_like, "benchmark_contamination_review")
    hints = metadata_hints or (spec if isinstance(spec, dict) else {})
    benchmarks = unique_records(
        named(
            hints.get("benchmarks") or hints.get("evaluation_benchmarks") or hints.get("datasets"),
            ("benchmark", "dataset", "source"),
        ),
        [{"name": "evaluation benchmark", "benchmark": "evaluation benchmark", "severity": "medium"}],
    )
    threshold = _threshold(hints.get("risk_threshold") or hints.get("threshold"), 0.05)
    callouts = _high_risk_callouts(benchmarks, threshold, evidence_ids)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "title": "Benchmark Contamination Review Plan",
        "summary": source_summary(
            ctx,
            benchmark_count=len(benchmarks),
            high_risk_callout_count=len(callouts),
        ),
        "benchmarks": [
            item(
                "BCR",
                index,
                record,
                "evaluation_owner",
                evidence_ids,
                "Review benchmark contamination",
                name_keys=("name", "benchmark", "dataset", "source"),
                extra_keys=("benchmark", "dataset", "source", "overlap_score", "threshold"),
            )
            for index, record in enumerate(benchmarks, start=1)
        ],
        "contamination_sources": section(
            hints,
            ("contamination_sources", "sources", "overlap_sources"),
            "BCS",
            "data_governance_owner",
            "Review contamination source",
            evidence_ids,
            ["training data, prompt examples, documentation snippets, synthetic fixtures, and eval rehearsal logs"],
        ),
        "detection_methods": section(
            hints,
            ("detection_methods", "methods", "checks"),
            "BCD",
            "evaluation_owner",
            "Run contamination detection method",
            evidence_ids,
            ["exact hash match, n-gram similarity, embedding nearest-neighbor search, and prompt fixture audit"],
        ),
        "thresholds": section(
            hints,
            ("thresholds", "gates", "risk_thresholds"),
            "BCT",
            "quality_owner",
            "Set contamination threshold",
            evidence_ids,
            [f"high-risk callout when overlap signal exceeds {threshold:g}"],
            extra_keys=("threshold", "metric"),
        ),
        "sampling_plan": section(
            hints,
            ("sampling_plan", "sampling", "sample"),
            "BCP",
            "evaluation_owner",
            "Sample benchmark for contamination",
            evidence_ids,
            ["stratified sample by task, source, age, and expected model capability"],
        ),
        "high_risk_callouts": callouts,
        "remediation_options": section(
            hints,
            ("remediation_options", "remediations", "actions"),
            "BCM",
            "evaluation_owner",
            "Plan contamination remediation",
            evidence_ids,
            ["remove contaminated examples, replace benchmark slice, quarantine fixture, or disclose limitation"],
        ),
        "benchmark_replacement": section(
            hints,
            ("benchmark_replacement", "replacement_plan", "replacement"),
            "BCE",
            "evaluation_owner",
            "Prepare benchmark replacement",
            evidence_ids,
            ["source fresh examples, version replacement set, rerun baseline, and archive lineage"],
        ),
        "disclosure_steps": section(
            hints,
            ("disclosure_steps", "disclosures", "disclosure"),
            "BCL",
            "program_owner",
            "Prepare contamination disclosure",
            evidence_ids,
            ["document affected benchmark, overlap signal, mitigation, and residual limitation"],
        ),
        "signoff": section(
            hints,
            ("signoff", "approvals", "approval_checklist"),
            "BCA",
            "program_owner",
            "Approve benchmark contamination review",
            evidence_ids,
            ["evaluation, data governance, model owner, and release manager signoff"],
        ),
        "evidence_references": ctx["evidence_references"],
    }


def _high_risk_callouts(
    benchmarks: list[dict[str, Any]], threshold: float, evidence_ids: list[str]
) -> list[dict[str, Any]]:
    callouts: list[dict[str, Any]] = []
    for record in benchmarks:
        score = _threshold(record.get("overlap_score") or record.get("overlap") or record.get("signal"), 0.0)
        if score <= threshold and compact(record.get("severity")).lower() not in {"critical", "high"}:
            continue
        name = compact(record.get("name") or record.get("benchmark") or record.get("dataset"))
        callouts.append(
            row(
                "BCH",
                len(callouts) + 1,
                f"high contamination signal for {name or 'benchmark'}",
                compact(record.get("owner")) or "evaluation_owner",
                f"Overlap signal {score:g} exceeds threshold {threshold:g}; replace, quarantine, or disclose before relying on this benchmark.",
                evidence_ids,
                severity=compact(record.get("severity")) or "high",
                benchmark=name,
                overlap_score=score,
                threshold=threshold,
            )
        )
    return callouts


def _threshold(value: Any, fallback: float) -> float:
    text = compact(value).strip("%")
    if not text:
        return fallback
    try:
        number = float(text)
    except ValueError:
        return fallback
    return number / 100 if number > 1 else number
