"""Generate deterministic evidence chain repair plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, context, number, string_list, summary

SCHEMA_VERSION = "max.spec.evidence_chain_repair_plan.v1"
KIND = "max.spec.evidence_chain_repair_plan"


def generate_evidence_chain_repair_plan(spec_like: Any) -> dict[str, Any]:
    """Return an operational plan for repairing broken evidence trace links."""
    spec = spec_like if isinstance(spec_like, dict) else {}
    ctx = context(spec)
    hints = _hints(spec)
    broken_links = _broken_links(hints.get("broken_chains") or hints.get("broken_links") or spec.get("broken_chains"))
    affected_specs = _affected_specs(broken_links)
    missing_root_signals = [item for item in broken_links if item["missing_link_type"] == "root_signal"]
    severity = _severity(len(affected_specs), len(missing_root_signals), broken_links)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(
            ctx,
            broken_link_count=len(broken_links),
            affected_spec_count=len(affected_specs),
            missing_root_signal_count=len(missing_root_signals),
            severity=severity,
        ),
        "detection_inputs": _detection_inputs(broken_links),
        "broken_chain_inventory": broken_links,
        "repair_strategies": _repair_strategies(broken_links),
        "validation_queries": _validation_queries(broken_links),
        "acceptance_metrics": _acceptance_metrics(severity),
        "evidence_references": ctx["evidence_references"],
    }


def _broken_links(value: Any) -> list[dict[str, Any]]:
    raw = value if isinstance(value, list) else []
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            continue
        missing_type = _missing_type(item)
        affected = sorted(set(string_list(item.get("affected_specs") or item.get("spec_ids") or item.get("tact_spec_ids"))), key=str.casefold)
        rows.append(
            {
                "id": compact(item.get("id")) or f"BR{index}",
                "missing_link_type": missing_type,
                "from_type": compact(item.get("from_type")) or compact(item.get("source_type")) or "unknown",
                "from_id": compact(item.get("from_id")) or compact(item.get("source_id")) or "unknown",
                "to_type": compact(item.get("to_type")) or compact(item.get("target_type")) or _target_type(missing_type),
                "to_id": compact(item.get("to_id")) or compact(item.get("target_id")) or "missing",
                "affected_specs": affected,
                "affected_spec_count": int(number(item.get("affected_spec_count")) or len(affected)),
                "missing_root_signal": missing_type == "root_signal" or bool(item.get("missing_root_signal")),
                "severity": compact(item.get("severity")) or "unclassified",
            }
        )
    return sorted(rows, key=lambda row: (_rank(row), row["missing_link_type"], row["from_type"], row["from_id"], row["to_id"]))


def _detection_inputs(broken_links: list[dict[str, Any]]) -> list[dict[str, Any]]:
    base = [
        ("DI1", "artifact_graph_export", "Export signals, insights, buildable units, evaluations, and tact specs with upstream and downstream ids."),
        ("DI2", "orphan_report", "Load evidence-chain orphan and missing-reference report rows."),
        ("DI3", "spec_inventory", "Load current tact spec inventory with profile and approval state."),
    ]
    if not broken_links:
        base.append(("DI4", "empty_inventory_review", "Confirm no broken-chain inventory was supplied before closing the repair cycle."))
    return [{"id": item_id, "type": item_type, "description": description, "required": True} for item_id, item_type, description in base]


def _repair_strategies(broken_links: list[dict[str, Any]]) -> list[dict[str, Any]]:
    link_types = sorted({item["missing_link_type"] for item in broken_links}, key=str.casefold) or ["no_broken_links"]
    actions = {
        "root_signal": "Recover or recreate missing source signal, then reattach dependent insights and tact specs.",
        "signal_to_insight": "Rebuild insight upstream_ids from validated signal ids and refresh downstream signal references.",
        "insight_to_unit": "Map each insight to the owning buildable unit and regenerate unit evidence references.",
        "unit_to_evaluation": "Attach evaluation results to buildable units and rerun missing evaluation checks.",
        "evaluation_to_spec": "Link evaluations to tact specs and refresh approval evidence.",
        "no_broken_links": "Keep graph read-only and run validation queries to confirm trace completeness.",
    }
    return [
        {
            "id": f"RS{index}",
            "missing_link_type": link_type,
            "owner": _owner(link_type),
            "action": actions.get(link_type, "Inspect source and target artifacts, repair ids, and record a manual evidence note."),
            "affected_spec_count": sum(item["affected_spec_count"] for item in broken_links if item["missing_link_type"] == link_type),
        }
        for index, link_type in enumerate(link_types, start=1)
    ]


def _validation_queries(broken_links: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"id": "VQ1", "name": "missing_upstream_references", "query": "artifacts where upstream_ids contain ids absent from artifact inventory", "expected_result": 0},
        {"id": "VQ2", "name": "terminal_tact_spec_orphans", "query": "approved tact specs without signal, insight, buildable unit, and evaluation ancestors", "expected_result": 0},
        {"id": "VQ3", "name": "repaired_artifact_sample", "query": "sample repaired chains by severity and profile for reviewer signoff", "expected_result": "all sampled chains accepted"},
        {"id": "VQ4", "name": "input_inventory_delta", "query": f"broken-chain inventory count changed from {len(broken_links)} to zero", "expected_result": 0},
    ]


def _acceptance_metrics(severity: str) -> list[dict[str, Any]]:
    sample_rate = "100%" if severity in {"critical", "high"} else "25%"
    return [
        {"id": "AM1", "name": "missing_reference_count", "target": 0},
        {"id": "AM2", "name": "terminal_orphan_count", "target": 0},
        {"id": "AM3", "name": "root_signal_recovery_rate", "target": "100% recovered or explicitly waived"},
        {"id": "AM4", "name": "review_sample_rate", "target": sample_rate},
    ]


def _severity(affected_spec_count: int, missing_root_signal_count: int, broken_links: list[dict[str, Any]]) -> str:
    if missing_root_signal_count >= 2 or affected_spec_count >= 10:
        return "critical"
    if missing_root_signal_count == 1 or affected_spec_count >= 3:
        return "high"
    if broken_links:
        return "medium"
    return "low"


def _affected_specs(broken_links: list[dict[str, Any]]) -> list[str]:
    specs: set[str] = set()
    for item in broken_links:
        specs.update(item["affected_specs"])
    return sorted(specs, key=str.casefold)


def _rank(row: dict[str, Any]) -> tuple[int, int]:
    severity_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(compact(row.get("severity")).lower(), 4)
    return severity_rank, -int(row.get("affected_spec_count") or 0)


def _missing_type(item: dict[str, Any]) -> str:
    explicit = compact(item.get("missing_link_type") or item.get("link_type")).lower()
    if explicit:
        return explicit
    from_type = compact(item.get("from_type") or item.get("source_type")).lower()
    to_type = compact(item.get("to_type") or item.get("target_type")).lower()
    if item.get("missing_root_signal") or to_type == "signal":
        return "root_signal"
    return f"{from_type or 'unknown'}_to_{to_type or 'unknown'}"


def _target_type(missing_type: str) -> str:
    return {"root_signal": "signal", "signal_to_insight": "insight", "insight_to_unit": "buildable_unit", "unit_to_evaluation": "evaluation", "evaluation_to_spec": "tact_spec"}.get(missing_type, "unknown")


def _owner(link_type: str) -> str:
    if link_type in {"root_signal", "signal_to_insight"}:
        return "research_owner"
    if link_type in {"unit_to_evaluation", "evaluation_to_spec"}:
        return "evaluation_owner"
    return "spec_owner"


def _hints(spec: dict[str, Any]) -> dict[str, Any]:
    metadata = spec.get("metadata") if isinstance(spec.get("metadata"), dict) else {}
    hints = metadata.get("evidence_chain_repair")
    return hints if isinstance(hints, dict) else {}
