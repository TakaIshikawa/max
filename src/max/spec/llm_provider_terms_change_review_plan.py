"""Generate deterministic LLM provider terms change review plans."""

from __future__ import annotations

from datetime import date
from typing import Any

from max.spec._planning_common import compact
from max.spec._review_plan_common import base, row, source_summary

SCHEMA_VERSION = "max.spec.llm_provider_terms_change_review_plan.v1"
KIND = "max.spec.llm_provider_terms_change_review_plan"

NEAR_TERM_DAYS = 14


def generate_llm_provider_terms_change_review_plan(
    spec_like: Any, *, as_of: str | None = None
) -> dict[str, Any]:
    spec, ctx, metadata_hints, evidence_ids = base(spec_like, "llm_provider_terms_change")
    hints = metadata_hints or (spec if isinstance(spec, dict) else {})
    provider = compact(hints.get("provider"))
    effective_date = compact(hints.get("effective_date"))
    changed_terms = _ordered_list(hints.get("changed_terms") or hints.get("terms_changes"))
    affected_products = _ordered_list(hints.get("affected_products") or hints.get("products"))
    data_use_impacts = _ordered_list(hints.get("data_use_impacts") or hints.get("data_use"))
    owner = compact(hints.get("owner"))
    legal_reviewer = compact(hints.get("legal_reviewer"))
    mitigation_actions = _mitigation_actions(hints.get("mitigation_actions"))
    validation_issues = _validation_issues(
        provider=provider,
        effective_date=effective_date,
        changed_terms=changed_terms,
        affected_products=affected_products,
        owner=owner,
        legal_reviewer=legal_reviewer,
    )
    days_until_effective = _days_until(effective_date, as_of)
    near_term = days_until_effective is not None and days_until_effective <= NEAR_TERM_DAYS
    if effective_date and days_until_effective is None:
        validation_issues.append("invalid_effective_date")

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "title": "LLM Provider Terms Change Review Plan",
        "summary": source_summary(
            ctx,
            provider=provider or "unknown_provider",
            effective_date=effective_date,
            changed_term_count=len(changed_terms),
            affected_product_count=len(affected_products),
            data_use_impact_count=len(data_use_impacts),
            validation_issue_count=len(validation_issues),
            days_until_effective=days_until_effective,
            review_urgency="near_term" if near_term else "standard",
            risk_level="high" if validation_issues or near_term else ctx["risk_level"],
        ),
        "provider": provider,
        "effective_date": effective_date,
        "owner": owner,
        "legal_reviewer": legal_reviewer,
        "changed_terms": changed_terms,
        "affected_products": affected_products,
        "data_use_impacts": data_use_impacts,
        "impact_review": [
            row(
                "LPI",
                index,
                product,
                owner or "product_owner",
                f"Map {provider or 'LLM provider'} terms changes to {product} workflows, data flows, prompts, logs, fine-tuning, and evaluation usage.",
                evidence_ids,
                severity="high" if near_term else "medium",
            )
            for index, product in enumerate(affected_products or ["affected LLM product"], start=1)
        ],
        "legal_assessment": [
            row(
                "LPL",
                index,
                term,
                legal_reviewer or "legal_reviewer",
                f"Assess contractual, privacy, security, data use, retention, training, output ownership, and customer notice impact for {term}.",
                evidence_ids,
                severity="high",
            )
            for index, term in enumerate(changed_terms or ["provider terms change"], start=1)
        ],
        "mitigation": [
            row(
                "LPM",
                index,
                action,
                owner or "mitigation_owner",
                f"Implement mitigation before {effective_date or 'provider terms effective date'} and attach completion evidence.",
                evidence_ids,
                severity="high" if near_term else "medium",
            )
            for index, action in enumerate(mitigation_actions, start=1)
        ],
        "communication": [
            row(
                "LPC",
                1,
                "internal stakeholder notice",
                owner or "program_owner",
                "Notify product, ML platform, security, privacy, support, and account teams of operational changes and required mitigations.",
                evidence_ids,
                severity="medium",
            ),
            row(
                "LPC",
                2,
                "customer impact communication",
                legal_reviewer or "legal_reviewer",
                "Decide whether customer notices, trust center updates, DPA updates, or contractual amendments are required.",
                evidence_ids,
                severity="high" if data_use_impacts else "medium",
            ),
        ],
        "approval_gates": [
            row(
                "LPA",
                1,
                "impact review signoff",
                owner or "program_owner",
                "Confirm affected LLM products and data use paths have been reviewed.",
                evidence_ids,
                severity="high" if near_term else "medium",
            ),
            row(
                "LPA",
                2,
                "legal approval",
                legal_reviewer or "legal_reviewer",
                "Approve continued provider use under the changed terms or require fallback execution.",
                evidence_ids,
                severity="high",
            ),
            row(
                "LPA",
                3,
                "go no-go decision",
                owner or "program_owner",
                "Record the provider terms go/no-go decision before the effective date.",
                evidence_ids,
                severity="high",
            ),
        ],
        "escalation_tasks": _escalation_tasks(
            near_term=near_term,
            provider=provider,
            effective_date=effective_date,
            owner=owner,
            legal_reviewer=legal_reviewer,
            evidence_ids=evidence_ids,
        ),
        "validation_issues": validation_issues,
        "evidence_references": ctx["evidence_references"],
    }


def _ordered_list(value: Any) -> list[str]:
    values: list[str] = []
    raw = value if isinstance(value, list) else ([value] if value else [])
    for item in raw:
        text = (
            compact(
                item.get("name")
                or item.get("title")
                or item.get("term")
                or item.get("product")
                or item.get("impact")
            )
            if isinstance(item, dict)
            else compact(item)
        )
        if text:
            values.append(text)
    return sorted(dict.fromkeys(values), key=str.casefold)


def _mitigation_actions(value: Any) -> list[str]:
    actions = _ordered_list(value)
    defaults = [
        "Confirm no-training and data use restrictions",
        "Update LLM provider configuration and routing policy",
        "Refresh customer-facing terms and trust center documentation",
    ]
    return sorted(dict.fromkeys([*actions, *defaults]), key=str.casefold)


def _validation_issues(
    *,
    provider: str,
    effective_date: str,
    changed_terms: list[str],
    affected_products: list[str],
    owner: str,
    legal_reviewer: str,
) -> list[str]:
    issues = []
    if not provider:
        issues.append("missing_provider")
    if not effective_date:
        issues.append("missing_effective_date")
    if not changed_terms:
        issues.append("missing_changed_terms")
    if not affected_products:
        issues.append("missing_affected_products")
    if not owner:
        issues.append("missing_owner")
    if not legal_reviewer:
        issues.append("missing_legal_reviewer")
    return issues


def _days_until(effective_date: str, as_of: str | None) -> int | None:
    try:
        effective = date.fromisoformat(effective_date[:10])
        current = date.fromisoformat((as_of or date.today().isoformat())[:10])
    except ValueError:
        return None
    return (effective - current).days


def _escalation_tasks(
    *,
    near_term: bool,
    provider: str,
    effective_date: str,
    owner: str,
    legal_reviewer: str,
    evidence_ids: list[str],
) -> list[dict[str, Any]]:
    if not near_term:
        return []
    return [
        row(
            "LPE",
            1,
            "near-term terms change escalation",
            owner or legal_reviewer or "program_owner",
            f"Escalate {provider or 'LLM provider'} terms change effective {effective_date or 'soon'} to legal, privacy, security, and executive approvers.",
            evidence_ids,
            severity="critical",
            status="required",
        )
    ]
