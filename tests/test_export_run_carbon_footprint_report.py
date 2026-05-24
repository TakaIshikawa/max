from __future__ import annotations

from max.exports.run_carbon_footprint_report import generate_run_carbon_footprint_report


def test_run_carbon_footprint_report_totals_and_rows_are_deterministic() -> None:
    report = generate_run_carbon_footprint_report(
        {
            "high_emission_threshold_kg": 1.0,
            "records": [
                {
                    "id": "b",
                    "stage": "rank",
                    "provider": "openai",
                    "model": "large",
                    "profile": "batch",
                    "region": "us-east",
                    "energy_kwh": 2,
                    "request_count": 150,
                    "cache_hit_rate": 0.2,
                },
                {
                    "id": "a",
                    "stage": "embed",
                    "provider": "openai",
                    "model": "small",
                    "profile": "interactive",
                    "region": "eu-west",
                    "energy_kwh": 2,
                    "request_count": 10,
                    "cache_hit_rate": 0.7,
                },
                {
                    "id": "c",
                    "stage": "rank",
                    "provider": "anthropic",
                    "model": "medium",
                    "profile": "batch",
                    "region": "eu-west",
                    "kgco2e": 0.46,
                },
            ],
        }
    )

    assert report["summary"]["total_kgco2e"] == 1.68
    assert report["summary"]["over_threshold"] is True
    assert [(row["name"], row["kgco2e"]) for row in report["stage_rows"]] == [
        ("rank", 1.22),
        ("embed", 0.46),
    ]
    assert [row["name"] for row in report["model_provider_rows"]] == [
        "openai/large",
        "anthropic/medium",
        "openai/small",
    ]
    assert [row["record_id"] for row in report["carbon_drivers"]] == ["b", "a", "c"]
    assert {row["type"] for row in report["recommendations"]} >= {
        "cache",
        "batching",
        "lower_carbon_region",
        "emission_threshold",
    }


def test_run_carbon_footprint_report_warns_for_missing_factors() -> None:
    report = generate_run_carbon_footprint_report(
        {
            "records": [
                {
                    "stage": "infer",
                    "provider": "p",
                    "model": "m",
                    "profile": "nightly",
                    "region": "ap-mars",
                    "energy_kwh": 3,
                }
            ]
        },
        emission_factors={"eu-west": 0.2},
    )

    assert report["summary"]["total_kgco2e"] == 0.0
    assert report["summary"]["missing_emission_factor_count"] == 1
    assert report["warnings"] == ["Missing emission factor for region 'ap-mars' on record 1"]


def test_run_carbon_footprint_report_empty_input() -> None:
    report = generate_run_carbon_footprint_report({"records": []})

    assert report["summary"]["total_kgco2e"] == 0
    assert report["stage_rows"] == []
    assert report["carbon_drivers"] == []
    assert report["warnings"] == []
