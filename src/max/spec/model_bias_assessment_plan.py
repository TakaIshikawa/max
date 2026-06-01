"""Generate deterministic model bias assessment plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, context, string_list, summary


SCHEMA_VERSION = "max.spec.model_bias_assessment_plan.v1"
KIND = "max.spec.model_bias_assessment_plan"


def generate_model_bias_assessment_plan(spec_like: Any) -> dict[str, Any]:
    spec = spec_like if isinstance(spec_like, dict) else {}
    ctx = context(spec)
    hints = _hints(spec)
    model = _required(hints, "model_name", "model name")
    users = _required_list(hints.get("target_users"), "target users")
    attributes = _required_list(hints.get("protected_attributes"), "protected attributes")
    datasets = _required_records(hints.get("evaluation_datasets"), "evaluation datasets", ("name", "dataset"))
    metrics = _required_records(hints.get("metrics"), "metrics", ("name", "metric"))
    owners = _required_list(hints.get("owners"), "owners")
    deadline = compact(hints.get("decision_deadline")) or "decision deadline not set"
    refs = [item["id"] for item in ctx["evidence_references"]]

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(
            ctx,
            model_name=model,
            target_user_count=len(users),
            protected_attribute_count=len(attributes),
            dataset_count=len(datasets),
            metric_count=len(metrics),
            decision_deadline=deadline,
        ),
        "dataset_audit": [
            _row(
                "MBA",
                index,
                dataset["name"],
                owners[(index - 1) % len(owners)],
                f"Audit {dataset['name']} coverage for {model} target users and protected attributes.",
                refs,
                target_users=users,
                protected_attributes=attributes,
                source=dataset.get("source"),
            )
            for index, dataset in enumerate(datasets, 1)
        ],
        "metric_thresholds": [
            _row(
                "MBT",
                index,
                metric["name"],
                owners[(index - 1) % len(owners)],
                f"Set bias assessment threshold for {metric['name']}.",
                refs,
                metric=metric.get("metric") or metric["name"],
                threshold=metric.get("threshold") or "threshold required before approval",
            )
            for index, metric in enumerate(metrics, 1)
        ],
        "subgroup_evaluation": [
            _row(
                "MBS",
                index,
                f"{attribute} subgroup evaluation",
                owners[(index - 1) % len(owners)],
                f"Evaluate {model} outcomes across {attribute} subgroups for {', '.join(users)}.",
                refs,
                protected_attribute=attribute,
                datasets=[dataset["name"] for dataset in datasets],
                metrics=[metric["name"] for metric in metrics],
            )
            for index, attribute in enumerate(attributes, 1)
        ],
        "mitigation_workflow": [
            _row(
                "MBM",
                1,
                "Bias finding mitigation workflow",
                owners[0],
                "Document root cause, mitigation option, re-evaluation evidence, and release recommendation.",
                refs,
                status="required",
                decision_deadline=deadline,
            )
        ],
        "approval_gates": [
            _row(
                "MBG",
                index,
                gate,
                owners[(index - 1) % len(owners)],
                f"Complete approval gate before {deadline}: {gate}.",
                refs,
                deadline=deadline,
            )
            for index, gate in enumerate(
                ["dataset audit approved", "metric thresholds met", "subgroup evaluation signed off"], 1
            )
        ],
        "evidence_references": ctx["evidence_references"],
    }


def _hints(spec: dict[str, Any]) -> dict[str, Any]:
    metadata = spec.get("metadata") if isinstance(spec.get("metadata"), dict) else {}
    value = metadata.get("model_bias_assessment")
    return value if isinstance(value, dict) else {}


def _required(hints: dict[str, Any], key: str, label: str) -> str:
    value = compact(hints.get(key))
    if not value or hints.get(key) in ([], {}):
        raise ValueError(f"model_bias_assessment requires {label}")
    return value


def _required_list(value: Any, label: str) -> list[str]:
    values = sorted(dict.fromkeys(item for item in string_list(value) if item), key=str.casefold)
    if not values:
        raise ValueError(f"model_bias_assessment requires {label}")
    return values


def _required_records(value: Any, label: str, name_keys: tuple[str, ...]) -> list[dict[str, str]]:
    raw = value if isinstance(value, list) else []
    records: list[dict[str, str]] = []
    for item in raw:
        record = item if isinstance(item, dict) else {"name": item}
        name = next((compact(record.get(key)) for key in name_keys if compact(record.get(key))), "")
        if name:
            records.append(
                {
                    "name": name,
                    "metric": compact(record.get("metric")),
                    "threshold": compact(record.get("threshold")),
                    "source": compact(record.get("source")),
                }
            )
    result = sorted({record["name"].casefold(): record for record in records}.values(), key=lambda item: item["name"].casefold())
    if not result:
        raise ValueError(f"model_bias_assessment requires {label}")
    return result


def _row(prefix: str, index: int, name: str, owner: str, description: str, refs: list[str], **extra: Any) -> dict[str, Any]:
    data = {"id": f"{prefix}{index}", "name": name, "owner": owner, "description": description, "evidence_reference_ids": refs}
    data.update({key: value for key, value in extra.items() if value not in ("", None, [])})
    return data
