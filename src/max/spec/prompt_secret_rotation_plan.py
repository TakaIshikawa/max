"""Generate deterministic prompt secret rotation plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._planning_common import compact
from max.spec._review_plan_common import base, row, source_summary, unique_records


SCHEMA_VERSION = "max.spec.prompt_secret_rotation_plan.v1"
KIND = "max.spec.prompt_secret_rotation_plan"


def generate_prompt_secret_rotation_plan(spec_like: Any) -> dict[str, Any]:
    """Return a stable rotation plan for secrets found in prompts or tool configs."""
    _spec, ctx, hints, evidence_ids = base(spec_like, "prompt_secret_rotation")
    affected_assets = unique_records(
        named(
            hints.get("affected_assets")
            or hints.get("affected_prompts")
            or hints.get("prompts")
            or hints.get("tools"),
            ("prompt", "tool", "config"),
        ),
        [{"name": "prompt and tool secret inventory", "asset_type": "prompt/tool config"}],
    )
    blockers = _blockers(affected_assets, hints, evidence_ids)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, affected_asset_count=len(affected_assets), blocker_count=len(blockers)),
        "affected_assets": [
            item(
                "PSA",
                index,
                record,
                "security_owner",
                evidence_ids,
                "Inventory prompt or tool secret",
                name_keys=("name", "prompt", "tool", "config"),
                extra_keys=("asset_type", "secret_type", "exposure", "validation_evidence"),
            )
            for index, record in enumerate(affected_assets, start=1)
        ],
        "rotation_steps": section(
            hints,
            ("rotation_steps", "replacement_steps", "rotation_actions"),
            "PSR",
            "security_owner",
            "Rotate prompt secret",
            evidence_ids,
            ["inventory affected prompts and tools", "replace embedded secret references", "revoke exposed credentials"],
        ),
        "validation_checklist": section(
            hints,
            ("validation_checklist", "validation", "post_rotation_validation"),
            "PSV",
            "quality_owner",
            "Validate prompt secret rotation",
            evidence_ids,
            ["prompt regression pass", "tool authentication smoke test", "no exposed secret scanner findings"],
        ),
        "rollback_plan": section(
            hints,
            ("rollback_plan", "rollback"),
            "PSB",
            "on_call_owner",
            "Prepare prompt secret rollback",
            evidence_ids,
            ["approved temporary credential restore path with expiry"],
        ),
        "owner_assignments": section(
            hints,
            ("owner_assignments", "owners"),
            "PSO",
            "program_owner",
            "Assign prompt secret owner",
            evidence_ids,
            ["security, prompt library, and tool integration owners assigned"],
        ),
        "incident_evidence": section(
            hints,
            ("incident_evidence", "evidence_requirements", "evidence"),
            "PSE",
            "security_owner",
            "Collect prompt secret incident evidence",
            evidence_ids,
            ["exposure timestamp, affected asset, rotation receipt, validation result, and incident link"],
        ),
        "blockers": blockers,
        "evidence_references": ctx["evidence_references"],
    }


def _blockers(assets: list[dict[str, Any]], hints: dict[str, Any], evidence_ids: list[str]) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    for asset in assets:
        exposed = compact(asset.get("exposure") or asset.get("status")).lower() in {"exposed", "leaked", "public", "missing"}
        if exposed and not compact(asset.get("owner")):
            blockers.append(row("PSK", len(blockers) + 1, f"{asset['name']} missing owner", "security_owner", "Exposed prompt secret cannot rotate without an accountable owner.", evidence_ids, severity="critical"))
        if exposed and not compact(asset.get("validation_evidence")):
            blockers.append(row("PSK", len(blockers) + 1, f"{asset['name']} missing validation evidence", "quality_owner", "Exposed prompt secret needs post-rotation validation evidence before closure.", evidence_ids, severity="high"))
    if compact(hints.get("owner_required")).lower() in {"true", "yes", "missing"} and not blockers:
        blockers.append(row("PSK", 1, "missing rotation owner", "program_owner", "Prompt secret rotation requires an accountable owner.", evidence_ids, severity="high"))
    return blockers
