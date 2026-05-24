"""Generate deterministic synthetic data usage exception plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._planning_common import compact
from max.spec._review_plan_common import base, source_summary, unique_records


SCHEMA_VERSION = "max.spec.synthetic_data_usage_exception_plan.v1"
KIND = "max.spec.synthetic_data_usage_exception_plan"


def generate_synthetic_data_usage_exception_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "synthetic_data_usage_exception")
    exceptions = [
        _exception(index, record, evidence_ids)
        for index, record in enumerate(
            unique_records(
                named(
                    hints.get("exceptions")
                    or hints.get("scopes")
                    or hints.get("datasets")
                    or hints.get("uses"),
                    ("scope", "dataset", "use_case", "purpose"),
                ),
                [
                    {
                        "name": "synthetic data usage exception",
                        "owner": "data_governance_owner",
                        "expiry": "30 days",
                    }
                ],
            ),
            start=1,
        )
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, exception_count=len(exceptions)),
        "exception_scope": exceptions,
        "generation_method": _named_section(
            hints,
            ("generation_method", "generation_methods", "method"),
            ("method", "tool", "model"),
            "SDG",
            "ml_platform_owner",
            "Document synthetic data generation method",
            evidence_ids,
            [],
            name_keys=("name", "method", "tool", "model", "description"),
            extra_keys=("method", "tool", "model", "dataset"),
        ),
        "source_data_restrictions": _named_section(
            hints,
            ("source_data_restrictions", "source_restrictions", "restrictions"),
            ("restriction", "source", "dataset"),
            "SDS",
            "privacy_owner",
            "Define source-data restriction",
            evidence_ids,
            [],
            name_keys=("name", "restriction", "source", "dataset", "description"),
            extra_keys=("data_classification", "source", "dataset"),
        ),
        "privacy_controls": _named_section(
            hints,
            ("privacy_controls", "controls", "compensating_controls"),
            ("control",),
            "SDP",
            "privacy_owner",
            "Operate synthetic data privacy control",
            evidence_ids,
            [],
            name_keys=("name", "control", "description"),
            extra_keys=("control", "data_classification"),
        ),
        "validation_checks": _named_section(
            hints,
            ("validation_checks", "validation", "checks"),
            ("check", "metric"),
            "SDV",
            "data_quality_owner",
            "Validate synthetic data exception",
            evidence_ids,
            [],
            name_keys=("name", "check", "metric", "description"),
            extra_keys=("check", "metric", "threshold"),
        ),
        "expiry_review": section(
            hints,
            ("expiry_review", "expiry", "review"),
            "SDE",
            "data_governance_owner",
            "Review synthetic data exception expiry",
            evidence_ids,
            [],
        ),
        "approval_criteria": section(
            hints,
            ("approval_criteria", "approvals", "approval_gates"),
            "SDA",
            "approval_owner",
            "Gate synthetic data exception approval",
            evidence_ids,
            [],
        ),
        "verification_evidence": section(
            hints,
            ("verification_evidence", "evidence", "verification"),
            "SDF",
            "data_governance_owner",
            "Capture synthetic data exception evidence",
            evidence_ids,
            [],
        ),
        "evidence_references": ctx["evidence_references"],
    }


def _named_section(
    hints: dict[str, Any],
    keys: tuple[str, ...],
    aliases: tuple[str, ...],
    prefix: str,
    owner: str,
    label: str,
    evidence_ids: list[str],
    fallback: list[Any],
    *,
    name_keys: tuple[str, ...] = ("name", "title", "id", "description"),
    extra_keys: tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    value = next((hints[key] for key in keys if key in hints), None)
    return section(
        {"value": named(value, aliases)},
        ("value",),
        prefix,
        owner,
        label,
        evidence_ids,
        fallback,
        name_keys=name_keys,
        extra_keys=extra_keys,
    )


def _exception(index: int, record: dict[str, Any], evidence_ids: list[str]) -> dict[str, Any]:
    scope = (
        compact(record.get("scope"))
        or compact(record.get("dataset"))
        or compact(record.get("use_case"))
        or compact(record.get("purpose"))
        or compact(record.get("name"))
        or "synthetic data usage exception"
    )
    expiry = compact(record.get("expiry") or record.get("expiration") or record.get("expires_at")) or "30 days"
    return item(
        "SDX",
        index,
        {**record, "name": scope, "expiry": expiry},
        "data_governance_owner",
        evidence_ids,
        "Review synthetic data usage exception",
        extra_keys=("scope", "dataset", "use_case", "purpose", "generation_method"),
    )
