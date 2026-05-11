from max.analysis.design_brief_market_entry_risk import KIND, SCHEMA_VERSION

from tests._design_brief_artifact_endpoint_helpers import assert_api_artifact


def test_design_brief_market_entry_risk_api(tmp_path) -> None:
    assert_api_artifact(
        tmp_path,
        path="market-entry-risk",
        kind=KIND,
        schema_version=SCHEMA_VERSION,
        markdown_heading="# Market Entry Risk Report:",
    )
