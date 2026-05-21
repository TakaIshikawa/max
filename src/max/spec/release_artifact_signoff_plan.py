"""Generate deterministic release artifact signoff plans."""

from __future__ import annotations

from typing import Any


SCHEMA_VERSION = "max-release-artifact-signoff-plan/v1"
KIND = "max.spec.release_artifact_signoff_plan"


def generate_release_artifact_signoff_plan(spec_like: Any) -> dict[str, Any]:
    spec = _dict(spec_like)
    plan = _nested(spec, "release_artifact_signoff")
    artifacts = _artifacts(plan, spec)
    approvers = _rows(plan.get("required_approvers") or plan.get("approvers") or spec.get("approvers"), "approver", "RAS-A")
    provenance = _rows(plan.get("provenance_evidence") or plan.get("verification_evidence") or spec.get("provenance_evidence"), "evidence", "RAS-P")
    destinations = _rows(plan.get("publication_destinations") or spec.get("publication_destinations"), "destination", "RAS-D")
    blockers = _blockers(artifacts, approvers, provenance, plan, spec)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "signed_count": sum(1 for row in artifacts if row["signoff_status"] == "signed"),
            "pending_count": sum(1 for row in artifacts if row["signoff_status"] == "pending"),
            "blocked_count": sum(1 for row in artifacts if row["signoff_status"] == "blocked") + len(blockers),
        },
        "artifacts": artifacts,
        "approvers": approvers,
        "provenance_evidence": provenance,
        "publication_destinations": destinations,
        "blockers": blockers,
        "signoff_status": "blocked" if blockers else ("pending" if any(row["signoff_status"] == "pending" for row in artifacts) else "signed"),
    }


def render_release_artifact_signoff_plan_markdown(plan_or_spec: dict[str, Any] | None = None) -> str:
    plan = plan_or_spec if isinstance(plan_or_spec, dict) and plan_or_spec.get("kind") == KIND else generate_release_artifact_signoff_plan(plan_or_spec)
    lines = ["# Release Artifact Signoff Plan", ""]
    for title, key, label in (("Artifacts", "artifacts", "artifact"), ("Approvers", "approvers", "approver"), ("Provenance Evidence", "provenance_evidence", "evidence"), ("Publication Destinations", "publication_destinations", "destination"), ("Blockers", "blockers", "blocker")):
        _section(lines, title, plan[key], label)
    return "\n".join(lines).rstrip() + "\n"


def _artifacts(plan: dict[str, Any], spec: dict[str, Any]) -> list[dict[str, str]]:
    rows = _rows(plan.get("artifacts") or spec.get("artifacts"), "artifact", "RAS-R")
    if not rows:
        rows = [{"id": "RAS-R001", "artifact": "artifact-required"}]
    for row in rows:
        signed = _text(row.get("signed")).casefold() in {"true", "yes", "signed"}
        required = _text(row.get("required") or "true").casefold() not in {"false", "no"}
        row["signoff_status"] = "signed" if signed else ("blocked" if required else "pending")
        row.setdefault("checksum", "checksum-required")
        row.setdefault("build_provenance", "provenance-required")
    return rows


def _blockers(artifacts: list[dict[str, str]], approvers: list[dict[str, str]], provenance: list[dict[str, str]], plan: dict[str, Any], spec: dict[str, Any]) -> list[dict[str, str]]:
    blockers = []
    if not approvers:
        blockers.append({"blocker": "missing approvers", "owner": "release_owner"})
    if not provenance and any(row.get("build_provenance") == "provenance-required" for row in artifacts):
        blockers.append({"blocker": "missing provenance", "owner": "build_owner"})
    for row in artifacts:
        if row["signoff_status"] == "blocked":
            blockers.append({"blocker": "unsigned required artifact", "artifact": row["artifact"], "owner": "release_owner"})
    return _numbered(blockers, "RAS-B")


def _rows(value: Any, key: str, prefix: str) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    rows = []
    for item in value:
        row = {str(k): _text(v) for k, v in (item.items() if isinstance(item, dict) else [(key, item)]) if _text(v)}
        if row.get(key) or row.get("name"):
            row[key] = row.get(key) or row["name"]
            rows.append(row)
    return _numbered(sorted(rows, key=lambda row: row[key].casefold()), prefix)


def _section(lines: list[str], title: str, rows: list[dict[str, str]], label: str) -> None:
    lines.extend([f"## {title}", ""])
    lines.extend(f"- {row['id']}: {row.get(label)}" for row in rows)
    if not rows:
        lines.append("- None.")
    lines.append("")


def _nested(spec: dict[str, Any], key: str) -> dict[str, Any]:
    metadata = spec.get("metadata") if isinstance(spec.get("metadata"), dict) else {}
    return _dict(spec.get(key) or metadata.get(key))


def _numbered(rows: list[dict[str, str]], prefix: str) -> list[dict[str, str]]:
    for index, row in enumerate(rows, start=1):
        row["id"] = f"{prefix}{index:03d}"
    return rows


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return " ".join(str(value).split()) if value is not None else ""
