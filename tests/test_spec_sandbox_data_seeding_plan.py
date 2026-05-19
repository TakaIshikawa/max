from __future__ import annotations

from max.spec.sandbox_data_seeding_plan import (
    generate_sandbox_data_seeding_plan,
    render_sandbox_data_seeding_plan_markdown,
)


def test_sandbox_data_seeding_handles_masked_and_synthetic_datasets() -> None:
    plan = generate_sandbox_data_seeding_plan(
        {
            "project": {"title": "Partner Sandbox"},
            "datasets": [
                {"name": "users", "type": "masked", "source": "production export", "owner": "data"},
                {"name": "orders", "type": "synthetic", "source": "factory", "owner": "qa"},
            ],
            "refresh_cadence": "daily",
        }
    )

    assert [row["name"] for row in plan["seed_datasets"]] == ["users", "orders"]
    assert plan["seed_datasets"][0]["masking_required"] is True
    assert plan["summary"]["masked_dataset_count"] == 1
    assert plan["summary"]["synthetic_dataset_count"] == 1
    assert "mask direct identifiers before sandbox load" in [row["control"] for row in plan["privacy_controls"]]


def test_sandbox_data_seeding_defaults_missing_owner() -> None:
    plan = generate_sandbox_data_seeding_plan({"datasets": [{"name": "accounts", "type": "synthetic"}]})

    assert plan["summary"]["owner"] == "sandbox_owner"
    assert plan["seed_datasets"][0]["owner"] == "sandbox_owner"
    assert plan["owners"][0] == {"role": "sandbox_owner", "owner": "Unassigned"}


def test_sandbox_data_seeding_markdown_has_stable_order_and_sections() -> None:
    plan = generate_sandbox_data_seeding_plan(
        {
            "project": {"title": "Partner Sandbox"},
            "datasets": [
                {"name": "zeta", "type": "synthetic"},
                {"name": "alpha", "type": "synthetic"},
            ],
            "reset_steps": ["reset database", "rerun factories"],
            "validation_checks": ["login fixture works"],
            "evidence": {"source_idea_ids": ["seed-1"]},
        }
    )

    markdown = render_sandbox_data_seeding_plan_markdown(plan)

    assert [row["name"] for row in plan["seed_datasets"]] == ["alpha", "zeta"]
    assert markdown.startswith("# Partner Sandbox Sandbox Data Seeding Plan")
    assert "## Setup" in markdown
    assert "### DATA2: alpha" in markdown
    assert "## Refresh" in markdown
    assert "## Reset" in markdown
    assert "## Privacy" in markdown
    assert "## Acceptance" in markdown
    assert "source_idea:seed-1" in markdown
