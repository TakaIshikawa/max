"""Generate deterministic synthetic evaluation disclosure plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._review_plan_common import base, source_summary, unique_records


SCHEMA_VERSION = "max.spec.synthetic_evaluation_disclosure_plan.v1"
KIND = "max.spec.synthetic_evaluation_disclosure_plan"


def generate_synthetic_evaluation_disclosure_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "synthetic_evaluation_disclosure")
    scopes = unique_records(
        named(hints.get("synthetic_data_scope") or hints.get("scopes") or hints.get("examples"), ("scope", "dataset", "benchmark")),
        [{"name": "synthetic evaluation examples", "scope": "evaluation and benchmark reporting"}],
    )
    risks = list(hints.get("risks") or [])
    if hints.get("unlabeled_synthetic_examples") or hints.get("unlabeled_examples"):
        risks.append({"name": "unlabeled synthetic examples", "severity": "high", "description": "Synthetic examples must be labeled before evaluation or reporting."})
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, scope_count=len(scopes)),
        "synthetic_data_scope": [
            item(
                "SED",
                index,
                record,
                "evaluation_owner",
                evidence_ids,
                "Document synthetic evaluation scope",
                name_keys=("name", "scope", "dataset", "benchmark"),
                extra_keys=("scope", "dataset", "benchmark", "purpose"),
            )
            for index, record in enumerate(scopes, start=1)
        ],
        "disclosure_audience": section(
            hints,
            ("disclosure_audience", "audience", "audiences"),
            "SEA",
            "communications_owner",
            "Define synthetic evaluation disclosure audience",
            evidence_ids,
            ["internal reviewers, customers, external benchmark readers, or regulators as applicable"],
        ),
        "labeling_requirements": section(
            hints,
            ("labeling_requirements", "labels", "labeling"),
            "SEL",
            "evaluation_owner",
            "Label synthetic evaluation example",
            evidence_ids,
            ["mark synthetic examples in datasets, reports, charts, model cards, and benchmark appendices"],
        ),
        "validation_evidence": section(
            hints,
            ("validation_evidence", "validation", "evidence"),
            "SEV",
            "data_quality_owner",
            "Validate synthetic evaluation disclosure",
            evidence_ids,
            ["generation method, sampling checks, human review, leakage check, and representativeness limits"],
        ),
        "exclusions": section(
            hints,
            ("exclusions", "excluded_uses"),
            "SEX",
            "evaluation_owner",
            "Exclude synthetic evaluation use",
            evidence_ids,
            ["do not present synthetic-only results as production, customer, or real-world benchmark performance"],
        ),
        "owner_checklist": section(
            hints,
            ("owner_checklist", "checklist", "owners"),
            "SEO",
            "program_owner",
            "Complete synthetic evaluation disclosure checklist",
            evidence_ids,
            ["evaluation, legal, communications, product, and responsible AI owners approve disclosure"],
        ),
        "risks": section({"risks": risks}, ("risks",), "SER", "risk_owner", "Review synthetic evaluation disclosure risk", evidence_ids, []),
        "acceptance_criteria": section(
            hints,
            ("acceptance_criteria", "approval_criteria"),
            "SEC",
            "program_owner",
            "Accept synthetic evaluation disclosure",
            evidence_ids,
            ["scope identified, audience disclosure approved, labels verified, and validation evidence attached"],
        ),
        "evidence_references": ctx["evidence_references"],
    }
