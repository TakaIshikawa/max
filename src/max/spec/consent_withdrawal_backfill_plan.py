"""Consent withdrawal backfill plan helper."""

from __future__ import annotations

from typing import Any, Mapping


def generate_consent_withdrawal_backfill_plan(config: Mapping[str, Any]) -> dict[str, Any]:
    return {"schema_version": "max.consent_withdrawal_backfill_plan.v1", "kind": "max.consent_withdrawal_backfill_plan", "affected_consent_records": _list(config.get("affected_consent_records")) or ["Identify consent withdrawals missing downstream suppression."], "downstream_processors": _list(config.get("downstream_processors")) or ["Inventory downstream processors before execution."], "backfill_batches": _list(config.get("backfill_batches")) or ["Run a pilot batch, then process remaining withdrawals by received_at order."], "suppression_verification": ["Verify processor suppression receipts.", "Sample withdrawn subjects for no further processing.", "Reconcile suppression audit logs."], "notification_requirements": _list(config.get("notification_requirements")) or ["Notify privacy owner and processor contacts after completion."], "rollback_controls": ["Pause new batches on verification failure.", "Restore previous suppression marker only with privacy approval.", "Preserve audit evidence for all reverted records."]}


def render_consent_withdrawal_backfill_plan_markdown(plan: Mapping[str, Any]) -> str:
    sections = [("Scope", "affected_consent_records"), ("Downstream Processors", "downstream_processors"), ("Execution Batches", "backfill_batches"), ("Verification", "suppression_verification"), ("Notifications", "notification_requirements"), ("Rollback", "rollback_controls")]
    lines = ["# Consent Withdrawal Backfill Plan"]
    for title, key in sections:
        lines.extend(["", f"## {title}", ""])
        lines.extend([f"- {item}" for item in plan.get(key, [])])
    return "\n".join(lines).rstrip() + "\n"


def _list(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [value]
    return [_text(item) for item in value if _text(item)] if isinstance(value, list) else []


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
