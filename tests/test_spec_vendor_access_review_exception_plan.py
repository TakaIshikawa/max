from max.spec import generate_vendor_access_review_exception_plan


def test_vendor_access_review_plan_uses_custom_vendor_metadata():
    plan = generate_vendor_access_review_exception_plan(
        {"metadata": {"vendor_access_review_exception": {"vendor_access_records": [{"vendor": "Datadog", "system": "prod logs"}], "monitoring": ["access log review"]}}}
    )

    assert plan["vendor_access_records"][0]["name"] == "Datadog"
    assert plan["vendor_access_records"][0]["system"] == "prod logs"
    assert plan["monitoring"][0]["name"] == "access log review"


def test_vendor_access_review_plan_defaults_control_and_expiry_output():
    plan = generate_vendor_access_review_exception_plan({})

    assert "least-privilege review" in plan["compensating_controls"][0]["description"]
    assert "access logging" in plan["compensating_controls"][0]["description"]
    assert "expiry check" in plan["revocation_workflow"][0]["description"]
