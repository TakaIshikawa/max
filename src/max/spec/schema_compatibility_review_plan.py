"""Generate deterministic schema compatibility review plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact
from max.spec._review_plan_common import base, row, source_summary, unique_records, values


SCHEMA_VERSION = "max.spec.schema_compatibility_review_plan.v1"
KIND = "max.spec.schema_compatibility_review_plan"


def generate_schema_compatibility_review_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "schema_compatibility_review")
    producers = values(
        hints.get("producers") or hints.get("producer_services"),
        [ctx["stack_label"] or "producer service"],
    )
    consumers = values(
        hints.get("consumers") or hints.get("consumer_services"), [ctx["target_user"]]
    )
    risks = unique_records(
        hints.get("compatibility_risks") or hints.get("schema_changes") or ctx["risks"],
        [
            {
                "name": "schema compatibility risk",
                "owner": "platform_owner",
                "description": "Assess producer and consumer compatibility before release.",
            }
        ],
    )
    migration = unique_records(
        hints.get("migration_backfill_work") or hints.get("backfill_requirements"),
        [
            {
                "name": "schema migration and backfill",
                "owner": "data_owner",
                "description": "Plan data migration or backfill required by schema changes.",
            }
        ],
    )
    tests = unique_records(
        hints.get("contract_tests") or hints.get("contract_test_coverage"),
        [
            {
                "name": "contract compatibility test",
                "owner": "quality_owner",
                "description": "Validate producer and consumer contract compatibility.",
            }
        ],
    )
    windows = unique_records(
        hints.get("version_windows") or hints.get("compatibility_windows"),
        [
            {
                "name": "version compatibility window",
                "owner": "release_owner",
                "description": "Define supported schema versions and deprecation timing.",
            }
        ],
    )
    approvals = unique_records(
        hints.get("owner_approvals") or hints.get("approvals"),
        [
            {
                "name": "schema owner approval",
                "owner": "platform_owner",
                "description": "Approve risks, migrations, tests, and version windows.",
            }
        ],
    )
    communications = unique_records(
        hints.get("communications"),
        [
            {
                "name": "schema change notice",
                "owner": "developer_relations_owner",
                "description": "Communicate schema compatibility expectations to affected owners.",
            }
        ],
    )
    checks = unique_records(
        hints.get("validation_checks"),
        [
            {
                "name": "schema compatibility validation",
                "owner": "quality_owner",
                "description": "Validate producers, consumers, risks, backfills, tests, and version windows.",
            }
        ],
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(
            ctx, producer_count=len(producers), consumer_count=len(consumers), risk_count=len(risks)
        ),
        "producers": [
            _named("PROD", index, item, "producer_owner", evidence_ids)
            for index, item in enumerate(producers, start=1)
        ],
        "consumers": [
            _named("CONS", index, item, "consumer_owner", evidence_ids)
            for index, item in enumerate(consumers, start=1)
        ],
        "compatibility_risks": [
            _item("RISK", index, item, "platform_owner", evidence_ids)
            for index, item in enumerate(risks, start=1)
        ],
        "migration_backfill_work": [
            _item("MB", index, item, "data_owner", evidence_ids)
            for index, item in enumerate(migration, start=1)
        ],
        "contract_tests": [
            _item("CT", index, item, "quality_owner", evidence_ids)
            for index, item in enumerate(tests, start=1)
        ],
        "version_windows": [
            _item("VW", index, item, "release_owner", evidence_ids)
            for index, item in enumerate(windows, start=1)
        ],
        "owner_approvals": [
            _item("APP", index, item, "platform_owner", evidence_ids)
            for index, item in enumerate(approvals, start=1)
        ],
        "communications": [
            _item("COM", index, item, "developer_relations_owner", evidence_ids)
            for index, item in enumerate(communications, start=1)
        ],
        "validation_checks": [
            _item("VC", index, item, "quality_owner", evidence_ids)
            for index, item in enumerate(checks, start=1)
        ],
        "evidence_references": ctx["evidence_references"],
    }


def _named(
    prefix: str, index: int, name: str, owner: str, evidence_ids: list[str]
) -> dict[str, Any]:
    return row(prefix, index, name, owner, name, evidence_ids)


def _item(
    prefix: str, index: int, item: dict[str, Any], owner: str, evidence_ids: list[str]
) -> dict[str, Any]:
    return row(
        prefix,
        index,
        compact(item.get("name")),
        compact(item.get("owner")) or owner,
        compact(item.get("description")) or compact(item.get("name")),
        evidence_ids,
        severity=item.get("severity"),
        status=item.get("status") or item.get("deadline_status"),
        deadline=item.get("deadline") or item.get("due"),
        version=item.get("version"),
    )
