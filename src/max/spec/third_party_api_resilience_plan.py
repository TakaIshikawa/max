"""Generate deterministic third-party API resilience plans for TactSpec previews."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, context, string_list, summary


SCHEMA_VERSION = "max.spec.third_party_api_resilience_plan.v1"
THIRD_PARTY_API_RESILIENCE_PLAN_SCHEMA_VERSION = SCHEMA_VERSION
KIND = "max.spec.third_party_api_resilience_plan"

_HIGH_RISK_TERMS = {
    "auth": "identity-critical",
    "authentication": "identity-critical",
    "authorization": "identity-critical",
    "crm": "revenue-critical",
    "customer": "customer-critical",
    "payment": "financial-critical",
    "payments": "financial-critical",
    "salesforce": "revenue-critical",
    "stripe": "financial-critical",
    "support": "customer-critical",
    "zendesk": "customer-critical",
}


def generate_third_party_api_resilience_plan(spec_like: dict[str, Any]) -> dict[str, Any]:
    """Return deterministic resilience guidance for external API dependencies."""
    spec = spec_like if isinstance(spec_like, dict) else {}
    ctx = context(spec)
    dependencies = _dependency_inventory(spec, ctx)
    evidence_ids = [item["id"] for item in ctx["evidence_references"]]
    high_risk_count = sum(1 for item in dependencies if item["risk_level"] == "high")

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(
            ctx,
            dependency_count=len(dependencies),
            high_risk_dependency_count=high_risk_count,
            resilience_posture="strict" if high_risk_count else ctx["strictness"],
        ),
        "dependency_inventory": dependencies,
        "failure_modes": _failure_modes(ctx, dependencies, evidence_ids),
        "fallback_strategies": _fallback_strategies(ctx, dependencies, evidence_ids),
        "retry_and_timeout_policy": _retry_and_timeout_policy(dependencies, evidence_ids),
        "monitoring_signals": _monitoring_signals(dependencies, evidence_ids),
        "owner_roles": _owner_roles(ctx),
        "evidence_references": ctx["evidence_references"],
    }


def _dependency_inventory(spec: dict[str, Any], ctx: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, str]] = []
    metadata = spec.get("metadata") if isinstance(spec.get("metadata"), dict) else {}
    solution = spec.get("solution") if isinstance(spec.get("solution"), dict) else {}
    artifacts = spec.get("artifacts") if isinstance(spec.get("artifacts"), dict) else {}
    dependency_artifact = (
        artifacts.get("dependency_inventory")
        if isinstance(artifacts.get("dependency_inventory"), dict)
        else {}
    )

    for source, value in (
        ("metadata.third_party_dependencies", metadata.get("third_party_dependencies")),
        ("metadata.dependencies", metadata.get("dependencies")),
        ("solution.dependencies", solution.get("dependencies")),
        ("solution.suggested_stack", solution.get("suggested_stack")),
        ("dependency_inventory.dependencies", dependency_artifact.get("dependencies")),
    ):
        records.extend(_dependency_records(source, value))

    if not records:
        records.append(
            {
                "name": "Unspecified third-party API",
                "category": "missing_inventory",
                "source_field": "metadata.third_party_dependencies",
            }
        )

    merged: dict[str, dict[str, Any]] = {}
    for record in records:
        name = record["name"]
        key = name.lower()
        current = merged.setdefault(
            key,
            {
                "name": name,
                "category": record.get("category") or _category(name),
                "source_fields": [],
            },
        )
        current["category"] = _strictest_category(current["category"], record.get("category") or _category(name))
        current["source_fields"].append(record["source_field"])

    result: list[dict[str, Any]] = []
    for index, item in enumerate(sorted(merged.values(), key=lambda value: value["name"].lower()), start=1):
        risk_hint = _risk_hint(item["name"], item["category"])
        result.append(
            {
                "id": f"TPA{index}",
                "name": item["name"],
                "category": item["category"],
                "risk_level": "high" if risk_hint else ("high" if item["category"] == "missing_inventory" else ctx["risk_level"]),
                "risk_hint": risk_hint or "standard",
                "source_fields": sorted(set(item["source_fields"])),
                "critical_path": bool(risk_hint) or item["category"] == "missing_inventory",
                "references": ["solution.suggested_stack", "metadata.dependencies", "dependency_inventory.dependencies"],
            }
        )
    return result


def _failure_modes(
    ctx: dict[str, Any], dependencies: list[dict[str, Any]], evidence_ids: list[str]
) -> list[dict[str, Any]]:
    dependency_ids = [item["id"] for item in dependencies]
    strict = any(item["risk_level"] == "high" for item in dependencies)
    return [
        _item(
            "FM1",
            "Provider outage or brownout",
            "high" if strict else "medium",
            "technical_owner",
            f"External APIs needed by {ctx['workflow_context']} are unavailable or return elevated 5xx errors.",
            "Serve degraded read-only or queued workflow paths without data loss.",
            dependency_ids,
            evidence_ids,
        ),
        _item(
            "FM2",
            "Rate limit or quota exhaustion",
            "high" if strict else "medium",
            "technical_owner",
            "Requests are throttled, quota is exhausted, or burst limits block customer-facing work.",
            "Back off, queue non-critical calls, and surface clear operator status.",
            dependency_ids,
            evidence_ids,
        ),
        _item(
            "FM3",
            "Authentication or contract drift",
            "high" if strict else "medium",
            "vendor_owner",
            "Tokens, scopes, schemas, webhooks, or response semantics change without matching application handling.",
            "Detect integration errors before customer impact and route to owner review.",
            dependency_ids,
            evidence_ids,
        ),
    ]


def _fallback_strategies(
    ctx: dict[str, Any], dependencies: list[dict[str, Any]], evidence_ids: list[str]
) -> list[dict[str, Any]]:
    return [
        {
            "id": f"FS{index}",
            "dependency_id": dependency["id"],
            "name": f"{dependency['name']} degraded operation",
            "owner": "technical_owner" if dependency["risk_level"] == "high" else "product_owner",
            "strategy": _fallback_for(dependency, ctx),
            "activation_condition": "dependency health check fails, error budget burn accelerates, or provider incident is confirmed",
            "recovery_condition": "successful canary calls and provider status remain healthy for two monitoring windows",
            "evidence_reference_ids": evidence_ids,
        }
        for index, dependency in enumerate(dependencies, start=1)
    ]


def _retry_and_timeout_policy(
    dependencies: list[dict[str, Any]], evidence_ids: list[str]
) -> list[dict[str, Any]]:
    return [
        {
            "id": f"RTP{index}",
            "dependency_id": dependency["id"],
            "owner": "technical_owner",
            "timeout": "2s connect / 5s overall" if dependency["risk_level"] == "high" else "3s connect / 10s overall",
            "retry": "bounded exponential backoff with jitter; no retries for non-idempotent writes without idempotency keys",
            "circuit_breaker": "open after 5 consecutive failures for high-risk dependencies" if dependency["risk_level"] == "high" else "open after sustained failure window",
            "queue_policy": "durable queue with operator replay for customer-critical writes" if dependency["critical_path"] else "short-lived retry queue for non-critical work",
            "evidence_reference_ids": evidence_ids,
        }
        for index, dependency in enumerate(dependencies, start=1)
    ]


def _monitoring_signals(
    dependencies: list[dict[str, Any]], evidence_ids: list[str]
) -> list[dict[str, Any]]:
    return [
        {
            "id": f"MS{index}",
            "dependency_id": dependency["id"],
            "name": f"{dependency['name']} dependency health",
            "owner": "technical_owner",
            "signals": [
                "success rate",
                "p95 latency",
                "timeout count",
                "retry count",
                "rate-limit responses",
                "circuit-breaker state",
            ],
            "alert_threshold": "page on sustained customer-impacting errors" if dependency["risk_level"] == "high" else "ticket on sustained degradation",
            "evidence_reference_ids": evidence_ids,
        }
        for index, dependency in enumerate(dependencies, start=1)
    ]


def _owner_roles(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "role": "technical_owner",
            "suggested_owner": "technical_owner",
            "responsibility": "Own timeout, retry, circuit breaker, queue, and monitoring implementation.",
        },
        {
            "role": "product_owner",
            "suggested_owner": ctx["buyer"],
            "responsibility": "Approve degraded user experience and customer-visible fallback behavior.",
        },
        {
            "role": "vendor_owner",
            "suggested_owner": "vendor_owner",
            "responsibility": "Track provider SLAs, quotas, status pages, support paths, and contract changes.",
        },
        {
            "role": "support_owner",
            "suggested_owner": "support_owner",
            "responsibility": "Coordinate customer messaging and manual workarounds during dependency incidents.",
        },
    ]


def _dependency_records(source: str, value: Any) -> list[dict[str, str]]:
    if isinstance(value, dict):
        records: list[dict[str, str]] = []
        for key, item in sorted(value.items()):
            if isinstance(item, dict):
                name = compact(item.get("name") or item.get("provider") or item.get("service") or item.get("vendor") or key)
                category = compact(item.get("category") or item.get("type") or key)
            else:
                name = compact(item)
                category = compact(key)
            if name:
                records.append({"name": name, "category": _category(category or name), "source_field": f"{source}.{key}"})
        return records
    if isinstance(value, list):
        records = []
        for index, item in enumerate(value, start=1):
            if isinstance(item, dict):
                name = compact(item.get("name") or item.get("provider") or item.get("service") or item.get("vendor"))
                category = compact(item.get("category") or item.get("type") or item.get("kind"))
            else:
                name = compact(item)
                category = ""
            if name:
                records.append({"name": name, "category": _category(category or name), "source_field": f"{source}[{index}]"})
        return records
    return [
        {"name": item, "category": _category(item), "source_field": source}
        for item in string_list(value)
    ]


def _fallback_for(dependency: dict[str, Any], ctx: dict[str, Any]) -> str:
    category = dependency["category"]
    if category == "payments":
        return "Preserve cart or invoice state, accept no duplicate charges, and provide manual payment review."
    if category == "auth":
        return "Keep existing sessions usable where safe, block risky privilege changes, and route sign-in issues to support."
    if category == "crm":
        return "Queue CRM writes with idempotency keys and expose an operator replay queue after recovery."
    if category == "support":
        return "Capture customer requests locally and publish delayed ticket creation status to support operators."
    if category == "missing_inventory":
        return "Block launch readiness until the external API owner, criticality, quota, and fallback path are documented."
    return f"Queue non-critical calls for {ctx['workflow_context']} and show a degraded status when synchronous calls fail."


def _item(
    item_id: str,
    name: str,
    severity: str,
    owner: str,
    condition: str,
    action: str,
    dependency_ids: list[str],
    evidence_ids: list[str],
) -> dict[str, Any]:
    return {
        "id": item_id,
        "name": name,
        "severity": severity,
        "owner": owner,
        "condition": condition,
        "action": action,
        "dependency_ids": dependency_ids,
        "evidence_reference_ids": evidence_ids,
    }


def _category(value: str) -> str:
    lowered = compact(value).lower()
    if any(term in lowered for term in ("stripe", "payment", "billing", "invoice")):
        return "payments"
    if any(term in lowered for term in ("auth", "oauth", "okta", "sso", "identity")):
        return "auth"
    if any(term in lowered for term in ("crm", "salesforce", "hubspot")):
        return "crm"
    if any(term in lowered for term in ("support", "zendesk", "freshdesk", "ticket")):
        return "support"
    if any(term in lowered for term in ("email", "sms", "twilio", "slack", "teams", "message")):
        return "communications"
    if any(term in lowered for term in ("datadog", "sentry", "observability", "monitor")):
        return "observability"
    if "missing" in lowered:
        return "missing_inventory"
    return "external_api"


def _strictest_category(left: str, right: str) -> str:
    order = ("payments", "auth", "crm", "support", "missing_inventory")
    for category in order:
        if category in {left, right}:
            return category
    return left if left != "external_api" else right


def _risk_hint(name: str, category: str) -> str:
    lowered = f"{name} {category}".lower()
    for term, hint in sorted(_HIGH_RISK_TERMS.items()):
        if term in lowered:
            return hint
    return ""
