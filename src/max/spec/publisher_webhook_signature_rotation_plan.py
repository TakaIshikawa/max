"""Generate publisher webhook signature rotation plans."""

from __future__ import annotations

from typing import Any, Iterable

SCHEMA_VERSION = "max.spec.publisher_webhook_signature_rotation_plan.v1"
KIND = "max.spec.publisher_webhook_signature_rotation_plan"


def generate_publisher_webhook_signature_rotation_plan(
    destinations: Iterable[dict[str, Any]],
    *,
    overlap_hours: int = 24,
) -> dict[str, Any]:
    hours = max(0, int(overlap_hours))
    rows = [_destination_row(raw, index) for index, raw in enumerate(destinations, start=1)]
    rows.sort(key=lambda row: (row["blocked"], row["wave"], row["destination"].casefold()))
    blockers = [row for row in rows if row["blocked"]]
    rollout = [row for row in rows if not row["blocked"]]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "destination_count": len(rows),
            "blocked_count": len(blockers),
            "rollout_wave_count": len({row["wave"] for row in rollout}),
            "overlap_hours": hours,
            "status": "blocked" if blockers else "ready",
        },
        "destinations": rows,
        "blockers": blockers,
        "preparation": [
            "inventory destination owners and endpoints",
            "issue next signing secret and publish verification schedule",
            f"configure dual-signing for {hours} hours before old-secret revocation",
        ],
        "rotation": [
            {"wave": wave, "destinations": [row["destination"] for row in rollout if row["wave"] == wave], "dual_signing_overlap_hours": hours}
            for wave in sorted({row["wave"] for row in rollout})
        ],
        "verification": [
            "verify consumers accept signatures from old and new secrets during overlap",
            "confirm new-secret-only delivery after overlap",
            "capture delivery success evidence for every destination",
        ],
        "rollback": [
            "pause revocation if verification fails",
            f"restore old-secret signing during the {hours}-hour overlap window",
            "notify destination owner and retry signed canary delivery",
        ],
        "customer_communication": [
            "send rotation notice before dual-signing begins",
            "send reminder halfway through overlap",
            "send completion notice after old-secret revocation",
        ],
        "evidence": [
            "destination validation checklist",
            "dual-signing delivery logs",
            "old-secret revocation record",
        ],
    }


def _destination_row(raw: dict[str, Any], index: int) -> dict[str, Any]:
    destination = _text(raw.get("destination") or raw.get("name") or raw.get("id")) or f"destination-{index}"
    endpoint = _text(raw.get("endpoint") or raw.get("url"))
    owner = _text(raw.get("owner"))
    blockers = []
    if not owner:
        blockers.append("missing-owner")
    if not endpoint:
        blockers.append("missing-endpoint")
    return {
        "destination": destination,
        "endpoint": endpoint,
        "owner": owner,
        "wave": _int(raw.get("wave"), default=index),
        "blocked": bool(blockers),
        "blockers": blockers,
    }


def _int(value: Any, *, default: int) -> int:
    try:
        return max(1, int(float(value)))
    except (TypeError, ValueError):
        return default


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
