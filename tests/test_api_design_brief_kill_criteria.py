from max.analysis.design_brief_kill_criteria import CSV_COLUMNS, KIND, SCHEMA_VERSION

from tests._design_brief_artifact_endpoint_helpers import assert_api_artifact


def test_design_brief_kill_criteria_api(tmp_path) -> None:
    assert_api_artifact(
        tmp_path,
        path="kill-criteria",
        kind=KIND,
        schema_version=SCHEMA_VERSION,
        markdown_heading="# Kill Criteria:",
        csv_header=CSV_COLUMNS,
    )
