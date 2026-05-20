"""Generate deterministic privacy review readiness plans for TactSpec previews."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, context, string_list, summary


SCHEMA_VERSION = "max.spec.privacy_review_readiness_plan.v1"
KIND = "max.spec.privacy_review_readiness_plan"
SENSITIVE_TERMS = ("health", "biometric", "financial", "payment", "location", "children", "minor", "ssn", "government")


def generate_privacy_review_readiness_plan(spec_like: Any) -> dict[str, Any]:
    """Return privacy questions, artifacts, owners, gaps, and blockers."""
    spec = spec_like if isinstance(spec_like, dict) else {}
    ctx = context(spec)
    hints = _hints(spec, "privacy_review_readiness")
    categories = _values(hints.get("data_categories") or spec.get("data_categories"), ["customer contact data"])
    populations = _values(hints.get("user_populations") or spec.get("user_populations"), ["primary users"])
    processors = _records(hints.get("processors") or spec.get("processors"), "processor")
    retention = compact(hints.get("retention") or spec.get("retention")) or "retention period pending review"
    consent = compact(hints.get("consent") or spec.get("consent")) or "consent basis pending review"
    risks = _values(hints.get("risks") or spec.get("privacy_risks"), [])
    evidence_ids = _evidence_ids(ctx)
    sensitive = any(_is_sensitive(category) for category in categories)
    gaps = _gaps(processors, retention, consent, risks)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(ctx, data_category_count=len(categories), processor_count=len(processors), sensitive_data=sensitive, gap_count=len(gaps)),
        "privacy_questions": _questions(categories, populations, processors, retention, consent, sensitive, evidence_ids),
        "required_artifacts": _artifacts(processors, retention, consent, evidence_ids),
        "readiness_gaps": gaps,
        "owners": _owners(hints.get("owners") or spec.get("owners")),
        "launch_blockers": _blockers(gaps, sensitive, evidence_ids),
        "evidence_references": ctx["evidence_references"],
    }


def _questions(
    categories: list[str],
    populations: list[str],
    processors: list[dict[str, str]],
    retention: str,
    consent: str,
    sensitive: bool,
    evidence_ids: list[str],
) -> list[dict[str, Any]]:
    return [
        {
            "id": "PQ1",
            "question": f"Is collection of {', '.join(categories)} necessary for {', '.join(populations)}?",
            "priority": "critical" if sensitive else "medium",
            "owner": "privacy_owner",
            "evidence_reference_ids": evidence_ids,
        },
        {
            "id": "PQ2",
            "question": f"Are processors documented and approved: {', '.join(item['name'] for item in processors) or 'none listed'}?",
            "priority": "high" if processors else "medium",
            "owner": "privacy_owner",
            "evidence_reference_ids": evidence_ids,
        },
        {
            "id": "PQ3",
            "question": f"Are retention and consent positions ready: retention={retention}; consent={consent}?",
            "priority": "high" if "pending" in retention or "pending" in consent else "medium",
            "owner": "legal_owner",
            "evidence_reference_ids": evidence_ids,
        },
    ]


def _artifacts(processors: list[dict[str, str]], retention: str, consent: str, evidence_ids: list[str]) -> list[dict[str, Any]]:
    artifacts = [
        {"id": "ART1", "type": "retention_evidence", "description": retention, "owner": "legal_owner", "evidence_reference_ids": evidence_ids},
        {"id": "ART2", "type": "consent_evidence", "description": consent, "owner": "privacy_owner", "evidence_reference_ids": evidence_ids},
    ]
    artifacts.extend(
        {
            "id": f"ART{index + 2}",
            "type": "processor_evidence",
            "processor": processor["name"],
            "description": processor["evidence"] or "processor evidence pending",
            "owner": processor["owner"] or "vendor_owner",
            "evidence_reference_ids": evidence_ids,
        }
        for index, processor in enumerate(processors, start=1)
    )
    return artifacts


def _gaps(processors: list[dict[str, str]], retention: str, consent: str, risks: list[str]) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    if "pending" in retention:
        gaps.append({"id": "GAP1", "type": "retention", "severity": "high", "description": "Retention period is pending review."})
    if "pending" in consent:
        gaps.append({"id": f"GAP{len(gaps) + 1}", "type": "consent", "severity": "high", "description": "Consent basis is pending review."})
    for processor in processors:
        if not processor["evidence"]:
            gaps.append({"id": f"GAP{len(gaps) + 1}", "type": "processor_evidence", "severity": "high", "description": f"Processor evidence missing for {processor['name']}."})
    gaps.extend({"id": f"GAP{len(gaps) + index}", "type": "risk", "severity": "medium", "description": risk} for index, risk in enumerate(risks, start=1))
    return gaps


def _blockers(gaps: list[dict[str, Any]], sensitive: bool, evidence_ids: list[str]) -> list[dict[str, Any]]:
    blockers = [
        {
            "id": f"LB{index}",
            "gap_id": gap["id"],
            "severity": "critical" if sensitive and gap["severity"] == "high" else gap["severity"],
            "owner": "privacy_owner",
            "action": f"Close privacy readiness gap: {gap['description']}",
            "evidence_reference_ids": evidence_ids,
        }
        for index, gap in enumerate(gaps, start=1)
    ]
    return sorted(blockers, key=lambda item: (item["severity"] != "critical", item["gap_id"]))


def _owners(value: Any) -> list[dict[str, str]]:
    owners = value if isinstance(value, dict) else {}
    return [
        {"role": "privacy_owner", "owner": compact(owners.get("privacy_owner")) or "privacy_owner"},
        {"role": "legal_owner", "owner": compact(owners.get("legal_owner")) or "legal_owner"},
        {"role": "vendor_owner", "owner": compact(owners.get("vendor_owner")) or "vendor_owner"},
    ]


def _records(value: Any, default_type: str) -> list[dict[str, str]]:
    raw = value if isinstance(value, list) else []
    records: list[dict[str, str]] = []
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            name = compact(item) or f"{default_type} {index}"
            records.append({"name": name, "owner": "", "evidence": ""})
            continue
        records.append(
            {
                "name": compact(item.get("name") or item.get("processor")) or f"{default_type} {index}",
                "owner": compact(item.get("owner")),
                "evidence": compact(item.get("evidence") or item.get("dpa") or item.get("contract")),
            }
        )
    return sorted(records, key=lambda item: item["name"].casefold())


def _values(value: Any, fallback: list[str]) -> list[str]:
    values = string_list(value)
    return sorted(dict.fromkeys(values), key=str.casefold) if values else fallback


def _is_sensitive(value: str) -> bool:
    lowered = value.casefold()
    return any(term in lowered for term in SENSITIVE_TERMS)


def _hints(spec: dict[str, Any], key: str) -> dict[str, Any]:
    metadata = spec.get("metadata") if isinstance(spec.get("metadata"), dict) else {}
    hints = metadata.get(key)
    return hints if isinstance(hints, dict) else {}


def _evidence_ids(ctx: dict[str, Any]) -> list[str]:
    return [item["id"] for item in ctx["evidence_references"]]
