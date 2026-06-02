"""SCIM directory sync cutover plan helper."""

from __future__ import annotations

from typing import Any, Mapping


def generate_scim_directory_sync_cutover_plan(config: Mapping[str, Any]) -> dict[str, Any]:
    groups = _list(config.get("group_mappings")) or ["Validate default all-groups mapping before cutover."]
    users = _list(config.get("user_scope")) or ["all active users"]
    return {"schema_version": "max.scim_directory_sync_cutover_plan.v1", "kind": "max.scim_directory_sync_cutover_plan", "source_idp": _text(config.get("source_idp")) or "unknown IdP", "target_scim_connector": _text(config.get("target_scim_connector")) or "unknown SCIM connector", "sync_scope": {"groups": groups, "users": users}, "dry_run_reconciliation": ["Compare IdP user count to SCIM provisioned count.", "Verify group memberships and suspended user handling.", "Resolve unmatched users before enabling writes."], "cutover_steps": ["Freeze manual directory edits.", "Enable SCIM connector in dry-run verified mode.", "Switch provisioning source to SCIM.", "Run post-cutover reconciliation."], "rollback": ["Disable SCIM writes.", "Restore previous directory provisioning source.", "Replay missed membership changes from audit logs."], "owner_approvals": _list(config.get("owner_approvals")) or ["Identity owner", "Security owner", "Application owner"], "post_cutover_monitoring": ["Provisioning error rate", "Group membership drift", "Login failure rate"]}


def render_scim_directory_sync_cutover_plan_markdown(plan: Mapping[str, Any]) -> str:
    lines = [f"# SCIM Directory Sync Cutover Plan", "", f"- Source IdP: {plan.get('source_idp')}", f"- Target SCIM Connector: {plan.get('target_scim_connector')}", "", "## SCIM Scope", ""]
    lines.extend([f"- Group: {item}" for item in plan.get("sync_scope", {}).get("groups", [])])
    lines.extend([f"- User: {item}" for item in plan.get("sync_scope", {}).get("users", [])])
    for title, key in [("Reconciliation Checks", "dry_run_reconciliation"), ("Cutover Checklist", "cutover_steps"), ("Rollback", "rollback"), ("Approvals", "owner_approvals"), ("Monitoring", "post_cutover_monitoring")]:
        lines.extend(["", f"## {title}", ""])
        lines.extend([f"- {item}" for item in plan.get(key, [])])
    return "\n".join(lines).rstrip() + "\n"


def _list(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [value]
    return [_text(item) for item in value if _text(item)] if isinstance(value, list) else []


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
