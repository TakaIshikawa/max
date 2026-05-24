"""Run carbon footprint export report."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import Any

SCHEMA_VERSION = "max.exports.run_carbon_footprint_report.v1"
KIND = "max.exports.run_carbon_footprint_report"

DEFAULT_EMISSION_FACTORS = {
    "eu-west": 0.23,
    "us-east": 0.38,
    "us-west": 0.31,
}


def generate_run_carbon_footprint_report(
    payload: Mapping[str, Any] | Iterable[Mapping[str, Any]],
    *,
    emission_factors: Mapping[str, Any] | None = None,
    high_emission_threshold_kg: float | None = None,
) -> dict[str, Any]:
    factors = _factors(payload, emission_factors)
    records = _records(payload, factors)
    total_kg = round(sum(row["kgco2e"] for row in records), 6)
    threshold = _float(
        high_emission_threshold_kg
        if high_emission_threshold_kg is not None
        else (payload.get("high_emission_threshold_kg") if isinstance(payload, Mapping) else 0)
    )
    warnings = [warning for row in records for warning in row["warnings"]]
    stage_rows = _group(records, "stage", total_kg)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "record_count": len(records),
            "total_kgco2e": total_kg,
            "missing_region_count": sum(1 for row in records if row["missing_region"]),
            "missing_emission_factor_count": sum(
                1 for row in records if row["missing_emission_factor"]
            ),
            "high_emission_threshold_kg": threshold,
            "over_threshold": bool(threshold and total_kg > threshold),
        },
        "stage_rows": stage_rows,
        "model_provider_rows": _group(records, "model_provider", total_kg),
        "profile_rows": _group(records, "profile", total_kg),
        "carbon_drivers": _drivers(records, total_kg),
        "highest_impact_stages": stage_rows[:3],
        "warnings": sorted(dict.fromkeys(warnings), key=str.casefold),
        "recommendations": _recommendations(records, stage_rows, total_kg, threshold),
    }


def render_run_carbon_footprint_json(report: Mapping[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True) + "\n"


def _records(
    payload: Mapping[str, Any] | Iterable[Mapping[str, Any]], factors: dict[str, float]
) -> list[dict[str, Any]]:
    if isinstance(payload, Mapping):
        source = (
            payload.get("records")
            or payload.get("usage_records")
            or payload.get("costs")
            or payload.get("runs")
        )
    else:
        source = list(payload)
    rows = [
        _record(item, index, factors)
        for index, item in enumerate(source if isinstance(source, list) else [], start=1)
        if isinstance(item, Mapping)
    ]
    rows.sort(
        key=lambda row: (
            -row["kgco2e"],
            row["stage"],
            row["model_provider"],
            row["profile"],
            row["record_id"],
        )
    )
    return rows


def _record(item: Mapping[str, Any], index: int, factors: dict[str, float]) -> dict[str, Any]:
    stage = _text(item.get("stage") or item.get("pipeline_stage")) or "unknown-stage"
    provider = _text(item.get("provider") or item.get("model_provider")) or "unknown-provider"
    model = _text(item.get("model") or item.get("model_name")) or "unknown-model"
    profile = (
        _text(item.get("profile") or item.get("run_profile") or item.get("persona"))
        or "unknown-profile"
    )
    region = _region(item.get("region") or item.get("cloud_region"))
    energy_kwh = _float(item.get("energy_kwh", item.get("kwh")))
    direct_kg = item.get("kgco2e", item.get("co2e_kg", item.get("carbon_kgco2e")))
    missing_region = not region
    factor = _float(item.get("emission_factor_kg_per_kwh") or item.get("emission_factor"))
    missing_emission_factor = False
    warnings = []
    if direct_kg not in (None, ""):
        kgco2e = _float(direct_kg)
    else:
        if not factor:
            factor = factors.get(region, 0.0)
        missing_emission_factor = energy_kwh > 0 and factor <= 0
        kgco2e = round(energy_kwh * factor, 6)
    if missing_region:
        warnings.append(
            f"Missing region for record {index}; lower-carbon region guidance may be incomplete"
        )
    if missing_emission_factor:
        warnings.append(
            f"Missing emission factor for region '{region or 'unknown'}' on record {index}"
        )
    return {
        "record_id": _text(item.get("record_id") or item.get("run_id") or item.get("id"))
        or f"record-{index}",
        "stage": stage,
        "provider": provider,
        "model": model,
        "model_provider": f"{provider}/{model}",
        "profile": profile,
        "region": region or "unknown-region",
        "energy_kwh": energy_kwh,
        "kgco2e": kgco2e,
        "request_count": max(0, int(_float(item.get("request_count", item.get("requests"))))),
        "cache_hit_rate": _rate_value(item.get("cache_hit_rate")),
        "missing_region": missing_region,
        "missing_emission_factor": missing_emission_factor,
        "warnings": warnings,
    }


def _group(records: list[dict[str, Any]], field: str, total_kg: float) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        grouped[row[field]].append(row)
    rows = []
    for name, items in grouped.items():
        kg = round(sum(item["kgco2e"] for item in items), 6)
        rows.append(
            {
                "name": name,
                "kgco2e": kg,
                "energy_kwh": round(sum(item["energy_kwh"] for item in items), 6),
                "percentage": _percentage(kg, total_kg),
                "record_count": len(items),
            }
        )
    rows.sort(key=lambda row: (-row["kgco2e"], row["name"]))
    return rows


def _drivers(records: list[dict[str, Any]], total_kg: float) -> list[dict[str, Any]]:
    rows = [
        {
            "record_id": row["record_id"],
            "stage": row["stage"],
            "model_provider": row["model_provider"],
            "profile": row["profile"],
            "region": row["region"],
            "kgco2e": row["kgco2e"],
            "percentage": _percentage(row["kgco2e"], total_kg),
        }
        for row in records
    ]
    rows.sort(
        key=lambda row: (
            -row["kgco2e"],
            row["stage"],
            row["model_provider"],
            row["profile"],
            row["record_id"],
        )
    )
    return rows


def _recommendations(
    records: list[dict[str, Any]],
    stage_rows: list[dict[str, Any]],
    total_kg: float,
    threshold: float,
) -> list[dict[str, Any]]:
    rows = []
    if threshold and total_kg > threshold:
        rows.append(
            {
                "type": "emission_threshold",
                "action": "Prioritize the highest-carbon stages until the run falls below the configured threshold",
            }
        )
    low_cache = [row for row in records if row["cache_hit_rate"] < 0.5 and row["request_count"] > 0]
    if low_cache:
        rows.append(
            {
                "type": "cache",
                "action": "Increase prompt and embedding cache reuse for repeated requests",
            }
        )
    if any(row["request_count"] >= 100 for row in records):
        rows.append(
            {
                "type": "batching",
                "action": "Batch high-volume inference requests to reduce duplicate overhead",
            }
        )
    if any(row["missing_region"] or row["missing_emission_factor"] for row in records) or any(
        row["region"] in {"us-east", "unknown-region"} for row in records
    ):
        rows.append(
            {
                "type": "lower_carbon_region",
                "action": "Route flexible workloads to regions with known lower-carbon emission factors",
            }
        )
    if stage_rows:
        rows.append(
            {
                "type": "stage_focus",
                "stage": stage_rows[0]["name"],
                "action": "Review model choice and retry behavior in the highest-impact stage",
            }
        )
    return rows


def _factors(
    payload: Mapping[str, Any] | Iterable[Mapping[str, Any]], override: Mapping[str, Any] | None
) -> dict[str, float]:
    raw = (
        override
        or (payload.get("emission_factors") if isinstance(payload, Mapping) else None)
        or DEFAULT_EMISSION_FACTORS
    )
    return (
        {_region(key): _float(value) for key, value in raw.items()}
        if isinstance(raw, Mapping)
        else dict(DEFAULT_EMISSION_FACTORS)
    )


def _percentage(numerator: float, denominator: float) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _rate_value(value: Any) -> float:
    return min(1.0, max(0.0, _float(value)))


def _float(value: Any) -> float:
    try:
        return round(max(float(value or 0), 0.0), 6)
    except (TypeError, ValueError):
        return 0.0


def _region(value: Any) -> str:
    return _text(value).lower().replace("_", "-")


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
