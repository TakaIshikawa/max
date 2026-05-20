"""Generate deterministic data quality remediation plans for TactSpec previews."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, context, string_list, summary


SCHEMA_VERSION = "max.spec.data_quality_remediation_plan.v1"
KIND = "max.spec.data_quality_remediation_plan"
SEVERITY_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}


def generate_data_quality_remediation_plan(spec_like: Any) -> dict[str, Any]:
    """Return remediation workstreams, validation checks, and exit criteria."""
    spec = spec_like if isinstance(spec_like, dict) else {}
    ctx = context(spec)
    hints = _hints(spec, "data_quality_remediation")
    datasets = _values(hints.get("datasets") or spec.get("datasets"), ["primary dataset"])
    findings = _findings(hints.get("findings") or spec.get("data_quality_findings") or spec.get("findings"), datasets)
    metrics = _metrics(hints.get("metrics") or spec.get("metrics"))
    owners = _owner_map(hints.get("owners") or spec.get("owners"))
    evidence_ids = _evidence_ids(ctx)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(
            ctx,
            affected_asset_count=len(datasets),
            finding_count=len(findings),
            customer_impacting_count=sum(1 for item in findings if item["customer_impacting"]),
        ),
        "affected_assets": [
            {
                "id": f"AS{index}",
                "dataset": dataset,
                "owner": owners.get(dataset.casefold()) or owners.get("default") or "data_owner",
                "evidence_reference_ids": evidence_ids,
            }
            for index, dataset in enumerate(datasets, start=1)
        ],
        "remediation_workstreams": [_workstream(index, finding, owners, evidence_ids) for index, finding in enumerate(findings, start=1)],
        "validation_checks": _validation_checks(findings, metrics, evidence_ids),
        "exit_criteria": _exit_criteria(metrics, evidence_ids),
        "evidence_references": ctx["evidence_references"],
    }


def _workstream(index: int, finding: dict[str, Any], owners: dict[str, str], evidence_ids: list[str]) -> dict[str, Any]:
    dataset = finding["dataset"]
    return {
        "id": f"WS{index}",
        "finding": finding["name"],
        "dataset": dataset,
        "severity": finding["severity"],
        "customer_impacting": finding["customer_impacting"],
        "owner": owners.get(dataset.casefold()) or owners.get("default") or "data_owner",
        "remediation_action": f"Correct {finding['name']} in {dataset} and document prevention controls.",
        "evidence_reference_ids": evidence_ids,
    }


def _validation_checks(findings: list[dict[str, Any]], metrics: list[dict[str, str]], evidence_ids: list[str]) -> list[dict[str, Any]]:
    checks = [
        {
            "id": f"VC{index}",
            "type": "finding_validation",
            "dataset": finding["dataset"],
            "severity": finding["severity"],
            "check": f"Re-run quality checks proving {finding['name']} is remediated.",
            "evidence_reference_ids": evidence_ids,
        }
        for index, finding in enumerate(findings, start=1)
    ]
    offset = len(checks)
    checks.extend(
        {
            "id": f"VC{offset + index}",
            "type": "metric_threshold",
            "metric": metric["name"],
            "check": f"Confirm {metric['name']} {metric['operator']} {metric['threshold']}.",
            "evidence_reference_ids": evidence_ids,
        }
        for index, metric in enumerate(metrics, start=1)
    )
    return checks


def _exit_criteria(metrics: list[dict[str, str]], evidence_ids: list[str]) -> list[dict[str, Any]]:
    if not metrics:
        return [
            {
                "id": "EC1",
                "criterion": "All high and customer-impacting findings are closed with reviewer signoff.",
                "owner": "data_owner",
                "evidence_reference_ids": evidence_ids,
            }
        ]
    return [
        {
            "id": f"EC{index}",
            "criterion": f"{metric['name']} remains {metric['operator']} {metric['threshold']} for the agreed validation window.",
            "owner": "data_owner",
            "evidence_reference_ids": evidence_ids,
        }
        for index, metric in enumerate(metrics, start=1)
    ]


def _findings(value: Any, datasets: list[str]) -> list[dict[str, Any]]:
    raw = value if isinstance(value, list) else string_list(value)
    findings: list[dict[str, Any]] = []
    for index, item in enumerate(raw, start=1):
        if isinstance(item, dict):
            name = compact(item.get("name") or item.get("finding") or item.get("description")) or f"finding {index}"
            severity = _severity(item.get("severity") or item.get("priority"))
            dataset = compact(item.get("dataset") or item.get("asset")) or datasets[0]
            customer_impacting = _truthy(item.get("customer_impacting") or item.get("customer_impact"))
        else:
            name = compact(item) or f"finding {index}"
            severity = "medium"
            dataset = datasets[0]
            customer_impacting = False
        findings.append({"name": name, "severity": severity, "dataset": dataset, "customer_impacting": customer_impacting})
    if not findings:
        findings.append({"name": "data quality review pending", "severity": "medium", "dataset": datasets[0], "customer_impacting": False})
    return sorted(
        findings,
        key=lambda item: (
            not item["customer_impacting"],
            -SEVERITY_RANK.get(item["severity"], 0),
            item["dataset"].casefold(),
            item["name"].casefold(),
        ),
    )


def _metrics(value: Any) -> list[dict[str, str]]:
    raw = value if isinstance(value, list) else []
    metrics: list[dict[str, str]] = []
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            continue
        name = compact(item.get("name") or item.get("metric")) or f"metric {index}"
        threshold = compact(item.get("threshold") or item.get("target")) or "target threshold"
        operator = compact(item.get("operator")) or ">="
        metrics.append({"name": name, "operator": operator, "threshold": threshold})
    return sorted(metrics, key=lambda item: item["name"].casefold())


def _values(value: Any, fallback: list[str]) -> list[str]:
    values = string_list(value)
    return sorted(dict.fromkeys(values), key=str.casefold) if values else fallback


def _owner_map(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {compact(key).casefold(): compact(owner) for key, owner in value.items() if compact(key) and compact(owner)}


def _hints(spec: dict[str, Any], key: str) -> dict[str, Any]:
    metadata = spec.get("metadata") if isinstance(spec.get("metadata"), dict) else {}
    hints = metadata.get(key)
    return hints if isinstance(hints, dict) else {}


def _severity(value: Any) -> str:
    text = compact(value).casefold()
    return text if text in SEVERITY_RANK else "medium"


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return compact(value).casefold() in {"1", "true", "yes", "y", "customer", "customer-impacting"}


def _evidence_ids(ctx: dict[str, Any]) -> list[str]:
    return [item["id"] for item in ctx["evidence_references"]]
