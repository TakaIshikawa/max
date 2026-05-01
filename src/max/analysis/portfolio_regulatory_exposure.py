"""Portfolio regulatory exposure analysis for persisted design briefs."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store


SCHEMA_VERSION = "max.portfolio_regulatory_exposure.v1"
KIND = "max.portfolio_regulatory_exposure"
DEFAULT_LIMIT = 10_000
DEFAULT_REPRESENTATIVE_LIMIT = 5


def build_portfolio_regulatory_exposure_report(
    store: Store,
    *,
    domain: str | Iterable[str] | None = None,
    limit: int = DEFAULT_LIMIT,
    representative_limit: int = DEFAULT_REPRESENTATIVE_LIMIT,
) -> dict[str, Any]:
    """Build a JSON-ready regulatory exposure report from persisted design briefs."""

    if limit < 1:
        raise ValueError("limit must be at least 1")

    domains = _filter_values(domain)
    if domains and len(domains) == 1:
        briefs = store.get_design_briefs(limit=limit, domain=next(iter(domains)))
    else:
        briefs = store.get_design_briefs(limit=limit)

    enriched = [_enriched_brief(store, brief) for brief in briefs]
    return build_portfolio_regulatory_exposure_from_records(
        design_briefs=enriched,
        domain=domains,
        representative_limit=representative_limit,
    )


def build_portfolio_regulatory_exposure_from_records(
    *,
    design_briefs: Iterable[Mapping[str, Any]],
    domain: str | Iterable[str] | set[str] | None = None,
    representative_limit: int = DEFAULT_REPRESENTATIVE_LIMIT,
) -> dict[str, Any]:
    """Group already-loaded design briefs by likely regulatory exposure area."""

    if representative_limit < 1:
        raise ValueError("representative_limit must be at least 1")

    domain_filter = _filter_values(domain)
    records = sorted(
        [
            _brief_record(brief)
            for brief in design_briefs
            if _matches_filter(_clean(brief.get("domain")) or "unspecified", domain_filter)
        ],
        key=lambda record: record["id"],
    )
    buckets = _exposure_buckets(records, representative_limit=representative_limit)
    summary = _summary(records, buckets)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "filters": {
            "domain": sorted(domain_filter) if domain_filter else None,
            "representative_limit": representative_limit,
        },
        "summary": summary,
        "exposure_buckets": buckets,
        "recommendations": _recommendations(buckets, summary),
    }


def _enriched_brief(store: Store, brief: Mapping[str, Any]) -> dict[str, Any]:
    enriched = dict(brief)
    source_ids = _dedupe(
        [
            *_list(brief.get("source_idea_ids")),
            *[
                source.get("idea_id")
                for source in _list(brief.get("sources"))
                if isinstance(source, Mapping)
            ],
        ]
    )
    source_ideas = []
    evidence_docs = []
    for source_id in source_ids:
        unit = store.get_buildable_unit(source_id)
        if unit is None:
            continue
        source_ideas.append(_unit_payload(unit))
        for signal_id in _list(_get(unit, "evidence_signals")):
            signal = store.get_signal(_clean(signal_id))
            if signal is not None:
                evidence_docs.append(_evidence_payload(signal, evidence_type="signal"))
        for insight_id in _list(_get(unit, "inspiring_insights")):
            insight = store.get_insight(_clean(insight_id))
            if insight is not None:
                evidence_docs.append(_evidence_payload(insight, evidence_type="insight"))
    enriched["source_ideas"] = source_ideas
    enriched["evidence_documents"] = evidence_docs
    return enriched


def _brief_record(brief: Mapping[str, Any]) -> dict[str, Any]:
    source_ideas = [
        idea for idea in _list(brief.get("source_ideas")) if isinstance(idea, Mapping)
    ]
    evidence_docs = [
        doc for doc in _list(brief.get("evidence_documents")) if isinstance(doc, Mapping)
    ]
    source_idea_ids = _dedupe(
        [
            *_list(brief.get("source_idea_ids")),
            *[
                source.get("idea_id")
                for source in _list(brief.get("sources"))
                if isinstance(source, Mapping)
            ],
            *[idea.get("id") for idea in source_ideas],
        ]
    )
    evidence_ids = _dedupe(
        [
            *source_idea_ids,
            *_flatten(brief.get("evidence_ids")),
            *_flatten(brief.get("evidence_signals")),
            *_flatten(brief.get("inspiring_insights")),
            *[
                doc.get("id")
                for doc in evidence_docs
                if isinstance(doc, Mapping)
            ],
            *[
                evidence
                for idea in source_ideas
                for evidence in [
                    *_list(idea.get("evidence_signals")),
                    *_list(idea.get("inspiring_insights")),
                ]
            ],
        ]
    )
    field_texts = {
        "domain": _clean(brief.get("domain")),
        "theme": _clean(brief.get("theme")),
        "title": _clean(brief.get("title")),
        "target_users": " ".join(
            [
                _clean(brief.get("target_users")),
                _clean(brief.get("buyer")),
                _clean(brief.get("specific_user")),
                *[_clean(idea.get("target_users")) for idea in source_ideas],
                *[_clean(idea.get("buyer")) for idea in source_ideas],
                *[_clean(idea.get("specific_user")) for idea in source_ideas],
            ]
        ),
        "risks": " ".join(
            [
                *_string_list(brief.get("risks")),
                *_string_list(brief.get("domain_risks")),
                *[
                    risk
                    for idea in source_ideas
                    for risk in _string_list(idea.get("domain_risks"))
                ],
            ]
        ),
        "artifacts": " ".join(
            [
                *_flatten(brief.get("compliance_artifacts")),
                *_flatten(brief.get("privacy_artifacts")),
                *_flatten(brief.get("security_artifacts")),
                *_flatten(brief.get("accessibility_artifacts")),
                *_flatten(brief.get("procurement_artifacts")),
                *_flatten(brief.get("suggested_stack")),
                *[
                    value
                    for idea in source_ideas
                    for value in _flatten(idea.get("suggested_stack"))
                ],
                *[_clean(idea.get("tech_approach")) for idea in source_ideas],
            ]
        ),
        "tags": " ".join(
            [
                *_flatten(brief.get("tags")),
                *_flatten(brief.get("rejection_tags")),
                *[
                    tag
                    for idea in source_ideas
                    for tag in _flatten(idea.get("tags"))
                ],
                *[
                    tag
                    for idea in source_ideas
                    for tag in _flatten(idea.get("rejection_tags"))
                ],
                *[
                    tag
                    for doc in evidence_docs
                    for tag in _flatten(doc.get("tags"))
                ],
            ]
        ),
        "evidence": " ".join(
            [
                *_flatten(brief.get("evidence")),
                *_flatten(brief.get("evidence_rationale")),
                *[
                    _clean(idea.get("evidence_rationale"))
                    for idea in source_ideas
                ],
                *[
                    " ".join(_flatten(doc))
                    for doc in evidence_docs
                ],
            ]
        ),
        "body": " ".join(
            [
                _clean(brief.get("why_this_now")),
                _clean(brief.get("merged_product_concept")),
                _clean(brief.get("synthesis_rationale")),
                _clean(brief.get("validation_plan")),
                _clean(brief.get("workflow_context")),
                " ".join(_string_list(brief.get("mvp_scope"))),
                " ".join(_string_list(brief.get("first_milestones"))),
                *[
                    _clean(idea.get(field))
                    for idea in source_ideas
                    for field in (
                        "one_liner",
                        "problem",
                        "solution",
                        "workflow_context",
                        "validation_plan",
                        "current_workaround",
                    )
                ],
            ]
        ),
    }
    exposures = _brief_exposures(field_texts)
    return {
        "id": _clean(brief.get("id")),
        "title": _clean(brief.get("title")) or _clean(brief.get("id")),
        "domain": _clean(brief.get("domain")) or "unspecified",
        "theme": _clean(brief.get("theme")) or "uncategorized",
        "readiness_score": _float(brief.get("readiness_score")),
        "design_status": _clean(brief.get("design_status")),
        "source_idea_ids": source_idea_ids,
        "evidence_ids": evidence_ids,
        "exposures": exposures,
    }


def _brief_exposures(field_texts: Mapping[str, str]) -> dict[str, list[dict[str, str]]]:
    exposures: dict[str, list[dict[str, str]]] = {}
    for config in _AREA_CONFIGS:
        reasons = []
        for field_name, text in field_texts.items():
            match = _keyword_match(text, config["keywords"])
            if match:
                reasons.append(
                    {
                        "field": field_name,
                        "matched_term": match,
                        "reason": f"{_FIELD_LABELS[field_name]} references {match}.",
                    }
                )
        if reasons:
            exposures[config["id"]] = reasons
    return exposures


def _exposure_buckets(
    records: list[dict[str, Any]],
    *,
    representative_limit: int,
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        for area in record["exposures"]:
            grouped.setdefault(area, []).append(record)

    total = len(records)
    buckets = []
    for config in _AREA_CONFIGS:
        area = config["id"]
        members = grouped.get(area, [])
        if not members:
            continue
        exposure_count = len(members)
        portfolio_share = round(exposure_count / total, 3) if total else 0.0
        risk_level = _risk_level(exposure_count, portfolio_share)
        representative_briefs = _representative_briefs(members, representative_limit)
        buckets.append(
            {
                "id": f"regulatory:{area}",
                "regulatory_area": area,
                "title": config["title"],
                "exposure_count": exposure_count,
                "portfolio_share": portfolio_share,
                "risk_level": risk_level,
                "representative_brief_ids": [
                    item["id"] for item in representative_briefs
                ],
                "representative_briefs": representative_briefs,
                "domains": _counter_rows(
                    Counter(member["domain"] for member in members),
                    "domain",
                ),
                "exposure_reasons": _exposure_reasons(area, members),
                "missing_evidence_notes": _missing_evidence_notes(area, members),
                "recommended_next_actions": _bucket_actions(config, risk_level),
            }
        )

    return sorted(
        buckets,
        key=lambda bucket: (
            _risk_rank(bucket["risk_level"]),
            -bucket["exposure_count"],
            bucket["regulatory_area"],
        ),
    )


def _summary(records: list[dict[str, Any]], buckets: list[dict[str, Any]]) -> dict[str, Any]:
    high = sum(1 for bucket in buckets if bucket["risk_level"] == "high")
    medium = sum(1 for bucket in buckets if bucket["risk_level"] == "medium")
    low = sum(1 for bucket in buckets if bucket["risk_level"] == "low")
    exposed_ids = {
        brief_id
        for bucket in buckets
        for brief_id in bucket["representative_brief_ids"]
    }
    exposed_ids.update(
        record["id"]
        for record in records
        if record["exposures"]
    )
    return {
        "design_brief_count": len(records),
        "exposed_brief_count": len(exposed_ids),
        "low_exposure_brief_count": len(records) - len(exposed_ids),
        "exposure_bucket_count": len(buckets),
        "high_risk_bucket_count": high,
        "medium_risk_bucket_count": medium,
        "low_risk_bucket_count": low,
        "overall_exposure_level": "high" if high else "medium" if medium else "low",
    }


def _exposure_reasons(area: str, members: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for member in sorted(members, key=lambda item: item["id"]):
        reasons = member["exposures"][area]
        rows.append(
            {
                "brief_id": member["id"],
                "fields": _dedupe(reason["field"] for reason in reasons),
                "matched_terms": _dedupe(reason["matched_term"] for reason in reasons),
                "reason": reasons[0]["reason"],
            }
        )
    return rows


def _missing_evidence_notes(area: str, members: list[dict[str, Any]]) -> list[str]:
    notes = []
    config = _AREA_BY_ID[area]
    for member in sorted(members, key=lambda item: item["id"]):
        if not member["evidence_ids"]:
            notes.append(
                f"{member['id']}: no source idea or evidence references are attached "
                "to this exposure."
            )
            continue
        evidence_reasons = [
            reason
            for reason in member["exposures"][area]
            if reason["field"] == "evidence"
        ]
        if not evidence_reasons:
            notes.append(
                f"{member['id']}: exposure is inferred from brief fields, but "
                f"evidence does not explicitly mention {config['title'].lower()}."
            )
    return notes


def _representative_briefs(
    members: list[dict[str, Any]],
    limit: int,
) -> list[dict[str, Any]]:
    ranked = sorted(
        members,
        key=lambda member: (
            -member["readiness_score"],
            member["id"],
        ),
    )
    return [
        {
            "id": member["id"],
            "title": member["title"],
            "domain": member["domain"],
            "theme": member["theme"],
            "readiness_score": member["readiness_score"],
            "design_status": member["design_status"],
            "evidence_ids": member["evidence_ids"][:5],
        }
        for member in ranked[:limit]
    ]


def _recommendations(
    buckets: list[dict[str, Any]],
    summary: Mapping[str, Any],
) -> list[dict[str, str]]:
    if summary["design_brief_count"] == 0:
        return [
            {
                "priority": "high",
                "action": "Generate or import design briefs before assessing regulatory exposure.",
                "rationale": "No persisted design briefs matched the selected filters.",
            }
        ]
    if not buckets:
        return [
            {
                "priority": "low",
                "action": (
                    "Keep lightweight legal, privacy, and security screening in the "
                    "design brief review workflow."
                ),
                "rationale": (
                    "No likely regulatory exposure was detected in the selected "
                    "design briefs."
                ),
            }
        ]

    top = buckets[0]
    priority = "high" if top["risk_level"] == "high" else "medium"
    recommendations = [
        {
            "priority": priority,
            "action": top["recommended_next_actions"][0],
            "rationale": (
                f"{top['title']} appears in {top['exposure_count']} brief(s), "
                f"covering {top['portfolio_share']:.1%} of the analyzed portfolio."
            ),
        }
    ]
    missing = next(
        (bucket for bucket in buckets if bucket["missing_evidence_notes"]),
        None,
    )
    if missing:
        recommendations.append(
            {
                "priority": "medium",
                "action": (
                    "Attach explicit evidence before advancing "
                    f"{missing['title'].lower()} exposed briefs."
                ),
                "rationale": missing["missing_evidence_notes"][0],
            }
        )
    return recommendations


def _bucket_actions(config: Mapping[str, Any], risk_level: str) -> list[str]:
    area = config["id"]
    if area == "privacy":
        first = (
            "Run privacy impact assessment and document data minimization, notice, "
            "retention, and deletion assumptions."
        )
    elif area == "healthcare":
        first = (
            "Route healthcare-facing briefs through clinical, HIPAA, and patient "
            "data review before pilots."
        )
    elif area == "finance":
        first = (
            "Review financial data, payments, credit, and audit assumptions with "
            "finance compliance before launch planning."
        )
    elif area == "security":
        first = (
            "Complete threat modeling, access-control review, and secrets-handling "
            "review before implementation."
        )
    elif area == "accessibility":
        first = (
            "Add accessibility acceptance criteria for keyboard, screen reader, "
            "contrast, and error states."
        )
    elif area == "procurement":
        first = (
            "Prepare buyer security, vendor, DPA, pricing, and procurement answers "
            "before sales or pilot handoff."
        )
    else:
        first = f"Route {config['title'].lower()} exposure through the accountable reviewer."

    if risk_level == "high":
        return [
            first,
            "Assign a named owner and block execution until review evidence is attached.",
        ]
    if risk_level == "medium":
        return [first, "Confirm review ownership during the next portfolio review."]
    return [first]


def _risk_level(exposure_count: int, portfolio_share: float) -> str:
    if exposure_count >= 3 or (exposure_count >= 2 and portfolio_share >= 0.5):
        return "high"
    if exposure_count >= 2 or portfolio_share >= 0.34:
        return "medium"
    return "low"


def _keyword_match(text: str, keywords: Iterable[str]) -> str:
    lowered = _clean(text).lower()
    if not lowered:
        return ""
    for keyword in keywords:
        pattern = r"(?<![a-z0-9])" + re.escape(keyword.lower()) + r"(?![a-z0-9])"
        if re.search(pattern, lowered):
            return keyword
    return ""


def _unit_payload(unit: Any) -> dict[str, Any]:
    return {
        "id": _get(unit, "id"),
        "title": _get(unit, "title"),
        "one_liner": _get(unit, "one_liner"),
        "problem": _get(unit, "problem"),
        "solution": _get(unit, "solution"),
        "target_users": _get(unit, "target_users"),
        "buyer": _get(unit, "buyer"),
        "specific_user": _get(unit, "specific_user"),
        "workflow_context": _get(unit, "workflow_context"),
        "validation_plan": _get(unit, "validation_plan"),
        "current_workaround": _get(unit, "current_workaround"),
        "domain_risks": _get(unit, "domain_risks"),
        "evidence_rationale": _get(unit, "evidence_rationale"),
        "rejection_tags": _get(unit, "rejection_tags"),
        "evidence_signals": _get(unit, "evidence_signals"),
        "inspiring_insights": _get(unit, "inspiring_insights"),
        "tech_approach": _get(unit, "tech_approach"),
        "suggested_stack": _get(unit, "suggested_stack"),
    }


def _evidence_payload(item: Any, *, evidence_type: str) -> dict[str, Any]:
    return {
        "id": _get(item, "id"),
        "type": evidence_type,
        "title": _get(item, "title"),
        "summary": _get(item, "summary"),
        "content": _get(item, "content"),
        "source_adapter": _get(item, "source_adapter"),
        "tags": _get(item, "tags"),
        "metadata": _get(item, "metadata"),
    }


def _counter_rows(counts: Counter[str], key: str) -> list[dict[str, Any]]:
    return [
        {key: value, "count": count}
        for value, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def _risk_rank(level: str) -> int:
    return {"high": 0, "medium": 1, "low": 2}.get(level, 3)


def _filter_values(value: str | Iterable[str] | set[str] | None) -> set[str] | None:
    if value is None:
        return None
    if isinstance(value, str):
        cleaned = _clean(value)
        return {cleaned} if cleaned else None
    values = {_clean(item) for item in value}
    values.discard("")
    return values or None


def _matches_filter(value: str, allowed: set[str] | None) -> bool:
    return allowed is None or value in allowed


def _dedupe(values: Iterable[Any]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        cleaned = _clean(value)
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        ordered.append(cleaned)
    return ordered


def _get(item: Any, key: str) -> Any:
    if isinstance(item, Mapping):
        return item.get(key)
    return getattr(item, key, None)


def _list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple | set):
        return list(value)
    return [value]


def _string_list(value: Any) -> list[str]:
    return [_clean(item) for item in _list(value) if _clean(item)]


def _flatten(value: Any) -> list[str]:
    if isinstance(value, Mapping):
        flattened: list[str] = []
        for key, item in value.items():
            flattened.append(str(key))
            flattened.extend(_flatten(item))
        return flattened
    if isinstance(value, list | tuple | set):
        flattened = []
        for item in value:
            flattened.extend(_flatten(item))
        return flattened
    if value in (None, ""):
        return []
    return [str(value)]


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


_AREA_CONFIGS: tuple[dict[str, Any], ...] = (
    {
        "id": "privacy",
        "title": "Privacy",
        "keywords": (
            "privacy",
            "pii",
            "personal data",
            "personal information",
            "consent",
            "gdpr",
            "ccpa",
            "data retention",
            "delete",
            "deletion",
            "user data",
            "customer data",
            "email",
            "profile",
        ),
    },
    {
        "id": "healthcare",
        "title": "Healthcare",
        "keywords": (
            "healthcare",
            "health care",
            "health",
            "hipaa",
            "patient",
            "clinical",
            "medical",
            "diagnosis",
            "doctor",
            "nurse",
            "care team",
        ),
    },
    {
        "id": "finance",
        "title": "Finance",
        "keywords": (
            "finance",
            "fintech",
            "financial",
            "bank",
            "payment",
            "payments",
            "credit",
            "loan",
            "payroll",
            "invoice",
            "billing",
            "tax",
            "audit",
            "sox",
        ),
    },
    {
        "id": "security",
        "title": "Security",
        "keywords": (
            "security",
            "credential",
            "credentials",
            "secret",
            "secrets",
            "oauth",
            "sso",
            "authentication",
            "authorization",
            "access control",
            "vulnerability",
            "threat",
            "cve",
            "soc 2",
            "soc2",
            "encryption",
        ),
    },
    {
        "id": "accessibility",
        "title": "Accessibility",
        "keywords": (
            "accessibility",
            "a11y",
            "wcag",
            "screen reader",
            "keyboard",
            "contrast",
            "aria",
            "disabled",
            "assistive",
        ),
    },
    {
        "id": "procurement",
        "title": "Procurement",
        "keywords": (
            "procurement",
            "vendor",
            "purchasing",
            "contract",
            "dpa",
            "msa",
            "security questionnaire",
            "legal review",
            "pricing review",
            "enterprise procurement",
        ),
    },
)

_AREA_BY_ID = {config["id"]: config for config in _AREA_CONFIGS}

_FIELD_LABELS = {
    "domain": "Domain",
    "theme": "Theme",
    "title": "Title",
    "target_users": "Target users",
    "risks": "Risk fields",
    "artifacts": "Compliance, privacy, security, or implementation artifacts",
    "tags": "Tags",
    "evidence": "Evidence",
    "body": "Brief narrative",
}
