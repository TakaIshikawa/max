from max.analysis.design_brief_investor_update import CSV_COLUMNS, KIND, SCHEMA_VERSION

from tests._design_brief_artifact_endpoint_helpers import assert_api_artifact


def test_design_brief_investor_update_api(tmp_path) -> None:
    assert_api_artifact(
        tmp_path,
        path="investor-update",
        kind=KIND,
        schema_version=SCHEMA_VERSION,
        markdown_heading="# Investor Update:",
        csv_header=CSV_COLUMNS,
    )
