"""Generate deterministic operational acceptance plans for TactSpec previews."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, context, string_list, summary


SCHEMA_VERSION = "max.spec.operational_acceptance_plan.v1"
KIND = "max.spec.operational_acceptance_plan"

SEVERITY_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}


def generate_operational_acceptance_plan(spec_like: Any) -> dict[str, Any]:
    """Return a stable operational acceptance plan with conservative defaults."""
    spec = spec_like if isinstance(spec_like, dict) else {}
    ctx = context(spec)
    hints = _hints(spec, "operational_acceptance")
    systems = _values(hints.get("systems") or spec.get("systems"), ["Primary service"])
    runbooks = _values(hints.get("runbooks") or spec.get("runbooks"), ["operational runbook"])
    owners = _owner_map(hints.get("owners") or spec.get("owners"))
    risks = _risk_items(hints.get("risks") or spec.get("risks") or ctx["risks"])
    gaps = _risk_items(hints.get("gaps") or spec.get("gaps"))
    evidence_ids = _evidence_ids(ctx)

    gates = [
        _item(
            f"G{index}",
            "system_acceptance",
            name=system,
            owner=_owner_for(system, owners, "operations_owner"),
            description=f"Confirm {system} has monitoring, alerting, rollback, and support ownership ready for acceptance.",
            evidence_ids=evidence_ids,
            references=["metadata.operational_acceptance.systems"],
        )
        for index, system in enumerate(systems, start=1)
    ]
    gates.extend(
        _item(
            f"R{index}",
            "runbook_acceptance",
            name=runbook,
            owner=_owner_for(runbook, owners, "runbook_owner"),
            description=f"Validate {runbook} covers triage, escalation, mitigation, and customer communication.",
            evidence_ids=evidence_ids,
            references=["metadata.operational_acceptance.runbooks"],
        )
        for index, runbook in enumerate(runbooks, start=1)
    )

    evidence_requirements = [
        _item(
            "EVR1",
            "evidence_packet",
            name="acceptance evidence packet",
            owner="release_manager",
            description="Attach monitoring screenshots, runbook review notes, owner signoffs, and validation results.",
            evidence_ids=evidence_ids,
            severity="high" if not evidence_ids else "medium",
            references=["evidence.references"],
        )
    ]
    blockers = _blockers(risks + gaps, owners, evidence_ids)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "title": f"{ctx['title']} Operational Acceptance Plan",
        "summary": summary(
            ctx,
            system_count=len(systems),
            runbook_count=len(runbooks),
            blocker_count=len(blockers),
            evidence_reference_count=len(evidence_ids),
        ),
        "gates": gates,
        "evidence_requirements": evidence_requirements,
        "blockers": blockers,
        "next_actions": _next_actions(blockers, evidence_ids),
        "evidence_references": ctx["evidence_references"],
    }


def _blockers(items: list[dict[str, str]], owners: dict[str, str], evidence_ids: list[str]) -> list[dict[str, Any]]:
    blockers = [
        _item(
            f"BLK{index}",
            "acceptance_blocker",
            name=item["name"],
            owner=_owner_for(item["name"], owners, "operations_owner"),
            description=item["description"],
            severity=item["severity"],
            evidence_ids=evidence_ids,
            references=["metadata.operational_acceptance.risks"],
        )
        for index, item in enumerate(items, start=1)
    ]
    return sorted(
        blockers,
        key=lambda item: (-SEVERITY_RANK.get(item["severity"], 0), item["name"].casefold(), item["id"]),
    )


def _next_actions(blockers: list[dict[str, Any]], evidence_ids: list[str]) -> list[dict[str, Any]]:
    actions = [
        _item(
            "NA1",
            "owner_signoff",
            name="collect operational owner signoff",
            owner="release_manager",
            description="Collect named owner approval for every gate before launch.",
            evidence_ids=evidence_ids,
        )
    ]
    if not evidence_ids:
        actions.append(
            _item(
                "NA2",
                "evidence_setup",
                name="create evidence trace",
                owner="release_manager",
                description="Add evidence references for operational validation, runbook review, and gate decisions.",
                severity="high",
            )
        )
    if blockers:
        actions.append(
            _item(
                "NA3",
                "blocker_burn_down",
                name="burn down unresolved blockers",
                owner="operations_owner",
                description="Resolve critical and high acceptance blockers before approving operational handoff.",
                severity="high",
                evidence_ids=evidence_ids,
            )
        )
    return actions


def _risk_items(value: Any) -> list[dict[str, str]]:
    raw_items = value if isinstance(value, list) else string_list(value)
    result: list[dict[str, str]] = []
    for index, raw in enumerate(raw_items, start=1):
        if isinstance(raw, dict):
            name = compact(raw.get("name") or raw.get("id") or raw.get("risk") or raw.get("description")) or f"risk {index}"
            description = compact(raw.get("description") or raw.get("risk") or raw.get("gap")) or name
            severity = _severity(raw.get("severity") or raw.get("priority"))
        else:
            name = compact(raw) or f"risk {index}"
            description = name
            severity = _infer_severity(name)
        result.append({"name": name, "description": description, "severity": severity})
    return result


def _owner_map(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {compact(key).casefold(): compact(owner) for key, owner in value.items() if compact(key) and compact(owner)}


def _owner_for(name: str, owners: dict[str, str], fallback: str) -> str:
    return owners.get(name.casefold()) or owners.get("default") or fallback


def _hints(spec: dict[str, Any], key: str) -> dict[str, Any]:
    metadata = spec.get("metadata") if isinstance(spec.get("metadata"), dict) else {}
    hints = metadata.get(key)
    return hints if isinstance(hints, dict) else {}


def _values(value: Any, fallback: list[str]) -> list[str]:
    values = string_list(value)
    return sorted(dict.fromkeys(values), key=str.casefold) if values else fallback


def _severity(value: Any) -> str:
    text = compact(value).casefold()
    return text if text in SEVERITY_RANK else "medium"


def _infer_severity(text: str) -> str:
    lowered = text.casefold()
    if any(term in lowered for term in ("outage", "data loss", "security", "privacy", "rollback")):
        return "high"
    return "medium"


def _item(
    item_id: str,
    item_type: str,
    *,
    name: str,
    owner: str,
    description: str,
    severity: str = "medium",
    evidence_ids: list[str] | None = None,
    references: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": item_id,
        "type": item_type,
        "name": name,
        "owner": owner,
        "severity": severity,
        "description": description,
        "evidence_reference_ids": evidence_ids or [],
        "references": references or [],
    }


def _evidence_ids(ctx: dict[str, Any]) -> list[str]:
    return [item["id"] for item in ctx["evidence_references"]]
