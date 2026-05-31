"""Generate deterministic model output retention plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._planning_common import compact
from max.spec._review_plan_common import base, source_summary, unique_records

SCHEMA_VERSION = "max.spec.model_output_retention_plan.v1"
KIND = "max.spec.model_output_retention_plan"


def generate_model_output_retention_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "model_output_retention")
    rules = unique_records(named(hints.get("retention_rules") or hints.get("rules") or hints.get("outputs"), ("output_class", "data_class", "name")), [{"name": "model output retention bootstrap", "output_class": "unknown", "retention_period": "define before launch"}])
    rules = sorted(rules, key=lambda row: (_sensitive(row), compact(row.get("name")).casefold()))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "source": ctx["source"], "title": "Model Output Retention Plan", "summary": source_summary(ctx, rule_count=len(rules), sensitive_rule_count=sum(1 for row in rules if _sensitive(row) == 0)), "retention_rules": [item("MOR", i, row, "data_owner", evidence_ids, "Define model output retention rule", extra_keys=("output_class", "data_class", "retention_period")) for i, row in enumerate(rules, 1)], "deletion_triggers": section(hints, ("deletion_triggers", "triggers"), "MOD", "data_owner", "Define model output deletion trigger", evidence_ids, ["retention expiry, customer deletion request, account closure, policy change, or incident purge"]), "legal_holds": section(hints, ("legal_holds", "holds"), "MOH", "legal_owner", "Track model output legal hold", evidence_ids, ["legal hold owner, scope, start date, release criteria, and exception approval"]), "audit_evidence": section(hints, ("audit_evidence", "evidence"), "MOE", "compliance_owner", "Collect retention audit evidence", evidence_ids, ["policy mapping, deletion logs, hold register, exception approvals, and sampled output ids"]), "exception_handling": section(hints, ("exception_handling", "exceptions"), "MOX", "data_owner", "Handle model output retention exception", evidence_ids, ["document exception reason, approval, expiration, compensating control, and review cadence"]), "review_actions": _review_actions(rules, evidence_ids), "evidence_references": ctx["evidence_references"]}


def _sensitive(row: dict[str, Any]) -> int:
    text = f"{compact(row.get('output_class'))} {compact(row.get('data_class'))} {compact(row.get('name'))}".lower()
    return 0 if any(term in text for term in ("sensitive", "pii", "phi", "regulated", "customer")) else 1


def _review_actions(rules: list[dict[str, Any]], evidence_ids: list[str]) -> list[dict[str, Any]]:
    return [item("MOV", i, {"name": compact(row.get("name")), "severity": "high" if _sensitive(row) == 0 else "medium", "description": "Sensitive output class requires shorter review cadence or explicit retention approval." if _sensitive(row) == 0 else "Confirm retention period, deletion trigger, owner, and evidence capture."}, "data_owner", evidence_ids, "Review model output retention rule") for i, row in enumerate(rules, 1)]
