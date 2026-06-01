from __future__ import annotations

from max.spec.publisher_webhook_signature_rotation_plan import generate_publisher_webhook_signature_rotation_plan


def test_publisher_webhook_signature_rotation_plan_validates_destinations() -> None:
    plan = generate_publisher_webhook_signature_rotation_plan(
        [{"destination": "crm", "endpoint": "https://example.test/webhook", "owner": "pubops"}]
    )

    assert plan["summary"]["status"] == "ready"
    assert plan["blockers"] == []
    assert plan["preparation"]
    assert plan["verification"]


def test_publisher_webhook_signature_rotation_plan_renders_overlap_hours() -> None:
    plan = generate_publisher_webhook_signature_rotation_plan(
        [{"destination": "crm", "endpoint": "https://example.test/webhook", "owner": "pubops"}],
        overlap_hours=48,
    )

    assert plan["summary"]["overlap_hours"] == 48
    assert plan["rotation"][0]["dual_signing_overlap_hours"] == 48
    assert "48 hours" in " ".join(plan["preparation"])


def test_publisher_webhook_signature_rotation_plan_lists_blocked_destinations() -> None:
    plan = generate_publisher_webhook_signature_rotation_plan([{"destination": "crm"}, {"destination": "erp", "endpoint": "https://e.test", "owner": "ops"}])

    assert plan["summary"]["status"] == "blocked"
    assert plan["blockers"][0]["destination"] == "crm"
    assert plan["blockers"][0]["blockers"] == ["missing-owner", "missing-endpoint"]


def test_publisher_webhook_signature_rotation_plan_orders_rollout_waves() -> None:
    plan = generate_publisher_webhook_signature_rotation_plan(
        [
            {"destination": "zeta", "endpoint": "https://z.test", "owner": "ops", "wave": 2},
            {"destination": "alpha", "endpoint": "https://a.test", "owner": "ops", "wave": 1},
            {"destination": "beta", "endpoint": "https://b.test", "owner": "ops", "wave": 1},
        ]
    )

    assert [wave["wave"] for wave in plan["rotation"]] == [1, 2]
    assert plan["rotation"][0]["destinations"] == ["alpha", "beta"]
