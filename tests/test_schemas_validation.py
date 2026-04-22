"""Tests for Pydantic field-level validation on REST API request schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from max.server.schemas import (
    BlueprintSourceBriefResponse,
    DesignBriefResponse,
    FeedbackCreate,
    IdeaCreate,
    InsightCreate,
    PipelineRunRequest,
    ScheduleUpdateRequest,
    SignalCreate,
    SimilarityRequest,
)


# ── SignalCreate.credibility ───────────────────────────────────────


class TestSignalCreateCredibility:
    REQUIRED = {"title": "t", "content": "c", "url": "https://x.com"}

    def test_default(self):
        m = SignalCreate(**self.REQUIRED)
        assert m.credibility == 0.5

    @pytest.mark.parametrize("val", [0.0, 0.5, 1.0])
    def test_accepts_valid(self, val):
        m = SignalCreate(**self.REQUIRED, credibility=val)
        assert m.credibility == val

    @pytest.mark.parametrize("val", [-0.1, 1.01, 2.0, -1.0])
    def test_rejects_invalid(self, val):
        with pytest.raises(ValidationError):
            SignalCreate(**self.REQUIRED, credibility=val)


# ── InsightCreate.confidence ───────────────────────────────────────


class TestInsightCreateConfidence:
    REQUIRED = {"title": "t", "summary": "s"}

    def test_default(self):
        m = InsightCreate(**self.REQUIRED)
        assert m.confidence == 0.5

    @pytest.mark.parametrize("val", [0.0, 0.5, 1.0])
    def test_accepts_valid(self, val):
        m = InsightCreate(**self.REQUIRED, confidence=val)
        assert m.confidence == val

    @pytest.mark.parametrize("val", [-0.01, 1.001, 5.0])
    def test_rejects_invalid(self, val):
        with pytest.raises(ValidationError):
            InsightCreate(**self.REQUIRED, confidence=val)


# ── FeedbackCreate.outcome ─────────────────────────────────────────


class TestFeedbackCreateOutcome:
    @pytest.mark.parametrize("val", ["approved", "rejected", "published", "abandoned"])
    def test_accepts_valid(self, val):
        m = FeedbackCreate(outcome=val)
        assert m.outcome == val

    @pytest.mark.parametrize("val", ["invalid", "APPROVED", "approve", ""])
    def test_rejects_invalid(self, val):
        with pytest.raises(ValidationError):
            FeedbackCreate(outcome=val)


# ── IdeaCreate.target_users ───────────────────────────────────────


class TestIdeaCreateTargetUsers:
    REQUIRED = {
        "title": "t",
        "one_liner": "o",
        "problem": "p",
        "solution": "s",
        "value_proposition": "v",
    }

    def test_default(self):
        m = IdeaCreate(**self.REQUIRED)
        assert m.target_users == "both"

    @pytest.mark.parametrize("val", ["humans", "agents", "both"])
    def test_accepts_valid(self, val):
        m = IdeaCreate(**self.REQUIRED, target_users=val)
        assert m.target_users == val

    @pytest.mark.parametrize("val", ["everyone", "HUMANS", "clinicians"])
    def test_accepts_profile_defined_values(self, val):
        m = IdeaCreate(**self.REQUIRED, target_users=val)
        assert m.target_users == val

    @pytest.mark.parametrize("val", [""])
    def test_rejects_invalid(self, val):
        with pytest.raises(ValidationError):
            IdeaCreate(**self.REQUIRED, target_users=val)


# ── IdeaCreate.category ───────────────────────────────────────────


class TestIdeaCreateCategory:
    REQUIRED = {
        "title": "t",
        "one_liner": "o",
        "problem": "p",
        "solution": "s",
        "value_proposition": "v",
    }

    def test_default(self):
        m = IdeaCreate(**self.REQUIRED)
        assert m.category == "application"

    def test_accepts_non_empty(self):
        m = IdeaCreate(**self.REQUIRED, category="cli_tool")
        assert m.category == "cli_tool"

    def test_rejects_empty_string(self):
        with pytest.raises(ValidationError):
            IdeaCreate(**self.REQUIRED, category="")


# ── PipelineRunRequest ─────────────────────────────────────────────


class TestPipelineRunRequest:
    def test_defaults(self):
        m = PipelineRunRequest()
        assert m.signal_limit == 30
        assert m.min_score == 50.0
        assert m.weight_profile == "default"
        assert m.ideation_mode == "direct"

    # signal_limit
    @pytest.mark.parametrize("val", [1, 250, 500])
    def test_signal_limit_valid(self, val):
        m = PipelineRunRequest(signal_limit=val)
        assert m.signal_limit == val

    @pytest.mark.parametrize("val", [0, -1, 501, 1000])
    def test_signal_limit_invalid(self, val):
        with pytest.raises(ValidationError):
            PipelineRunRequest(signal_limit=val)

    # min_score
    @pytest.mark.parametrize("val", [0.0, 50.0, 100.0])
    def test_min_score_valid(self, val):
        m = PipelineRunRequest(min_score=val)
        assert m.min_score == val

    @pytest.mark.parametrize("val", [-0.1, 100.1, 200.0])
    def test_min_score_invalid(self, val):
        with pytest.raises(ValidationError):
            PipelineRunRequest(min_score=val)

    # weight_profile
    @pytest.mark.parametrize(
        "val", ["default", "quick_wins", "moonshots", "ecosystem", "agent_first"]
    )
    def test_weight_profile_valid(self, val):
        m = PipelineRunRequest(weight_profile=val)
        assert m.weight_profile == val

    @pytest.mark.parametrize("val", ["custom", "DEFAULT", ""])
    def test_weight_profile_invalid(self, val):
        with pytest.raises(ValidationError):
            PipelineRunRequest(weight_profile=val)

    # ideation_mode
    @pytest.mark.parametrize("val", ["direct", "refinement", "cross_domain"])
    def test_ideation_mode_valid(self, val):
        m = PipelineRunRequest(ideation_mode=val)
        assert m.ideation_mode == val

    @pytest.mark.parametrize("val", ["random", "DIRECT", ""])
    def test_ideation_mode_invalid(self, val):
        with pytest.raises(ValidationError):
            PipelineRunRequest(ideation_mode=val)


# ── SimilarityRequest ──────────────────────────────────────────────


class TestSimilarityRequest:
    REQUIRED = {"text": "some text", "entity_type": "signal"}

    def test_defaults(self):
        m = SimilarityRequest(**self.REQUIRED)
        assert m.threshold == 0.8
        assert m.limit == 5

    # threshold
    @pytest.mark.parametrize("val", [0.0, 0.5, 1.0])
    def test_threshold_valid(self, val):
        m = SimilarityRequest(**self.REQUIRED, threshold=val)
        assert m.threshold == val

    @pytest.mark.parametrize("val", [-0.01, 1.01, 2.0])
    def test_threshold_invalid(self, val):
        with pytest.raises(ValidationError):
            SimilarityRequest(**self.REQUIRED, threshold=val)

    # limit
    @pytest.mark.parametrize("val", [1, 50, 100])
    def test_limit_valid(self, val):
        m = SimilarityRequest(**self.REQUIRED, limit=val)
        assert m.limit == val

    @pytest.mark.parametrize("val", [0, -1, 101, 500])
    def test_limit_invalid(self, val):
        with pytest.raises(ValidationError):
            SimilarityRequest(**self.REQUIRED, limit=val)


# ── ScheduleUpdateRequest ─────────────────────────────────────────


class TestScheduleUpdateRequest:
    def test_all_none_defaults(self):
        m = ScheduleUpdateRequest()
        assert m.enabled is None
        assert m.interval_seconds is None
        assert m.profile is None
        assert m.include_all is None
        assert m.signal_limit is None
        assert m.min_score is None
        assert m.weight_profile is None
        assert m.ideation_mode is None
        assert m.quality_loop_enabled is None
        assert m.trigger_now is False

    # interval_seconds
    @pytest.mark.parametrize("val", [60, 3600, 86400])
    def test_interval_seconds_valid(self, val):
        m = ScheduleUpdateRequest(interval_seconds=val)
        assert m.interval_seconds == val

    @pytest.mark.parametrize("val", [0, 1, 59])
    def test_interval_seconds_invalid(self, val):
        with pytest.raises(ValidationError):
            ScheduleUpdateRequest(interval_seconds=val)

    def test_interval_seconds_none_allowed(self):
        m = ScheduleUpdateRequest(interval_seconds=None)
        assert m.interval_seconds is None

    # signal_limit
    def test_signal_limit_valid(self):
        m = ScheduleUpdateRequest(signal_limit=100)
        assert m.signal_limit == 100

    @pytest.mark.parametrize("val", [0, 501])
    def test_signal_limit_invalid(self, val):
        with pytest.raises(ValidationError):
            ScheduleUpdateRequest(signal_limit=val)

    # min_score
    def test_min_score_valid(self):
        m = ScheduleUpdateRequest(min_score=75.0)
        assert m.min_score == 75.0

    @pytest.mark.parametrize("val", [-1.0, 100.1])
    def test_min_score_invalid(self, val):
        with pytest.raises(ValidationError):
            ScheduleUpdateRequest(min_score=val)

    # weight_profile
    def test_weight_profile_valid(self):
        m = ScheduleUpdateRequest(weight_profile="moonshots")
        assert m.weight_profile == "moonshots"

    def test_weight_profile_invalid(self):
        with pytest.raises(ValidationError):
            ScheduleUpdateRequest(weight_profile="bad_profile")

    # ideation_mode
    def test_ideation_mode_valid(self):
        m = ScheduleUpdateRequest(ideation_mode="cross_domain")
        assert m.ideation_mode == "cross_domain"

    def test_ideation_mode_invalid(self):
        with pytest.raises(ValidationError):
            ScheduleUpdateRequest(ideation_mode="bad_mode")


# ── Nested / composition ──────────────────────────────────────────


class TestComposition:
    """Verify that models with all valid fields compose correctly."""

    def test_full_signal(self):
        m = SignalCreate(
            title="Full",
            content="Content",
            url="https://example.com",
            source_type="registry",
            source_adapter="npm",
            author="tester",
            tags=["a", "b"],
            credibility=0.9,
            metadata={"key": "value"},
        )
        assert m.model_dump()["credibility"] == 0.9
        assert m.model_dump()["tags"] == ["a", "b"]

    def test_full_pipeline_request(self):
        m = PipelineRunRequest(
            signal_limit=100,
            min_score=75.0,
            weight_profile="moonshots",
            ideation_mode="refinement",
            output_dir="/tmp/out",
        )
        d = m.model_dump()
        assert d["signal_limit"] == 100
        assert d["weight_profile"] == "moonshots"
        assert d["output_dir"] == "/tmp/out"

    def test_full_schedule_update(self):
        m = ScheduleUpdateRequest(
            enabled=True,
            interval_seconds=7200,
            profile="devtools",
            include_all=True,
            signal_limit=50,
            min_score=60.0,
            weight_profile="ecosystem",
            ideation_mode="cross_domain",
            quality_loop_enabled=True,
            trigger_now=True,
        )
        d = m.model_dump()
        assert d["enabled"] is True
        assert d["interval_seconds"] == 7200
        assert d["profile"] == "devtools"
        assert d["include_all"] is True
        assert d["quality_loop_enabled"] is True
        assert d["trigger_now"] is True

    def test_design_brief_response(self):
        m = DesignBriefResponse(
            id="dbf-1",
            title="Brief",
            domain="devtools",
            theme="agent-ops",
            readiness_score=80.0,
            lead_idea_id="bu-1",
            buyer="VP Engineering",
            specific_user="platform engineer",
            workflow_context="release validation",
            why_this_now="timely",
            merged_product_concept="concept",
            synthesis_rationale="rationale",
            mvp_scope=["scope"],
            first_milestones=["milestone"],
            validation_plan="validate",
            risks=["risk"],
            source_idea_ids=["bu-1"],
            design_status="candidate",
            created_at="2026-04-22T00:00:00+00:00",
            updated_at="2026-04-22T00:00:00+00:00",
            sources=[{"idea_id": "bu-1", "role": "lead", "rank": 0}],
        )
        assert m.sources[0].role == "lead"

    def test_blueprint_source_brief_response(self):
        m = BlueprintSourceBriefResponse(
            schema_version="max.blueprint.source_brief.v1",
            source={"project": "max"},
            design_brief={"id": "dbf-1"},
            source_ideas=[{"id": "bu-1"}],
            blueprint_import_hints={"recommended_source_priority": "design_brief"},
        )
        assert m.schema_version == "max.blueprint.source_brief.v1"
