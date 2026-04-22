"""Tests for the embeddings engine — cosine similarity, embedding, and SemanticIndex."""

from __future__ import annotations

import json
import math
from unittest.mock import patch

import pytest

from max.embeddings.engine import (
    SemanticIndex,
    _cosine_similarity,
    _simple_embed,
    embed_text,
    embed_texts,
)
from max.store.db import Store


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
