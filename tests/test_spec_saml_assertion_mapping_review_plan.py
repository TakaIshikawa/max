from __future__ import annotations

from max.spec import generate_saml_assertion_mapping_review_plan


def test_saml_assertion_mapping_review_plan_covers_mapping_readiness() -> None:
    plan = generate_saml_assertion_mapping_review_plan(
        {
            "metadata": {
                "saml_assertion_mapping_review": {
                    "identity_providers": [{"idp": "Okta enterprise tenant", "customer": "Acme"}],
                    "mappings": [{"attribute": "email", "claim": "Email", "target_field": "user.email"}],
                    "required_claims": ["NameID"],
                    "test_users": [{"email": "admin@example.com", "role": "admin"}],
                    "rollback": ["restore previous SSO app"],
                    "customer_coordination": ["customer IdP admin sign-off"],
                    "approvals": ["security approval"],
                }
            }
        }
    )

    assert plan["attribute_mappings"][0]["name"] == "email"
    assert plan["validation_warnings"] == []
    assert set(plan) >= {"identity_provider_scope", "required_claims", "test_users", "rollback", "customer_coordination", "approval_evidence"}


def test_saml_assertion_mapping_review_plan_warns_when_mappings_missing() -> None:
    plan = generate_saml_assertion_mapping_review_plan({})

    assert plan["attribute_mappings"][0]["status"] == "missing"
    assert plan["validation_warnings"][0]["name"] == "SAML assertion mappings required"
