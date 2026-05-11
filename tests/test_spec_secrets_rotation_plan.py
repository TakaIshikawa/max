from __future__ import annotations

import csv
import io

from max.spec.secrets_rotation_plan import KIND, SECRETS_ROTATION_PLAN_SCHEMA_VERSION, generate_secrets_rotation_plan, render_secrets_rotation_plan_csv, render_secrets_rotation_plan_markdown


def test_secrets_rotation_plan_identifies_secret_classes_and_sections() -> None:
    spec = {"schema_version": "tact-spec-preview/v1", "kind": "tact.project_spec", "source": {"idea_id": "secret-1"}, "project": {"title": "Integration Runner", "workflow_context": "Slack webhook automation"}, "solution": {"suggested_stack": {"database": "Postgres", "ai": "OpenAI", "messaging": "Slack", "cloud": "AWS"}, "technical_approach": "GitHub Actions deploys API keys, database credentials, webhook secrets, and cloud credentials."}}
    plan = generate_secrets_rotation_plan(spec)
    names = {item["name"] for item in plan["secret_classes"]}
    assert plan["schema_version"] == SECRETS_ROTATION_PLAN_SCHEMA_VERSION
    assert plan["kind"] == KIND
    assert {"api_keys", "database_credentials", "webhook_secrets", "cloud_provider_credentials", "ci_cd_secrets"} <= names
    assert plan["validation_steps"]
    assert plan["rollback_handling"]
    assert plan["evidence_requirements"]
    assert "# Integration Runner Secrets Rotation Plan" in render_secrets_rotation_plan_markdown(plan)
    rows = list(csv.DictReader(io.StringIO(render_secrets_rotation_plan_csv(plan))))
    assert rows[0]["section"] == "secret_classes"
