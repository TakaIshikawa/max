"""Generate deterministic webhook consumer migration plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact
from max.spec._review_plan_common import base, row, source_summary, unique_records


SCHEMA_VERSION = "max.spec.webhook_consumer_migration_plan.v1"
KIND = "max.spec.webhook_consumer_migration_plan"


def generate_webhook_consumer_migration_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "webhook_consumer_migration")
    consumers = unique_records(
        hints.get("consumer_inventory") or hints.get("consumers"),
        [
            {
                "name": "default webhook consumer",
                "owner": "integration_owner",
                "description": "Inventory active webhook consumers before migration.",
            }
        ],
    )
    endpoints = unique_records(
        hints.get("endpoint_changes") or hints.get("endpoints"),
        [
            {
                "name": "endpoint migration",
                "owner": "integration_owner",
                "description": "Document old and new webhook endpoint behavior.",
            }
        ],
    )
    secrets = unique_records(
        hints.get("signing_secret_actions") or hints.get("signing_secrets"),
        [
            {
                "name": "signing secret rotation",
                "owner": "security_owner",
                "description": "Plan signing secret handling for migrated consumers.",
            }
        ],
    )
    retry = unique_records(
        hints.get("retry_backfill_strategy") or hints.get("backfill_strategy"),
        [
            {
                "name": "retry and backfill coverage",
                "owner": "platform_owner",
                "description": "Define retries and backfill for missed webhook deliveries.",
            }
        ],
    )
    window = unique_records(
        hints.get("compatibility_window") or hints.get("compatibility_windows"),
        [
            {
                "name": "compatibility window",
                "owner": "product_owner",
                "description": "Keep legacy and migrated webhook paths compatible through cutover.",
            }
        ],
    )
    communications = unique_records(
        hints.get("communications") or hints.get("consumer_communications"),
        [
            {
                "name": "consumer migration notice",
                "owner": "partner_owner",
                "description": "Notify webhook consumers of endpoint, secret, and retry changes.",
            }
        ],
    )
    checks = unique_records(
        hints.get("validation_checks"),
        [
            {
                "name": "webhook migration validation",
                "owner": "integration_owner",
                "description": "Validate endpoint delivery, signatures, retries, backfill, and compatibility.",
            }
        ],
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(
            ctx, consumer_count=len(consumers), endpoint_change_count=len(endpoints)
        ),
        "consumer_inventory": [
            _item("CON", index, item, "integration_owner", evidence_ids)
            for index, item in enumerate(consumers, start=1)
        ],
        "endpoint_changes": [
            _item("END", index, item, "integration_owner", evidence_ids)
            for index, item in enumerate(endpoints, start=1)
        ],
        "signing_secret_actions": [
            _item("SEC", index, item, "security_owner", evidence_ids)
            for index, item in enumerate(secrets, start=1)
        ],
        "retry_backfill_strategy": [
            _item("RET", index, item, "platform_owner", evidence_ids)
            for index, item in enumerate(retry, start=1)
        ],
        "compatibility_window": [
            _item("WIN", index, item, "product_owner", evidence_ids)
            for index, item in enumerate(window, start=1)
        ],
        "communications": [
            _item("COM", index, item, "partner_owner", evidence_ids)
            for index, item in enumerate(communications, start=1)
        ],
        "validation_checks": [
            _item("VC", index, item, "integration_owner", evidence_ids)
            for index, item in enumerate(checks, start=1)
        ],
        "evidence_references": ctx["evidence_references"],
    }


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
        endpoint=item.get("endpoint"),
    )
