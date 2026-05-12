"""Compatibility tests for the Google Sheets row publisher batch adapter."""

from tests.test_google_sheets_publisher import (
    test_build_row_payload_maps_tact_spec_fields_deterministically,
    test_dry_run_returns_exact_append_payload_without_token_or_network,
    test_from_env_reads_google_sheets_configuration,
    test_live_publish_posts_authenticated_append_request,
    test_live_publish_requires_access_token,
)
