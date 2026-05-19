"""Generate deterministic sandbox data seeding plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, evidence_references, markdown_header, string_list


SCHEMA_VERSION = "max-sandbox-data-seeding-plan/v1"
KIND = "max.sandbox_data_seeding_plan"


def generate_sandbox_data_seeding_plan(spec_like: Any) -> dict[str, Any]:
    """Return stable guidance for repeatable sandbox data seeding."""
    spec = spec_like if isinstance(spec_like, dict) else {}
    datasets = _datasets(spec.get("datasets") or spec.get("seed_datasets"))
    privacy = _privacy_controls(spec, datasets)
    refresh = _first(spec.get("refresh_cadence"), "weekly")
    reset = _items(spec.get("reset_steps") or ["snapshot baseline", "truncate mutable tables", "rerun seed job"])
    validation = _items(spec.get("validation_checks") or ["record counts match manifest", "masked fields pass scan"])

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "title": _title(spec),
            "dataset_count": len(datasets),
            "masked_dataset_count": sum(1 for item in datasets if item["dataset_type"] == "masked"),
            "synthetic_dataset_count": sum(1 for item in datasets if item["dataset_type"] == "synthetic"),
            "refresh_cadence": refresh,
            "owner": _first(spec.get("owner"), "sandbox_owner"),
        },
        "seed_datasets": datasets,
        "privacy_controls": privacy,
        "refresh_cadence": refresh,
        "reset_procedure": reset,
        "validation_checks": validation,
        "owners": _owners(spec, datasets),
        "evidence": evidence_references(spec),
    }


def render_sandbox_data_seeding_plan_markdown(plan: dict[str, Any]) -> str:
    """Render a sandbox data seeding plan as deterministic Markdown."""
    lines = markdown_header(plan, "Sandbox Data Seeding Plan")
    _extend(lines, "Setup", plan.get("seed_datasets") or [], _render_dataset)
    _extend(lines, "Refresh", [{"id": "REF1", "cadence": plan.get("refresh_cadence")}], _render_refresh)
    _extend(lines, "Reset", plan.get("reset_procedure") or [], _render_text)
    _extend(lines, "Privacy", plan.get("privacy_controls") or [], _render_control)
    _extend(lines, "Acceptance", plan.get("validation_checks") or [], _render_text)
    _extend(lines, "Evidence", plan.get("evidence") or [], _render_evidence)
    return "\n".join(lines).rstrip() + "\n"


def _datasets(value: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for index, row in enumerate(value if isinstance(value, list) else [], start=1):
        item = row if isinstance(row, dict) else {"name": row}
        dataset_type = _dataset_type(item)
        result.append(
            {
                "id": f"DATA{index}",
                "name": _first(item.get("name"), f"dataset_{index}"),
                "dataset_type": dataset_type,
                "source": _first(item.get("source"), "seed fixture"),
                "masking_required": dataset_type == "masked" or _truthy(item.get("masking_required")),
                "owner": _first(item.get("owner"), "sandbox_owner"),
                "refresh_cadence": _first(item.get("refresh_cadence"), "inherit plan cadence"),
            }
        )
    if not result:
        result.append(
            {
                "id": "DATA1",
                "name": "representative_fixture",
                "dataset_type": "synthetic",
                "source": "generated fixture",
                "masking_required": False,
                "owner": "sandbox_owner",
                "refresh_cadence": "inherit plan cadence",
            }
        )
    return sorted(result, key=lambda item: (item["dataset_type"], item["name"].casefold()))


def _privacy_controls(spec: dict[str, Any], datasets: list[dict[str, Any]]) -> list[dict[str, str]]:
    explicit = _items(spec.get("masking_requirements") or spec.get("privacy_controls"))
    controls = explicit or ["exclude production secrets", "scan seeded data before publish"]
    if any(item["masking_required"] for item in datasets):
        controls.append("mask direct identifiers before sandbox load")
    if any(item["dataset_type"] == "synthetic" for item in datasets):
        controls.append("document synthetic data generation rules")
    unique = sorted(dict.fromkeys(controls), key=str.casefold)
    return [{"id": f"PRIV{index}", "control": value} for index, value in enumerate(unique, start=1)]


def _owners(spec: dict[str, Any], datasets: list[dict[str, Any]]) -> list[dict[str, str]]:
    owners = spec.get("owners") if isinstance(spec.get("owners"), dict) else {}
    rows = [{"role": compact(role), "owner": compact(owner)} for role, owner in sorted(owners.items()) if compact(role)]
    if not rows:
        rows.append({"role": "sandbox_owner", "owner": _first(spec.get("owner"), "Unassigned")})
    seen = {row["role"] for row in rows}
    for item in datasets:
        owner = compact(item.get("owner"))
        if owner and owner not in seen:
            rows.append({"role": owner, "owner": owner})
            seen.add(owner)
    return rows


def _render_dataset(item: dict[str, Any]) -> list[str]:
    return [f"### {item['id']}: {item['name']}", "", f"- Type: {item['dataset_type']}", f"- Source: {item['source']}", f"- Masking required: {str(item['masking_required']).lower()}", f"- Owner: {item['owner']}", f"- Refresh cadence: {item['refresh_cadence']}"]


def _render_refresh(item: dict[str, Any]) -> list[str]:
    return [f"### {item['id']}", "", f"- Cadence: {item['cadence']}"]


def _render_control(item: dict[str, Any]) -> list[str]:
    return [f"### {item['id']}", "", f"- Control: {item['control']}"]


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


def _dataset_type(item: dict[str, Any]) -> str:
    label = compact(item.get("dataset_type") or item.get("type")).lower()
    if label in {"masked", "synthetic", "fixture"}:
        return label
    if _truthy(item.get("masking_required")):
        return "masked"
    return "synthetic"


def _title(spec: dict[str, Any]) -> str:
    project = spec.get("project") if isinstance(spec.get("project"), dict) else {}
    return _first(project.get("title"), spec.get("title"), "Sandbox Data")


def _items(value: Any) -> list[str]:
    return sorted(dict.fromkeys(string_list(value)), key=str.casefold)


def _first(*values: Any) -> str:
    for value in values:
        result = compact(value)
        if result:
            return result
    return "Unknown"


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return compact(value).lower() in {"true", "yes", "required", "masked"}
