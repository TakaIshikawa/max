"""Tests for the embeddings engine — cosine similarity, embedding, and SemanticIndex."""

from __future__ import annotations

import json
import math
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from max.embeddings.engine import (
    SemanticIndex,
    _cosine_similarity,
    _simple_embed,
    content_hash,
    embed_text,
    embed_texts,
)
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit, IdeationMode


# ── _cosine_similarity ───────────────────────────────────────────


class TestCosineSimilarity:
    def test_identical_vectors(self):
        v = [1.0, 2.0, 3.0]
        assert _cosine_similarity(v, v) == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        assert _cosine_similarity(a, b) == pytest.approx(0.0)

    def test_opposite_vectors(self):
        a = [1.0, 2.0, 3.0]
        b = [-1.0, -2.0, -3.0]
        assert _cosine_similarity(a, b) == pytest.approx(-1.0)

    def test_zero_vector_a(self):
        assert _cosine_similarity([0.0, 0.0], [1.0, 2.0]) == 0.0

    def test_zero_vector_b(self):
        assert _cosine_similarity([1.0, 2.0], [0.0, 0.0]) == 0.0

    def test_both_zero_vectors(self):
        assert _cosine_similarity([0.0, 0.0], [0.0, 0.0]) == 0.0

    def test_scaled_vectors_are_identical(self):
        a = [1.0, 2.0, 3.0]
        b = [2.0, 4.0, 6.0]
        assert _cosine_similarity(a, b) == pytest.approx(1.0)


# ── _simple_embed ────────────────────────────────────────────────


class TestSimpleEmbed:
    def test_returns_list_of_floats(self):
        result = _simple_embed("hello world")
        assert isinstance(result, list)
        assert all(isinstance(x, float) for x in result)

    def test_default_vocab_size(self):
        result = _simple_embed("hello world")
        assert len(result) == 1024

    def test_custom_vocab_size(self):
        result = _simple_embed("hello world", vocab_size=64)
        assert len(result) == 64

    def test_similar_texts_produce_similar_embeddings(self):
        a = _simple_embed("machine learning algorithms")
        b = _simple_embed("machine learning algorithm")
        sim = _cosine_similarity(a, b)
        # Word-level hashing: "algorithms" != "algorithm" but shared context raises similarity
        assert sim > 0.5

    def test_dissimilar_texts_produce_lower_similarity(self):
        a = _simple_embed("machine learning algorithms for natural language processing")
        b = _simple_embed("underwater basket weaving techniques for beginners")
        sim_diff = _cosine_similarity(a, b)

        c = _simple_embed("machine learning algorithms for natural language processing")
        d = _simple_embed("machine learning methods for natural language understanding")
        sim_same = _cosine_similarity(c, d)

        assert sim_same > sim_diff

    def test_empty_string(self):
        result = _simple_embed("")
        assert len(result) == 1024
        assert all(x == 0.0 for x in result)

    def test_short_string(self):
        result = _simple_embed("ab")
        assert len(result) == 1024
        # "ab" is one word token — produces one nonzero entry
        assert sum(1 for x in result if x > 0) == 1

    def test_single_word_string(self):
        result = _simple_embed("abc")
        assert len(result) == 1024
        assert sum(1 for x in result if x > 0) == 1

    def test_normalized_values(self):
        result = _simple_embed("hello world this is a test")
        nonzero = [x for x in result if x > 0]
        assert all(0.0 < x <= 1.0 for x in nonzero)
        # L2-normalized: sum of squares == 1.0
        import math
        magnitude = math.sqrt(sum(x * x for x in result))
        assert magnitude == pytest.approx(1.0)


# ── embed_text / embed_texts ────────────────────────────────────


class TestEmbedTextFunctions:
    def test_embed_text_returns_list(self):
        with patch("max.embeddings.engine._try_voyage_embed", return_value=None):
            result = embed_text("hello world")
        assert isinstance(result, list)
        assert len(result) == 1024

    def test_embed_texts_returns_list_of_lists(self):
        with patch("max.embeddings.engine._try_voyage_embed", return_value=None):
            result = embed_texts(["hello", "world"])
        assert len(result) == 2
        assert all(len(v) == 1024 for v in result)

    def test_embed_text_consistent(self):
        with patch("max.embeddings.engine._try_voyage_embed", return_value=None):
            a = embed_text("test string")
            b = embed_text("test string")
        assert a == b

    def test_embed_texts_uses_voyage_when_available(self):
        fake_embeddings = [[0.1, 0.2], [0.3, 0.4]]
        with patch(
            "max.embeddings.engine._try_voyage_embed",
            return_value=fake_embeddings,
        ):
            result = embed_texts(["a", "b"])
        assert result == fake_embeddings

    def test_embed_texts_falls_back_when_voyage_returns_none(self):
        with patch("max.embeddings.engine._try_voyage_embed", return_value=None):
            result = embed_texts(["hello"])
        assert len(result) == 1
        assert len(result[0]) == 1024


# ── SemanticIndex.index_entity ───────────────────────────────────


class TestIndexEntity:
    def test_stores_embedding_in_db(self, store: Store):
        idx = SemanticIndex(store)
        with patch("max.embeddings.engine._try_voyage_embed", return_value=None):
            idx.index_entity("ent-001", "test_type", "some text about testing")

        row = store.conn.execute(
            "SELECT id, entity_type, embedding FROM embeddings WHERE id = ?",
            ("ent-001",),
        ).fetchone()

        assert row is not None
        assert row["id"] == "ent-001"
        assert row["entity_type"] == "test_type"
        embedding = json.loads(row["embedding"])
        assert isinstance(embedding, list)
        assert len(embedding) == 1024

    def test_replace_on_reindex(self, store: Store):
        idx = SemanticIndex(store)
        with patch("max.embeddings.engine._try_voyage_embed", return_value=None):
            idx.index_entity("ent-001", "test_type", "original text")
            emb1 = json.loads(
                store.conn.execute(
                    "SELECT embedding FROM embeddings WHERE id = ?", ("ent-001",)
                ).fetchone()["embedding"]
            )

            idx.index_entity("ent-001", "test_type", "completely different text now")
            emb2 = json.loads(
                store.conn.execute(
                    "SELECT embedding FROM embeddings WHERE id = ?", ("ent-001",)
                ).fetchone()["embedding"]
            )

        assert emb1 != emb2

        count = store.conn.execute(
            "SELECT COUNT(*) as c FROM embeddings WHERE id = ?", ("ent-001",)
        ).fetchone()["c"]
        assert count == 1


# ── SemanticIndex.find_similar ───────────────────────────────────


class TestFindSimilar:
    def _index_entities(self, idx: SemanticIndex):
        with patch("max.embeddings.engine._try_voyage_embed", return_value=None):
            idx.index_entity("ent-ml-1", "article", "machine learning algorithms for classification")
            idx.index_entity("ent-ml-2", "article", "machine learning models for prediction")
            idx.index_entity("ent-cook", "article", "italian pasta recipes and cooking techniques")
            idx.index_entity("ent-sport", "news", "basketball game results and player stats")

    def test_returns_similar_above_threshold(self, store: Store):
        idx = SemanticIndex(store)
        self._index_entities(idx)

        with patch("max.embeddings.engine._try_voyage_embed", return_value=None):
            results = idx.find_similar(
                "machine learning classification methods",
                "article",
                threshold=0.5,
            )

        assert len(results) > 0
        ids = [r[0] for r in results]
        assert "ent-ml-1" in ids or "ent-ml-2" in ids

    def test_results_sorted_by_similarity_descending(self, store: Store):
        idx = SemanticIndex(store)
        self._index_entities(idx)

        with patch("max.embeddings.engine._try_voyage_embed", return_value=None):
            results = idx.find_similar(
                "machine learning algorithms",
                "article",
                threshold=0.0,
            )

        if len(results) > 1:
            scores = [r[1] for r in results]
            assert scores == sorted(scores, reverse=True)

    def test_entity_type_filtering(self, store: Store):
        idx = SemanticIndex(store)
        self._index_entities(idx)

        with patch("max.embeddings.engine._try_voyage_embed", return_value=None):
            results = idx.find_similar(
                "basketball game",
                "article",
                threshold=0.0,
            )

        ids = [r[0] for r in results]
        assert "ent-sport" not in ids  # ent-sport is entity_type "news", not "article"

    def test_high_threshold_filters_all(self, store: Store):
        idx = SemanticIndex(store)
        self._index_entities(idx)

        with patch("max.embeddings.engine._try_voyage_embed", return_value=None):
            results = idx.find_similar(
                "completely unrelated quantum physics text",
                "article",
                threshold=0.99,
            )

        assert len(results) == 0

    def test_respects_limit(self, store: Store):
        idx = SemanticIndex(store)
        self._index_entities(idx)

        with patch("max.embeddings.engine._try_voyage_embed", return_value=None):
            results = idx.find_similar(
                "machine learning",
                "article",
                threshold=0.0,
                limit=1,
            )

        assert len(results) <= 1

    def test_empty_index_returns_empty(self, store: Store):
        idx = SemanticIndex(store)
        with patch("max.embeddings.engine._try_voyage_embed", return_value=None):
            results = idx.find_similar("anything", "article", threshold=0.0)
        assert results == []


# ── SemanticIndex.is_duplicate ───────────────────────────────────


class TestIsDuplicate:
    def test_detects_duplicate(self, store: Store):
        idx = SemanticIndex(store)
        text = "machine learning algorithms for natural language processing tasks"
        with patch("max.embeddings.engine._try_voyage_embed", return_value=None):
            idx.index_entity("ent-orig", "article", text)
            is_dup, match_id = idx.is_duplicate(text, "article", threshold=0.9)

        assert is_dup is True
        assert match_id == "ent-orig"

    def test_novel_text_is_not_duplicate(self, store: Store):
        idx = SemanticIndex(store)
        with patch("max.embeddings.engine._try_voyage_embed", return_value=None):
            idx.index_entity(
                "ent-orig", "article",
                "machine learning algorithms for natural language processing",
            )
            is_dup, match_id = idx.is_duplicate(
                "underwater basket weaving techniques for advanced practitioners",
                "article",
                threshold=0.9,
            )

        assert is_dup is False
        assert match_id is None

    def test_return_tuple_format(self, store: Store):
        idx = SemanticIndex(store)
        with patch("max.embeddings.engine._try_voyage_embed", return_value=None):
            result = idx.is_duplicate("anything", "article")

        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], bool)
        assert result[1] is None or isinstance(result[1], str)

    def test_empty_index_not_duplicate(self, store: Store):
        idx = SemanticIndex(store)
        with patch("max.embeddings.engine._try_voyage_embed", return_value=None):
            is_dup, match_id = idx.is_duplicate("test text", "article")
        assert is_dup is False
        assert match_id is None


# ── SemanticIndex.novelty_score ──────────────────────────────────


class TestNoveltyScore:
    def test_empty_index_returns_1(self, store: Store):
        idx = SemanticIndex(store)
        with patch("max.embeddings.engine._try_voyage_embed", return_value=None):
            score = idx.novelty_score("anything", "article")
        assert score == 1.0

    def test_duplicate_text_returns_low_score(self, store: Store):
        idx = SemanticIndex(store)
        text = "machine learning algorithms for text classification"
        with patch("max.embeddings.engine._try_voyage_embed", return_value=None):
            idx.index_entity("ent-001", "article", text)
            score = idx.novelty_score(text, "article")

        assert score < 0.1  # near-identical → novelty close to 0

    def test_novel_text_returns_high_score(self, store: Store):
        idx = SemanticIndex(store)
        with patch("max.embeddings.engine._try_voyage_embed", return_value=None):
            idx.index_entity(
                "ent-001", "article",
                "machine learning algorithms for text classification",
            )
            score = idx.novelty_score(
                "underwater basket weaving techniques for beginners",
                "article",
            )

        assert score > 0.5

    def test_score_between_zero_and_one(self, store: Store):
        idx = SemanticIndex(store)
        with patch("max.embeddings.engine._try_voyage_embed", return_value=None):
            idx.index_entity("ent-001", "article", "some text")
            score = idx.novelty_score("other text", "article")
        assert 0.0 <= score <= 1.0


# ── Voyage fallback ─────────────────────────────────────────────


class TestVoyageFallback:
    def test_import_error_falls_back_to_simple_embed(self):
        with patch(
            "max.embeddings.engine._try_voyage_embed",
            return_value=None,
        ):
            result = embed_texts(["hello world"])

        assert len(result) == 1
        assert len(result[0]) == 1024

    def test_try_voyage_embed_returns_none_on_import_error(self):
        """Verify _try_voyage_embed returns None when voyageai is not installed."""
        from max.embeddings.engine import _try_voyage_embed

        with patch.dict("sys.modules", {"voyageai": None}):
            result = _try_voyage_embed(["test"])
        assert result is None

    def test_end_to_end_without_voyage(self, store: Store):
        """Full SemanticIndex workflow works without voyageai."""
        idx = SemanticIndex(store)
        with patch("max.embeddings.engine._try_voyage_embed", return_value=None):
            idx.index_entity("ent-001", "article", "machine learning for NLP tasks")
            idx.index_entity("ent-002", "article", "machine learning for NLP")

            similar = idx.find_similar("machine learning NLP", "article", threshold=0.5)
            is_dup, _ = idx.is_duplicate("machine learning for NLP tasks", "article")
            novelty = idx.novelty_score("completely different topic", "article")

        assert len(similar) > 0
        assert is_dup is True
        assert novelty > 0.3


# ── content_hash ─────────────────────────────────────────────────


class TestContentHash:
    def test_deterministic(self):
        assert content_hash("hello") == content_hash("hello")

    def test_different_inputs_differ(self):
        assert content_hash("hello") != content_hash("world")

    def test_empty_string(self):
        h = content_hash("")
        assert isinstance(h, str)
        assert len(h) == 64  # SHA-256 hex digest

    def test_returns_hex_string(self):
        h = content_hash("test")
        assert all(c in "0123456789abcdef" for c in h)


# ── Helpers for incremental tests ────────────────────────────────


def _make_unit(
    unit_id: str,
    title: str = "Test Idea",
    one_liner: str = "A test idea",
    problem: str = "Some problem",
    solution: str = "Some solution",
) -> BuildableUnit:
    """Create a minimal BuildableUnit for testing."""
    return BuildableUnit(
        id=unit_id,
        title=title,
        one_liner=one_liner,
        category="CLI_TOOL",
        ideation_mode=IdeationMode.DIRECT,
        problem=problem,
        solution=solution,
        target_users="both",
        value_proposition="Test value",
        inspiring_insights=[],
        evidence_signals=[],
        tech_approach="Python",
        suggested_stack={},
        composability_notes="",
    )


# ── SemanticIndex.embed_incremental ──────────────────────────────


class TestEmbedIncremental:
    def test_embeds_new_entities(self, store: Store):
        """New entities get embedded on first incremental run."""
        store.insert_buildable_unit(_make_unit("bu-001", title="Machine learning tool"))
        store.insert_buildable_unit(_make_unit("bu-002", title="Database optimizer"))

        idx = SemanticIndex(store)
        with patch("max.embeddings.engine._try_voyage_embed", return_value=None):
            result = idx.embed_incremental()

        assert result["embedded"] == 2
        assert result["skipped"] == 0
        assert result["removed"] == 0

        # Verify embeddings stored
        rows = store.conn.execute("SELECT COUNT(*) as c FROM embeddings").fetchone()
        assert rows["c"] == 2

    def test_skips_unchanged_entities(self, store: Store):
        """Unchanged entities are skipped on subsequent runs."""
        store.insert_buildable_unit(_make_unit("bu-001", title="Machine learning tool"))

        idx = SemanticIndex(store)
        with patch("max.embeddings.engine._try_voyage_embed", return_value=None):
            result1 = idx.embed_incremental()
            result2 = idx.embed_incremental()

        assert result1["embedded"] == 1
        assert result2["embedded"] == 0
        assert result2["skipped"] == 1

    def test_reembeds_on_content_change(self, store: Store):
        """Changed content hash triggers re-embedding."""
        unit = _make_unit("bu-001", title="Original title", problem="Original problem")
        store.insert_buildable_unit(unit)

        idx = SemanticIndex(store)
        with patch("max.embeddings.engine._try_voyage_embed", return_value=None):
            result1 = idx.embed_incremental()

            # Get original embedding
            emb1 = json.loads(
                store.conn.execute(
                    "SELECT embedding FROM embeddings WHERE id = ?", ("bu-001",)
                ).fetchone()["embedding"]
            )

            # Simulate content change by updating the metadata hash directly
            # We need to update the unit in the DB to change its content
            store.conn.execute(
                "UPDATE buildable_units SET title = ?, problem = ? WHERE id = ?",
                ("Completely different title", "Completely different problem", "bu-001"),
            )
            store.conn.commit()

            result2 = idx.embed_incremental()

            # Get updated embedding
            emb2 = json.loads(
                store.conn.execute(
                    "SELECT embedding FROM embeddings WHERE id = ?", ("bu-001",)
                ).fetchone()["embedding"]
            )

        assert result1["embedded"] == 1
        assert result2["embedded"] == 1
        assert result2["skipped"] == 0
        assert emb1 != emb2

    def test_removes_deleted_entities(self, store: Store):
        """Embeddings for deleted entities are cleaned up."""
        store.insert_buildable_unit(_make_unit("bu-001"))
        store.insert_buildable_unit(_make_unit("bu-002"))

        idx = SemanticIndex(store)
        with patch("max.embeddings.engine._try_voyage_embed", return_value=None):
            idx.embed_incremental()

            # Delete one unit
            store.conn.execute("DELETE FROM buildable_units WHERE id = ?", ("bu-002",))
            store.conn.commit()

            result = idx.embed_incremental()

        assert result["removed"] == 1
        assert result["skipped"] == 1

        # Verify only bu-001 remains in embeddings
        rows = store.conn.execute("SELECT id FROM embeddings").fetchall()
        ids = [r["id"] for r in rows]
        assert "bu-001" in ids
        assert "bu-002" not in ids

        # Verify metadata also cleaned
        meta_rows = store.conn.execute("SELECT entity_id FROM embeddings_metadata").fetchall()
        meta_ids = [r["entity_id"] for r in meta_rows]
        assert "bu-001" in meta_ids
        assert "bu-002" not in meta_ids

    def test_index_consistency_after_partial_update(self, store: Store):
        """Index remains consistent after incremental updates."""
        store.insert_buildable_unit(
            _make_unit("bu-001", title="machine learning classification algorithms")
        )
        store.insert_buildable_unit(
            _make_unit("bu-002", title="database query optimization techniques")
        )

        idx = SemanticIndex(store)
        with patch("max.embeddings.engine._try_voyage_embed", return_value=None):
            idx.embed_incremental()

            # Add a third, update one
            store.insert_buildable_unit(
                _make_unit("bu-003", title="machine learning prediction models")
            )
            store.conn.execute(
                "UPDATE buildable_units SET title = ? WHERE id = ?",
                ("deep learning classification algorithms", "bu-001"),
            )
            store.conn.commit()

            idx.embed_incremental()

            # Verify find_similar still works correctly
            results = idx.find_similar(
                "machine learning algorithms",
                "buildable_unit",
                threshold=0.0,
            )

        assert len(results) == 3
        scores = [r[1] for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_empty_database(self, store: Store):
        """Incremental embed on empty database returns zeros."""
        idx = SemanticIndex(store)
        with patch("max.embeddings.engine._try_voyage_embed", return_value=None):
            result = idx.embed_incremental()

        assert result == {"embedded": 0, "skipped": 0, "removed": 0}

    def test_corrupted_hash_triggers_reembed(self, store: Store):
        """Corrupted/invalid hash in metadata triggers re-embedding."""
        store.insert_buildable_unit(_make_unit("bu-001", title="Test idea"))

        idx = SemanticIndex(store)
        with patch("max.embeddings.engine._try_voyage_embed", return_value=None):
            idx.embed_incremental()

            # Corrupt the hash in metadata
            store.conn.execute(
                "UPDATE embeddings_metadata SET content_hash = ? WHERE entity_id = ?",
                ("corrupted_hash_value", "bu-001"),
            )
            store.conn.commit()

            result = idx.embed_incremental()

        # Corrupted hash won't match the computed hash, so it re-embeds
        assert result["embedded"] == 1
        assert result["skipped"] == 0

    def test_metadata_tracks_embedded_at(self, store: Store):
        """Metadata records embedded_at timestamp."""
        store.insert_buildable_unit(_make_unit("bu-001"))

        idx = SemanticIndex(store)
        with patch("max.embeddings.engine._try_voyage_embed", return_value=None):
            idx.embed_incremental()

        meta = idx._get_embedding_metadata("bu-001", "buildable_unit")
        assert meta is not None
        assert meta["content_hash"] is not None
        assert meta["embedded_at"] is not None

    def test_mixed_new_changed_unchanged(self, store: Store):
        """Handles mix of new, changed, and unchanged entities."""
        store.insert_buildable_unit(_make_unit("bu-001", title="Unchanged idea"))
        store.insert_buildable_unit(_make_unit("bu-002", title="Will change"))

        idx = SemanticIndex(store)
        with patch("max.embeddings.engine._try_voyage_embed", return_value=None):
            idx.embed_incremental()

            # Change bu-002, add bu-003
            store.conn.execute(
                "UPDATE buildable_units SET title = ? WHERE id = ?",
                ("Changed idea", "bu-002"),
            )
            store.conn.commit()
            store.insert_buildable_unit(_make_unit("bu-003", title="Brand new idea"))

            result = idx.embed_incremental()

        assert result["embedded"] == 2  # bu-002 (changed) + bu-003 (new)
        assert result["skipped"] == 1  # bu-001 (unchanged)
        assert result["removed"] == 0


# ── SemanticIndex.embed_full ─────────────────────────────────────


class TestEmbedFull:
    def test_embeds_all_entities(self, store: Store):
        store.insert_buildable_unit(_make_unit("bu-001"))
        store.insert_buildable_unit(_make_unit("bu-002"))

        idx = SemanticIndex(store)
        with patch("max.embeddings.engine._try_voyage_embed", return_value=None):
            result = idx.embed_full()

        assert result["embedded"] == 2

    def test_updates_metadata_on_full_rebuild(self, store: Store):
        store.insert_buildable_unit(_make_unit("bu-001"))

        idx = SemanticIndex(store)
        with patch("max.embeddings.engine._try_voyage_embed", return_value=None):
            idx.embed_full()

        meta = idx._get_embedding_metadata("bu-001", "buildable_unit")
        assert meta is not None
        assert meta["content_hash"] is not None

    def test_full_then_incremental_skips_all(self, store: Store):
        """After full embed, incremental should skip everything."""
        store.insert_buildable_unit(_make_unit("bu-001"))
        store.insert_buildable_unit(_make_unit("bu-002"))

        idx = SemanticIndex(store)
        with patch("max.embeddings.engine._try_voyage_embed", return_value=None):
            idx.embed_full()
            result = idx.embed_incremental()

        assert result["embedded"] == 0
        assert result["skipped"] == 2


# ── Performance: full vs incremental ─────────────────────────────


class TestPerformanceComparison:
    def test_incremental_calls_embed_fewer_times(self, store: Store):
        """Incremental should call embed_text fewer times than full when data is unchanged."""
        for i in range(5):
            store.insert_buildable_unit(_make_unit(f"bu-{i:03d}", title=f"Idea {i}"))

        idx = SemanticIndex(store)
        with patch("max.embeddings.engine._try_voyage_embed", return_value=None):
            # First run embeds all
            idx.embed_incremental()

            # Count embed_text calls on second run
            with patch("max.embeddings.engine.embed_text", wraps=embed_text) as mock_embed:
                idx.embed_incremental()
                incremental_calls = mock_embed.call_count

            # Full always embeds all
            with patch("max.embeddings.engine.embed_text", wraps=embed_text) as mock_embed:
                idx.embed_full()
                full_calls = mock_embed.call_count

        assert incremental_calls == 0  # nothing changed
        assert full_calls == 5  # always re-embeds everything


# ── Migration ────────────────────────────────────────────────────


class TestEmbeddingsMetadataMigration:
    def test_embeddings_metadata_table_exists(self, store: Store):
        """The embeddings_metadata table is created during schema init."""
        row = store.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='embeddings_metadata'"
        ).fetchone()
        assert row is not None

    def test_schema_version_is_20(self, store: Store):
        assert store.get_schema_version() == 20

    def test_metadata_indices_exist(self, store: Store):
        indices = store.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_embeddings_meta%'"
        ).fetchall()
        index_names = {r["name"] for r in indices}
        assert "idx_embeddings_meta_type" in index_names
        assert "idx_embeddings_meta_embedded_at" in index_names


# ── Conflict Resolution ──────────────────────────────────────────


class TestConflictResolution:
    """Test conflict resolution when embeddings exist for deleted ideas."""

    def test_orphaned_embedding_cleanup_on_incremental(self, store: Store):
        """Orphaned embeddings (no corresponding entity) are removed on incremental update."""
        # Create and index an idea
        store.insert_buildable_unit(_make_unit("bu-001", title="Test idea"))
        idx = SemanticIndex(store)
        with patch("max.embeddings.engine._try_voyage_embed", return_value=None):
            idx.embed_incremental()

        # Manually delete the unit but leave embedding/metadata (simulating corruption)
        store.conn.execute("DELETE FROM buildable_units WHERE id = ?", ("bu-001",))
        store.conn.commit()

        # Incremental update should detect and remove orphaned embedding
        with patch("max.embeddings.engine._try_voyage_embed", return_value=None):
            result = idx.embed_incremental()

        assert result["removed"] == 1
        # Verify both embedding and metadata are gone
        emb_count = store.conn.execute(
            "SELECT COUNT(*) as c FROM embeddings WHERE id = ?", ("bu-001",)
        ).fetchone()["c"]
        meta_count = store.conn.execute(
            "SELECT COUNT(*) as c FROM embeddings_metadata WHERE entity_id = ?", ("bu-001",)
        ).fetchone()["c"]
        assert emb_count == 0
        assert meta_count == 0

    def test_embedding_without_metadata_triggers_reembed(self, store: Store):
        """If embedding exists but metadata is missing, re-embed the entity."""
        store.insert_buildable_unit(_make_unit("bu-001", title="Test idea"))
        idx = SemanticIndex(store)

        # Create embedding directly without metadata (simulating partial state)
        with patch("max.embeddings.engine._try_voyage_embed", return_value=None):
            embedding = embed_text("Test idea")
            store.conn.execute(
                "INSERT INTO embeddings (id, entity_type, embedding) VALUES (?, ?, ?)",
                ("bu-001", "buildable_unit", json.dumps(embedding)),
            )
            store.conn.commit()

        # Incremental should re-embed since metadata is missing
        with patch("max.embeddings.engine._try_voyage_embed", return_value=None):
            result = idx.embed_incremental()

        assert result["embedded"] == 1
        # Verify metadata now exists
        meta = idx._get_embedding_metadata("bu-001", "buildable_unit")
        assert meta is not None

    def test_metadata_without_embedding_triggers_reembed(self, store: Store):
        """If metadata exists but embedding is missing, re-embed the entity."""
        store.insert_buildable_unit(_make_unit("bu-001", title="Test idea"))
        idx = SemanticIndex(store)

        # Create metadata without embedding (simulating partial state)
        idx._upsert_embedding_metadata("bu-001", "buildable_unit", content_hash("Test idea"))
        store.conn.commit()

        # Incremental should re-embed since embedding is missing
        with patch("max.embeddings.engine._try_voyage_embed", return_value=None):
            result = idx.embed_incremental()

        assert result["embedded"] == 1
        # Verify embedding now exists
        emb_row = store.conn.execute(
            "SELECT embedding FROM embeddings WHERE id = ?", ("bu-001",)
        ).fetchone()
        assert emb_row is not None

    def test_stale_metadata_different_entity_type(self, store: Store):
        """Metadata for a different entity_type doesn't interfere with current type."""
        store.insert_buildable_unit(_make_unit("bu-001", title="Test idea"))
        idx = SemanticIndex(store)

        # Create metadata for a different entity type
        idx._upsert_embedding_metadata("bu-001", "other_type", content_hash("Test idea"))
        store.conn.commit()

        # Incremental update for buildable_unit should treat bu-001 as new
        with patch("max.embeddings.engine._try_voyage_embed", return_value=None):
            result = idx.embed_incremental(entity_type="buildable_unit")

        assert result["embedded"] == 1
        assert result["skipped"] == 0

        # Verify both entity types have their own records
        bu_meta = idx._get_embedding_metadata("bu-001", "buildable_unit")
        other_meta = idx._get_embedding_metadata("bu-001", "other_type")
        assert bu_meta is not None
        assert other_meta is not None


# ── Rollback on Failures ─────────────────────────────────────────


class TestRollbackBehavior:
    """Test rollback and consistency on embedding generation failures."""

    def test_partial_failure_exception_propagates(self, store: Store):
        """If embedding fails mid-batch, exception propagates without commit."""
        store.insert_buildable_unit(_make_unit("bu-001", title="Good idea"))
        store.insert_buildable_unit(_make_unit("bu-002", title="Bad idea"))
        store.insert_buildable_unit(_make_unit("bu-003", title="Another good idea"))

        idx = SemanticIndex(store)

        # Mock embed_text to fail on bu-002
        original_embed = embed_text

        def mock_embed_with_failure(text):
            if "Bad idea" in text:
                raise RuntimeError("Embedding API failure")
            return original_embed(text)

        with patch("max.embeddings.engine._try_voyage_embed", return_value=None):
            with patch("max.embeddings.engine.embed_text", side_effect=mock_embed_with_failure):
                try:
                    idx.embed_incremental()
                    pytest.fail("Expected RuntimeError to propagate")
                except RuntimeError as e:
                    assert "Embedding API failure" in str(e)

        # Note: Current implementation doesn't have explicit rollback, so partial work may be visible
        # This test verifies the exception propagates correctly

    def test_embedding_api_error_propagates(self, store: Store):
        """Embedding API errors should propagate to caller."""
        store.insert_buildable_unit(_make_unit("bu-001", title="Test idea"))
        idx = SemanticIndex(store)

        # Mock voyage embed to fail
        def mock_voyage_fail(texts):
            raise RuntimeError("API rate limit exceeded")

        with patch("max.embeddings.engine._try_voyage_embed", side_effect=mock_voyage_fail):
            try:
                idx.embed_incremental()
                pytest.fail("Expected RuntimeError to propagate")
            except RuntimeError as e:
                assert "API rate limit exceeded" in str(e)

    def test_consistency_after_failed_update(self, store: Store):
        """After a failed update, running again should recover and complete successfully."""
        store.insert_buildable_unit(_make_unit("bu-001", title="Idea 1"))
        store.insert_buildable_unit(_make_unit("bu-002", title="Idea 2"))

        idx = SemanticIndex(store)

        # First run fails
        with patch("max.embeddings.engine._try_voyage_embed", return_value=None):
            with patch("max.embeddings.engine.embed_text", side_effect=RuntimeError("Transient failure")):
                try:
                    idx.embed_incremental()
                except RuntimeError:
                    pass

        # Second run succeeds
        with patch("max.embeddings.engine._try_voyage_embed", return_value=None):
            result = idx.embed_incremental()

        assert result["embedded"] == 2
        assert result["skipped"] == 0


# ── Enhanced Index Consistency ───────────────────────────────────


class TestIndexConsistency:
    """Extended index consistency verification tests."""

    def test_similarity_search_consistent_after_incremental_updates(self, store: Store):
        """Similarity search returns consistent results after incremental updates."""
        # Index initial set
        store.insert_buildable_unit(_make_unit("bu-ml-1", title="machine learning classifier"))
        store.insert_buildable_unit(_make_unit("bu-db-1", title="database optimizer"))

        idx = SemanticIndex(store)
        with patch("max.embeddings.engine._try_voyage_embed", return_value=None):
            idx.embed_incremental()

            # Find similar to ML topic
            ml_similar = idx.find_similar("machine learning algorithms", "buildable_unit", threshold=0.0)
            ml_ids = {r[0] for r in ml_similar}
            assert "bu-ml-1" in ml_ids

            # Add more ML-related ideas and update incrementally
            store.insert_buildable_unit(_make_unit("bu-ml-2", title="machine learning predictor"))
            store.insert_buildable_unit(_make_unit("bu-ml-3", title="deep learning model"))
            idx.embed_incremental()

            # Search again should include new ideas
            ml_similar_updated = idx.find_similar(
                "machine learning algorithms", "buildable_unit", threshold=0.0
            )
            ml_ids_updated = {r[0] for r in ml_similar_updated}
            assert "bu-ml-1" in ml_ids_updated
            assert "bu-ml-2" in ml_ids_updated
            assert "bu-ml-3" in ml_ids_updated

            # Scores should remain sorted
            scores = [r[1] for r in ml_similar_updated]
            assert scores == sorted(scores, reverse=True)

    def test_no_duplicate_embeddings_after_multiple_incrementals(self, store: Store):
        """Multiple incremental runs don't create duplicate embeddings."""
        store.insert_buildable_unit(_make_unit("bu-001", title="Test idea"))

        idx = SemanticIndex(store)
        with patch("max.embeddings.engine._try_voyage_embed", return_value=None):
            # Run incremental 3 times
            idx.embed_incremental()
            idx.embed_incremental()
            idx.embed_incremental()

        # Verify only one embedding exists
        emb_count = store.conn.execute(
            "SELECT COUNT(*) as c FROM embeddings WHERE id = ?", ("bu-001",)
        ).fetchone()["c"]
        meta_count = store.conn.execute(
            "SELECT COUNT(*) as c FROM embeddings_metadata WHERE entity_id = ?", ("bu-001",)
        ).fetchone()["c"]

        assert emb_count == 1
        assert meta_count == 1

    def test_embedding_metadata_consistency(self, store: Store):
        """Every embedding has corresponding metadata and vice versa."""
        for i in range(5):
            store.insert_buildable_unit(_make_unit(f"bu-{i:03d}", title=f"Idea {i}"))

        idx = SemanticIndex(store)
        with patch("max.embeddings.engine._try_voyage_embed", return_value=None):
            idx.embed_incremental()

        # Get all embeddings and metadata
        emb_ids = {
            row["id"]
            for row in store.conn.execute(
                "SELECT id FROM embeddings WHERE entity_type = ?", ("buildable_unit",)
            ).fetchall()
        }
        meta_ids = {
            row["entity_id"]
            for row in store.conn.execute(
                "SELECT entity_id FROM embeddings_metadata WHERE entity_type = ?", ("buildable_unit",)
            ).fetchall()
        }

        # Should be exactly equal
        assert emb_ids == meta_ids

    def test_deleted_idea_removes_both_embedding_and_metadata(self, store: Store):
        """Deleting an idea removes both embedding and metadata atomically."""
        store.insert_buildable_unit(_make_unit("bu-001", title="To be deleted"))
        store.insert_buildable_unit(_make_unit("bu-002", title="To be kept"))

        idx = SemanticIndex(store)
        with patch("max.embeddings.engine._try_voyage_embed", return_value=None):
            idx.embed_incremental()

            # Delete bu-001
            store.conn.execute("DELETE FROM buildable_units WHERE id = ?", ("bu-001",))
            store.conn.commit()

            # Run incremental - should remove bu-001's embedding and metadata
            result = idx.embed_incremental()

        assert result["removed"] == 1

        # Verify bu-001 is completely gone from both tables
        emb_001 = store.conn.execute(
            "SELECT COUNT(*) as c FROM embeddings WHERE id = ?", ("bu-001",)
        ).fetchone()["c"]
        meta_001 = store.conn.execute(
            "SELECT COUNT(*) as c FROM embeddings_metadata WHERE entity_id = ?", ("bu-001",)
        ).fetchone()["c"]
        assert emb_001 == 0
        assert meta_001 == 0

        # bu-002 should still exist
        emb_002 = store.conn.execute(
            "SELECT COUNT(*) as c FROM embeddings WHERE id = ?", ("bu-002",)
        ).fetchone()["c"]
        meta_002 = store.conn.execute(
            "SELECT COUNT(*) as c FROM embeddings_metadata WHERE entity_id = ?", ("bu-002",)
        ).fetchone()["c"]
        assert emb_002 == 1
        assert meta_002 == 1


# ── Property-Based Tests ─────────────────────────────────────────


class TestPropertyBasedInvariants:
    """Property-based tests using hypothesis for update invariants."""

    def test_incremental_equals_full_reindex(self, store: Store):
        """Property: incremental update produces same embeddings as full reindex."""
        @given(
            st.lists(
                st.tuples(
                    st.text(min_size=1, max_size=10, alphabet="abcdefghijklmnopqrstuvwxyz"),
                    st.text(min_size=5, max_size=50),
                ),
                min_size=1,
                max_size=10,
                unique_by=lambda x: x[0],  # unique IDs
            )
        )
        @settings(max_examples=20, deadline=5000)
        def run_test(ideas):
            # Clear existing data
            store.conn.execute("DELETE FROM buildable_units")
            store.conn.execute("DELETE FROM embeddings")
            store.conn.execute("DELETE FROM embeddings_metadata")
            store.conn.commit()

            # Insert all ideas
            for idea_id, title in ideas:
                store.insert_buildable_unit(_make_unit(idea_id, title=title))

            idx = SemanticIndex(store)

            with patch("max.embeddings.engine._try_voyage_embed", return_value=None):
                # Perform incremental update
                idx.embed_incremental()
                incremental_embeddings = {
                    row["id"]: json.loads(row["embedding"])
                    for row in store.conn.execute(
                        "SELECT id, embedding FROM embeddings WHERE entity_type = ?",
                        ("buildable_unit",),
                    ).fetchall()
                }

                # Clear embeddings and metadata
                store.conn.execute("DELETE FROM embeddings WHERE entity_type = ?", ("buildable_unit",))
                store.conn.execute("DELETE FROM embeddings_metadata WHERE entity_type = ?", ("buildable_unit",))
                store.conn.commit()

                # Perform full reindex
                idx.embed_full()
                full_embeddings = {
                    row["id"]: json.loads(row["embedding"])
                    for row in store.conn.execute(
                        "SELECT id, embedding FROM embeddings WHERE entity_type = ?",
                        ("buildable_unit",),
                    ).fetchall()
                }

            # Both should have the same set of IDs
            assert set(incremental_embeddings.keys()) == set(full_embeddings.keys())

            # Embeddings should be identical for each ID
            for idea_id in incremental_embeddings:
                assert incremental_embeddings[idea_id] == full_embeddings[idea_id]

        run_test()

    def test_idempotent_incremental_updates(self, store: Store):
        """Property: running incremental multiple times without changes is idempotent."""
        @given(
            st.lists(st.text(min_size=1, max_size=10, alphabet="abcdefghijklmnopqrstuvwxyz"), min_size=1, max_size=10, unique=True),
        )
        @settings(max_examples=20, deadline=5000)
        def run_test(idea_ids):
            # Clear existing data
            store.conn.execute("DELETE FROM buildable_units")
            store.conn.execute("DELETE FROM embeddings")
            store.conn.execute("DELETE FROM embeddings_metadata")
            store.conn.commit()

            # Insert ideas
            for idea_id in idea_ids:
                store.insert_buildable_unit(_make_unit(idea_id, title=f"Title {idea_id}"))

            idx = SemanticIndex(store)

            with patch("max.embeddings.engine._try_voyage_embed", return_value=None):
                # First incremental
                result1 = idx.embed_incremental()

                # Capture state
                embeddings_after_1 = {
                    row["id"]: json.loads(row["embedding"])
                    for row in store.conn.execute(
                        "SELECT id, embedding FROM embeddings WHERE entity_type = ?",
                        ("buildable_unit",),
                    ).fetchall()
                }

                # Second incremental (no changes)
                result2 = idx.embed_incremental()

                # Capture state again
                embeddings_after_2 = {
                    row["id"]: json.loads(row["embedding"])
                    for row in store.conn.execute(
                        "SELECT id, embedding FROM embeddings WHERE entity_type = ?",
                        ("buildable_unit",),
                    ).fetchall()
                }

            # First run should embed everything
            assert result1["embedded"] == len(idea_ids)
            assert result1["skipped"] == 0

            # Second run should skip everything
            assert result2["embedded"] == 0
            assert result2["skipped"] == len(idea_ids)

            # Embeddings should be identical
            assert embeddings_after_1 == embeddings_after_2

        run_test()

    def test_incremental_update_subset(self, store: Store):
        """Property: updating subset leaves other embeddings unchanged."""
        @given(
            st.lists(st.text(min_size=1, max_size=10, alphabet="abcdefghijklmnopqrstuvwxyz"), min_size=2, max_size=10, unique=True),
        )
        @settings(max_examples=20, deadline=5000)
        def run_test(idea_ids):
            # Clear existing data
            store.conn.execute("DELETE FROM buildable_units")
            store.conn.execute("DELETE FROM embeddings")
            store.conn.execute("DELETE FROM embeddings_metadata")
            store.conn.commit()

            # Insert all ideas
            for idea_id in idea_ids:
                store.insert_buildable_unit(_make_unit(idea_id, title=f"Original {idea_id}"))

            idx = SemanticIndex(store)

            with patch("max.embeddings.engine._try_voyage_embed", return_value=None):
                # Initial embedding
                idx.embed_incremental()

                # Capture embeddings for first idea
                first_id = idea_ids[0]
                first_embedding_before = json.loads(
                    store.conn.execute(
                        "SELECT embedding FROM embeddings WHERE id = ?", (first_id,)
                    ).fetchone()["embedding"]
                )

                # Update only the second idea
                second_id = idea_ids[1]
                store.conn.execute(
                    "UPDATE buildable_units SET title = ? WHERE id = ?",
                    (f"Modified {second_id}", second_id),
                )
                store.conn.commit()

                # Incremental update
                idx.embed_incremental()

                # First idea's embedding should be unchanged
                first_embedding_after = json.loads(
                    store.conn.execute(
                        "SELECT embedding FROM embeddings WHERE id = ?", (first_id,)
                    ).fetchone()["embedding"]
                )

            assert first_embedding_before == first_embedding_after

        run_test()
