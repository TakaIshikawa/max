"""Generate deterministic data processing agreement renewal plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, context, string_list, summary


SCHEMA_VERSION = "max.spec.data_processing_agreement_renewal_plan.v1"
KIND = "max.spec.data_processing_agreement_renewal_plan"


def generate_data_processing_agreement_renewal_plan(spec_like: Any) -> dict[str, Any]:
    spec = spec_like if isinstance(spec_like, dict) else {}
    ctx = context(spec)
    hints = _hints(spec)
    agreements = _agreements(hints.get("agreements"))
    refs = [item["id"] for item in ctx["evidence_references"]]
    blockers = [
        _row("DPB", i, item["name"], item["owner"] or "legal_owner", f"Resolve blocker for {item['name']}: {item['blocker']}.", refs, status="blocked")
        for i, item in enumerate((a for a in agreements if a["blocker"]), 1)
    ]

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(ctx, agreement_count=len(agreements), blocker_count=len(blockers)),
        "renewal_waves": [_wave(i, agreement, refs) for i, agreement in enumerate(agreements, 1)],
        "jurisdiction_groups": _jurisdictions(agreements, refs),
        "escalations": blockers,
        "verification_steps": [_row("DPV", 1, "Agreement verification", "legal_owner", "Verify signed DPA, subprocessors, transfer terms, and effective dates.", refs)],
        "customer_communication_checks": [_row("DPC", 1, "Customer communication check", "customer_owner", "Confirm customer impact and renewal notice obligations.", refs)],
        "approval_gates": [_row("DPA", 1, "Legal approval", "legal_owner", "Approve renewal language and execution package.", refs), _row("DPA", 2, "Privacy approval", "privacy_owner", "Approve jurisdictions, subprocessors, and customer impact.", refs)],
        "evidence_references": ctx["evidence_references"],
    }


def _hints(spec: dict[str, Any]) -> dict[str, Any]:
    metadata = spec.get("metadata") if isinstance(spec.get("metadata"), dict) else {}
    value = metadata.get("data_processing_agreement_renewal")
    return value if isinstance(value, dict) else {}


def _agreements(value: Any) -> list[dict[str, str]]:
    raw = value if isinstance(value, list) else []
    if not raw:
        raise ValueError("data_processing_agreement_renewal requires agreements")
    agreements = []
    for index, item in enumerate(raw, 1):
        if not isinstance(item, dict):
            item = {"name": item}
        name = compact(item.get("name") or item.get("agreement") or item.get("customer") or item.get("vendor")) or f"agreement {index}"
        expiry = compact(item.get("expiry_date") or item.get("expiry")) or "missing"
        owner = compact(item.get("owner"))
        status = compact(item.get("status")).casefold()
        blocker = "missing owner" if not owner else ("overdue agreement" if status == "overdue" or expiry.casefold().startswith("overdue") else "")
        agreements.append({"name": name, "owner": owner, "expiry_date": expiry, "jurisdiction": compact(item.get("jurisdiction")) or "unspecified", "subprocessors": "; ".join(string_list(item.get("subprocessors"))), "customer_impact": compact(item.get("customer_impact")) or "impact review required", "escalation_window": compact(item.get("escalation_window")) or "standard", "blocker": blocker})
    return sorted(agreements, key=lambda item: (0 if item["blocker"] == "overdue agreement" else 1 if item["blocker"] else 2, item["expiry_date"], item["name"].casefold()))


def _wave(index: int, agreement: dict[str, str], refs: list[str]) -> dict[str, Any]:
    return _row("DPR", index, agreement["name"], agreement["owner"] or "legal_owner", f"Renew DPA before {agreement['expiry_date']} for {agreement['jurisdiction']}.", refs, expiry_date=agreement["expiry_date"], jurisdiction=agreement["jurisdiction"], subprocessors=agreement["subprocessors"], customer_impact=agreement["customer_impact"], escalation_window=agreement["escalation_window"], status="blocked" if agreement["blocker"] else "planned")


def _jurisdictions(agreements: list[dict[str, str]], refs: list[str]) -> list[dict[str, Any]]:
    names = sorted({item["jurisdiction"] for item in agreements}, key=str.casefold)
    return [_row("DPJ", i, name, "privacy_owner", f"Review renewal requirements for {name}.", refs, agreement_count=sum(1 for item in agreements if item["jurisdiction"] == name)) for i, name in enumerate(names, 1)]


def _row(prefix: str, index: int, name: str, owner: str, description: str, refs: list[str], **extra: Any) -> dict[str, Any]:
    data = {"id": f"{prefix}{index}", "name": name, "owner": owner, "description": description, "evidence_reference_ids": refs}
    data.update({key: value for key, value in extra.items() if value not in ("", None)})
    return data
