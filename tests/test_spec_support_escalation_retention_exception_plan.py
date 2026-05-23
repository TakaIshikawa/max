from max.spec import generate_support_escalation_retention_exception_plan


def test_support_escalation_retention_plan_uses_retained_records():
    plan = generate_support_escalation_retention_exception_plan(
        {"metadata": {"support_escalation_retention_exception": {"retained_records": [{"ticket": "SUP-7", "customer": "Acme"}]}}}
    )

    assert plan["retained_records"][0]["name"] == "SUP-7"
    assert plan["retained_records"][0]["customer"] == "Acme"


def test_support_escalation_retention_plan_defaults_duration_and_privacy_review():
    plan = generate_support_escalation_retention_exception_plan({})

    assert "90-day time-boxed retention period" in plan["retention_duration"][0]["description"]
    assert "privacy owner review" in plan["privacy_controls"][0]["description"]
