"""Generate deterministic feedback taxonomy migration plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, section
from max.spec._planning_common import compact
from max.spec._review_plan_common import base, source_summary, unique_records

SCHEMA_VERSION = "max.spec.feedback_taxonomy_migration_plan.v1"
KIND = "max.spec.feedback_taxonomy_migration_plan"


def generate_feedback_taxonomy_migration_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "feedback_taxonomy_migration")
    current = unique_records(hints.get("current_taxonomy") or hints.get("legacy_labels"), [{"name": "legacy feedback label"}])
    proposed = unique_records(hints.get("proposed_taxonomy") or hints.get("new_labels"), [{"name": "new feedback label"}])
    mappings = unique_records(hints.get("mapping_rules") or hints.get("mappings"), [])
    mapped = {compact(r.get("from") or r.get("legacy") or r.get("name")).casefold() for r in mappings}
    blockers = [r["name"] for r in current if compact(r.get("name")).casefold() not in mapped] if mappings else [r["name"] for r in current]
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "source": ctx["source"], "title": "Feedback Taxonomy Migration Plan", "summary": source_summary(ctx, legacy_label_count=len(current), proposed_label_count=len(proposed), blocker_count=len(blockers)), "current_taxonomy": [item("FTL", i, r, "feedback_owner", evidence_ids, "Inventory legacy taxonomy") for i, r in enumerate(current, 1)], "proposed_taxonomy": [item("FTN", i, r, "feedback_owner", evidence_ids, "Inventory proposed taxonomy") for i, r in enumerate(proposed, 1)], "mapping_rules": [item("FTM", i, r, "feedback_owner", evidence_ids, "Map taxonomy label", name_keys=("name", "from", "legacy"), extra_keys=("from", "to", "legacy", "new")) for i, r in enumerate(mappings or [{"name": "define legacy-to-new label mapping"}], 1)], "blockers": [{"label": label, "reason": "Legacy label has no deterministic mapping rule."} for label in blockers], "migration_steps": section(hints, ("migration_steps", "steps"), "FTS", "feedback_owner", "Run taxonomy migration", evidence_ids, ["freeze writes, backfill mapped labels, dual-write, validate reports, remove legacy labels"]), "validation_checks": section(hints, ("validation_checks", "checks"), "FTV", "feedback_owner", "Validate taxonomy migration", evidence_ids, ["record counts match, unmapped labels are zero, and score distributions remain explainable"]), "reporting_impacts": section(hints, ("reporting_impacts", "reporting"), "FTR", "analytics_owner", "Document reporting impact", evidence_ids, ["update dashboards, exports, and historical label glossary"]), "rollback_plan": section(hints, ("rollback_plan", "rollback"), "FTB", "feedback_owner", "Prepare taxonomy rollback", evidence_ids, ["restore legacy labels from immutable mapping snapshot"]), "approval_roles": section(hints, ("approval_roles", "approvers"), "FTA", "feedback_owner", "Approve taxonomy migration", evidence_ids, ["feedback owner, analytics owner, and product owner approval"]), "evidence_references": ctx["evidence_references"]}
