"""Generate deterministic model monitoring plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, evidence_references, markdown_header, string_list


SCHEMA_VERSION = "max-model-monitoring-plan/v1"
KIND = "max.model_monitoring_plan"


def generate_model_monitoring_plan(spec_like: Any) -> dict[str, Any]:
    """Return stable monitoring guidance for model-backed systems."""
    spec = spec_like if isinstance(spec_like, dict) else {}
    models = _models(spec.get("models") or spec.get("monitored_models"))
    metrics = _metric_thresholds(spec)
    actions = _owner_actions(models)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "title": _title(spec),
            "model_count": len(models),
            "rollback_needed_count": sum(1 for item in models if item["state"] == "rollback_needed"),
            "degraded_count": sum(1 for item in models if item["state"] == "degraded"),
            "evaluation_cadence": _first(spec.get("evaluation_cadence"), "weekly"),
        },
        "monitored_models": models,
        "metric_thresholds": metrics,
        "drift_response": _drift_response(models),
        "evaluation_datasets": _items(spec.get("evaluation_datasets") or spec.get("datasets")),
        "owner_actions": actions,
        "rollback_criteria": _items(spec.get("rollback_criteria") or ["critical quality regression", "drift exceeds rollback threshold", "human review blocks release"]),
        "human_review_steps": _items(spec.get("human_review_steps") or ["review sampled failures", "approve remediation before rollout resumes"]),
        "evidence": evidence_references(spec),
    }


def render_model_monitoring_plan_markdown(plan: dict[str, Any]) -> str:
    """Render a model monitoring plan as deterministic Markdown."""
    lines = markdown_header(plan, "Model Monitoring Plan")
    _extend(lines, "Monitoring Matrix", plan.get("monitored_models") or [], _render_model)
    _extend(lines, "Metric Thresholds", plan.get("metric_thresholds") or [], _render_metric)
    _extend(lines, "Drift Response", plan.get("drift_response") or [], _render_response)
    _extend(lines, "Evaluation Cadence", [{"id": "CAD1", "cadence": plan.get("summary", {}).get("evaluation_cadence")}], _render_cadence)
    _extend(lines, "Human Review", plan.get("human_review_steps") or [], _render_text)
    _extend(lines, "Evidence", plan.get("evidence") or [], _render_evidence)
    return "\n".join(lines).rstrip() + "\n"


def _models(value: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for index, row in enumerate(value if isinstance(value, list) else [], start=1):
        item = row if isinstance(row, dict) else {"name": row}
        quality = _number(item.get("quality_score"), 1.0)
        drift = _number(item.get("drift_score"), 0.0)
        state = _state(quality, drift, item.get("state"))
        result.append(
            {
                "id": f"MODEL{index}",
                "name": _first(item.get("name"), f"model_{index}"),
                "state": state,
                "quality_score": quality,
                "drift_score": drift,
                "owner": _first(item.get("owner"), "model_owner"),
                "rollback_criteria": _first(item.get("rollback_criteria"), "state reaches rollback_needed"),
                "human_review": _first(item.get("human_review"), "review sampled failures before widening rollout"),
            }
        )
    if not result:
        result.append(
            {
                "id": "MODEL1",
                "name": "primary_model",
                "state": "normal",
                "quality_score": 1.0,
                "drift_score": 0.0,
                "owner": "model_owner",
                "rollback_criteria": "state reaches rollback_needed",
                "human_review": "review sampled failures before widening rollout",
            }
        )
    return sorted(result, key=lambda item: (_state_rank(item["state"]), item["name"].casefold()))


def _metric_thresholds(spec: dict[str, Any]) -> list[dict[str, str]]:
    rows = spec.get("metric_thresholds") or spec.get("quality_metrics")
    result: list[dict[str, str]] = []
    for index, row in enumerate(rows if isinstance(rows, list) else [], start=1):
        item = row if isinstance(row, dict) else {"name": row}
        result.append(
            {
                "id": f"MET{index}",
                "name": _first(item.get("name"), f"metric_{index}"),
                "threshold": _first(item.get("threshold"), item.get("target"), "maintain baseline"),
                "owner": _first(item.get("owner"), "model_owner"),
            }
        )
    if not result:
        result = [
            {"id": "MET1", "name": "quality_score", "threshold": ">= 0.90", "owner": "model_owner"},
            {"id": "MET2", "name": "drift_score", "threshold": "<= 0.20", "owner": "model_owner"},
        ]
    return sorted(result, key=lambda item: item["name"].casefold())


def _drift_response(models: list[dict[str, Any]]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for model in models:
        if model["state"] == "rollback_needed":
            action = "Rollback model or disable automated decisions until owner approval."
        elif model["state"] == "degraded":
            action = "Open remediation task and increase evaluation sampling."
        else:
            action = "Continue routine monitoring."
        result.append({"id": f"DRIFT{len(result) + 1}", "model": model["name"], "state": model["state"], "owner": model["owner"], "action": action})
    return result


def _owner_actions(models: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [{"id": f"ACT{index}", "owner": item["owner"], "action": f"{item['owner']} reviews {item['name']} state: {item['state']}."} for index, item in enumerate(models, start=1)]


def _render_model(item: dict[str, Any]) -> list[str]:
    return [f"### {item['id']}: {item['name']}", "", f"- State: {item['state']}", f"- Quality score: {item['quality_score']}", f"- Drift score: {item['drift_score']}", f"- Owner: {item['owner']}", f"- Rollback criteria: {item['rollback_criteria']}", f"- Human review: {item['human_review']}"]


def _render_metric(item: dict[str, str]) -> list[str]:
    return [f"### {item['id']}: {item['name']}", "", f"- Threshold: {item['threshold']}", f"- Owner: {item['owner']}"]


def _render_response(item: dict[str, str]) -> list[str]:
    return [f"### {item['id']}: {item['model']}", "", f"- State: {item['state']}", f"- Owner: {item['owner']}", f"- Action: {item['action']}"]


def _render_cadence(item: dict[str, Any]) -> list[str]:
    return [f"### {item['id']}", "", f"- Cadence: {item['cadence']}"]


def _render_text(item: str) -> list[str]:
    return [f"- {item}"]


def _render_evidence(item: dict[str, Any]) -> list[str]:
    return [f"### {item['id']}", "", f"- Type: {item['type']}", f"- Reference: {item['reference']}"]


def _extend(lines: list[str], title: str, items: list[Any], renderer: Any) -> None:
    lines.extend([f"## {title}", ""])
    if not items:
        lines.extend(["None.", ""])
        return
    for item in items:
        lines.extend(renderer(item))
        lines.append("")


def _state(quality: float, drift: float, explicit: Any) -> str:
    label = compact(explicit).lower()
    if label in {"normal", "degraded", "rollback_needed"}:
        return label
    if quality < 0.75 or drift > 0.35:
        return "rollback_needed"
    if quality < 0.9 or drift > 0.2:
        return "degraded"
    return "normal"


def _state_rank(value: str) -> int:
    return {"rollback_needed": 0, "degraded": 1, "normal": 2}.get(value, 3)


def _title(spec: dict[str, Any]) -> str:
    project = spec.get("project") if isinstance(spec.get("project"), dict) else {}
    return _first(project.get("title"), spec.get("title"), "Model Monitoring")


def _items(value: Any) -> list[str]:
    return sorted(dict.fromkeys(string_list(value)), key=str.casefold)


def _first(*values: Any) -> str:
    for value in values:
        result = compact(value)
        if result:
            return result
    return "Unknown"


def _number(value: Any, default: float) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default
