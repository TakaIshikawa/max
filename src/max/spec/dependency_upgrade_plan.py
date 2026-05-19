"""Generate deterministic dependency upgrade plans for TactSpec previews."""

from __future__ import annotations

from typing import Any, Mapping

from max.spec._launch_governance import CSV_COLUMNS, base_context, item, render_csv, render_markdown, summary

DEPENDENCY_UPGRADE_PLAN_SCHEMA_VERSION = "max-dependency-upgrade-plan/v1"
KIND = "max.dependency_upgrade_plan"
DEPENDENCY_UPGRADE_PLAN_CSV_COLUMNS = CSV_COLUMNS
SECTIONS = ("dependency_list", "upgrade_rationale", "affected_surfaces", "compatibility_checks", "test_matrix", "rollout_sequence", "rollback", "evidence")


def generate_dependency_upgrade_plan(tact_spec: dict[str, Any]) -> dict[str, Any]:
    context = base_context(tact_spec)
    upgrade = _mapping(context["spec"].get("dependency_upgrade") or context["spec"].get("dependency"))
    dependencies = _list(upgrade.get("dependencies")) or [_text(upgrade.get("package")) or "primary dependency"]
    reason = (_text(upgrade.get("reason")) or "routine maintenance").lower()
    security_driven = "security" in reason or "cve" in reason or _bool(upgrade.get("security"))
    services = _list(upgrade.get("affected_services")) or [context["workflow"]]

    return {
        "schema_version": DEPENDENCY_UPGRADE_PLAN_SCHEMA_VERSION,
        "kind": KIND,
        "source": context["source"],
        "summary": summary(context, dependency_count=len(dependencies), security_driven=security_driven),
        "dependency_list": [
            item("DEP1", "dependency_inventory", f"Upgrade dependencies: {', '.join(dependencies)}.", "engineering_owner", severity="high" if security_driven else "medium", evidence=["dependency_upgrade.dependencies"])
        ],
        "upgrade_rationale": [
            item("WHY1", "upgrade_reason", f"Upgrade rationale: {reason}.", "engineering_owner", severity="high" if security_driven else "low", action="Prioritize security-driven upgrade handling." if security_driven else "Track through routine release planning.", evidence=["dependency_upgrade.reason"])
        ],
        "affected_surfaces": [
            item("SRF1", "service_inventory", f"Affected services and surfaces: {', '.join(services)}.", "release_owner", evidence=["dependency_upgrade.affected_services"])
        ],
        "compatibility_checks": [
            item("CMP1", "compatibility_review", "Check APIs, transitive dependencies, runtime versions, configs, and generated artifacts.", "engineering_owner", action="Block rollout on incompatible contracts.", evidence=["solution.technical_approach"])
        ],
        "test_matrix": [
            item("TST1", "upgrade_tests", "Run unit, integration, smoke, dependency audit, and service-specific regression tests.", "qa_owner", evidence=["execution.validation_plan"])
        ],
        "rollout_sequence": [
            item("ROL1", "progressive_rollout", "Roll out through dev, staging, canary, then production with monitoring gates.", "release_owner", timing="release window", evidence=["project.workflow_context"])
        ],
        "rollback": [
            item("RB1", "version_pin", "Keep previous lockfile, artifact, and deploy version ready for rollback.", "release_owner", severity="high", evidence=["execution.risks"])
        ],
        "evidence": [
            item("EV1", "upgrade_evidence", "Attach dependency diff, rationale, compatibility notes, test matrix results, rollout logs, and rollback proof.", "release_manager", action="Required for closure.", evidence=["evidence.references"])
        ],
        "evidence_references": context["evidence_references"],
    }


def render_dependency_upgrade_plan_markdown(plan: dict[str, Any]) -> str:
    return render_markdown(plan, "Dependency Upgrade Plan", SECTIONS)


def render_dependency_upgrade_plan_csv(plan: dict[str, Any]) -> str:
    return render_csv(plan, SECTIONS)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _list(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    text = _text(value)
    return [text] if text else []


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y"}
