"""Comprehensive tests for all Pydantic models in src/max/server/schemas.py.

Tests cover:
1. Valid input construction
2. Required field validation errors
3. Type coercion and field validators
4. Serialization via model_dump()
5. Custom validators raising ValidationError on invalid input
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from max.server.schemas import (
    DimensionScoreResponse,
    DryRunReportResponse,
    EvaluationResponse,
    FeedbackCreate,
    FeedbackLogEntryResponse,
    FeedbackWebhookRequest,
    FeedbackWebhookResponse,
    HealthResponse,
    IdeaCreate,
    IdeaDetailResponse,
    IdeaMemoryResponse,
    IdeaSummaryResponse,
    InsightCreate,
    InsightDetailResponse,
    InsightResponse,
    PaginatedResponse,
    PaginationMeta,
    PaginationParams,
    PipelineDryRunRequest,
    PipelinePostRunRequest,
    PipelinePostRunResponse,
    PipelineResultResponse,
    PipelineResultSummary,
    PipelineRunHistoryResponse,
    PipelineRunRequest,
    ProfileDetailResponse,
    ProfileSummaryResponse,
    FetchAllocationSimulationApprovalResponse,
    FetchAllocationSimulationCircuitBreakerResponse,
    FetchAllocationSimulationQualityResponse,
    FetchAllocationSimulationResponse,
    FetchAllocationSimulationSourceResponse,
    DesignBriefCustomerJourneyMapResponse,
    DesignBriefEventDictionaryResponse,
    DesignBriefExperimentBacklogResponse,
    DesignBriefGtmChannelPlanResponse,
    DesignBriefInstrumentationPlanResponse,
    DesignBriefPrivacyImpactAssessmentRequest,
    DesignBriefPrivacyImpactAssessmentResponse,
    DesignBriefRolloutCommsPlanResponse,
    DesignBriefSuccessMetricsResponse,
    DesignBriefTrainingPlanRequest,
    DesignBriefTrainingPlanResponse,
    ScheduleStatusResponse,
    ScheduleUpdateRequest,
    SecurityReviewResponse,
    SignalCreate,
    SignalResponse,
    SimilarityRequest,
    SimilarityResult,
    StageSummaryResponse,
    StatsResponse,
)
from max.profiles.schema import DomainContext, EvaluationConfig, SourceConfig


# ── Request Models ──────────────────────────────────────────────────


class TestSignalCreate:
    """Tests for SignalCreate request model."""

    def test_valid_construction_minimal(self):
        """Test construction with minimal required fields."""
        signal = SignalCreate(
            title="Test Signal",
            content="Test content",
            url="https://example.com/signal",
        )
        assert signal.title == "Test Signal"
        assert signal.content == "Test content"
        assert signal.url == "https://example.com/signal"
        assert signal.source_type == "forum"
        assert signal.source_adapter == "api"
        assert signal.author is None
        assert signal.tags == []
        assert signal.credibility == 0.5
        assert signal.metadata == {}

    def test_valid_construction_full(self):
        """Test construction with all fields."""
        signal = SignalCreate(
            title="Full Signal",
            content="Full content",
            url="https://example.com/full",
            source_type="reddit",
            source_adapter="pushshift",
            author="test_user",
            tags=["tag1", "tag2"],
            credibility=0.8,
            metadata={"key": "value"},
        )
        assert signal.source_type == "reddit"
        assert signal.author == "test_user"
        assert signal.tags == ["tag1", "tag2"]
        assert signal.credibility == 0.8

    def test_required_fields(self):
        """Test that required fields raise ValidationError when missing."""
        with pytest.raises(ValidationError) as exc_info:
            SignalCreate()
        errors = exc_info.value.errors()
        missing_fields = {e["loc"][0] for e in errors}
        assert "title" in missing_fields
        assert "content" in missing_fields
        assert "url" in missing_fields

    def test_credibility_validation(self):
        """Test credibility field validation (0.0 to 1.0)."""
        # Valid values
        for val in [0.0, 0.5, 1.0]:
            signal = SignalCreate(
                title="Test", content="Test", url="https://example.com", credibility=val
            )
            assert signal.credibility == val

        # Invalid values
        for val in [-0.1, 1.1, 2.0]:
            with pytest.raises(ValidationError):
                SignalCreate(
                    title="Test", content="Test", url="https://example.com", credibility=val
                )

    def test_serialization(self):
        """Test model_dump produces expected JSON structure."""
        signal = SignalCreate(
            title="Test",
            content="Content",
            url="https://example.com",
            tags=["a", "b"],
            credibility=0.7,
        )
        dumped = signal.model_dump()
        assert dumped["title"] == "Test"
        assert dumped["content"] == "Content"
        assert dumped["url"] == "https://example.com"
        assert dumped["tags"] == ["a", "b"]
        assert dumped["credibility"] == 0.7
        assert dumped["source_type"] == "forum"
        assert dumped["metadata"] == {}


class TestInsightCreate:
    """Tests for InsightCreate request model."""

    def test_valid_construction_minimal(self):
        """Test construction with minimal required fields."""
        insight = InsightCreate(title="Test Insight", summary="Test summary")
        assert insight.title == "Test Insight"
        assert insight.summary == "Test summary"
        assert insight.category == "emerging_pattern"
        assert insight.evidence == []
        assert insight.confidence == 0.5
        assert insight.domains == []
        assert insight.implications == []
        assert insight.time_horizon == "near_term"

    def test_valid_construction_full(self):
        """Test construction with all fields."""
        insight = InsightCreate(
            category="trend",
            title="Full Insight",
            summary="Full summary",
            evidence=["e1", "e2"],
            confidence=0.9,
            domains=["d1", "d2"],
            implications=["i1", "i2"],
            time_horizon="long_term",
        )
        assert insight.category == "trend"
        assert insight.evidence == ["e1", "e2"]
        assert insight.confidence == 0.9
        assert insight.domains == ["d1", "d2"]

    def test_required_fields(self):
        """Test that required fields raise ValidationError when missing."""
        with pytest.raises(ValidationError) as exc_info:
            InsightCreate()
        errors = exc_info.value.errors()
        missing_fields = {e["loc"][0] for e in errors}
        assert "title" in missing_fields
        assert "summary" in missing_fields

    def test_confidence_validation(self):
        """Test confidence field validation (0.0 to 1.0)."""
        # Valid values
        for val in [0.0, 0.5, 1.0]:
            insight = InsightCreate(title="Test", summary="Test", confidence=val)
            assert insight.confidence == val

        # Invalid values
        for val in [-0.1, 1.1, 2.0]:
            with pytest.raises(ValidationError):
                InsightCreate(title="Test", summary="Test", confidence=val)

    def test_serialization(self):
        """Test model_dump produces expected JSON structure."""
        insight = InsightCreate(
            title="Test",
            summary="Summary",
            evidence=["ev1"],
            confidence=0.8,
            domains=["ai"],
        )
        dumped = insight.model_dump()
        assert dumped["title"] == "Test"
        assert dumped["summary"] == "Summary"
        assert dumped["evidence"] == ["ev1"]
        assert dumped["confidence"] == 0.8
        assert dumped["domains"] == ["ai"]


class TestIdeaCreate:
    """Tests for IdeaCreate request model."""

    def test_valid_construction_minimal(self):
        """Test construction with minimal required fields."""
        idea = IdeaCreate(
            title="Test Idea",
            one_liner="One line description",
            problem="Problem statement",
            solution="Solution statement",
            value_proposition="Value prop",
        )
        assert idea.title == "Test Idea"
        assert idea.one_liner == "One line description"
        assert idea.category == "application"
        assert idea.target_users == "both"
        assert idea.tech_approach == ""
        assert idea.suggested_stack == {}
        assert idea.composability_notes == ""

    def test_valid_construction_full(self):
        """Test construction with all fields."""
        idea = IdeaCreate(
            title="Full Idea",
            one_liner="Full one-liner",
            category="tool",
            problem="Full problem",
            solution="Full solution",
            target_users="agents",
            value_proposition="Full value",
            tech_approach="Tech details",
            suggested_stack={"frontend": "react"},
            composability_notes="Composable with X",
        )
        assert idea.category == "tool"
        assert idea.target_users == "agents"
        assert idea.tech_approach == "Tech details"
        assert idea.suggested_stack == {"frontend": "react"}

    def test_required_fields(self):
        """Test that required fields raise ValidationError when missing."""
        with pytest.raises(ValidationError) as exc_info:
            IdeaCreate()
        errors = exc_info.value.errors()
        missing_fields = {e["loc"][0] for e in errors}
        assert "title" in missing_fields
        assert "one_liner" in missing_fields
        assert "problem" in missing_fields
        assert "solution" in missing_fields
        assert "value_proposition" in missing_fields

    def test_target_users_accepts_profile_defined_values(self):
        """Test target_users accepts generic and profile-defined values."""
        for val in ["humans", "agents", "both", "clinicians", "administrators"]:
            idea = IdeaCreate(
                title="T",
                one_liner="O",
                problem="P",
                solution="S",
                value_proposition="V",
                target_users=val,
            )
            assert idea.target_users == val

    def test_category_min_length(self):
        """Test category has minimum length validation."""
        with pytest.raises(ValidationError):
            IdeaCreate(
                title="T",
                one_liner="O",
                problem="P",
                solution="S",
                value_proposition="V",
                category="",
            )

    def test_serialization(self):
        """Test model_dump produces expected JSON structure."""
        idea = IdeaCreate(
            title="Test",
            one_liner="One",
            problem="Problem",
            solution="Solution",
            value_proposition="Value",
            category="cli",
            target_users="humans",
        )
        dumped = idea.model_dump()
        assert dumped["title"] == "Test"
        assert dumped["category"] == "cli"
        assert dumped["target_users"] == "humans"


class TestFeedbackCreate:
    """Tests for FeedbackCreate request model."""

    def test_valid_construction_minimal(self):
        """Test construction with minimal required fields."""
        feedback = FeedbackCreate(outcome="approved")
        assert feedback.outcome == "approved"
        assert feedback.reason == ""

    def test_valid_construction_with_reason(self):
        """Test construction with reason."""
        feedback = FeedbackCreate(outcome="rejected", reason="Not viable")
        assert feedback.outcome == "rejected"
        assert feedback.reason == "Not viable"

    def test_required_fields(self):
        """Test that required fields raise ValidationError when missing."""
        with pytest.raises(ValidationError) as exc_info:
            FeedbackCreate()
        errors = exc_info.value.errors()
        assert any(e["loc"][0] == "outcome" for e in errors)

    def test_outcome_validation(self):
        """Test outcome literal validation."""
        # Valid values
        for val in ["approved", "rejected", "published", "abandoned"]:
            feedback = FeedbackCreate(outcome=val)
            assert feedback.outcome == val

        # Invalid values
        with pytest.raises(ValidationError):
            FeedbackCreate(outcome="invalid")

    def test_serialization(self):
        """Test model_dump produces expected JSON structure."""
        feedback = FeedbackCreate(outcome="published", reason="Ready to ship")
        dumped = feedback.model_dump()
        assert dumped["outcome"] == "published"
        assert dumped["reason"] == "Ready to ship"


class TestFeedbackWebhookRequest:
    """Tests for FeedbackWebhookRequest request model."""

    def test_valid_construction_full(self):
        feedback = FeedbackWebhookRequest(
            idea_id="bu-webhook",
            outcome="approved",
            reason="passed external checks",
            approval_score=8,
            external_run_id="run-123",
            external_url="https://example.com/runs/run-123",
            metadata={"executor": "ci", "duration_seconds": 42},
        )

        assert feedback.idea_id == "bu-webhook"
        assert feedback.outcome == "approved"
        assert feedback.reason == "passed external checks"
        assert feedback.approval_score == 8
        assert feedback.external_run_id == "run-123"
        assert feedback.metadata["executor"] == "ci"

    def test_metadata_defaults_to_empty_dict(self):
        feedback = FeedbackWebhookRequest(
            idea_id="bu-webhook",
            outcome="rejected",
            external_run_id="run-123",
            external_url="https://example.com/runs/run-123",
        )

        assert feedback.reason == ""
        assert feedback.metadata == {}

    def test_outcome_validation(self):
        with pytest.raises(ValidationError):
            FeedbackWebhookRequest(
                idea_id="bu-webhook",
                outcome="invalid",
                external_run_id="run-123",
                external_url="https://example.com/runs/run-123",
            )

    def test_response_construction(self):
        response = FeedbackWebhookResponse(
            status="ok",
            idea_id="bu-webhook",
            outcome="published",
            external_run_id="run-123",
        )

        dumped = response.model_dump()
        assert dumped == {
            "status": "ok",
            "idea_id": "bu-webhook",
            "outcome": "published",
            "external_run_id": "run-123",
        }


class TestFeedbackLogEntryResponse:
    """Tests for FeedbackLogEntryResponse model."""

    def test_valid_construction(self):
        entry = FeedbackLogEntryResponse(
            unit_id="bu-log-1",
            title="Test Idea",
            domain="testing",
            category="application",
            outcome="approved",
            reason="strong fit",
            approval_score=9,
            score=82.5,
            recommendation="yes",
            created_at="2026-04-23T00:00:00+00:00",
        )

        assert entry.unit_id == "bu-log-1"
        assert entry.title == "Test Idea"
        assert entry.domain == "testing"
        assert entry.category == "application"
        assert entry.outcome == "approved"
        assert entry.reason == "strong fit"
        assert entry.approval_score == 9
        assert entry.score == 82.5
        assert entry.recommendation == "yes"

    def test_serialization(self):
        entry = FeedbackLogEntryResponse(
            unit_id="bu-log-1",
            title="Test Idea",
            domain="testing",
            category="application",
            outcome="rejected",
            reason="too narrow",
            created_at="2026-04-23T00:00:00+00:00",
        )

        dumped = entry.model_dump()
        assert dumped["unit_id"] == "bu-log-1"
        assert dumped["title"] == "Test Idea"
        assert dumped["reason"] == "too narrow"
        assert dumped["created_at"] == "2026-04-23T00:00:00+00:00"


class TestPipelineRunRequest:
    """Tests for PipelineRunRequest model."""

    def test_valid_construction_defaults(self):
        """Test construction with default values."""
        request = PipelineRunRequest()
        assert request.signal_limit == 30
        assert request.min_score == 50.0
        assert request.weight_profile == "default"
        assert request.ideation_mode == "direct"
        assert request.quality_loop_enabled is False
        assert request.draft_count == 8
        assert request.output_dir is None
        assert request.stages is None

    def test_valid_construction_custom(self):
        """Test construction with custom values."""
        request = PipelineRunRequest(
            signal_limit=100,
            min_score=75.0,
            weight_profile="moonshots",
            ideation_mode="refinement",
            quality_loop_enabled=True,
            draft_count=12,
            output_dir="/tmp/out",
            stages=["fetch", "synthesize"],
        )
        assert request.signal_limit == 100
        assert request.min_score == 75.0
        assert request.weight_profile == "moonshots"
        assert request.ideation_mode == "refinement"
        assert request.quality_loop_enabled is True
        assert request.draft_count == 12
        assert request.output_dir == "/tmp/out"
        assert request.stages == ["fetch", "synthesize"]

    def test_signal_limit_validation(self):
        """Test signal_limit range validation (1 to 500)."""
        # Valid values
        for val in [1, 250, 500]:
            request = PipelineRunRequest(signal_limit=val)
            assert request.signal_limit == val

        # Invalid values
        for val in [0, -1, 501]:
            with pytest.raises(ValidationError):
                PipelineRunRequest(signal_limit=val)

    def test_min_score_validation(self):
        """Test min_score range validation (0.0 to 100.0)."""
        # Valid values
        for val in [0.0, 50.0, 100.0]:
            request = PipelineRunRequest(min_score=val)
            assert request.min_score == val

        # Invalid values
        for val in [-0.1, 100.1]:
            with pytest.raises(ValidationError):
                PipelineRunRequest(min_score=val)

    def test_weight_profile_validation(self):
        """Test weight_profile literal validation."""
        valid = ["default", "quick_wins", "moonshots", "ecosystem", "agent_first"]
        for val in valid:
            request = PipelineRunRequest(weight_profile=val)
            assert request.weight_profile == val

        with pytest.raises(ValidationError):
            PipelineRunRequest(weight_profile="invalid")

    def test_ideation_mode_validation(self):
        """Test ideation_mode literal validation."""
        for val in ["direct", "refinement", "cross_domain"]:
            request = PipelineRunRequest(ideation_mode=val)
            assert request.ideation_mode == val

        with pytest.raises(ValidationError):
            PipelineRunRequest(ideation_mode="invalid")

    def test_serialization(self):
        """Test model_dump produces expected JSON structure."""
        request = PipelineRunRequest(
            signal_limit=50,
            min_score=60.0,
            quality_loop_enabled=True,
            draft_count=10,
        )
        dumped = request.model_dump()
        assert dumped["signal_limit"] == 50
        assert dumped["min_score"] == 60.0
        assert dumped["weight_profile"] == "default"
        assert dumped["quality_loop_enabled"] is True
        assert dumped["draft_count"] == 10


class TestPipelineDryRunRequest:
    """Tests for PipelineDryRunRequest model."""

    def test_valid_construction_defaults(self):
        """Test construction with default values."""
        request = PipelineDryRunRequest()
        assert request.profile is None
        assert request.signal_limit == 30
        assert request.stages is None

    def test_valid_construction_custom(self):
        """Test construction with custom values."""
        request = PipelineDryRunRequest(
            profile="moonshots", signal_limit=100, stages=["fetch", "evaluate"]
        )
        assert request.profile == "moonshots"
        assert request.signal_limit == 100
        assert request.stages == ["fetch", "evaluate"]

    def test_signal_limit_validation(self):
        """Test signal_limit range validation."""
        # Valid
        request = PipelineDryRunRequest(signal_limit=250)
        assert request.signal_limit == 250

        # Invalid
        with pytest.raises(ValidationError):
            PipelineDryRunRequest(signal_limit=0)

    def test_serialization(self):
        """Test model_dump produces expected JSON structure."""
        request = PipelineDryRunRequest(profile="ecosystem", signal_limit=75)
        dumped = request.model_dump()
        assert dumped["profile"] == "ecosystem"
        assert dumped["signal_limit"] == 75


class TestPipelinePostRunRequest:
    """Tests for PipelinePostRunRequest model."""

    def test_valid_construction_defaults(self):
        """Test construction with default values."""
        request = PipelinePostRunRequest()
        assert request.domain is None

    def test_valid_construction_with_domain(self):
        """Test construction with optional domain."""
        request = PipelinePostRunRequest(domain="fintech")
        assert request.domain == "fintech"


class TestSimilarityRequest:
    """Tests for SimilarityRequest model."""

    def test_valid_construction_defaults(self):
        """Test construction with default values."""
        request = SimilarityRequest(text="test text", entity_type="signal")
        assert request.text == "test text"
        assert request.entity_type == "signal"
        assert request.threshold == 0.8
        assert request.limit == 5

    def test_valid_construction_custom(self):
        """Test construction with custom values."""
        request = SimilarityRequest(
            text="custom text", entity_type="idea", threshold=0.9, limit=10
        )
        assert request.threshold == 0.9
        assert request.limit == 10

    def test_required_fields(self):
        """Test that required fields raise ValidationError when missing."""
        with pytest.raises(ValidationError) as exc_info:
            SimilarityRequest()
        errors = exc_info.value.errors()
        missing_fields = {e["loc"][0] for e in errors}
        assert "text" in missing_fields
        assert "entity_type" in missing_fields

    def test_threshold_validation(self):
        """Test threshold range validation (0.0 to 1.0)."""
        # Valid
        for val in [0.0, 0.5, 1.0]:
            request = SimilarityRequest(text="t", entity_type="e", threshold=val)
            assert request.threshold == val

        # Invalid
        for val in [-0.1, 1.1]:
            with pytest.raises(ValidationError):
                SimilarityRequest(text="t", entity_type="e", threshold=val)

    def test_limit_validation(self):
        """Test limit range validation (1 to 100)."""
        # Valid
        for val in [1, 50, 100]:
            request = SimilarityRequest(text="t", entity_type="e", limit=val)
            assert request.limit == val

        # Invalid
        for val in [0, 101]:
            with pytest.raises(ValidationError):
                SimilarityRequest(text="t", entity_type="e", limit=val)

    def test_serialization(self):
        """Test model_dump produces expected JSON structure."""
        request = SimilarityRequest(
            text="search", entity_type="insight", threshold=0.85, limit=15
        )
        dumped = request.model_dump()
        assert dumped["text"] == "search"
        assert dumped["entity_type"] == "insight"
        assert dumped["threshold"] == 0.85
        assert dumped["limit"] == 15


class TestPaginationParams:
    """Tests for PaginationParams model."""

    def test_valid_construction_defaults(self):
        """Test construction with default values."""
        params = PaginationParams()
        assert params.cursor is None
        assert params.limit == 20

    def test_valid_construction_custom(self):
        """Test construction with custom values."""
        params = PaginationParams(cursor="abc123", limit=50)
        assert params.cursor == "abc123"
        assert params.limit == 50

    def test_limit_validation(self):
        """Test limit range validation (1 to 100)."""
        # Valid
        for val in [1, 50, 100]:
            params = PaginationParams(limit=val)
            assert params.limit == val

        # Invalid
        for val in [0, 101]:
            with pytest.raises(ValidationError):
                PaginationParams(limit=val)

    def test_serialization(self):
        """Test model_dump produces expected JSON structure."""
        params = PaginationParams(cursor="xyz", limit=30)
        dumped = params.model_dump()
        assert dumped["cursor"] == "xyz"
        assert dumped["limit"] == 30


class TestScheduleUpdateRequest:
    """Tests for ScheduleUpdateRequest model."""

    def test_valid_construction_defaults(self):
        """Test construction with default values."""
        request = ScheduleUpdateRequest()
        assert request.enabled is None
        assert request.interval_seconds is None
        assert request.profile is None
        assert request.include_all is None
        assert request.max_execution_seconds is None
        assert request.signal_limit is None
        assert request.min_score is None
        assert request.weight_profile is None
        assert request.ideation_mode is None
        assert request.quality_loop_enabled is None
        assert request.max_consecutive_failures is None
        assert request.trigger_now is False

    def test_valid_construction_custom(self):
        """Test construction with custom values."""
        request = ScheduleUpdateRequest(
            enabled=True,
            interval_seconds=3600,
            profile="devtools",
            include_all=True,
            max_execution_seconds=2400,
            signal_limit=50,
            min_score=70.0,
            weight_profile="quick_wins",
            ideation_mode="cross_domain",
            quality_loop_enabled=True,
            max_consecutive_failures=5,
            trigger_now=True,
        )
        assert request.enabled is True
        assert request.interval_seconds == 3600
        assert request.profile == "devtools"
        assert request.include_all is True
        assert request.max_execution_seconds == 2400
        assert request.signal_limit == 50
        assert request.min_score == 70.0
        assert request.weight_profile == "quick_wins"
        assert request.ideation_mode == "cross_domain"
        assert request.quality_loop_enabled is True
        assert request.max_consecutive_failures == 5
        assert request.trigger_now is True

    def test_interval_seconds_validation(self):
        """Test interval_seconds minimum validation (>= 60)."""
        # Valid
        for val in [60, 3600, 86400]:
            request = ScheduleUpdateRequest(interval_seconds=val)
            assert request.interval_seconds == val

        # Invalid
        for val in [0, 59]:
            with pytest.raises(ValidationError):
                ScheduleUpdateRequest(interval_seconds=val)

    def test_signal_limit_validation(self):
        """Test signal_limit range validation."""
        # Valid
        request = ScheduleUpdateRequest(signal_limit=100)
        assert request.signal_limit == 100

        # Invalid
        for val in [0, 501]:
            with pytest.raises(ValidationError):
                ScheduleUpdateRequest(signal_limit=val)

    def test_min_score_validation(self):
        """Test min_score range validation."""
        # Valid
        request = ScheduleUpdateRequest(min_score=80.0)
        assert request.min_score == 80.0

        # Invalid
        for val in [-1.0, 100.1]:
            with pytest.raises(ValidationError):
                ScheduleUpdateRequest(min_score=val)

    def test_max_consecutive_failures_validation(self):
        """Test max_consecutive_failures minimum validation."""
        # Valid
        request = ScheduleUpdateRequest(max_consecutive_failures=1)
        assert request.max_consecutive_failures == 1

        # Invalid
        with pytest.raises(ValidationError):
            ScheduleUpdateRequest(max_consecutive_failures=0)

    def test_serialization(self):
        """Test model_dump produces expected JSON structure."""
        request = ScheduleUpdateRequest(enabled=True, interval_seconds=7200)
        dumped = request.model_dump()
        assert dumped["enabled"] is True
        assert dumped["interval_seconds"] == 7200
        assert dumped["trigger_now"] is False


# ── Response Models ─────────────────────────────────────────────────


class TestPaginationMeta:
    """Tests for PaginationMeta model."""

    def test_valid_construction(self):
        """Test construction with all fields."""
        meta = PaginationMeta(next_cursor="abc123", has_more=True, total_count=100)
        assert meta.next_cursor == "abc123"
        assert meta.has_more is True
        assert meta.total_count == 100

    def test_required_fields(self):
        """Test that required fields raise ValidationError when missing."""
        with pytest.raises(ValidationError) as exc_info:
            PaginationMeta()
        errors = exc_info.value.errors()
        missing_fields = {e["loc"][0] for e in errors}
        assert "has_more" in missing_fields
        assert "total_count" in missing_fields

    def test_serialization(self):
        """Test model_dump produces expected JSON structure."""
        meta = PaginationMeta(next_cursor=None, has_more=False, total_count=42)
        dumped = meta.model_dump()
        assert dumped["next_cursor"] is None
        assert dumped["has_more"] is False
        assert dumped["total_count"] == 42


class TestPaginatedResponse:
    """Tests for generic PaginatedResponse model."""

    def test_valid_construction_with_dict(self):
        """Test construction with dict items."""
        items = [{"id": "1", "name": "item1"}, {"id": "2", "name": "item2"}]
        pagination = PaginationMeta(next_cursor=None, has_more=False, total_count=2)
        response = PaginatedResponse(items=items, pagination=pagination)
        assert len(response.items) == 2
        assert response.pagination.total_count == 2

    def test_required_fields(self):
        """Test that required fields raise ValidationError when missing."""
        with pytest.raises(ValidationError) as exc_info:
            PaginatedResponse()
        errors = exc_info.value.errors()
        missing_fields = {e["loc"][0] for e in errors}
        assert "items" in missing_fields
        assert "pagination" in missing_fields

    def test_serialization(self):
        """Test model_dump produces expected JSON structure."""
        items = [{"data": "test"}]
        pagination = PaginationMeta(next_cursor="xyz", has_more=True, total_count=10)
        response = PaginatedResponse(items=items, pagination=pagination)
        dumped = response.model_dump()
        assert dumped["items"] == [{"data": "test"}]
        assert dumped["pagination"]["next_cursor"] == "xyz"
        assert dumped["pagination"]["has_more"] is True


class TestSignalResponse:
    """Tests for SignalResponse model."""

    def test_valid_construction_minimal(self):
        """Test construction with minimal required fields."""
        signal = SignalResponse(
            id="sig_123",
            source_type="forum",
            source_adapter="api",
            title="Test Signal",
            content="Test content",
            url="https://example.com",
            fetched_at="2024-01-01T00:00:00Z",
            tags=[],
            credibility=0.5,
            metadata={},
        )
        assert signal.id == "sig_123"
        assert signal.author is None
        assert signal.published_at is None

    def test_valid_construction_full(self):
        """Test construction with all fields."""
        signal = SignalResponse(
            id="sig_456",
            source_type="reddit",
            source_adapter="pushshift",
            title="Full Signal",
            content="Full content",
            url="https://reddit.com/r/test",
            author="user123",
            published_at="2024-01-01T12:00:00Z",
            fetched_at="2024-01-01T13:00:00Z",
            tags=["ai", "ml"],
            credibility=0.9,
            metadata={"score": 42},
        )
        assert signal.author == "user123"
        assert signal.published_at == "2024-01-01T12:00:00Z"
        assert signal.tags == ["ai", "ml"]

    def test_required_fields(self):
        """Test that required fields raise ValidationError when missing."""
        with pytest.raises(ValidationError) as exc_info:
            SignalResponse()
        errors = exc_info.value.errors()
        missing_fields = {e["loc"][0] for e in errors}
        assert "id" in missing_fields
        assert "title" in missing_fields
        assert "content" in missing_fields
        assert "url" in missing_fields

    def test_serialization(self):
        """Test model_dump produces expected JSON structure."""
        signal = SignalResponse(
            id="sig_789",
            source_type="hn",
            source_adapter="algolia",
            title="HN Post",
            content="Content",
            url="https://news.ycombinator.com/item?id=123",
            fetched_at="2024-01-01T00:00:00Z",
            tags=["tech"],
            credibility=0.8,
            metadata={},
        )
        dumped = signal.model_dump()
        assert dumped["id"] == "sig_789"
        assert dumped["source_type"] == "hn"
        assert dumped["tags"] == ["tech"]


class TestInsightResponse:
    """Tests for InsightResponse model."""

    def test_valid_construction(self):
        """Test construction with all required fields."""
        insight = InsightResponse(
            id="ins_123",
            category="trend",
            title="Test Insight",
            summary="Summary",
            evidence=["e1", "e2"],
            confidence=0.85,
            domains=["ai"],
            implications=["i1"],
            time_horizon="near_term",
            created_at="2024-01-01T00:00:00Z",
        )
        assert insight.id == "ins_123"
        assert insight.category == "trend"
        assert insight.confidence == 0.85

    def test_required_fields(self):
        """Test that required fields raise ValidationError when missing."""
        with pytest.raises(ValidationError) as exc_info:
            InsightResponse()
        errors = exc_info.value.errors()
        missing_fields = {e["loc"][0] for e in errors}
        assert "id" in missing_fields
        assert "category" in missing_fields
        assert "title" in missing_fields

    def test_serialization(self):
        """Test model_dump produces expected JSON structure."""
        insight = InsightResponse(
            id="ins_456",
            category="emerging_pattern",
            title="Pattern",
            summary="Summary",
            evidence=[],
            confidence=0.7,
            domains=["web3"],
            implications=["imp"],
            time_horizon="long_term",
            created_at="2024-01-01T00:00:00Z",
        )
        dumped = insight.model_dump()
        assert dumped["id"] == "ins_456"
        assert dumped["time_horizon"] == "long_term"


class TestInsightDetailResponse:
    """Tests for InsightDetailResponse model."""

    def test_valid_construction_with_evidence_signals(self):
        signal = SignalResponse(
            id="sig_123",
            source_type="forum",
            source_adapter="hn",
            signal_role="problem",
            title="Evidence",
            content="Evidence content",
            url="https://example.com/evidence",
            fetched_at="2024-01-01T00:00:00Z",
            tags=["evidence"],
            credibility=0.8,
            metadata={},
        )
        insight = InsightDetailResponse(
            id="ins_123",
            category="gap",
            title="Test Insight",
            summary="Summary",
            evidence=["sig_123", "sig_missing"],
            confidence=0.85,
            domains=["ai"],
            implications=[],
            time_horizon="near_term",
            created_at="2024-01-01T00:00:00Z",
            evidence_signals=[signal],
            missing_evidence_ids=["sig_missing"],
        )
        assert insight.evidence_signals[0].id == "sig_123"
        assert insight.missing_evidence_ids == ["sig_missing"]

    def test_defaults_to_empty_evidence_resolution_lists(self):
        insight = InsightDetailResponse(
            id="ins_456",
            category="trend",
            title="Pattern",
            summary="Summary",
            evidence=[],
            confidence=0.7,
            domains=[],
            implications=[],
            time_horizon="long_term",
            created_at="2024-01-01T00:00:00Z",
        )
        dumped = insight.model_dump()
        assert dumped["evidence_signals"] == []
        assert dumped["missing_evidence_ids"] == []


class TestDimensionScoreResponse:
    """Tests for DimensionScoreResponse model."""

    def test_valid_construction(self):
        """Test construction with all required fields."""
        score = DimensionScoreResponse(
            value=8.5, confidence=0.9, reasoning="Strong evidence"
        )
        assert score.value == 8.5
        assert score.confidence == 0.9
        assert score.reasoning == "Strong evidence"

    def test_required_fields(self):
        """Test that required fields raise ValidationError when missing."""
        with pytest.raises(ValidationError) as exc_info:
            DimensionScoreResponse()
        errors = exc_info.value.errors()
        missing_fields = {e["loc"][0] for e in errors}
        assert "value" in missing_fields
        assert "confidence" in missing_fields
        assert "reasoning" in missing_fields

    def test_serialization(self):
        """Test model_dump produces expected JSON structure."""
        score = DimensionScoreResponse(value=7.0, confidence=0.8, reasoning="Good")
        dumped = score.model_dump()
        assert dumped["value"] == 7.0
        assert dumped["confidence"] == 0.8
        assert dumped["reasoning"] == "Good"


class TestEvaluationResponse:
    """Tests for EvaluationResponse model."""

    def test_valid_construction(self):
        """Test construction with all required fields."""
        dim_score = DimensionScoreResponse(value=8.0, confidence=0.9, reasoning="Test")
        evaluation = EvaluationResponse(
            buildable_unit_id="idea_123",
            pain_severity=dim_score,
            addressable_scale=dim_score,
            build_effort=dim_score,
            composability=dim_score,
            competitive_density=dim_score,
            timing_fit=dim_score,
            compounding_value=dim_score,
            overall_score=85.5,
            rank=1,
            strengths=["s1", "s2"],
            weaknesses=["w1"],
            recommendation="Pursue immediately",
            weights_used={"pain_severity": 0.2},
        )
        assert evaluation.buildable_unit_id == "idea_123"
        assert evaluation.overall_score == 85.5
        assert evaluation.rank == 1

    def test_required_fields(self):
        """Test that required fields raise ValidationError when missing."""
        with pytest.raises(ValidationError) as exc_info:
            EvaluationResponse()
        errors = exc_info.value.errors()
        missing_fields = {e["loc"][0] for e in errors}
        assert "buildable_unit_id" in missing_fields
        assert "overall_score" in missing_fields

    def test_serialization(self):
        """Test model_dump produces expected JSON structure."""
        dim_score = DimensionScoreResponse(value=7.5, confidence=0.85, reasoning="OK")
        evaluation = EvaluationResponse(
            buildable_unit_id="idea_456",
            pain_severity=dim_score,
            addressable_scale=dim_score,
            build_effort=dim_score,
            composability=dim_score,
            competitive_density=dim_score,
            timing_fit=dim_score,
            compounding_value=dim_score,
            overall_score=75.0,
            rank=None,
            strengths=["str"],
            weaknesses=["weak"],
            recommendation="Consider",
            weights_used={},
        )
        dumped = evaluation.model_dump()
        assert dumped["buildable_unit_id"] == "idea_456"
        assert dumped["overall_score"] == 75.0
        assert dumped["rank"] is None


class TestIdeaSummaryResponse:
    """Tests for IdeaSummaryResponse model."""

    def test_valid_construction_minimal(self):
        """Test construction with minimal required fields."""
        idea = IdeaSummaryResponse(
            id="idea_123",
            title="Test Idea",
            one_liner="One line",
            category="application",
            status="pending",
            target_users="both",
        )
        assert idea.id == "idea_123"
        assert idea.domain == ""
        assert idea.score is None
        assert idea.recommendation is None

    def test_valid_construction_full(self):
        """Test construction with all fields."""
        idea = IdeaSummaryResponse(
            id="idea_456",
            title="Full Idea",
            one_liner="Full one-liner",
            category="tool",
            domain="ai",
            status="evaluated",
            target_users="agents",
            score=85.5,
            recommendation="High priority",
        )
        assert idea.domain == "ai"
        assert idea.score == 85.5
        assert idea.recommendation == "High priority"

    def test_required_fields(self):
        """Test that required fields raise ValidationError when missing."""
        with pytest.raises(ValidationError) as exc_info:
            IdeaSummaryResponse()
        errors = exc_info.value.errors()
        missing_fields = {e["loc"][0] for e in errors}
        assert "id" in missing_fields
        assert "title" in missing_fields
        assert "status" in missing_fields

    def test_serialization(self):
        """Test model_dump produces expected JSON structure."""
        idea = IdeaSummaryResponse(
            id="idea_789",
            title="Summary",
            one_liner="Line",
            category="framework",
            status="approved",
            target_users="humans",
            score=90.0,
        )
        dumped = idea.model_dump()
        assert dumped["id"] == "idea_789"
        assert dumped["score"] == 90.0


class TestIdeaDetailResponse:
    """Tests for IdeaDetailResponse model."""

    def test_valid_construction_minimal(self):
        """Test construction with minimal required fields."""
        idea = IdeaDetailResponse(
            id="idea_123",
            title="Detail Test",
            one_liner="One",
            category="app",
            ideation_mode="direct",
            problem="Problem",
            solution="Solution",
            target_users="both",
            value_proposition="Value",
            inspiring_insights=[],
            evidence_signals=[],
            tech_approach="",
            suggested_stack={},
            composability_notes="",
            status="pending",
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
        )
        assert idea.id == "idea_123"
        assert idea.evaluation is None

    def test_valid_construction_full(self):
        """Test construction with all fields including evaluation."""
        dim_score = DimensionScoreResponse(value=8.0, confidence=0.9, reasoning="Good")
        evaluation = EvaluationResponse(
            buildable_unit_id="idea_456",
            pain_severity=dim_score,
            addressable_scale=dim_score,
            build_effort=dim_score,
            composability=dim_score,
            competitive_density=dim_score,
            timing_fit=dim_score,
            compounding_value=dim_score,
            overall_score=82.0,
            rank=2,
            strengths=["s"],
            weaknesses=["w"],
            recommendation="Rec",
            weights_used={},
        )
        idea = IdeaDetailResponse(
            id="idea_456",
            title="Full Detail",
            one_liner="Full",
            category="platform",
            domain="ml",
            ideation_mode="refinement",
            problem="Full problem",
            solution="Full solution",
            target_users="agents",
            value_proposition="Full value",
            inspiring_insights=["ins1"],
            evidence_signals=["sig1"],
            tech_approach="Tech",
            suggested_stack={"lang": "python"},
            composability_notes="Notes",
            status="evaluated",
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-02T00:00:00Z",
            evaluation=evaluation,
        )
        assert idea.evaluation is not None
        assert idea.evaluation.overall_score == 82.0

    def test_required_fields(self):
        """Test that required fields raise ValidationError when missing."""
        with pytest.raises(ValidationError) as exc_info:
            IdeaDetailResponse()
        errors = exc_info.value.errors()
        missing_fields = {e["loc"][0] for e in errors}
        assert "id" in missing_fields
        assert "title" in missing_fields
        assert "problem" in missing_fields
        assert "solution" in missing_fields

    def test_serialization(self):
        """Test model_dump produces expected JSON structure."""
        idea = IdeaDetailResponse(
            id="idea_789",
            title="Serialize Test",
            one_liner="Line",
            category="service",
            ideation_mode="cross_domain",
            problem="P",
            solution="S",
            target_users="humans",
            value_proposition="V",
            inspiring_insights=[],
            evidence_signals=[],
            tech_approach="",
            suggested_stack={},
            composability_notes="",
            status="pending",
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
        )
        dumped = idea.model_dump()
        assert dumped["id"] == "idea_789"
        assert dumped["ideation_mode"] == "cross_domain"
        assert dumped["evaluation"] is None


class TestIdeaMemoryResponse:
    """Tests for IdeaMemoryResponse model."""

    def test_valid_construction(self):
        memory = IdeaMemoryResponse(
            id="mem-001",
            buildable_unit_id="bu-001",
            domain="healthcare",
            outcome="rejected",
            pattern="Broad assistant: weak buyer",
            rejection_tags=["weak_evidence"],
            score=3.0,
            evidence_rationale="No supporting signals",
            created_at="2026-01-01T00:00:00+00:00",
        )
        assert memory.id == "mem-001"
        assert memory.buildable_unit_id == "bu-001"
        assert memory.rejection_tags == ["weak_evidence"]

    def test_valid_construction_without_unit(self):
        memory = IdeaMemoryResponse(
            id="mem-002",
            domain="",
            outcome="quality_rejected",
            pattern="Generic assistant",
            rejection_tags=[],
            score=0.0,
            evidence_rationale="",
            created_at="2026-01-01T00:00:00+00:00",
        )
        assert memory.buildable_unit_id is None
        assert memory.domain == ""

    def test_required_fields(self):
        with pytest.raises(ValidationError) as exc_info:
            IdeaMemoryResponse()
        missing_fields = {e["loc"][0] for e in exc_info.value.errors()}
        assert "id" in missing_fields
        assert "outcome" in missing_fields
        assert "pattern" in missing_fields
        assert "created_at" in missing_fields


class TestProfileSummaryResponse:
    """Tests for ProfileSummaryResponse model."""

    def test_valid_construction(self):
        profile = ProfileSummaryResponse(
            name="devtools",
            domain="developer-tools",
            description="Developer tools",
            enabled_source_count=7,
            signal_limit=30,
            min_score=50.0,
            weight_profile="default",
            ideation_mode="direct",
            quality_loop_enabled=False,
        )
        assert profile.name == "devtools"
        assert profile.domain == "developer-tools"
        assert profile.enabled_source_count == 7

    def test_required_fields(self):
        with pytest.raises(ValidationError) as exc_info:
            ProfileSummaryResponse()
        missing_fields = {e["loc"][0] for e in exc_info.value.errors()}
        assert "name" in missing_fields
        assert "domain" in missing_fields
        assert "enabled_source_count" in missing_fields

    def test_serialization(self):
        profile = ProfileSummaryResponse(
            name="healthcare",
            domain="healthcare",
            description="Healthcare",
            enabled_source_count=3,
            signal_limit=25,
            min_score=65.0,
            weight_profile="quick_wins",
            ideation_mode="refinement",
            quality_loop_enabled=True,
        )
        dumped = profile.model_dump()
        assert dumped["description"] == "Healthcare"
        assert dumped["quality_loop_enabled"] is True


class TestProfileDetailResponse:
    """Tests for ProfileDetailResponse model."""

    def test_valid_construction(self):
        profile = ProfileDetailResponse(
            name="devtools",
            domain=DomainContext(
                name="developer-tools",
                description="Developer tools",
                categories=["cli_tool"],
                target_user_types=["developers"],
            ),
            sources=[SourceConfig(adapter="hackernews")],
            evaluation=EvaluationConfig(weight_profile="default", min_score=50.0),
            output_dir=".max-output",
            signal_limit=30,
            ideation_mode="direct",
            quality_loop_enabled=False,
            draft_count=8,
        )
        assert profile.domain.name == "developer-tools"
        assert profile.sources[0].adapter == "hackernews"
        assert profile.evaluation.min_score == 50.0

    def test_required_fields(self):
        with pytest.raises(ValidationError) as exc_info:
            ProfileDetailResponse()
        missing_fields = {e["loc"][0] for e in exc_info.value.errors()}
        assert "name" in missing_fields
        assert "domain" in missing_fields
        assert "sources" in missing_fields

    def test_serialization(self):
        profile = ProfileDetailResponse(
            name="fintech",
            domain=DomainContext(
                name="fintech",
                description="Financial technology",
                categories=["compliance_automation"],
                target_user_types=["analysts"],
                hard_constraints=["auditability"],
            ),
            sources=[SourceConfig(adapter="reddit", enabled=False)],
            evaluation=EvaluationConfig(weight_profile="agent_first", min_score=70.0),
            output_dir=".fintech-output",
            signal_limit=20,
            ideation_mode="cross_domain",
            quality_loop_enabled=True,
            draft_count=5,
        )
        dumped = profile.model_dump()
        assert dumped["domain"]["hard_constraints"] == ["auditability"]
        assert dumped["sources"][0]["enabled"] is False
        assert dumped["evaluation"]["weight_profile"] == "agent_first"


class TestPipelineResultResponse:
    """Tests for PipelineResultResponse model."""

    def test_valid_construction(self):
        """Test construction with all required fields."""
        result = PipelineResultResponse(
            signals_fetched=100,
            signals_new=20,
            insights_generated=15,
            ideas_generated=10,
            ideas_evaluated=10,
            avg_insight_confidence=0.82,
            avg_idea_score=78.5,
            token_usage={"input": 1000, "output": 500},
            top_ideas=[{"id": "idea_1", "score": 90.0}],
        )
        assert result.signals_fetched == 100
        assert result.signals_new == 20
        assert result.avg_idea_score == 78.5

    def test_required_fields(self):
        """Test that required fields raise ValidationError when missing."""
        with pytest.raises(ValidationError) as exc_info:
            PipelineResultResponse()
        errors = exc_info.value.errors()
        missing_fields = {e["loc"][0] for e in errors}
        assert "signals_fetched" in missing_fields
        assert "insights_generated" in missing_fields

    def test_serialization(self):
        """Test model_dump produces expected JSON structure."""
        result = PipelineResultResponse(
            signals_fetched=50,
            signals_new=10,
            insights_generated=5,
            ideas_generated=3,
            ideas_evaluated=3,
            avg_insight_confidence=0.75,
            avg_idea_score=80.0,
            token_usage={},
            top_ideas=[],
        )
        dumped = result.model_dump()
        assert dumped["signals_fetched"] == 50
        assert dumped["top_ideas"] == []


class TestPipelinePostRunResponse:
    """Tests for PipelinePostRunResponse model."""

    def test_valid_construction(self):
        """Test construction with all required fields."""
        result = PipelinePostRunResponse(
            duplicates_marked=1,
            ideas_synthesized=2,
            source_ideas_merged=3,
            synthesis_clusters=4,
            prior_art_checked=5,
            prior_art_strong=6,
            prior_art_weak=7,
            prior_art_clear=8,
            triage_auto_approved=9,
            triage_auto_rejected=10,
            triage_pending_review=11,
        )
        assert result.duplicates_marked == 1
        assert result.triage_pending_review == 11

    def test_required_fields(self):
        """Test that required fields raise ValidationError when missing."""
        with pytest.raises(ValidationError) as exc_info:
            PipelinePostRunResponse()
        errors = exc_info.value.errors()
        missing_fields = {e["loc"][0] for e in errors}
        assert "duplicates_marked" in missing_fields
        assert "triage_pending_review" in missing_fields


class TestSimilarityResult:
    """Tests for SimilarityResult model."""

    def test_valid_construction(self):
        """Test construction with all required fields."""
        result = SimilarityResult(entity_id="ent_123", score=0.95)
        assert result.entity_id == "ent_123"
        assert result.score == 0.95

    def test_required_fields(self):
        """Test that required fields raise ValidationError when missing."""
        with pytest.raises(ValidationError) as exc_info:
            SimilarityResult()
        errors = exc_info.value.errors()
        missing_fields = {e["loc"][0] for e in errors}
        assert "entity_id" in missing_fields
        assert "score" in missing_fields

    def test_serialization(self):
        """Test model_dump produces expected JSON structure."""
        result = SimilarityResult(entity_id="ent_456", score=0.88)
        dumped = result.model_dump()
        assert dumped["entity_id"] == "ent_456"
        assert dumped["score"] == 0.88


class TestStatsResponse:
    """Tests for StatsResponse model."""

    def test_valid_construction(self):
        """Test construction with all required fields."""
        stats = StatsResponse(
            signals_count=1000,
            insights_count=50,
            ideas_count=20,
            evaluated_count=15,
            avg_score=82.5,
        )
        assert stats.signals_count == 1000
        assert stats.avg_score == 82.5

    def test_required_fields(self):
        """Test that required fields raise ValidationError when missing."""
        with pytest.raises(ValidationError) as exc_info:
            StatsResponse()
        errors = exc_info.value.errors()
        missing_fields = {e["loc"][0] for e in errors}
        assert "signals_count" in missing_fields
        assert "insights_count" in missing_fields

    def test_serialization(self):
        """Test model_dump produces expected JSON structure."""
        stats = StatsResponse(
            signals_count=500,
            insights_count=25,
            ideas_count=10,
            evaluated_count=8,
            avg_score=None,
        )
        dumped = stats.model_dump()
        assert dumped["signals_count"] == 500
        assert dumped["avg_score"] is None


class TestPipelineResultSummary:
    """Tests for PipelineResultSummary model."""

    def test_valid_construction(self):
        """Test construction with all required fields."""
        summary = PipelineResultSummary(
            signals_fetched=200,
            signals_new=40,
            insights_generated=30,
            ideas_generated=20,
            ideas_evaluated=18,
            avg_insight_confidence=0.88,
            avg_idea_score=85.2,
        )
        assert summary.signals_fetched == 200
        assert summary.avg_idea_score == 85.2

    def test_required_fields(self):
        """Test that required fields raise ValidationError when missing."""
        with pytest.raises(ValidationError) as exc_info:
            PipelineResultSummary()
        errors = exc_info.value.errors()
        missing_fields = {e["loc"][0] for e in errors}
        assert "signals_fetched" in missing_fields
        assert "insights_generated" in missing_fields

    def test_serialization(self):
        """Test model_dump produces expected JSON structure."""
        summary = PipelineResultSummary(
            signals_fetched=100,
            signals_new=20,
            insights_generated=15,
            ideas_generated=10,
            ideas_evaluated=10,
            avg_insight_confidence=0.8,
            avg_idea_score=80.0,
        )
        dumped = summary.model_dump()
        assert dumped["signals_fetched"] == 100
        assert dumped["avg_insight_confidence"] == 0.8


class TestScheduleStatusResponse:
    """Tests for ScheduleStatusResponse model."""

    def test_valid_construction_minimal(self):
        """Test construction with minimal required fields."""
        status = ScheduleStatusResponse(
            enabled=True,
            interval_seconds=3600,
            running=False,
            max_execution_seconds=1800,
            run_count=0,
            pipeline_config={},
        )
        assert status.enabled is True
        assert status.profile is None
        assert status.include_all is False
        assert status.max_execution_seconds == 1800
        assert status.last_run_at is None
        assert status.failure_streak == 0
        assert status.max_consecutive_failures == 3

    def test_valid_construction_full(self):
        """Test construction with all fields."""
        summary = PipelineResultSummary(
            signals_fetched=50,
            signals_new=10,
            insights_generated=8,
            ideas_generated=5,
            ideas_evaluated=5,
            avg_insight_confidence=0.85,
            avg_idea_score=82.0,
        )
        status = ScheduleStatusResponse(
            enabled=True,
            interval_seconds=7200,
            profile="all",
            include_all=True,
            max_execution_seconds=2400,
            running=True,
            last_run_at="2024-01-01T12:00:00Z",
            next_run_at="2024-01-01T14:00:00Z",
            run_count=42,
            last_error="Connection timeout",
            last_error_at="2024-01-01T11:00:00Z",
            failure_streak=2,
            max_consecutive_failures=5,
            last_result=summary,
            pipeline_config={"signal_limit": 30},
        )
        assert status.running is True
        assert status.profile == "all"
        assert status.include_all is True
        assert status.max_execution_seconds == 2400
        assert status.run_count == 42
        assert status.last_result is not None
        assert status.last_result.avg_idea_score == 82.0

    def test_required_fields(self):
        """Test that required fields raise ValidationError when missing."""
        with pytest.raises(ValidationError) as exc_info:
            ScheduleStatusResponse()
        errors = exc_info.value.errors()
        missing_fields = {e["loc"][0] for e in errors}
        assert "enabled" in missing_fields
        assert "interval_seconds" in missing_fields
        assert "running" in missing_fields

    def test_serialization(self):
        """Test model_dump produces expected JSON structure."""
        status = ScheduleStatusResponse(
            enabled=False,
            interval_seconds=1800,
            max_execution_seconds=1200,
            running=False,
            run_count=5,
            pipeline_config={"min_score": 50.0},
        )
        dumped = status.model_dump()
        assert dumped["enabled"] is False
        assert dumped["interval_seconds"] == 1800
        assert dumped["max_execution_seconds"] == 1200
        assert dumped["pipeline_config"] == {"min_score": 50.0}


class TestHealthResponse:
    """Tests for HealthResponse model."""

    def test_valid_construction(self):
        """Test construction with all required fields."""
        health = HealthResponse(
            status="healthy", database=True, version=5, uptime_seconds=3600.5
        )
        assert health.status == "healthy"
        assert health.database is True
        assert health.version == 5
        assert health.uptime_seconds == 3600.5

    def test_required_fields(self):
        """Test that required fields raise ValidationError when missing."""
        with pytest.raises(ValidationError) as exc_info:
            HealthResponse()
        errors = exc_info.value.errors()
        missing_fields = {e["loc"][0] for e in errors}
        assert "status" in missing_fields
        assert "database" in missing_fields
        assert "version" in missing_fields

    def test_serialization(self):
        """Test model_dump produces expected JSON structure."""
        health = HealthResponse(
            status="degraded", database=False, version=3, uptime_seconds=120.0
        )
        dumped = health.model_dump()
        assert dumped["status"] == "degraded"
        assert dumped["database"] is False
        assert dumped["version"] == 3


class TestPipelineRunHistoryResponse:
    """Tests for PipelineRunHistoryResponse model."""

    def test_valid_construction_running(self):
        """Test construction for a running pipeline."""
        history = PipelineRunHistoryResponse(
            id="run_123",
            started_at="2024-01-01T10:00:00Z",
            finished_at=None,
            signals_fetched=50,
            insights_generated=10,
            ideas_generated=5,
            ideas_evaluated=0,
            status="running",
        )
        assert history.id == "run_123"
        assert history.finished_at is None
        assert history.status == "running"

    def test_valid_construction_completed(self):
        """Test construction for a completed pipeline."""
        history = PipelineRunHistoryResponse(
            id="run_456",
            started_at="2024-01-01T10:00:00Z",
            finished_at="2024-01-01T10:30:00Z",
            signals_fetched=100,
            insights_generated=20,
            ideas_generated=15,
            ideas_evaluated=15,
            status="completed",
        )
        assert history.finished_at == "2024-01-01T10:30:00Z"
        assert history.status == "completed"

    def test_required_fields(self):
        """Test that required fields raise ValidationError when missing."""
        with pytest.raises(ValidationError) as exc_info:
            PipelineRunHistoryResponse()
        errors = exc_info.value.errors()
        missing_fields = {e["loc"][0] for e in errors}
        assert "id" in missing_fields
        assert "started_at" in missing_fields
        assert "status" in missing_fields

    def test_serialization(self):
        """Test model_dump produces expected JSON structure."""
        history = PipelineRunHistoryResponse(
            id="run_789",
            started_at="2024-01-01T00:00:00Z",
            finished_at="2024-01-01T01:00:00Z",
            signals_fetched=75,
            insights_generated=12,
            ideas_generated=8,
            ideas_evaluated=7,
            status="failed",
        )
        dumped = history.model_dump()
        assert dumped["id"] == "run_789"
        assert dumped["status"] == "failed"


class TestStageSummaryResponse:
    """Tests for StageSummaryResponse model."""

    def test_valid_construction(self):
        """Test construction with all required fields."""
        stage = StageSummaryResponse(
            name="fetch",
            would_process=100,
            estimated_llm_calls=10,
            skipped=False,
            reason="",
        )
        assert stage.name == "fetch"
        assert stage.would_process == 100
        assert stage.skipped is False

    def test_required_fields(self):
        """Test that required fields raise ValidationError when missing."""
        with pytest.raises(ValidationError) as exc_info:
            StageSummaryResponse()
        errors = exc_info.value.errors()
        missing_fields = {e["loc"][0] for e in errors}
        assert "name" in missing_fields
        assert "would_process" in missing_fields
        assert "estimated_llm_calls" in missing_fields

    def test_serialization(self):
        """Test model_dump produces expected JSON structure."""
        stage = StageSummaryResponse(
            name="evaluate",
            would_process=20,
            estimated_llm_calls=20,
            skipped=True,
            reason="Not enough ideas",
        )
        dumped = stage.model_dump()
        assert dumped["name"] == "evaluate"
        assert dumped["skipped"] is True
        assert dumped["reason"] == "Not enough ideas"


class TestDryRunReportResponse:
    """Tests for DryRunReportResponse model."""

    def test_valid_construction(self):
        """Test construction with all required fields."""
        stages = [
            StageSummaryResponse(
                name="fetch", would_process=100, estimated_llm_calls=0, skipped=False, reason=""
            ),
            StageSummaryResponse(
                name="synthesize",
                would_process=50,
                estimated_llm_calls=10,
                skipped=False,
                reason="",
            ),
        ]
        report = DryRunReportResponse(
            stages=stages, estimated_total_llm_calls=10, estimated_token_budget=5000
        )
        assert len(report.stages) == 2
        assert report.estimated_total_llm_calls == 10
        assert report.estimated_token_budget == 5000

    def test_required_fields(self):
        """Test that required fields raise ValidationError when missing."""
        with pytest.raises(ValidationError) as exc_info:
            DryRunReportResponse()
        errors = exc_info.value.errors()
        missing_fields = {e["loc"][0] for e in errors}
        assert "stages" in missing_fields
        assert "estimated_total_llm_calls" in missing_fields

    def test_serialization(self):
        """Test model_dump produces expected JSON structure."""
        stages = [
            StageSummaryResponse(
                name="test", would_process=10, estimated_llm_calls=5, skipped=False, reason=""
            )
        ]
        report = DryRunReportResponse(
            stages=stages, estimated_total_llm_calls=5, estimated_token_budget=2000
        )
        dumped = report.model_dump()
        assert len(dumped["stages"]) == 1
        assert dumped["estimated_total_llm_calls"] == 5


class TestFetchAllocationSimulationResponse:
    """Tests for FetchAllocationSimulationResponse model."""

    def test_valid_construction(self):
        response = FetchAllocationSimulationResponse(
            profile="devtools",
            domain="developer-tools",
            total_budget=30,
            allocation={"hackernews": 30},
            sources=[
                FetchAllocationSimulationSourceResponse(
                    adapter="hackernews",
                    enabled=True,
                    configured_weight=1.0,
                    params={"topics": ["mcp"]},
                    quality=FetchAllocationSimulationQualityResponse(
                        total_signals=5,
                        insight_hit_rate=0.4,
                        idea_hit_rate=0.2,
                    ),
                    approval=FetchAllocationSimulationApprovalResponse(
                        total_feedbacked=3,
                        approved=2,
                        rejected=1,
                        approval_rate=2 / 3,
                    ),
                    circuit_breaker=FetchAllocationSimulationCircuitBreakerResponse(
                        state="closed",
                        failure_count=0,
                        retry_after_seconds=0.0,
                    ),
                    allocated_limit=30,
                )
            ],
        )

        assert response.profile == "devtools"
        assert response.domain == "developer-tools"
        assert response.total_budget == 30
        assert response.sources[0].approval.approval_rate == pytest.approx(2 / 3)

    def test_serialization(self):
        response = FetchAllocationSimulationResponse(
            profile="devtools",
            domain="developer-tools",
            total_budget=30,
            allocation={"hackernews": 30},
            sources=[],
        )

        dumped = response.model_dump()
        assert dumped["profile"] == "devtools"
        assert dumped["allocation"] == {"hackernews": 30}
        assert dumped["sources"] == []


class TestDesignBriefSuccessMetricsResponse:
    def test_valid_construction_and_serialization(self):
        response = DesignBriefSuccessMetricsResponse(
            schema_version="max.design_brief.success_metrics.v1",
            brief_id="dbf-success",
            title="Success Metrics Brief",
            north_star_metric={
                "metric": "Qualified workflow success",
                "definition": "Qualified teams complete the workflow.",
                "target": "3+ teams confirm repeat value.",
                "rationale": "Measures completed workflow value.",
                "confidence": "high",
                "source_fields": ["title"],
            },
            activation_metrics=[
                {
                    "id": "A1",
                    "metric": "Qualified setup completion",
                    "definition": "Users complete setup.",
                    "target": "60%+ complete setup.",
                    "rationale": "Confirms usable setup.",
                    "source_fields": ["workflow_context"],
                }
            ],
            retention_metrics=[
                {
                    "id": "R1",
                    "metric": "Repeat workflow usage",
                    "definition": "Users repeat the workflow.",
                    "target": "35%+ repeat within 14 days.",
                    "rationale": "Repeat use signals recurring value.",
                    "source_fields": ["workflow_context"],
                }
            ],
            validation_metrics=[
                {
                    "id": "V1",
                    "metric": "Validation plan completion",
                    "definition": "Run the validation plan.",
                    "target": "Record a pass/fail decision.",
                    "rationale": "Keeps build tied to evidence.",
                    "source_fields": ["validation_plan"],
                }
            ],
            risk_guardrails=[
                {
                    "id": "G1",
                    "metric": "Negative workflow impact",
                    "threshold": "No material workflow regression.",
                    "severity": "high",
                    "action": "Pause rollout and revise scope.",
                    "source_fields": ["risks"],
                }
            ],
            instrumentation_events=[
                {
                    "id": "E1",
                    "event": "success_metrics_report_generated",
                    "description": "Success metrics were exported.",
                    "properties": ["brief_id"],
                }
            ],
            missing_inputs=[],
        )

        dumped = response.model_dump()
        assert dumped["schema_version"] == "max.design_brief.success_metrics.v1"
        assert dumped["brief_id"] == "dbf-success"
        assert dumped["north_star_metric"]["confidence"] == "high"
        assert dumped["activation_metrics"][0]["id"] == "A1"

    def test_required_fields(self):
        with pytest.raises(ValidationError) as exc_info:
            DesignBriefSuccessMetricsResponse()

        missing_fields = {error["loc"][0] for error in exc_info.value.errors()}
        assert "schema_version" in missing_fields
        assert "brief_id" in missing_fields
        assert "north_star_metric" in missing_fields


class TestDesignBriefInstrumentationPlanResponse:
    def test_preserves_instrumentation_plan_artifact_sections(self):
        response = DesignBriefInstrumentationPlanResponse(
            schema_version="max.design_brief.instrumentation_plan.v1",
            kind="max.design_brief.instrumentation_plan",
            design_brief={"id": "dbf-instrumentation", "title": "Instrumentation Brief"},
            summary={"event_count": 1, "guardrail_event_count": 1},
            events=[
                {
                    "id": "E1",
                    "name": "activation_started",
                    "category": "activation",
                    "trigger": "A qualified actor starts the workflow.",
                    "required_properties": ["brief_id", "actor_role"],
                    "privacy_notes": [],
                }
            ],
            activation_funnel_steps=[
                {
                    "step": "Start",
                    "event_name": "activation_started",
                    "description": "User starts activation.",
                    "required_properties": ["brief_id"],
                }
            ],
            retention_checkpoints=[
                {
                    "checkpoint": "Repeat use",
                    "event_name": "core_workflow_repeated",
                    "description": "Activated account repeats the workflow.",
                    "window": "14 days",
                }
            ],
            guardrail_alerts=[
                {
                    "name": "security_approval_blocked",
                    "event_name": "guardrail_alert_triggered",
                    "severity": "high",
                    "condition": "Security approval blocks rollout.",
                    "response": "Pause rollout.",
                }
            ],
            privacy_notes=["Do not include raw customer content."],
            missing_inputs=[],
        )

        dumped = response.model_dump()
        assert dumped["schema_version"] == "max.design_brief.instrumentation_plan.v1"
        assert dumped["kind"] == "max.design_brief.instrumentation_plan"
        assert dumped["events"][0]["name"] == "activation_started"
        assert dumped["guardrail_alerts"][0]["severity"] == "high"

    def test_required_fields(self):
        with pytest.raises(ValidationError) as exc_info:
            DesignBriefInstrumentationPlanResponse()

        missing_fields = {error["loc"][0] for error in exc_info.value.errors()}
        assert "schema_version" in missing_fields
        assert "kind" in missing_fields
        assert "design_brief" in missing_fields
        assert "events" in missing_fields
        assert "guardrail_alerts" in missing_fields


class TestDesignBriefEventDictionaryResponse:
    def test_preserves_event_dictionary_artifact_sections(self):
        response = DesignBriefEventDictionaryResponse(
            schema_version="max.design_brief.event_dictionary.v1",
            kind="max.design_brief.event_dictionary",
            source={"project": "max", "entity_type": "design_brief", "id": "dbf-event"},
            design_brief={"id": "dbf-event", "title": "Event Dictionary Brief"},
            summary={"event_count": 1, "event_group_count": 1},
            event_context={"target_user": "platform engineer"},
            linked_metrics=[{"id": "activation_rate", "definition": "Activated accounts"}],
            event_groups=[
                {
                    "category": "activation",
                    "title": "Activation Events",
                    "events": [{"event_name": "design_brief_workflow_started"}],
                }
            ],
            events=[{"event_name": "design_brief_workflow_started"}],
            property_contracts=[{"name": "user_id", "type": "string"}],
            source_ideas=[{"id": "bu-event"}],
        )

        dumped = response.model_dump()
        assert dumped["schema_version"] == "max.design_brief.event_dictionary.v1"
        assert dumped["design_brief"]["id"] == "dbf-event"
        assert dumped["linked_metrics"][0]["id"] == "activation_rate"
        assert dumped["property_contracts"][0]["name"] == "user_id"

    def test_required_fields(self):
        with pytest.raises(ValidationError) as exc_info:
            DesignBriefEventDictionaryResponse()

        missing_fields = {error["loc"][0] for error in exc_info.value.errors()}
        assert "schema_version" in missing_fields
        assert "design_brief" in missing_fields
        assert "event_groups" in missing_fields
        assert "property_contracts" in missing_fields


class TestDesignBriefCustomerJourneyMapResponse:
    def test_preserves_customer_journey_map_artifact_sections(self):
        response = DesignBriefCustomerJourneyMapResponse(
            schema_version="max.design_brief.customer_journey_map.v1",
            kind="max.design_brief.customer_journey_map",
            source={"project": "max", "entity_type": "design_brief", "id": "dbf-journey"},
            design_brief={"id": "dbf-journey", "title": "Journey Brief"},
            summary={"target_user": "operator", "stage_count": 1},
            journey_stages=[
                {
                    "id": "JM1",
                    "sequence": 1,
                    "name": "Problem Awareness",
                    "owner": "Product marketing owner",
                    "user_goals": ["Recognize the problem."],
                    "touchpoints": ["discovery conversation"],
                    "friction_points": ["The pain is described too generally."],
                    "success_signals": ["User can restate the problem."],
                    "evidence_reference_ids": ["design_brief.why_this_now"],
                    "source_idea_ids": ["bu-journey"],
                }
            ],
            pain_points=[
                {
                    "id": "JM1-P1",
                    "stage_id": "JM1",
                    "stage_name": "Problem Awareness",
                    "pain_point": "The pain is described too generally.",
                    "source_idea_ids": ["bu-journey"],
                }
            ],
            moments_of_value=[
                {
                    "id": "JM1-V1",
                    "stage_id": "JM1",
                    "stage_name": "Problem Awareness",
                    "moment": "User can restate the problem.",
                    "source_idea_ids": ["bu-journey"],
                }
            ],
            follow_up_actions=[
                {
                    "id": "FA1",
                    "owner": "Product lead",
                    "action": "Review journey evidence after first use.",
                    "source": "journey_stages",
                    "stage_id": "JM1",
                }
            ],
            evidence_references=[
                {
                    "id": "design_brief.why_this_now",
                    "type": "brief_field",
                    "summary": "Why now.",
                    "source_idea_ids": ["bu-journey"],
                }
            ],
            readiness_warnings=[],
            source_ideas=[{"id": "bu-journey"}],
        )

        dumped = response.model_dump()
        assert dumped["schema_version"] == "max.design_brief.customer_journey_map.v1"
        assert dumped["kind"] == "max.design_brief.customer_journey_map"
        assert dumped["journey_stages"][0]["id"] == "JM1"
        assert dumped["pain_points"][0]["stage_id"] == "JM1"
        assert dumped["moments_of_value"][0]["moment"] == "User can restate the problem."
        assert dumped["follow_up_actions"][0]["owner"] == "Product lead"

    def test_required_fields(self):
        with pytest.raises(ValidationError) as exc_info:
            DesignBriefCustomerJourneyMapResponse()

        missing_fields = {error["loc"][0] for error in exc_info.value.errors()}
        assert "schema_version" in missing_fields
        assert "kind" in missing_fields
        assert "design_brief" in missing_fields
        assert "journey_stages" in missing_fields
        assert "pain_points" in missing_fields
        assert "moments_of_value" in missing_fields
        assert "follow_up_actions" in missing_fields


class TestSecurityReviewResponse:
    def test_preserves_security_review_artifact_sections(self):
        response = SecurityReviewResponse(
            schema_version="max-security-review/v1",
            kind="max.security_review",
            source={"idea_id": "bu-sec", "tact_spec_schema_version": "tact-spec-preview/v1"},
            summary={"title": "Security Review", "finding_count": 1},
            security_context={"mentions_authentication": True},
            findings=[{"id": "SEC-F1", "category": "authentication", "severity": "high"}],
            recommended_controls=[{"id": "SEC-C1", "category": "authentication"}],
            open_questions=[{"id": "SEC-Q1", "category": "authentication"}],
        )

        dumped = response.model_dump()
        assert dumped["schema_version"] == "max-security-review/v1"
        assert dumped["source"]["idea_id"] == "bu-sec"
        assert dumped["summary"]["finding_count"] == 1
        assert dumped["findings"][0]["severity"] == "high"

    def test_required_fields(self):
        with pytest.raises(ValidationError) as exc_info:
            SecurityReviewResponse()

        missing_fields = {error["loc"][0] for error in exc_info.value.errors()}
        assert "schema_version" in missing_fields
        assert "source" in missing_fields
        assert "summary" in missing_fields
        assert "security_context" in missing_fields
        assert "findings" in missing_fields


class TestDesignBriefTrainingPlanSchemas:
    def test_request_defaults_to_json(self):
        request = DesignBriefTrainingPlanRequest()

        assert request.model_dump() == {"format": "json"}

    def test_response_preserves_training_artifact_sections(self):
        response = DesignBriefTrainingPlanResponse(
            schema_version="max.design_brief.training_plan.v1",
            kind="max.design_brief.training_plan",
            source={"project": "max", "entity_type": "design_brief", "id": "dbf-training"},
            design_brief={"id": "dbf-training", "title": "Training Brief"},
            summary={"buyer": "engineering director", "target_user": "platform lead"},
            learner_segments=[{"id": "customer_practitioners", "name": "Practitioners"}],
            learning_objectives=[{"id": "LO1", "objective": "Complete setup"}],
            session_outline=[{"id": "SO1", "title": "Context"}],
            prerequisite_setup=[{"id": "PS1", "name": "Workspace"}],
            hands_on_exercises=[{"id": "EX1", "title": "Run workflow"}],
            success_checks=[{"id": "SC1", "check": "Workflow completed"}],
            follow_up_materials=[{"id": "FM1", "name": "Runbook"}],
            evidence_references=[{"id": "sig-training", "type": "signal"}],
            gaps_to_resolve=[],
            next_actions=[],
            source_ideas=[{"id": "bu-training"}],
        )

        dumped = response.model_dump()
        assert dumped["schema_version"] == "max.design_brief.training_plan.v1"
        assert dumped["design_brief"]["id"] == "dbf-training"
        assert dumped["learning_objectives"][0]["id"] == "LO1"
        assert dumped["evidence_references"][0]["id"] == "sig-training"

    def test_response_required_fields(self):
        with pytest.raises(ValidationError) as exc_info:
            DesignBriefTrainingPlanResponse()

        missing_fields = {error["loc"][0] for error in exc_info.value.errors()}
        assert "schema_version" in missing_fields
        assert "design_brief" in missing_fields
        assert "learning_objectives" in missing_fields


class TestDesignBriefPrivacyImpactAssessmentSchemas:
    def test_request_defaults_to_json(self):
        request = DesignBriefPrivacyImpactAssessmentRequest()

        assert request.model_dump() == {"format": "json"}

    def test_response_preserves_privacy_assessment_artifact_sections(self):
        response = DesignBriefPrivacyImpactAssessmentResponse(
            schema_version="max.design_brief.privacy_impact_assessment.v1",
            kind="max.design_brief.privacy_impact_assessment",
            source={"project": "max", "entity_type": "design_brief", "id": "dbf-privacy"},
            design_brief={"id": "dbf-privacy", "title": "Privacy Brief"},
            summary={"privacy_gate": "privacy_review_required", "sensitive_data_expected": True},
            privacy_context={"buyer": "hospital compliance lead"},
            data_categories=[{"id": "regulated_sensitive_data", "classification": "sensitive_personal_data"}],
            processing_purposes=[{"id": "core_workflow_delivery"}],
            risk_areas=[{"id": "PR1", "severity": "high"}],
            mitigations=[{"id": "M6", "owner": "Privacy owner"}],
            open_questions=[],
            owners=[{"role": "Privacy owner"}],
            launch_gates=[{"id": "LG1", "status": "blocked"}],
            source_ideas=[{"id": "bu-privacy"}],
        )

        dumped = response.model_dump()
        assert dumped["schema_version"] == "max.design_brief.privacy_impact_assessment.v1"
        assert dumped["design_brief"]["id"] == "dbf-privacy"
        assert dumped["summary"]["privacy_gate"] == "privacy_review_required"
        assert dumped["data_categories"][0]["id"] == "regulated_sensitive_data"

    def test_response_required_fields(self):
        with pytest.raises(ValidationError) as exc_info:
            DesignBriefPrivacyImpactAssessmentResponse()

        missing_fields = {error["loc"][0] for error in exc_info.value.errors()}
        assert "schema_version" in missing_fields
        assert "design_brief" in missing_fields
        assert "privacy_context" in missing_fields
        assert "data_categories" in missing_fields


class TestDesignBriefExperimentBacklogResponse:
    def test_preserves_experiment_backlog_artifact_sections(self):
        response = DesignBriefExperimentBacklogResponse(
            schema_version="max.design_brief.experiment_backlog.v1",
            kind="max.design_brief.experiment_backlog",
            source={"project": "max", "entity_type": "design_brief", "id": "dbf-backlog"},
            design_brief={"id": "dbf-backlog", "title": "Experiment Backlog Brief"},
            summary={"backlog_item_count": 1, "evidence_gap_count": 1},
            backlog_items=[
                {
                    "id": "EXP-001",
                    "title": "Validate buyer urgency",
                    "priority_score": 92,
                }
            ],
            evidence_references=[{"id": "sig-backlog", "kind": "signal"}],
            evidence_gaps=[{"id": "GAP-001", "field": "buyer", "gap": "Missing buyer proof"}],
            recommended_next_actions=[{"id": "NEXT-001", "action": "Run interviews"}],
            source_ideas=[{"id": "bu-backlog"}],
        )

        dumped = response.model_dump()
        assert dumped["schema_version"] == "max.design_brief.experiment_backlog.v1"
        assert dumped["design_brief"]["id"] == "dbf-backlog"
        assert dumped["summary"]["backlog_item_count"] == 1
        assert dumped["backlog_items"][0]["priority_score"] == 92

    def test_response_required_fields(self):
        with pytest.raises(ValidationError) as exc_info:
            DesignBriefExperimentBacklogResponse()

        missing_fields = {error["loc"][0] for error in exc_info.value.errors()}
        assert "schema_version" in missing_fields
        assert "design_brief" in missing_fields
        assert "backlog_items" in missing_fields


class TestDesignBriefGtmChannelPlanResponse:
    def test_preserves_nested_channel_recommendation_fields(self):
        response = DesignBriefGtmChannelPlanResponse(
            schema_version="max.design_brief.gtm_channel_plan.v1",
            kind="max.design_brief.gtm_channel_plan",
            source={"id": "dbf-gtm"},
            design_brief={"id": "dbf-gtm", "title": "GTM Brief"},
            summary={"primary_channel": "design partner outreach"},
            channel_recommendations=[
                {
                    "id": "GTM1",
                    "channel": "design partner outreach",
                    "success_metric": {
                        "metric": "qualified_conversation_rate",
                        "target": "25%+ positive replies",
                    },
                    "tactics": [
                        {
                            "name": "warm account list",
                            "owner": "product marketing",
                            "description": "Identify qualified accounts.",
                        }
                    ],
                }
            ],
            launch_sequence=[],
            measurement_plan=[],
            source_ideas=[],
        )

        dumped = response.model_dump()
        recommendation = dumped["channel_recommendations"][0]
        assert recommendation["success_metric"]["target"] == "25%+ positive replies"
        assert recommendation["tactics"][0]["owner"] == "product marketing"

    def test_required_fields(self):
        with pytest.raises(ValidationError) as exc_info:
            DesignBriefGtmChannelPlanResponse()

        missing_fields = {error["loc"][0] for error in exc_info.value.errors()}
        assert "schema_version" in missing_fields
        assert "channel_recommendations" in missing_fields


class TestDesignBriefRolloutCommsPlanResponse:
    def test_preserves_nested_rollout_comms_fields(self):
        response = DesignBriefRolloutCommsPlanResponse(
            schema_version="max.design_brief.rollout_comms_plan.v1",
            kind="max.design_brief.rollout_comms_plan",
            source={"id": "dbf-rollout"},
            design_brief={"id": "dbf-rollout", "title": "Rollout Brief"},
            summary={"rollout_goal": "Coordinate rollout communications."},
            target_audiences=[
                {
                    "id": "pilot_customers",
                    "name": "Pilot customers",
                    "type": "external",
                    "need": "Know what changed.",
                    "message_angle": "Early value",
                    "preferred_channels": ["email"],
                    "source_idea_ids": ["bu-rollout"],
                }
            ],
            launch_phases=[
                {
                    "id": "prep",
                    "sequence": 1,
                    "name": "Prep and message lock",
                    "timing": "T-10",
                    "objective": "Confirm scope.",
                    "owner": "Product lead",
                    "exit_criteria": "Messages approved.",
                    "source_idea_ids": ["bu-rollout"],
                }
            ],
            channel_message_matrix=[
                {
                    "id": "RCM1",
                    "phase_id": "prep",
                    "phase": "Prep and message lock",
                    "audience_id": "pilot_customers",
                    "audience": "Pilot customers",
                    "channel": "email",
                    "message": "Try the launch.",
                    "call_to_action": "Reply with feedback.",
                    "owner": "Product lead",
                    "source_idea_ids": ["bu-rollout"],
                    "source_fields": ["mvp_scope"],
                }
            ],
            internal_enablement_notes=[
                {
                    "id": "IEN1",
                    "topic": "Positioning",
                    "owner": "Product marketing",
                    "detail": "Explain the rollout.",
                    "source_idea_ids": ["bu-rollout"],
                    "source_fields": ["title"],
                }
            ],
            customer_facing_announcement_drafts=[
                {
                    "id": "CFA1",
                    "name": "Pilot invitation email",
                    "channel": "email",
                    "audience": "pilot user",
                    "headline": "Join the rollout",
                    "body": "The rollout is ready.",
                    "call_to_action": "Request access.",
                    "source_idea_ids": ["bu-rollout"],
                    "source_fields": ["workflow_context"],
                }
            ],
            risk_faq_hooks=[
                {
                    "id": "FAQ1",
                    "question": "How are we handling support?",
                    "answer_hook": "Name the owner.",
                    "source": "design_brief.risks",
                    "source_idea_ids": ["bu-rollout"],
                }
            ],
            evidence_references=[
                {
                    "id": "sig-rollout",
                    "type": "evidence_signal",
                    "summary": "Evidence signal linked to source idea.",
                    "source_idea_ids": ["bu-rollout"],
                }
            ],
            readiness_warnings=[
                {
                    "id": "RW1",
                    "severity": "medium",
                    "warning": "Keep rollout controlled.",
                    "recommended_action": "Limit broad announcement.",
                }
            ],
            source_ideas=[{"id": "bu-rollout"}],
        )

        dumped = response.model_dump()
        assert dumped["target_audiences"][0]["preferred_channels"] == ["email"]
        assert dumped["launch_phases"][0]["sequence"] == 1
        assert dumped["channel_message_matrix"][0]["call_to_action"] == "Reply with feedback."
        assert dumped["customer_facing_announcement_drafts"][0]["headline"] == "Join the rollout"
        assert dumped["evidence_references"][0]["type"] == "evidence_signal"
        assert dumped["readiness_warnings"][0]["severity"] == "medium"

    def test_required_fields(self):
        with pytest.raises(ValidationError) as exc_info:
            DesignBriefRolloutCommsPlanResponse()

        missing_fields = {error["loc"][0] for error in exc_info.value.errors()}
        assert "schema_version" in missing_fields
        assert "target_audiences" in missing_fields
        assert "channel_message_matrix" in missing_fields
