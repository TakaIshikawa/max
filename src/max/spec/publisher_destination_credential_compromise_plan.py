"""Generate deterministic publisher destination credential compromise plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, summary
from max.spec._review_plan_common import base, ordered, row, unique_records, values

SCHEMA_VERSION = "max.spec.publisher_destination_credential_compromise_plan.v1"
KIND = "max.spec.publisher_destination_credential_compromise_plan"


def generate_publisher_destination_credential_compromise_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "publisher_destination_credential_compromise")
    required = ("destination", "credential_id", "detected_at", "exposure_scope", "owner")
    _require(hints, required)

    destination = compact(hints["destination"])
    credential_id = compact(hints["credential_id"])
    owner = compact(hints["owner"])
    scope = compact(hints["exposure_scope"])
    critical = scope.lower() == "critical"
    publications = unique_records(
        hints.get("affected_publications"),
        [{"name": "publication impact to be confirmed"}],
    )
    rotation_steps = values(
        hints.get("rotation_steps"),
        ["create replacement credential", "deploy replacement to publisher destination", "revoke compromised credential"],
    )
    containment_actions = values(
        hints.get("containment_actions"),
        ["disable compromised credential", "restrict publisher destination egress"],
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(
            ctx,
            destination=destination,
            credential_id=credential_id,
            detected_at=compact(hints["detected_at"]),
            exposure_scope=scope,
            affected_publication_count=len(publications),
        ),
        "containment": _containment(containment_actions, owner, critical, evidence_ids),
        "revocation": [
            row(
                "PDCR",
                1,
                f"Revoke {credential_id}",
                owner,
                f"Revoke compromised credential {credential_id} for {destination} and preserve revocation evidence.",
                evidence_ids,
                timing="immediate" if critical else "same business day",
                destination=destination,
                credential_id=credential_id,
            )
        ],
        "rotation": [
            row("PDRO", index, step, owner, f"Rotate {destination} credential: {step}.", evidence_ids)
            for index, step in enumerate(rotation_steps, start=1)
        ],
        "affected_publications": [
            row(
                "PDAP",
                index,
                compact(publication["name"]),
                owner,
                "Review publication delivery, replay eligibility, and customer-visible state after credential compromise.",
                evidence_ids,
                publication_id=compact(publication.get("id")) or f"publication-{index:03d}",
                status=compact(publication.get("status")) or "review_required",
            )
            for index, publication in enumerate(publications, start=1)
        ],
        "replay_review": [
            row(
                "PDRR",
                1,
                "Replay delivery review",
                owner,
                f"Compare successful, failed, and suspicious publishes for {destination} after {compact(hints['detected_at'])}.",
                evidence_ids,
                required=True,
            )
        ],
        "recovery_approval": [
            row(
                "PDRA",
                1,
                "Recovery approval",
                owner,
                "Approve destination recovery only after containment, revocation, rotation, and replay review evidence is attached.",
                evidence_ids,
                required=True,
            )
        ],
        "evidence_references": ctx["evidence_references"],
    }


def _containment(actions: list[str], owner: str, critical: bool, evidence_ids: list[str]) -> list[dict[str, Any]]:
    items = [
        row("PDCN", index, action, owner, f"Contain publisher credential exposure: {action}.", evidence_ids, timing="immediate" if critical else "same business day")
        for index, action in enumerate(actions, start=1)
    ]
    if critical:
        items.insert(0, row("PDCN", 0, "Immediate containment", owner, "Immediately isolate the destination path and block compromised credential use.", evidence_ids, timing="immediate", severity="critical"))
        items.append(row("PDCN", len(items), "Pause affected publications", owner, "Pause affected publication delivery until replacement credentials are validated.", evidence_ids, timing="immediate", severity="critical"))
    return items


def _require(hints: dict[str, Any], keys: tuple[str, ...]) -> None:
    missing = [key for key in keys if not compact(hints.get(key))]
    if missing:
        raise ValueError(f"Missing publisher destination credential compromise fields: {', '.join(ordered(missing))}")
