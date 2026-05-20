"""Publication failure triage digest for idea publication history."""

from __future__ import annotations

import csv
import json
from collections.abc import Mapping
from io import StringIO
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store


SCHEMA_VERSION = "max.publication_failure_triage.v1"
KIND = "max.publication_failure_triage"
SUCCESS_STATUSES = {"published", "success", "succeeded", "completed"}
CSV_COLUMNS = (
    "target_type",
    "target_url",
    "status",
    "open_failure_count",
    "affected_idea_count",
    "latest_failure_at",
    "latest_error",
    "retry_priority",
)


def build_publication_failure_triage(
    store: "Store",
    *,
    limit: int = 500,
) -> dict[str, Any]:
    """Build a deterministic digest of open publication failures."""
    if limit < 1:
        raise ValueError("limit must be at least 1")

    attempts = _publication_attempts(store, limit)
    open_failures = _open_failures(attempts)
    groups = _failure_groups(open_failures)
    affected = _affected_ideas(open_failures, attempts)
    summary = {
        "attempt_count": len(attempts),
        "failure_attempt_count": sum(1 for item in attempts if not _is_success(item)),
        "open_failure_count": len(open_failures),
        "failure_group_count": len(groups),
        "affected_idea_count": len(affected),
        "cleared_failure_count": max(
            sum(1 for item in attempts if not _is_success(item)) - len(open_failures),
            0,
        ),
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "filters": {"limit": limit},
        "summary": summary,
        "failure_groups": groups,
        "affected_ideas": affected,
        "next_actions": _next_actions(groups),
    }


def render_publication_failure_triage(report: Mapping[str, Any], *, fmt: str = "json") -> str:
    """Render publication failure triage as JSON, Markdown, or CSV."""
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt == "csv":
        return _render_csv(report)
    if fmt != "markdown":
        raise ValueError(f"Unsupported publication failure triage format: {fmt}")

    summary = _mapping(report.get("summary"))
    lines = [
        "# Publication Failure Triage",
        "",
        f"Schema: `{report.get('schema_version')}`",
        f"Open failures: {summary.get('open_failure_count', 0)}",
        f"Affected ideas: {summary.get('affected_idea_count', 0)}",
        "",
        "## Failure Groups",
        "",
        "| Target Type | Target | Status | Open Failures | Ideas | Latest Failure | Priority |",
        "| --- | --- | --- | ---: | ---: | --- | --- |",
    ]
    for group in _list_of_maps(report.get("failure_groups")):
        lines.append(
            "| `{}` | `{}` | `{}` | {} | {} | {} | {} |".format(
                group.get("target_type") or "",
                group.get("target_url") or "",
                group.get("status") or "",
                group.get("open_failure_count", 0),
                group.get("affected_idea_count", 0),
                group.get("latest_failure_at") or "",
                group.get("retry_priority") or "",
            )
        )
    if not report.get("failure_groups"):
        lines.append("| none | none | none | 0 | 0 |  | none |")
    lines.extend(["", "## Next Actions", ""])
    actions = report.get("next_actions")
    lines.extend(f"- {item}" for item in actions) if isinstance(actions, list) and actions else lines.append("- None")
    return "\n".join(lines).rstrip() + "\n"


def _render_csv(report: Mapping[str, Any]) -> str:
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for group in _list_of_maps(report.get("failure_groups")):
        writer.writerow({key: group.get(key, "") for key in CSV_COLUMNS})
    return output.getvalue()


def _publication_attempts(store: "Store", limit: int) -> list[dict[str, Any]]:
    attempts: list[dict[str, Any]] = []
    for unit in store.get_buildable_units(limit=limit):
        attempts.extend(store.list_publication_attempts(unit.id, limit=100))
    return sorted(attempts, key=lambda row: (str(row.get("created_at") or ""), str(row.get("id") or "")))


def _open_failures(attempts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest_success: dict[tuple[str, str, str], str] = {}
    for item in attempts:
        if _is_success(item):
            latest_success[_idea_target_key(item)] = str(item.get("created_at") or "")
    result = []
    for item in attempts:
        if _is_success(item):
            continue
        success_at = latest_success.get(_idea_target_key(item))
        if success_at and success_at >= str(item.get("created_at") or ""):
            continue
        result.append(item)
    return result


def _failure_groups(open_failures: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for item in open_failures:
        key = (
            str(item.get("target_type") or "unknown"),
            str(item.get("target_url") or ""),
            str(item.get("status") or "failed"),
        )
        grouped.setdefault(key, []).append(item)

    rows = []
    for (target_type, target_url, status), items in grouped.items():
        latest = max(items, key=lambda row: (str(row.get("created_at") or ""), str(row.get("id") or "")))
        idea_ids = sorted({str(row.get("idea_id") or "") for row in items if row.get("idea_id")})
        count = len(items)
        rows.append(
            {
                "target_type": target_type,
                "target_url": target_url,
                "status": status,
                "open_failure_count": count,
                "affected_idea_ids": idea_ids,
                "affected_idea_count": len(idea_ids),
                "latest_failure_at": latest.get("created_at"),
                "latest_error": latest.get("error") or _status_text(latest),
                "retry_priority": _priority(count, latest.get("response_status")),
            }
        )
    return sorted(
        rows,
        key=lambda row: (
            -int(row["open_failure_count"]),
            _reverse_text(row.get("latest_failure_at")),
            str(row.get("target_type") or ""),
            str(row.get("target_url") or ""),
            str(row.get("status") or ""),
        ),
    )


def _affected_ideas(open_failures: list[dict[str, Any]], attempts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest_by_idea: dict[str, dict[str, Any]] = {}
    open_by_idea: dict[str, list[dict[str, Any]]] = {}
    for item in attempts:
        idea_id = str(item.get("idea_id") or "")
        if idea_id:
            latest_by_idea[idea_id] = item
    for item in open_failures:
        idea_id = str(item.get("idea_id") or "")
        if idea_id:
            open_by_idea.setdefault(idea_id, []).append(item)
    rows = []
    for idea_id, failures in open_by_idea.items():
        latest_failure = max(failures, key=lambda row: (str(row.get("created_at") or ""), str(row.get("id") or "")))
        rows.append(
            {
                "idea_id": idea_id,
                "open_failure_count": len(failures),
                "latest_failure_at": latest_failure.get("created_at"),
                "latest_error": latest_failure.get("error") or _status_text(latest_failure),
                "latest_publication_status": latest_by_idea.get(idea_id, {}).get("status"),
                "targets": sorted({_target_key(row) for row in failures}),
            }
        )
    return sorted(rows, key=lambda row: (-int(row["open_failure_count"]), _reverse_text(row.get("latest_failure_at")), str(row["idea_id"])))


def _next_actions(groups: list[dict[str, Any]]) -> list[str]:
    if not groups:
        return ["No open publication failures require retry triage."]
    actions = []
    for group in groups[:3]:
        actions.append(
            "Retry or repair `{}` publications for {} affected idea(s); latest error: {}".format(
                group["target_type"],
                group["affected_idea_count"],
                group["latest_error"] or "unknown",
            )
        )
    return actions


def _is_success(item: Mapping[str, Any]) -> bool:
    return str(item.get("status") or "").lower() in SUCCESS_STATUSES


def _idea_target_key(item: Mapping[str, Any]) -> tuple[str, str, str]:
    return (str(item.get("idea_id") or ""), str(item.get("target_type") or ""), str(item.get("target_url") or ""))


def _target_key(item: Mapping[str, Any]) -> str:
    return f"{item.get('target_type') or 'unknown'}:{item.get('target_url') or ''}"


def _status_text(item: Mapping[str, Any]) -> str:
    status = item.get("response_status")
    return f"HTTP {status}" if status is not None else str(item.get("status") or "failed")


def _priority(count: int, response_status: Any) -> str:
    if count >= 3:
        return "p0"
    if response_status in (429, 500, 502, 503, 504):
        return "p1"
    return "p2"


def _reverse_text(value: Any) -> str:
    return "".join(chr(0x10FFFF - ord(ch)) for ch in str(value or ""))


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list_of_maps(value: Any) -> list[Mapping[str, Any]]:
    return [item for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []
