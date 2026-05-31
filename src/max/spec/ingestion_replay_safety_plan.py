"""Generate ingestion replay safety plans."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping


def generate_ingestion_replay_safety_plan(replay_request: Mapping[str, Any], current_checkpoints: Mapping[str, Any]) -> dict[str, Any]:
    source = _text(replay_request.get("source")) or "unknown"
    profile = _text(replay_request.get("profile")) or "default"
    start = _text(replay_request.get("start_at"))
    end = _text(replay_request.get("end_at"))
    duration_hours = round((_parse(end) - _parse(start)).total_seconds() / 3600, 2) if start and end else 0.0
    checkpoint_key = f"{source}:{profile}"
    previous_checkpoint = _text(current_checkpoints.get(checkpoint_key) or current_checkpoints.get(source) or current_checkpoints.get("checkpoint"))
    dedupe_enabled = replay_request.get("dedupe_enabled", True) is not False
    backup = bool(replay_request.get("checkpoint_backup") or replay_request.get("backup_id"))
    blockers = []
    if not backup:
        blockers.append("missing checkpoint backup")
    if duration_hours > 168:
        blockers.append("broad replay range")
    if not dedupe_enabled:
        blockers.append("dedupe disabled")
    return {"schema_version": "max.ingestion_replay_safety_plan.v1", "kind": "max.ingestion_replay_safety_plan", "scope": {"source": source, "profile": profile, "start_at": start, "end_at": end, "duration_hours": duration_hours}, "checkpoint_backup": {"present": backup, "previous_checkpoint": previous_checkpoint, "expected_checkpoint_after_replay": end or previous_checkpoint}, "dedupe_safeguards": {"enabled": dedupe_enabled, "key": "source/profile/external_id"}, "dry_run_sample_size": _int(replay_request.get("dry_run_sample_size"), 100), "budget_guardrails": replay_request.get("budget_guardrails") or {"max_records": _int(replay_request.get("max_records"), 10000)}, "execution_steps": [{"id": "STEP1", "description": "Backup checkpoint and export replay candidate IDs."}, {"id": "STEP2", "description": "Run write-disabled replay sample."}, {"id": "STEP3", "description": "Run bounded replay with dedupe checks."}], "rollback_steps": [{"id": "RB1", "description": "Restore previous checkpoint."}, {"id": "RB2", "description": "Delete replay writes by replay batch ID if validation fails."}], "verification_queries": ["count replayed signals by source/profile", "count duplicate external IDs"], "abort_criteria": ["duplicate spike", "checkpoint moves outside requested window", "budget guardrail breach"], "blockers": blockers}


def _parse(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _int(value: Any, default: int) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return default


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
