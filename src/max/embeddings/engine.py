"""Embedding engine — semantic similarity for deduplication and novelty detection.

Uses Anthropic's Voyage embeddings via the voyageai SDK, falling back to a
simple TF-IDF approach if the SDK is not available.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import logging
import math
from collections import Counter
from datetime import datetime, timezone
from typing import Protocol, cast

from max.store.db import Store

logger = logging.getLogger(__name__)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def _simple_embed(text: str, vocab_size: int = 1024) -> list[float]:
    """Hybrid embedding for when no external API is available.

    Combines word unigrams (semantic matching) with character 4-grams
    (fuzzy matching for word variants like "server"/"servers").
    """
    import re

    text = text.lower().strip()
    words = re.findall(r"[a-z0-9]+", text)

    counts: Counter[int] = Counter()
    # Word unigrams — primary semantic signal
    for w in words:
        h = hash(w) % vocab_size
        counts[h] += 1
    # Character 4-grams — catches word variants and morphological similarity
    for i in range(len(text) - 3):
        h = hash(text[i : i + 4]) % vocab_size
        counts[h] += 1

    vec = [0.0] * vocab_size
    mag = math.sqrt(sum(c * c for c in counts.values())) or 1.0
    for idx, count in counts.items():
        vec[idx] = count / mag

    return vec


def content_hash(text: str) -> str:
    """Compute SHA-256 hash of text for change detection."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


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


_voyage_disabled = False  # Auto-disable on rate limit to avoid slowdown


class _VoyageEmbedResult(Protocol):
    embeddings: list[list[float]]


class _VoyageClient(Protocol):
    def embed(self, texts: list[str], *, model: str) -> _VoyageEmbedResult: ...


class _VoyageModule(Protocol):
    def Client(
        self, *, api_key: str, max_retries: int, timeout: int
    ) -> _VoyageClient: ...


def _load_voyage_module() -> _VoyageModule:
    """Load the optional Voyage SDK with the minimal shape we use."""
    return cast(_VoyageModule, importlib.import_module("voyageai"))


def _try_voyage_embed(texts: list[str]) -> list[list[float]] | None:
    """Try to use Voyage AI embeddings. Returns None if unavailable or rate-limited."""
    global _voyage_disabled  # noqa: PLW0603
    if _voyage_disabled:
        return None
    try:
        voyageai = _load_voyage_module()

        api_key = _resolve_voyage_api_key()
        if not api_key:
            return None
        client = voyageai.Client(api_key=api_key, max_retries=1, timeout=15)
        result = client.embed(texts, model="voyage-3-lite")
        return result.embeddings
    except Exception as e:
        err_msg = str(e)
        if "rate limit" in err_msg.lower() or "payment method" in err_msg.lower():
            _voyage_disabled = True
            logger.warning("Voyage rate-limited — falling back to local embeddings for this session")
        else:
            logger.debug("Voyage AI embedding unavailable, using fallback", exc_info=True)
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

    def _get_embeddable_text(self, unit) -> str:
        """Build the text to embed for a buildable unit."""
        parts = [unit.title, unit.one_liner, unit.problem, unit.solution]
        return " ".join(parts)

    def _get_embedding_metadata(
        self, entity_id: str, entity_type: str
    ) -> dict | None:
        """Get embedding metadata for an entity."""
        row = self.store.conn.execute(
            """SELECT entity_id, entity_type, content_hash, embedded_at
               FROM embeddings_metadata
               WHERE entity_id = ? AND entity_type = ?""",
            (entity_id, entity_type),
        ).fetchone()
        if not row:
            return None
        return {
            "entity_id": row["entity_id"],
            "entity_type": row["entity_type"],
            "content_hash": row["content_hash"],
            "embedded_at": row["embedded_at"],
        }

    def _upsert_embedding_metadata(
        self, entity_id: str, entity_type: str, hash_val: str
    ) -> None:
        """Insert or update embedding metadata."""
        now = datetime.now(timezone.utc).isoformat()
        self.store.conn.execute(
            """INSERT OR REPLACE INTO embeddings_metadata
               (entity_id, entity_type, content_hash, embedded_at)
               VALUES (?, ?, ?, ?)""",
            (entity_id, entity_type, hash_val, now),
        )

    def _remove_embedding(self, entity_id: str, entity_type: str) -> None:
        """Remove embedding and metadata for a deleted entity."""
        self.store.conn.execute(
            "DELETE FROM embeddings WHERE id = ? AND entity_type = ?",
            (entity_id, entity_type),
        )
        self.store.conn.execute(
            "DELETE FROM embeddings_metadata WHERE entity_id = ? AND entity_type = ?",
            (entity_id, entity_type),
        )

    def embed_incremental(
        self, entity_type: str = "buildable_unit"
    ) -> dict:
        """Incrementally update embeddings — only new/changed entities.

        Compares content hashes to detect changes. Removes embeddings for
        deleted entities.

        Returns dict with counts: embedded, skipped, removed.
        """
        # Get all current buildable units
        units = self.store.get_buildable_units(limit=10000)

        # Get all existing metadata for this entity_type
        rows = self.store.conn.execute(
            "SELECT entity_id, content_hash FROM embeddings_metadata WHERE entity_type = ?",
            (entity_type,),
        ).fetchall()
        existing_meta = {row["entity_id"]: row["content_hash"] for row in rows}

        current_ids = set()
        embedded = 0
        skipped = 0

        for unit in units:
            current_ids.add(unit.id)
            text = self._get_embeddable_text(unit)
            new_hash = content_hash(text)

            old_hash = existing_meta.get(unit.id)
            if old_hash == new_hash:
                skipped += 1
                continue

            # New or changed — re-embed
            embedding = embed_text(text)
            self.store.conn.execute(
                """INSERT OR REPLACE INTO embeddings (id, entity_type, embedding)
                   VALUES (?, ?, ?)""",
                (unit.id, entity_type, json.dumps(embedding)),
            )
            self._upsert_embedding_metadata(unit.id, entity_type, new_hash)
            embedded += 1

        # Remove embeddings for deleted entities
        removed = 0
        stale_ids = set(existing_meta.keys()) - current_ids
        for stale_id in stale_ids:
            self._remove_embedding(stale_id, entity_type)
            removed += 1

        self.store.conn.commit()

        logger.info(
            "Incremental embedding: %d embedded, %d skipped, %d removed",
            embedded, skipped, removed,
        )
        return {"embedded": embedded, "skipped": skipped, "removed": removed}

    def embed_full(self, entity_type: str = "buildable_unit") -> dict:
        """Full re-embedding of all entities.

        Returns dict with count: embedded.
        """
        units = self.store.get_buildable_units(limit=10000)
        embedded = 0

        for unit in units:
            text = self._get_embeddable_text(unit)
            new_hash = content_hash(text)

            embedding = embed_text(text)
            self.store.conn.execute(
                """INSERT OR REPLACE INTO embeddings (id, entity_type, embedding)
                   VALUES (?, ?, ?)""",
                (unit.id, entity_type, json.dumps(embedding)),
            )
            self._upsert_embedding_metadata(unit.id, entity_type, new_hash)
            embedded += 1

        self.store.conn.commit()

        logger.info("Full embedding: %d embedded", embedded)
        return {"embedded": embedded}
