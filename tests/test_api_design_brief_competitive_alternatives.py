from max.analysis.design_brief_competitive_alternatives import KIND, SCHEMA_VERSION

from tests._design_brief_artifact_endpoint_helpers import assert_api_artifact


def test_design_brief_competitive_alternatives_api(tmp_path) -> None:
    assert_api_artifact(
        tmp_path,
        path="competitive-alternatives",
        kind=KIND,
        schema_version=SCHEMA_VERSION,
        markdown_heading="# Competitive Alternatives Matrix:",
    )
