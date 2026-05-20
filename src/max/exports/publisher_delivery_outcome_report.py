"""Publisher delivery outcome report export."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from typing import Any, Iterable, Literal, TypedDict

SCHEMA_VERSION = "max.publisher_delivery_outcome_report.v1"
KIND = "max.publisher_delivery_outcome_report"

DeliveryOutcome = Literal["success", "failure", "blocked", "pending"]


class PublisherDeliveryAttemptInput(TypedDict, total=False):
    target: str
    target_id: str
    target_type: str
    publisher: str
    outcome: str
    status: str
    attempt_id: str
    artifact_id: str
    attempted_at: str
    retry_needed: bool
    retryable: bool
    blocking: bool
    error: str
    error_message: str


def build_publisher_delivery_outcome_report(
    records: Iterable[PublisherDeliveryAttemptInput | dict[str, Any]],
    *,
    title: str = "Publisher Delivery Outcome Report",
    blocking_error_limit: int = 5,
) -> dict[str, Any]:
    attempts = _normalize_attempts(records)
    targets = _target_summaries(attempts)
    retry_candidates = [attempt for attempt in attempts if attempt["retry_needed"]]
    retry_candidates.sort(key=lambda row: (row["attempted_at"] or "9999-12-31", row["target"].lower(), row["attempt_id"].lower()))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "title": _text(title) or "Publisher Delivery Outcome Report",
        "summary": _summary(attempts, retry_candidates),
        "targets": targets,
        "outcome_counts": _outcome_counts(attempts),
        "retry_candidates": retry_candidates,
        "recent_blocking_errors": _recent_blocking_errors(attempts, limit=blocking_error_limit),
        "attempts": attempts,
    }


def render_publisher_delivery_outcome_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    lines = [
        f"# {report.get('title') or 'Publisher Delivery Outcome Report'}",
        "",
        f"Schema: `{report.get('schema_version', SCHEMA_VERSION)}`",
        "",
        "## Summary",
        "",
        f"- Attempts: {summary.get('attempt_count', 0)}",
        f"- Successes: {summary.get('success_count', 0)}",
        f"- Failures: {summary.get('failure_count', 0)}",
        f"- Retry candidates: {summary.get('retry_candidate_count', 0)}",
        f"- Blocking errors: {summary.get('blocking_error_count', 0)}",
        "",
        "## Targets",
        "",
    ]
    targets = report.get("targets") or []
    if targets:
        for target in targets:
            lines.extend(
                [
                    f"### {target['target']}",
                    "",
                    f"- Type: {target['target_type']}",
                    f"- Reliability: {target['reliability_percent']}%",
                    f"- Success/failure: {target['success_count']}/{target['failure_count']}",
                    f"- Retry needed: {target['retry_needed_count']}",
                    "",
                ]
            )
    else:
        lines.append("- No publisher delivery attempts were supplied.")
    return "\n".join(lines).rstrip() + "\n"


def render_publisher_delivery_outcome_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def _normalize_attempts(records: Iterable[PublisherDeliveryAttemptInput | dict[str, Any]]) -> list[dict[str, Any]]:
    attempts = []
    for index, raw in enumerate(records):
        outcome = _outcome(raw.get("outcome") or raw.get("status"))
        error = _text(raw.get("error") or raw.get("error_message"))
        retry_needed = bool(raw.get("retry_needed") or raw.get("retryable") or (outcome in {"failure", "blocked"} and error))
        attempts.append(
            {
                "attempt_id": _text(raw.get("attempt_id") or f"attempt-{index + 1}"),
                "artifact_id": _text(raw.get("artifact_id")),
                "target": _text(raw.get("target") or raw.get("target_id") or raw.get("publisher") or "Unspecified target"),
                "target_type": _target_type(raw.get("target_type") or raw.get("publisher")),
                "outcome": outcome,
                "attempted_at": _text(raw.get("attempted_at")),
                "retry_needed": retry_needed,
                "blocking": bool(raw.get("blocking") or outcome == "blocked"),
                "error": error,
            }
        )
    attempts.sort(key=_attempt_sort_key)
    return attempts


def _target_summaries(attempts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for attempt in attempts:
        grouped[(attempt["target"], attempt["target_type"])].append(attempt)

    targets = []
    for (target, target_type), items in grouped.items():
        success_count = sum(1 for item in items if item["outcome"] == "success")
        failure_count = sum(1 for item in items if item["outcome"] in {"failure", "blocked"})
        attempt_count = len(items)
        targets.append(
            {
                "target": target,
                "target_type": target_type,
                "attempt_count": attempt_count,
                "success_count": success_count,
                "failure_count": failure_count,
                "pending_count": sum(1 for item in items if item["outcome"] == "pending"),
                "retry_needed_count": sum(1 for item in items if item["retry_needed"]),
                "reliability_percent": round((success_count / attempt_count) * 100, 1) if attempt_count else 0.0,
            }
        )
    targets.sort(key=lambda row: (row["reliability_percent"], -row["failure_count"], row["target_type"], row["target"].lower()))
    return targets


def _summary(attempts: list[dict[str, Any]], retry_candidates: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "attempt_count": len(attempts),
        "target_count": len({(attempt["target"], attempt["target_type"]) for attempt in attempts}),
        "success_count": sum(1 for attempt in attempts if attempt["outcome"] == "success"),
        "failure_count": sum(1 for attempt in attempts if attempt["outcome"] in {"failure", "blocked"}),
        "pending_count": sum(1 for attempt in attempts if attempt["outcome"] == "pending"),
        "retry_candidate_count": len(retry_candidates),
        "blocking_error_count": sum(1 for attempt in attempts if attempt["blocking"] and attempt["error"]),
    }


def _outcome_counts(attempts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter(attempt["outcome"] for attempt in attempts)
    return [{"outcome": outcome, "count": count} for outcome, count in sorted(counts.items(), key=lambda item: item[0])]


def _recent_blocking_errors(attempts: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    errors = [
        {
            "attempt_id": attempt["attempt_id"],
            "target": attempt["target"],
            "target_type": attempt["target_type"],
            "attempted_at": attempt["attempted_at"],
            "error": attempt["error"],
        }
        for attempt in attempts
        if attempt["blocking"] and attempt["error"]
    ]
    errors.sort(key=lambda row: (row["attempted_at"] or "", row["target"].lower(), row["attempt_id"].lower()), reverse=True)
    return errors[: max(limit, 0)]


def _attempt_sort_key(attempt: dict[str, Any]) -> tuple[str, str, str]:
    return (attempt["target"].lower(), attempt["attempted_at"] or "", attempt["attempt_id"].lower())


def _outcome(value: Any) -> DeliveryOutcome:
    text = _text(value).lower()
    if text in {"success", "succeeded", "delivered", "complete", "completed"}:
        return "success"
    if text in {"blocked", "blocking"}:
        return "blocked"
    if text in {"pending", "queued", "in_progress"}:
        return "pending"
    if text in {"failure", "failed", "error", "errored"}:
        return "failure"
    return "pending"


def _target_type(value: Any) -> str:
    text = _text(value).lower().replace(" ", "_").replace("-", "_")
    if text in {"filesystem", "file", "local_file", "local"}:
        return "filesystem"
    if text in {"tact", "tact_daemon", "daemon"}:
        return "tact_daemon"
    if text in {"external", "external_publisher", "publisher"}:
        return "external_publisher"
    return text or "external_publisher"


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()
