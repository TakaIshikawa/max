"""Generate deterministic environment promotion plans."""

from __future__ import annotations

from typing import Any


SCHEMA_VERSION = "max-environment-promotion-plan/v1"
KIND = "max.spec.environment_promotion_plan"
DEFAULT_ORDER = ["dev", "staging", "production"]


def generate_environment_promotion_plan(spec_like: dict[str, Any] | None = None) -> dict[str, Any]:
    spec = spec_like if isinstance(spec_like, dict) else {}
    path = _promotion_path(spec)
    gates = _gate_checks(spec, path)
    blockers = [gate for gate in gates if gate["status"] == "blocked"]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "environment_count": len(path),
            "gate_count": len(gates),
            "blocked_gate_count": len(blockers),
            "freeze_window_count": sum(1 for row in path if row["freeze_window"] != "none"),
        },
        "promotion_path": path,
        "gate_checks": gates,
        "blockers": blockers,
        "rollback_checkpoint": _rollback_checkpoint(spec, path),
    }


def render_environment_promotion_plan_markdown(plan_or_spec: dict[str, Any] | None = None) -> str:
    plan = plan_or_spec if _is_plan(plan_or_spec) else generate_environment_promotion_plan(plan_or_spec)
    lines = ["# Environment Promotion Plan", "", f"Schema version: {plan['schema_version']}", "", "## Promotion Path", ""]
    for row in plan["promotion_path"]:
        lines.append(f"- {row['id']}: {row['environment']} artifact={row['artifact']} owner={row['owner']} freeze={row['freeze_window']}")
    lines.extend(["", "## Gate Checks", ""])
    for gate in plan["gate_checks"]:
        lines.append(f"- {gate['id']}: {gate['environment']} {gate['gate']} status={gate['status']} owner={gate['owner']}")
    lines.extend(["", "## Blockers", ""])
    if plan["blockers"]:
        for blocker in plan["blockers"]:
            lines.append(f"- {blocker['id']}: {blocker['environment']} {blocker['gate']}")
    else:
        lines.append("- No blockers identified.")
    checkpoint = plan["rollback_checkpoint"]
    lines.extend(["", "## Rollback Checkpoint", "", f"- Environment: {checkpoint['environment']}", f"- Artifact: {checkpoint['artifact']}", f"- Owner: {checkpoint['owner']}"])
    return "\n".join(lines).rstrip() + "\n"


def _promotion_path(spec: dict[str, Any]) -> list[dict[str, str]]:
    raw_envs = _raw_envs(spec)
    if not raw_envs:
        raw_envs = [{"environment": name, "order": index} for index, name in enumerate(DEFAULT_ORDER, start=1)]
    rows = []
    for index, raw in enumerate(raw_envs, start=1):
        rows.append({"id": "", "environment": _text(raw.get("environment") or raw.get("name")) or f"environment-{index}", "order": _int(raw.get("order"), _order_index(raw.get("environment") or raw.get("name"), index)), "artifact": _text(raw.get("artifact") or raw.get("release_artifact")) or _artifact(spec), "owner": _text(raw.get("owner")) or "release_owner", "freeze_window": _text(raw.get("freeze_window")) or "none"})
    rows = sorted(rows, key=lambda row: (row["order"], row["environment"].casefold()))
    for index, row in enumerate(rows, start=1):
        row["id"] = f"EPP-{index:03d}"
    return rows


def _gate_checks(spec: dict[str, Any], path: list[dict[str, str]]) -> list[dict[str, str]]:
    raw_gates = _raw_items(spec, "approval_gates", "environment_promotion") + _raw_items(spec, "smoke_checks", "environment_promotion") + _raw_items(spec, "data_migration_checks", "environment_promotion")
    rows = []
    if raw_gates:
        for index, raw in enumerate(raw_gates, start=1):
            rows.append({"id": "", "environment": _text(raw.get("environment")) or "all", "gate": _text(raw.get("gate") or raw.get("name") or raw.get("check")) or f"gate-{index}", "status": _status(raw), "owner": _text(raw.get("owner")) or "release_owner"})
    else:
        for env in path:
            rows.append({"id": "", "environment": env["environment"], "gate": "approval gate", "status": "pending", "owner": env["owner"]})
            rows.append({"id": "", "environment": env["environment"], "gate": "smoke check", "status": "pending", "owner": env["owner"]})
    rows = sorted(rows, key=lambda row: (_env_order(row["environment"], path), row["status"] != "blocked", row["gate"].casefold()))
    for index, row in enumerate(rows, start=1):
        row["id"] = f"EGC-{index:03d}"
    return rows


def _rollback_checkpoint(spec: dict[str, Any], path: list[dict[str, str]]) -> dict[str, str]:
    checkpoint = _dict(_dict(spec.get("metadata")).get("rollback_checkpoint") or spec.get("rollback_checkpoint"))
    target = path[-2] if len(path) > 1 else path[0]
    return {"environment": _text(checkpoint.get("environment")) or target["environment"], "artifact": _text(checkpoint.get("artifact")) or target["artifact"], "owner": _text(checkpoint.get("owner")) or target["owner"]}


def _raw_envs(spec: dict[str, Any]) -> list[dict[str, Any]]:
    return _raw_items(spec, "environments", "environment_promotion")


def _raw_items(spec: dict[str, Any], key: str, nested: str) -> list[dict[str, Any]]:
    metadata = _dict(spec.get("metadata"))
    plan = _dict(metadata.get(nested) or spec.get(nested))
    candidates = plan.get(key) or metadata.get(key) or spec.get(key)
    return [item for item in candidates if isinstance(item, dict)] if isinstance(candidates, list) else []


def _artifact(spec: dict[str, Any]) -> str:
    artifacts = spec.get("release_artifacts") or _dict(spec.get("metadata")).get("release_artifacts")
    if isinstance(artifacts, list) and artifacts:
        return _text(artifacts[0]) or "release-artifact-required"
    return _text(spec.get("release_artifact")) or "release-artifact-required"


def _status(raw: dict[str, Any]) -> str:
    value = _text(raw.get("status")).casefold()
    if value in {"blocked", "failed", "fail"} or raw.get("blocked") is True:
        return "blocked"
    if value in {"passed", "approved", "complete"}:
        return "passed"
    return "pending"


def _env_order(name: str, path: list[dict[str, str]]) -> int:
    lookup = {row["environment"]: index for index, row in enumerate(path)}
    return lookup.get(name, len(path))


def _order_index(value: Any, fallback: int) -> int:
    text = _text(value).casefold()
    return DEFAULT_ORDER.index(text) + 1 if text in DEFAULT_ORDER else fallback


def _is_plan(value: dict[str, Any] | None) -> bool:
    return isinstance(value, dict) and value.get("kind") == KIND and "promotion_path" in value


def _int(value: Any, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return " ".join(str(value).split()) if value is not None else ""
