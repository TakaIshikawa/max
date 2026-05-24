"""JSON API renderer for tact publish readiness."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import bool_or_default, int_or_zero, list_of_maps, mapping, source_metadata, strings


SCHEMA_VERSION = "max.api.tact_publish_readiness.v1"
KIND = "max.api.tact_publish_readiness"
READY_STATUSES = {"ready", "passed", "valid"}
BLOCKED_STATUSES = {"blocked", "failed", "invalid"}


def tact_publish_readiness_to_json(payload: Mapping[str, Any]) -> str:
    specs = _specs(payload)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": _summary(payload, specs),
        "specs": specs,
        "destinations": _destinations(payload, specs),
        "validation_failures": _validation_failures(payload, specs),
        "missing_evidence": _missing_evidence(payload, specs),
        "dry_run_results": _dry_run_results(payload),
        "next_actions": _next_actions(payload, specs),
        "metadata": source_metadata(payload, spec_count=len(specs)),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _specs(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("specs")
    if not isinstance(source, list):
        source = payload.get("generated_specs")
    rows = [_spec(item, index) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    return sorted(rows, key=lambda row: (str(row["spec_id"]), str(row["destination"])))


def _spec(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    validation_status = str(item.get("validation_status") or item.get("status") or "unknown").lower()
    destination_ready = bool_or_default(item.get("destination_ready"), default=validation_status in READY_STATUSES)
    evidence = strings(item.get("missing_evidence") or item.get("missing_evidence_ids"))
    ready = item.get("ready")
    if ready is None:
        ready = validation_status in READY_STATUSES and destination_ready and not evidence
    return {
        "spec_id": item.get("spec_id") or item.get("id") or f"S{index}",
        "title": item.get("title") or item.get("name"),
        "destination": item.get("destination") or item.get("target_type") or "unknown",
        "validation_status": validation_status,
        "destination_ready": destination_ready,
        "publisher_configured": bool_or_default(item.get("publisher_configured"), default=destination_ready),
        "ready": bool(ready),
        "missing_evidence": evidence,
        "failure_reasons": strings(item.get("failure_reasons") or item.get("errors")),
        "metadata": dict(mapping(item.get("metadata"))),
    }


def _summary(payload: Mapping[str, Any], specs: list[dict[str, Any]]) -> dict[str, int]:
    source = mapping(payload.get("summary"))
    ready_count = sum(1 for spec in specs if spec["ready"])
    return {
        "ready_count": int_or_zero(source.get("ready_count", ready_count)),
        "blocked_count": int_or_zero(source.get("blocked_count", len(specs) - ready_count)),
        "total_count": int_or_zero(source.get("total_count", len(specs))),
    }


def _destinations(payload: Mapping[str, Any], specs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    explicit = list_of_maps(payload.get("destinations"))
    if explicit:
        return sorted(
            [{"destination": item.get("destination") or item.get("target_type") or "unknown", "configured_count": int_or_zero(item.get("configured_count")), "unconfigured_count": int_or_zero(item.get("unconfigured_count")), "ready_count": int_or_zero(item.get("ready_count"))} for item in explicit],
            key=lambda row: str(row["destination"]),
        )
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for spec in specs:
        grouped[str(spec["destination"] or "unknown")].append(spec)
    return [
        {
            "destination": destination,
            "configured_count": sum(1 for spec in rows if spec["publisher_configured"]),
            "unconfigured_count": sum(1 for spec in rows if not spec["publisher_configured"]),
            "ready_count": sum(1 for spec in rows if spec["ready"]),
        }
        for destination, rows in sorted(grouped.items())
    ]


def _validation_failures(payload: Mapping[str, Any], specs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    explicit = list_of_maps(payload.get("validation_failures"))
    if explicit:
        return sorted([{"spec_id": item.get("spec_id") or item.get("id") or f"V{index}", "reasons": strings(item.get("reasons") or item.get("failure_reasons"))} for index, item in enumerate(explicit, start=1)], key=lambda row: str(row["spec_id"]))
    return [{"spec_id": spec["spec_id"], "reasons": spec["failure_reasons"]} for spec in specs if spec["validation_status"] in BLOCKED_STATUSES or spec["failure_reasons"]]


def _missing_evidence(payload: Mapping[str, Any], specs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    explicit = list_of_maps(payload.get("missing_evidence"))
    if explicit:
        return sorted([{"spec_id": item.get("spec_id") or item.get("id") or f"E{index}", "evidence_ids": strings(item.get("evidence_ids") or item.get("missing_evidence"))} for index, item in enumerate(explicit, start=1)], key=lambda row: str(row["spec_id"]))
    return [{"spec_id": spec["spec_id"], "evidence_ids": spec["missing_evidence"]} for spec in specs if spec["missing_evidence"]]


def _dry_run_results(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    return sorted(
        [{"spec_id": item.get("spec_id") or item.get("id") or f"D{index}", "destination": item.get("destination") or item.get("target_type"), "status": item.get("status"), "message": item.get("message")} for index, item in enumerate(list_of_maps(payload.get("dry_run_results")), start=1)],
        key=lambda row: (str(row["spec_id"]), str(row["destination"] or "")),
    )


def _next_actions(payload: Mapping[str, Any], specs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    explicit = list_of_maps(payload.get("next_actions"))
    if explicit:
        return sorted([{"id": item.get("id") or f"A{index}", "action": item.get("action") or item.get("title"), "spec_id": item.get("spec_id"), "owner": item.get("owner")} for index, item in enumerate(explicit, start=1)], key=lambda row: str(row["id"]))
    return sorted([{"id": f"fix-{spec['spec_id']}", "action": "Resolve publish readiness blocker", "spec_id": spec["spec_id"], "owner": None} for spec in specs if not spec["ready"]], key=lambda row: str(row["id"]))
