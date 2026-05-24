"""Generate deterministic model card publication plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._review_plan_common import base, source_summary, unique_records


SCHEMA_VERSION = "max.spec.model_card_publication_plan.v1"
KIND = "max.spec.model_card_publication_plan"


def generate_model_card_publication_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "model_card_publication")
    models = unique_records(
        named(hints.get("models") or hints.get("model_identity") or hints.get("model"), ("model", "name", "id")),
        [
            {
                "name": "model pending card publication",
                "model": "model pending card publication",
                "version": "to be confirmed",
                "owner": "model_owner",
            }
        ],
    )
    risk_flags = _risk_flags(hints, evidence_ids)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(
            ctx,
            model_count=len(models),
            publication_blocker_count=sum(1 for flag in risk_flags if flag["severity"] == "high"),
        ),
        "model_identity": [
            item(
                "MCP",
                index,
                record,
                "model_owner",
                evidence_ids,
                "Identify model card subject",
                name_keys=("name", "model", "id"),
                extra_keys=("model", "version", "status"),
            )
            for index, record in enumerate(models, start=1)
        ],
        "intended_use": section(
            hints,
            ("intended_use", "uses", "intended_users"),
            "MCU",
            "product_owner",
            "Document model card intended use",
            evidence_ids,
            ["intended users, supported workflows, excluded uses, and operating context"],
            extra_keys=("user", "role", "workflow"),
        ),
        "limitations": section(
            hints,
            ("limitations", "known_limitations", "constraints"),
            "MCL",
            "model_owner",
            "Document model limitation",
            evidence_ids,
            ["known model limitations, unsupported populations, failure modes, and misuse constraints"],
        ),
        "evaluation_results": section(
            hints,
            ("evaluation_results", "evaluations", "eval_summary", "evals"),
            "MCE",
            "evaluation_owner",
            "Summarize model evaluation result",
            evidence_ids,
            ["missing evaluation summary blocks publication until metrics and test coverage are documented"],
            extra_keys=("metric", "score", "threshold", "dataset"),
        ),
        "data_provenance_summary": section(
            hints,
            ("data_provenance_summary", "data_provenance", "training_data", "datasets"),
            "MCD",
            "data_owner",
            "Summarize model card data provenance",
            evidence_ids,
            ["training, tuning, evaluation, and excluded data sources with provenance and consent notes"],
            extra_keys=("dataset", "source", "license", "retention"),
        ),
        "safety_considerations": section(
            hints,
            ("safety_considerations", "safety", "risk_considerations"),
            "MCS",
            "safety_owner",
            "Document model safety consideration",
            evidence_ids,
            ["missing safety considerations block publication until risks, mitigations, and review evidence are documented"],
        ),
        "publication_checklist": section(
            hints,
            ("publication_checklist", "checklist", "publication_tasks"),
            "MCC",
            "model_owner",
            "Complete model card publication checklist",
            evidence_ids,
            ["confirm identity, version, intended use, limitations, evaluations, data provenance, safety, and links"],
        ),
        "owner_approvals": section(
            hints,
            ("owner_approvals", "approvals", "approval_gates"),
            "MCA",
            "model_owner",
            "Approve model card publication",
            evidence_ids,
            ["model owner, product owner, safety owner, data owner, and compliance approval"],
            extra_keys=("role", "approver", "status"),
        ),
        "post_publication_updates": section(
            hints,
            ("post_publication_updates", "updates", "maintenance"),
            "MCX",
            "model_owner",
            "Schedule model card post-publication update",
            evidence_ids,
            ["refresh model card after version changes, new evaluations, safety findings, or data provenance changes"],
            extra_keys=("cadence", "trigger", "deadline"),
        ),
        "publication_risk_flags": risk_flags,
        "evidence_references": ctx["evidence_references"],
    }


def _risk_flags(hints: dict[str, Any], evidence_ids: list[str]) -> list[dict[str, Any]]:
    flags = []
    if not any(key in hints for key in ("evaluation_results", "evaluations", "eval_summary", "evals")):
        flags.append(
            item(
                "MCF",
                len(flags) + 1,
                {
                    "name": "missing evaluation results",
                    "severity": "high",
                    "description": "Model card publication is blocked until evaluation results are documented.",
                },
                "evaluation_owner",
                evidence_ids,
                "Flag model card publication blocker",
            )
        )
    if not any(key in hints for key in ("safety_considerations", "safety", "risk_considerations")):
        flags.append(
            item(
                "MCF",
                len(flags) + 1,
                {
                    "name": "missing safety considerations",
                    "severity": "high",
                    "description": "Model card publication is blocked until safety considerations are documented.",
                },
                "safety_owner",
                evidence_ids,
                "Flag model card publication blocker",
            )
        )
    return flags or [
        item(
            "MCF",
            1,
            {
                "name": "required publication sections present",
                "severity": "low",
                "description": "Evaluation and safety sections are present for publication review.",
            },
            "model_owner",
            evidence_ids,
            "Record model card publication risk",
        )
    ]
