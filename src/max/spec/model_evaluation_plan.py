"""Generate deterministic model evaluation plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, evidence_references, string_list


SCHEMA_VERSION = "max-model-evaluation-plan/v1"
KIND = "max.model_evaluation_plan"


def generate_model_evaluation_plan(spec_like: Any) -> dict[str, Any]:
    """Return stable evaluation guidance for model-backed product behavior."""
    spec = spec_like if isinstance(spec_like, dict) else {}
    project = _section(spec, "project")
    model = _section(spec, "model")
    metadata = _section(spec, "metadata")
    strict = _strict(model, metadata, spec)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "title": _first(project.get("title"), spec.get("title"), "Unknown"),
            "gate_level": "strict" if strict else "standard",
            "regression_cadence": "per release" if strict else "monthly",
        },
        "objectives": _items(model.get("objectives") or ["quality", "safety", "business fit"]),
        "datasets": _items(model.get("datasets") or metadata.get("evaluation_datasets")),
        "metrics": _items(model.get("metrics") or ["accuracy", "precision", "recall"]),
        "baselines": _items(model.get("baselines") or ["current production behavior"]),
        "acceptance_thresholds": _thresholds(strict),
        "bias_checks": _items(model.get("bias_checks") or ["segment performance parity", "failure mode review"]),
        "regression_cadence": "per release" if strict else "monthly",
        "evidence": _evidence(spec, metadata),
    }


def _thresholds(strict: bool) -> dict[str, str]:
    if strict:
        return {"minimum_metric": ">= 0.95", "regression_limit": "<= 1%", "critical_failure_rate": "0"}
    return {"minimum_metric": ">= 0.85", "regression_limit": "<= 5%", "critical_failure_rate": "<= 1%"}


def _strict(model: dict[str, Any], metadata: dict[str, Any], spec: dict[str, Any]) -> bool:
    text = " ".join(
        string_list(model.get("use_cases"))
        + string_list(model.get("domains"))
        + string_list(metadata.get("domains"))
        + [compact(model.get("behavior") or spec.get("behavior"))]
    ).lower()
    return any(term in text for term in ("recommendation", "user-facing", "regulated", "finance", "healthcare", "legal"))


def _section(spec: dict[str, Any], name: str) -> dict[str, Any]:
    value = spec.get(name)
    return value if isinstance(value, dict) else {}


def _items(value: Any) -> list[str]:
    return _sorted_unique(value) or ["Unknown"]


def _evidence(spec: dict[str, Any], metadata: dict[str, Any]) -> list[str]:
    refs = [item["reference"] for item in evidence_references(spec)]
    refs.extend(string_list(metadata.get("evidence_links")))
    return _sorted_unique(refs)


def _sorted_unique(value: Any) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in string_list(value):
        if item not in seen:
            seen.add(item)
            result.append(item)
    return sorted(result, key=str.casefold)


def _first(*values: Any) -> str:
    for value in values:
        text = compact(value)
        if text:
            return text
    return "Unknown"
