"""JSON API renderer for signal quality gate status."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import int_or_zero, list_of_maps, mapping, source_metadata, strings


SCHEMA_VERSION = "max.api.signal_quality_gate_status.v1"
KIND = "max.api.signal_quality_gate_status"
PASS_STATUSES = {"pass", "passed", "ok", "success"}
WARN_STATUSES = {"warn", "warning"}
FAIL_STATUSES = {"fail", "failed", "error", "blocked"}


def signal_quality_gate_status_to_json(payload: Mapping[str, Any]) -> str:
    checks = _checks(payload)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": _summary(payload, checks),
        "checks": checks,
        "failed_checks": _checks_with_status(payload, checks, "failed_checks", FAIL_STATUSES),
        "warning_checks": _checks_with_status(payload, checks, "warning_checks", WARN_STATUSES),
        "by_source": _by_source(payload, checks),
        "remediation_actions": _remediation_actions(payload, checks),
        "metadata": source_metadata(payload, check_count=len(checks)),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _checks(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("checks")
    if not isinstance(source, list):
        source = payload.get("quality_checks")
    rows = [
        _check(item, index)
        for index, item in enumerate(source if isinstance(source, list) else [], start=1)
        if isinstance(item, Mapping)
    ]
    return sorted(rows, key=lambda row: (str(row["check_id"]), str(row["name"] or ""), str(row["status"])))


def _check(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    status = str(item.get("status") or "unknown").lower()
    return {
        "check_id": item.get("check_id") or item.get("id") or f"C{index}",
        "name": item.get("name") or item.get("check_name"),
        "category": item.get("category") or item.get("gate"),
        "source": item.get("source") or item.get("source_id") or "unknown",
        "status": status,
        "severity": item.get("severity"),
        "message": item.get("message") or item.get("reason"),
        "affected_signal_count": int_or_zero(item.get("affected_signal_count", item.get("signal_count"))),
        "remediation": item.get("remediation") or item.get("action"),
        "metadata": dict(mapping(item.get("metadata"))),
    }


def _summary(payload: Mapping[str, Any], checks: list[dict[str, Any]]) -> dict[str, int]:
    source = mapping(payload.get("summary"))
    statuses = Counter(str(check["status"]) for check in checks)
    return {
        "passed_count": int_or_zero(source.get("passed_count", sum(statuses[status] for status in PASS_STATUSES))),
        "warning_count": int_or_zero(source.get("warning_count", sum(statuses[status] for status in WARN_STATUSES))),
        "failed_count": int_or_zero(source.get("failed_count", sum(statuses[status] for status in FAIL_STATUSES))),
        "total_count": int_or_zero(source.get("total_count", len(checks))),
    }


def _checks_with_status(
    payload: Mapping[str, Any],
    checks: list[dict[str, Any]],
    field: str,
    statuses: set[str],
) -> list[dict[str, Any]]:
    explicit = list_of_maps(payload.get(field))
    if explicit:
        return sorted(
            [
                {
                    "check_id": item.get("check_id") or item.get("id") or f"X{index}",
                    "name": item.get("name") or item.get("check_name"),
                    "source": item.get("source") or item.get("source_id"),
                    "message": item.get("message") or item.get("reason"),
                }
                for index, item in enumerate(explicit, start=1)
            ],
            key=lambda row: str(row["check_id"]),
        )
    return [
        {
            "check_id": check["check_id"],
            "name": check["name"],
            "source": check["source"],
            "message": check["message"],
        }
        for check in checks
        if check["status"] in statuses
    ]


def _by_source(payload: Mapping[str, Any], checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    explicit = list_of_maps(payload.get("by_source"))
    if explicit:
        return sorted(
            [
                {
                    "source": item.get("source") or item.get("source_id") or "unknown",
                    "passed_count": int_or_zero(item.get("passed_count")),
                    "warning_count": int_or_zero(item.get("warning_count")),
                    "failed_count": int_or_zero(item.get("failed_count")),
                }
                for item in explicit
            ],
            key=lambda row: str(row["source"]),
        )
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for check in checks:
        grouped[str(check["source"] or "unknown")].append(check)
    return [
        {
            "source": source,
            "passed_count": sum(1 for check in rows if check["status"] in PASS_STATUSES),
            "warning_count": sum(1 for check in rows if check["status"] in WARN_STATUSES),
            "failed_count": sum(1 for check in rows if check["status"] in FAIL_STATUSES),
        }
        for source, rows in sorted(grouped.items())
    ]


def _remediation_actions(payload: Mapping[str, Any], checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    explicit = list_of_maps(payload.get("remediation_actions"))
    if explicit:
        return sorted(
            [{"id": item.get("id") or f"A{index}", "action": item.get("action") or item.get("title"), "check_id": item.get("check_id"), "owner": item.get("owner")} for index, item in enumerate(explicit, start=1)],
            key=lambda row: str(row["id"]),
        )
    actions = [
        {
            "id": f"remediate-{check['check_id']}",
            "action": check["remediation"] or "Remediate signal quality check",
            "check_id": check["check_id"],
            "owner": None,
        }
        for check in checks
        if check["status"] in FAIL_STATUSES | WARN_STATUSES
    ]
    return sorted(actions, key=lambda row: str(row["id"]))
