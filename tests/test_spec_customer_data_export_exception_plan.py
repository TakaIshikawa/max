from max.spec import generate_customer_data_export_exception_plan


def test_customer_data_export_exception_plan_normalizes_customer_scope():
    plan = generate_customer_data_export_exception_plan(
        {"metadata": {"customer_data_export_exception": {"export_scope": [{"customer": "Acme", "destination": "SFTP"}], "data_categories": ["usage logs"]}}}
    )

    assert plan["export_scope"][0]["name"] == "Acme"
    assert plan["export_scope"][0]["destination"] == "SFTP"
    assert plan["data_classification"][0]["name"] == "usage logs"


def test_customer_data_export_exception_plan_defaults_secure_transfer_and_retention():
    plan = generate_customer_data_export_exception_plan({})

    assert "encrypted transfer" in plan["secure_transfer_controls"][0]["description"]
    assert "deletion confirmation" in plan["retention_follow_up"][0]["description"]
