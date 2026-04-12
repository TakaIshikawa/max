"""Embedding engine — semantic similarity for deduplication and novelty detection.

Uses Anthropic's Voyage embeddings via the voyageai SDK, falling back to a
simple TF-IDF approach if the SDK is not available.
"""

from __future__ import annotations

import json
import math
from collections import Counter

from max.store.db import Store


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def _simple_embed(text: str, vocab_size: int = 256) -> list[float]:
    """Simple hash-based embedding for when no external API is available.

    Uses character trigram hashing for a lightweight semantic fingerprint.
    This is NOT as good as real embeddings but provides basic dedup capability.
    """
    text = text.lower().strip()
    trigrams = [text[i : i + 3] for i in range(len(text) - 2)]
    counts: Counter[int] = Counter()
    for tri in trigrams:
        h = hash(tri) % vocab_size
        counts[h] += 1

    vec = [0.0] * vocab_size
    total = sum(counts.values()) or 1
    for idx, count in counts.items():
        vec[idx] = count / total

    return vec


def _resolve_voyage_api_key() -> str | None:
    """Resolve Voyage API key: env var first, then vault."""
    import os

    key = os.environ.get("VOYAGE_API_KEY")
    if key:
        return key
    try:
        import subprocess

        result = subprocess.run(
            ["vault", "get", "voyage/api_key"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    return None


def _try_voyage_embed(texts: list[str]) -> list[list[float]] | None:
    """Try to use Voyage AI embeddings. Returns None if unavailable."""
    try:
        import voyageai  # type: ignore[import-untyped]

        api_key = _resolve_voyage_api_key()
        if not api_key:
            return None
        client = voyageai.Client(api_key=api_key)
        result = client.embed(texts, model="voyage-3-lite")
        return result.embeddings
    except Exception:
        return None


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a list of texts. Uses Voyage if available, else fallback."""
    result = _try_voyage_embed(texts)
    if result is not None:
        return result
    return [_simple_embed(t) for t in texts]


def embed_text(text: str) -> list[float]:
    """Embed a single text."""
    return embed_texts([text])[0]


class SemanticIndex:
    """Manages embeddings stored in SQLite for similarity queries."""

    def __init__(self, store: Store):
        self.store = store

    def index_entity(self, entity_id: str, entity_type: str, text: str) -> None:
        """Compute and store embedding for an entity."""
        embedding = embed_text(text)
        self.store.conn.execute(
            """INSERT OR REPLACE INTO embeddings (id, entity_type, embedding)
               VALUES (?, ?, ?)""",
            (entity_id, entity_type, json.dumps(embedding)),
        )
        self.store.conn.commit()

    def find_similar(
        self,
        text: str,
        entity_type: str,
        *,
        threshold: float = 0.8,
        limit: int = 5,
    ) -> list[tuple[str, float]]:
        """Find entities similar to the given text.

        Returns list of (entity_id, similarity_score) pairs above threshold.
        """
        query_embedding = embed_text(text)

        rows = self.store.conn.execute(
            "SELECT id, embedding FROM embeddings WHERE entity_type = ?",
            (entity_type,),
        ).fetchall()

        scored: list[tuple[str, float]] = []
        for row in rows:
            stored_embedding = json.loads(row["embedding"])
            sim = _cosine_similarity(query_embedding, stored_embedding)
            if sim >= threshold:
                scored.append((row["id"], sim))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:limit]

    def is_duplicate(
        self,
        text: str,
        entity_type: str,
        *,
        threshold: float = 0.9,
    ) -> tuple[bool, str | None]:
        """Check if text is semantically duplicate of existing entity.

        Returns (is_dup, matching_id) tuple.
        """
        similar = self.find_similar(text, entity_type, threshold=threshold, limit=1)
        if similar:
            return True, similar[0][0]
        return False, None

    def novelty_score(self, text: str, entity_type: str) -> float:
        """Compute novelty score (0-1). Higher = more novel.

        Returns 1.0 - max_similarity to any existing entity.
        """
        query_embedding = embed_text(text)

        rows = self.store.conn.execute(
            "SELECT embedding FROM embeddings WHERE entity_type = ?",
            (entity_type,),
        ).fetchall()

        if not rows:
            return 1.0

        max_sim = 0.0
        for row in rows:
            stored_embedding = json.loads(row["embedding"])
            sim = _cosine_similarity(query_embedding, stored_embedding)
            max_sim = max(max_sim, sim)

        return 1.0 - max_sim
