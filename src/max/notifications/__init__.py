"""Notifications and external integrations for Max."""

from max.notifications.pipeline_digest import (
    PipelineDigest,
    build_pipeline_digest,
    render_digest_html,
    render_digest_json,
    render_digest_text,
)

__all__ = [
    "PipelineDigest",
    "build_pipeline_digest",
    "render_digest_html",
    "render_digest_json",
    "render_digest_text",
]
