"""Generate source onboarding validation plans."""

from __future__ import annotations

from typing import Any, Mapping


def generate_source_onboarding_validation_plan(source_config: Mapping[str, Any], profile_requirements: Mapping[str, Any]) -> dict[str, Any]:
    credentials = _list(source_config.get("credentials") or source_config.get("required_credentials"))
    provided = set(_list(source_config.get("provided_credentials")))
    required_categories = set(_list(profile_requirements.get("required_categories")))
    source_categories = set(_list(source_config.get("categories")))
    blockers = []
    blockers.extend([f"missing credential: {credential}" for credential in sorted(set(credentials) - provided)])
    blockers.extend([f"missing profile category: {category}" for category in sorted(required_categories - source_categories)])
    fields = sorted(set(_list(profile_requirements.get("normalization_fields"))) | set(_list(source_config.get("normalization_fields"))))
    return {"schema_version": "max.source_onboarding_validation_plan.v1", "kind": "max.source_onboarding_validation_plan", "source_identity": {"source": _text(source_config.get("source") or source_config.get("name")) or "unknown-source", "owner": _text(source_config.get("owner")) or "unknown"}, "required_credentials": sorted(credentials), "rate_limits": source_config.get("rate_limits") or {"status": "unknown"}, "normalization_contract": [{"field": field, "required": field in _list(profile_requirements.get("normalization_fields"))} for field in fields], "profile_fit_checks": [{"category": category, "status": "covered" if category in source_categories else "blocked"} for category in sorted(required_categories)], "sample_queries": [{"id": f"Q{index}", "query": _text(query)} for index, query in enumerate(_list(source_config.get("sample_queries")) or ["smoke query"], start=1)], "acceptance_checks": [{"id": "ACC1", "description": "Credentials validate in staging."}, {"id": "ACC2", "description": "Normalized payload satisfies profile contract."}], "rollback_triggers": ["credential failure", "freshness SLA breach", "normalization failure spike"], "evidence_requirements": ["credential test output", "sample payloads", "normalization diff"], "blockers": blockers}


def _list(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return [_text(item) for item in value if _text(item)]
    return [] if value in (None, "") else [_text(value)]


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
