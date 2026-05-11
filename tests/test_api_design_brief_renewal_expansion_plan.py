from max.analysis.design_brief_renewal_expansion_plan import CSV_COLUMNS, KIND, SCHEMA_VERSION

from tests._design_brief_artifact_endpoint_helpers import assert_api_artifact


def test_design_brief_renewal_expansion_plan_api(tmp_path) -> None:
    assert_api_artifact(
        tmp_path,
        path="renewal-expansion-plan",
        kind=KIND,
        schema_version=SCHEMA_VERSION,
        markdown_heading="# Renewal and Expansion Plan:",
        csv_header=CSV_COLUMNS,
    )
