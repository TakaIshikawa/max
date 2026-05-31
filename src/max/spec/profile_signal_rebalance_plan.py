"""Generate deterministic profile signal rebalance plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, context, number, summary

SCHEMA_VERSION = "max.spec.profile_signal_rebalance_plan.v1"
KIND = "max.spec.profile_signal_rebalance_plan"
EXPECTED_ROLES = ("problem", "solution", "market")


def generate_profile_signal_rebalance_plan(spec_like: Any) -> dict[str, Any]:
    spec = spec_like if isinstance(spec_like, dict) else {}
    ctx = context(spec)
    hints = _hints(spec)
    profiles = _profiles(hints.get("profiles") or spec.get("profiles"))
    unknown = [role for profile in profiles for role in profile["unknown_roles"]]

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(ctx, profile_count=len(profiles), imbalanced_profile_count=sum(1 for item in profiles if item["status"] != "balanced"), unknown_role_count=len(unknown)),
        "profile_role_balance": profiles,
        "allocation_adjustments": _allocation_adjustments(profiles),
        "monitoring_checks": _monitoring_checks(),
        "success_criteria": _success_criteria(),
        "evidence_references": ctx["evidence_references"],
    }


def _profiles(value: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(value if isinstance(value, list) else [], start=1):
        if not isinstance(item, dict):
            continue
        profile = compact(item.get("profile") or item.get("name")) or f"profile_{index}"
        counts = {role: 0 for role in EXPECTED_ROLES}
        unknown: list[str] = []
        signals = item.get("signals") if isinstance(item.get("signals"), list) else []
        role_counts = item.get("role_counts") if isinstance(item.get("role_counts"), dict) else {}
        for role, count in role_counts.items():
            normalized = compact(role).casefold()
            if normalized in counts:
                counts[normalized] += int(number(count) or 0)
            elif normalized:
                unknown.append(normalized)
        for signal in signals:
            if not isinstance(signal, dict):
                continue
            role = compact(signal.get("role") or signal.get("signal_role")).casefold()
            if role in counts:
                counts[role] += 1
            elif role:
                unknown.append(role)
        missing = [role for role in EXPECTED_ROLES if counts[role] == 0]
        total = sum(counts.values())
        overrepresented = [role for role in EXPECTED_ROLES if total and counts[role] / total >= 0.6 and counts[role] >= 2]
        rows.append(
            {
                "id": f"PSR{index}",
                "profile": profile,
                "role_counts": counts,
                "missing_roles": missing,
                "overrepresented_roles": overrepresented,
                "unknown_roles": sorted(set(unknown), key=str.casefold),
                "status": "balanced" if not missing and not overrepresented and not unknown else "rebalance_needed",
            }
        )
    return sorted(rows, key=lambda row: (0 if row["status"] == "rebalance_needed" else 1, row["profile"].casefold()))


def _allocation_adjustments(profiles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    adjustments: list[dict[str, Any]] = []
    for profile in profiles:
        for role in profile["missing_roles"]:
            adjustments.append({"id": f"PSA{len(adjustments) + 1}", "profile": profile["profile"], "role": role, "action": f"Increase {role} source allocation until profile has valid coverage."})
        for role in profile["overrepresented_roles"]:
            adjustments.append({"id": f"PSA{len(adjustments) + 1}", "profile": profile["profile"], "role": role, "action": f"Reduce {role} intake share and redirect collection to missing roles."})
        for role in profile["unknown_roles"]:
            adjustments.append({"id": f"PSA{len(adjustments) + 1}", "profile": profile["profile"], "role": role, "action": "Review unknown signal role; do not count it toward balance coverage."})
    return adjustments


def _monitoring_checks() -> list[dict[str, str]]:
    return [
        {"id": "PSM1", "name": "role_coverage", "target": "each profile has problem, solution, and market signals"},
        {"id": "PSM2", "name": "source_mix_drift", "target": "no role exceeds agreed profile share"},
        {"id": "PSM3", "name": "unknown_role_queue", "target": "unknown roles reviewed or mapped explicitly"},
    ]


def _success_criteria() -> list[dict[str, str]]:
    return [
        {"id": "PSC1", "name": "balanced_profiles", "target": "100% active profiles balanced"},
        {"id": "PSC2", "name": "unknown_role_count", "target": "0 unreviewed unknown roles"},
    ]


def _hints(spec: dict[str, Any]) -> dict[str, Any]:
    metadata = spec.get("metadata") if isinstance(spec.get("metadata"), dict) else {}
    hints = metadata.get("profile_signal_rebalance")
    return hints if isinstance(hints, dict) else {}
