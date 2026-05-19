"""Generate deterministic secrets exposure response plans for TactSpec previews."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, context, string_list, summary


SCHEMA_VERSION = "max.spec.secrets_exposure_response_plan.v1"
SECRETS_EXPOSURE_RESPONSE_PLAN_SCHEMA_VERSION = SCHEMA_VERSION
KIND = "max.spec.secrets_exposure_response_plan"


def generate_secrets_exposure_response_plan(spec_like: dict[str, Any]) -> dict[str, Any]:
    """Return deterministic response planning data for suspected secrets exposure."""
    spec = spec_like if isinstance(spec_like, dict) else {}
    ctx = context(spec)
    hints = _secrets_hints(spec, ctx)
    evidence_ids = [item["id"] for item in ctx["evidence_references"]]
    strictness = "strict" if hints["production"] or hints["customer_impacting"] or hints["high_risk"] else ctx["strictness"]

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(
            ctx,
            response_strictness=strictness,
            exposure_type=hints["exposure_type"],
            customer_impacting=hints["customer_impacting"],
            production=hints["production"],
            secret_count=len(hints["secrets"]),
        ),
        "exposure_triage": _exposure_triage(ctx, hints, strictness, evidence_ids),
        "containment_steps": _containment_steps(hints, strictness, evidence_ids),
        "rotation_sequence": _rotation_sequence(hints, strictness, evidence_ids),
        "blast_radius_review": _blast_radius_review(hints, strictness, evidence_ids),
        "verification_checks": _verification_checks(hints, strictness, evidence_ids),
        "communication_path": _communication_path(ctx, hints, strictness, evidence_ids),
        "owner_roles": _owner_roles(ctx),
        "evidence_references": ctx["evidence_references"],
    }


def _secrets_hints(spec: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    metadata = spec.get("metadata") if isinstance(spec.get("metadata"), dict) else {}
    exposure = metadata.get("secrets_exposure") if isinstance(metadata.get("secrets_exposure"), dict) else {}
    execution = spec.get("execution") if isinstance(spec.get("execution"), dict) else {}
    project = spec.get("project") if isinstance(spec.get("project"), dict) else {}

    explicit_secrets = _ordered(
        string_list(exposure.get("secrets"))
        + string_list(metadata.get("secrets"))
        + string_list(exposure.get("secret_types"))
    )
    secrets = explicit_secrets or ["application credential under review"]
    explicit_systems = _ordered(
        string_list(exposure.get("systems"))
        + string_list(metadata.get("systems"))
        + string_list(execution.get("mvp_scope"))
    )
    systems = explicit_systems or ["primary application system"]
    environments = _ordered(string_list(exposure.get("environments")) + string_list(metadata.get("environments")))
    text = " ".join(
        explicit_secrets
        + explicit_systems
        + environments
        + string_list(execution.get("risks"))
        + string_list(execution.get("mvp_scope"))
        + [
            compact(exposure.get("severity")),
            compact(exposure.get("impact")),
            compact(exposure.get("type") or exposure.get("exposure_type")),
            compact(project.get("workflow_context")),
            compact(project.get("summary")),
        ]
    ).lower()
    production = _truthy(exposure.get("production")) or any(term in text for term in ("production", "prod", "live", "customer-facing"))
    customer_impacting = _truthy(exposure.get("customer_impacting")) or any(term in text for term in ("customer", "tenant", "user data", "public"))
    high_risk = _truthy(exposure.get("high_risk")) or any(term in text for term in ("leaked", "exposed", "credential", "token", "private key", "api key", "database password"))

    return {
        "exposure_type": compact(exposure.get("type") or exposure.get("exposure_type")) or "suspected secrets exposure",
        "detected_at": compact(exposure.get("detected_at") or exposure.get("discovery_time")) or "first confirmed detection time",
        "secrets": secrets,
        "systems": systems,
        "environments": environments or (["production"] if production else ["unconfirmed environment"]),
        "production": production,
        "customer_impacting": customer_impacting,
        "high_risk": high_risk,
        "ticket": compact(exposure.get("ticket")) or "security incident ticket",
    }


def _exposure_triage(
    ctx: dict[str, Any], hints: dict[str, Any], strictness: str, evidence_ids: list[str]
) -> dict[str, Any]:
    return {
        "id": "ET1",
        "name": "Secrets exposure triage",
        "owner": "incident_commander",
        "strictness": strictness,
        "exposure_type": hints["exposure_type"],
        "detected_at": hints["detected_at"],
        "classification": "production customer-impacting secret exposure"
        if strictness == "strict"
        else "suspected secret exposure under review",
        "description": f"Classify affected secrets, systems, and exposure path for {ctx['workflow_context']}.",
        "evidence_reference_ids": evidence_ids,
    }


def _containment_steps(
    hints: dict[str, Any], strictness: str, evidence_ids: list[str]
) -> list[dict[str, Any]]:
    timing = "immediate" if strictness == "strict" else "same business day"
    steps = [
        ("CS1", "Revoke exposed material", "Disable exposed tokens, keys, sessions, and deploy credentials."),
        ("CS2", "Freeze unsafe propagation", "Stop jobs, builds, logs, or releases that could continue distributing the secret."),
        ("CS3", "Preserve evidence", f"Capture source, timestamps, and access traces in {hints['ticket']}."),
    ]
    if strictness == "strict":
        steps.append(("CS4", "Production access guard", "Temporarily restrict privileged production access until replacement credentials are verified."))
    return [
        {
            "id": item_id,
            "name": name,
            "owner": "security_owner" if item_id != "CS4" else "platform_owner",
            "timing": timing,
            "strictness": strictness,
            "action": action,
            "evidence_reference_ids": evidence_ids,
        }
        for item_id, name, action in steps
    ]


def _rotation_sequence(
    hints: dict[str, Any], strictness: str, evidence_ids: list[str]
) -> list[dict[str, Any]]:
    timing = "rotate before restoring normal production access" if strictness == "strict" else "rotate before incident closure"
    return [
        {
            "id": f"RS{index}",
            "secret": secret,
            "owner": "platform_owner",
            "timing": timing,
            "sequence": index,
            "action": "create replacement, deploy safely, revoke old value, and confirm no fallback uses the exposed secret",
            "evidence_reference_ids": evidence_ids,
        }
        for index, secret in enumerate(hints["secrets"], start=1)
    ]


def _blast_radius_review(
    hints: dict[str, Any], strictness: str, evidence_ids: list[str]
) -> list[dict[str, Any]]:
    return [
        {
            "id": f"BR{index}",
            "system": system,
            "owner": "security_owner",
            "strictness": strictness,
            "review": "inspect access logs, privilege scope, downstream integrations, and customer data touchpoints",
            "customer_impact_review_required": hints["customer_impacting"] or strictness == "strict",
            "evidence_reference_ids": evidence_ids,
        }
        for index, system in enumerate(hints["systems"], start=1)
    ]


def _verification_checks(
    hints: dict[str, Any], strictness: str, evidence_ids: list[str]
) -> list[dict[str, Any]]:
    checks = [
        ("VC1", "Old secret rejected", "prove the exposed secret no longer authenticates"),
        ("VC2", "Replacement deployed", "prove all services use the replacement secret"),
        ("VC3", "Log and repository cleanup", "prove indexed logs, build artifacts, and repositories no longer expose the value"),
    ]
    if strictness == "strict":
        checks.append(("VC4", "Customer-impact review", "prove customer-impacting actions and suspicious access were reviewed"))
    return [
        {
            "id": item_id,
            "name": name,
            "owner": "security_owner",
            "required": True,
            "strictness": strictness,
            "expected_result": expected,
            "evidence_reference_ids": evidence_ids,
        }
        for item_id, name, expected in checks
    ]


def _communication_path(
    ctx: dict[str, Any], hints: dict[str, Any], strictness: str, evidence_ids: list[str]
) -> list[dict[str, Any]]:
    items = [
        ("CP1", "security_owner", "Open incident channel and assign containment, rotation, and verification owners."),
        ("CP2", ctx["buyer"], "Provide response status and launch or operational risk decision."),
    ]
    if strictness == "strict":
        items.append(("CP3", "communications_owner", "Prepare customer or stakeholder notification if blast-radius review confirms impact."))
    return [
        {
            "id": item_id,
            "owner": owner,
            "timing": "immediate" if strictness == "strict" else "same business day",
            "message": message,
            "channels": ["incident channel", "security ticket", "executive update"] if strictness == "strict" else ["security ticket", "team channel"],
            "evidence_reference_ids": evidence_ids,
        }
        for item_id, owner, message in items
    ]


def _owner_roles(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"role": "incident_commander", "suggested_owner": "incident_commander", "responsibility": "Own severity, timeline, and response coordination."},
        {"role": "security_owner", "suggested_owner": "security_owner", "responsibility": "Own exposure triage, containment, and blast-radius review."},
        {"role": "platform_owner", "suggested_owner": "platform_owner", "responsibility": "Own rotation, deployment, and production verification."},
        {"role": "communications_owner", "suggested_owner": "communications_owner", "responsibility": "Own customer or stakeholder communication readiness."},
        {"role": "business_owner", "suggested_owner": ctx["buyer"], "responsibility": "Approve residual risk and operational restart."},
    ]


def _ordered(values: list[str]) -> list[str]:
    return sorted(dict.fromkeys(values), key=str.casefold)


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return compact(value).lower() in {"1", "true", "yes", "y", "required", "high"}
