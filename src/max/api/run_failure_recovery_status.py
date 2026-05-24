"""JSON API renderer for run failure recovery status."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "max.api.run_failure_recovery_status.v1"
KIND = "max.api.run_failure_recovery_status"
STATUS_RANK = {"terminal": 0, "blocked": 1, "resumable": 2, "retryable": 3}
SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def run_failure_recovery_status_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    runs = _runs(payload)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": _summary(runs),
        "runs": runs,
        "blocked_runs": [row for row in runs if row["recovery_status"] == "blocked"],
        "terminal_runs": [row for row in runs if row["recovery_status"] == "terminal"],
        "recovery_actions": [action for row in runs for action in row["recovery_actions"]],
        "metadata": _metadata(payload, runs, as_of),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _runs(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("runs") if isinstance(payload.get("runs"), list) else payload.get("failures")
    rows = [_run(item, index) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    rows.sort(key=lambda row: (SEVERITY_RANK[row["severity"]], STATUS_RANK[row["recovery_status"]], row["run_id"]))
    return rows


def _run(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    checkpoint = _text(item.get("resumable_checkpoint") or item.get("checkpoint") or item.get("resume_from"))
    deps = _strings(item.get("blocked_dependencies", item.get("dependencies")))
    lost = _int(item.get("lost_artifact_count", item.get("missing_artifacts", item.get("lost_artifacts"))))
    retryable = _bool(item.get("retryable", item.get("can_retry")))
    terminal = _bool(item.get("terminal", item.get("fatal")))
    status = _status(checkpoint, deps, retryable, terminal)
    severity = _severity(item.get("severity"), status, lost, deps)
    run_id = _text(item.get("run_id") or item.get("id")) or f"run-{index}"
    return {
        "run_id": run_id,
        "failed_stage": _text(item.get("failed_stage") or item.get("stage")) or "unknown-stage",
        "recovery_status": status,
        "retry_eligible": retryable and not terminal and not deps,
        "resumable_checkpoint": checkpoint,
        "lost_artifact_count": lost,
        "blocked_dependencies": deps,
        "severity": severity,
        "owner": _text(item.get("owner")) or "unassigned",
        "recovery_actions": _actions(run_id, status, checkpoint, deps, lost, item),
    }


def _status(checkpoint: str, deps: list[str], retryable: bool, terminal: bool) -> str:
    if terminal:
        return "terminal"
    if deps:
        return "blocked"
    if checkpoint:
        return "resumable"
    if retryable:
        return "retryable"
    return "terminal"


def _severity(value: Any, status: str, lost: int, deps: list[str]) -> str:
    explicit = _text(value).lower()
    if explicit in SEVERITY_RANK:
        return explicit
    if status == "terminal" or lost >= 5:
        return "critical"
    if status == "blocked" or deps:
        return "high"
    if lost:
        return "medium"
    return "low"


def _actions(run_id: str, status: str, checkpoint: str, deps: list[str], lost: int, item: Mapping[str, Any]) -> list[dict[str, Any]]:
    owner = _text(item.get("owner")) or "unassigned"
    if status == "blocked":
        return [{"run_id": run_id, "owner": owner, "action": "Unblock dependency before recovery", "dependency": dep} for dep in deps]
    if status == "resumable":
        return [{"run_id": run_id, "owner": owner, "action": "Resume run from checkpoint", "checkpoint": checkpoint}]
    if status == "retryable":
        return [{"run_id": run_id, "owner": owner, "action": "Retry failed stage"}]
    return [{"run_id": run_id, "owner": owner, "action": "Triage terminal failure and rebuild lost artifacts", "lost_artifact_count": lost}]


def _summary(runs: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(row["recovery_status"] for row in runs)
    return {"run_count": len(runs), "resumable_count": counts["resumable"], "retryable_count": counts["retryable"], "blocked_count": counts["blocked"], "terminal_count": counts["terminal"], "lost_artifact_count": sum(row["lost_artifact_count"] for row in runs)}


def _metadata(payload: Mapping[str, Any], runs: list[dict[str, Any]], as_of: str | datetime | None) -> dict[str, Any]:
    metadata = dict(payload.get("metadata") if isinstance(payload.get("metadata"), Mapping) else {})
    return {**metadata, "source_schema_version": payload.get("schema_version"), "source_kind": payload.get("kind"), "as_of": _as_of(as_of), "run_count": len(runs)}


def _strings(value: Any) -> list[str]:
    values = value if isinstance(value, list) else ([] if value in (None, "") else [value])
    return sorted(_text(item) for item in values if _text(item))


def _bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _int(value: Any) -> int:
    if isinstance(value, list):
        return len(value)
    try:
        return max(0, int(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def _as_of(value: str | datetime | None) -> str | None:
    if isinstance(value, datetime):
        parsed = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return value


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
