"""Generate deterministic secret rotation runbooks."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._planning_common import compact
from max.spec._review_plan_common import base, row, source_summary, unique_records


SCHEMA_VERSION = "max.spec.secret_rotation_runbook.v1"
KIND = "max.spec.secret_rotation_runbook"


def generate_secret_rotation_runbook(spec_like: Any) -> dict[str, Any]:
    """Return an ordered runbook for rotating application and platform secrets."""
    _spec, ctx, hints, evidence_ids = base(spec_like, "secret_rotation")
    secrets = unique_records(
        named(
            hints.get("secret_inventory") or hints.get("secrets") or hints.get("secret_identifiers"),
            ("secret_id", "identifier", "name"),
        ),
        [{"name": "secret rotation inventory", "secret_id": "secret rotation inventory"}],
    )
    service_records = unique_records(
        named(hints.get("dependent_services") or hints.get("services") or hints.get("dependencies"), ("service", "name")),
        [],
    )
    rotation_window = _rotation_window(hints)
    blockers = _blockers(secrets, service_records, evidence_ids)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "title": "Secret Rotation Runbook",
        "summary": source_summary(
            ctx,
            secret_count=len(secrets),
            dependent_service_count=len(service_records),
            blocker_count=len(blockers),
            rotation_window=rotation_window,
        ),
        "rotation_window": rotation_window,
        "secret_inventory": [
            item(
                "SRI",
                index,
                record,
                "security_owner",
                evidence_ids,
                "Inventory secret for rotation",
                name_keys=("name", "secret_id", "identifier"),
                extra_keys=("secret_id", "identifier", "environment", "last_rotated", "rotation_window"),
            )
            for index, record in enumerate(secrets, start=1)
        ],
        "owners": section(
            hints,
            ("owners", "owner_assignments"),
            "SRO",
            "security_owner",
            "Assign secret rotation owner",
            evidence_ids,
            ["security owner, service owner, on-call owner, and approver assigned"],
            extra_keys=("role", "team", "service"),
        ),
        "dependent_services": [
            item(
                "SRD",
                index,
                record,
                "service_owner",
                evidence_ids,
                "Map dependent service",
                name_keys=("name", "service"),
                extra_keys=("service", "environment", "validation_endpoint", "owner_role"),
            )
            for index, record in enumerate(service_records, start=1)
        ],
        "rotation_steps": _rotation_steps(secrets, rotation_window, evidence_ids),
        "validation_steps": section(
            hints,
            ("validation_steps", "validation", "post_rotation_validation"),
            "SRV",
            "quality_owner",
            "Validate rotated secret",
            evidence_ids,
            ["smoke test dependent services", "verify authentication succeeds", "confirm old credential is revoked"],
            extra_keys=("service", "validation_endpoint", "expected_result"),
        ),
        "rollback_steps": section(
            hints,
            ("rollback_steps", "rollback"),
            "SRB",
            "on_call_owner",
            "Prepare secret rotation rollback",
            evidence_ids,
            ["restore previous secret from approved vault version, validate service health, and expire rollback credential"],
            extra_keys=("service", "rollback_owner", "expiry"),
        ),
        "communication_checkpoints": section(
            hints,
            ("communication_checkpoints", "comms", "communications"),
            "SRC",
            "release_manager",
            "Send secret rotation communication",
            evidence_ids,
            ["pre-rotation notice, start checkpoint, validation complete notice, and closure summary"],
            extra_keys=("channel", "audience", "deadline"),
        ),
        "blockers": blockers,
        "evidence_references": ctx["evidence_references"],
    }


def _rotation_steps(
    secrets: list[dict[str, Any]], rotation_window: str, evidence_ids: list[str]
) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    for secret in secrets:
        name = compact(secret.get("name")) or compact(secret.get("secret_id")) or "secret rotation inventory"
        owner = compact(secret.get("owner")) or "security_owner"
        steps.extend(
            [
                row(
                    "SRR",
                    len(steps) + 1,
                    f"prepare {name}",
                    owner,
                    f"Confirm consumers, vault path, and rotation window {rotation_window}.",
                    evidence_ids,
                    phase="prepare",
                    secret=name,
                ),
                row(
                    "SRR",
                    len(steps) + 1,
                    f"rotate {name}",
                    owner,
                    "Create replacement secret, deploy it to consumers, and revoke the old credential.",
                    evidence_ids,
                    phase="rotate",
                    secret=name,
                ),
            ]
        )
    return steps


def _blockers(
    secrets: list[dict[str, Any]], services: list[dict[str, Any]], evidence_ids: list[str]
) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    for secret in secrets:
        name = compact(secret.get("name")) or "secret"
        if not compact(secret.get("owner")):
            blockers.append(row("SRK", len(blockers) + 1, f"missing owner for {name}", "security_owner", "Secret rotation requires an accountable owner.", evidence_ids, severity="high", secret=name, missing_field="owner"))
        if not compact(secret.get("secret_id") or secret.get("identifier")):
            blockers.append(row("SRK", len(blockers) + 1, f"missing secret identifier for {name}", "security_owner", "Secret rotation requires a vault path, key id, or secret identifier.", evidence_ids, severity="critical", secret=name, missing_field="secret_identifier"))
    if not services:
        blockers.append(row("SRK", len(blockers) + 1, "missing dependent service", "service_owner", "Secret rotation must identify dependent services before execution.", evidence_ids, severity="high", missing_field="dependent_service"))
    return blockers


def _rotation_window(hints: dict[str, Any]) -> str:
    explicit = compact(hints.get("rotation_window") or hints.get("recommended_rotation_window"))
    if explicit:
        return explicit
    emergency = compact(hints.get("emergency") or hints.get("urgency") or hints.get("incident")).lower()
    if emergency in {"true", "yes", "emergency", "urgent", "incident", "compromised"}:
        return "within 4 hours"
    return "within 7 days"
