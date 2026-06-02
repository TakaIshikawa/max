from __future__ import annotations

from max.spec import generate_consent_withdrawal_backfill_plan
from max.spec.consent_withdrawal_backfill_plan import render_consent_withdrawal_backfill_plan_markdown


def test_consent_withdrawal_backfill_plan_sections_and_defaults() -> None:
    plan = generate_consent_withdrawal_backfill_plan({})
    markdown = render_consent_withdrawal_backfill_plan_markdown(plan)

    assert "Inventory downstream processors" in plan["downstream_processors"][0]
    assert "pilot batch" in plan["backfill_batches"][0]
    for heading in ("## Scope", "## Downstream Processors", "## Execution Batches", "## Verification", "## Notifications", "## Rollback"):
        assert heading in markdown
    assert callable(generate_consent_withdrawal_backfill_plan)
