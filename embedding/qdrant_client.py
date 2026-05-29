"""pgvector vector store — replaces Qdrant. Uses existing Neon Postgres with halfvec(384)."""
import logging
import uuid
from typing import Any

import asyncpg
from pgvector import HalfVector
from pgvector.asyncpg import register_vector

from schema.config import get_settings

logger = logging.getLogger(__name__)

_instance: "PGVectorStore | None" = None

CREATE_TABLE = """
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS synapse_vectors (
    id          TEXT PRIMARY KEY,
    label       TEXT NOT NULL,
    name        TEXT NOT NULL,
    domain      TEXT NOT NULL DEFAULT 'ai',
    embedding   halfvec(384) NOT NULL
);
CREATE INDEX IF NOT EXISTS synapse_vectors_hnsw
    ON synapse_vectors USING hnsw (embedding halfvec_cosine_ops);
CREATE INDEX IF NOT EXISTS synapse_vectors_label
    ON synapse_vectors (label);
"""


class PGVectorStore:
    """asyncpg-backed halfvec(384) store. Drop-in replacement for QdrantVectorStore."""

    def __init__(self):
        self._pool: asyncpg.Pool | None = None
        self._url = get_settings().postgres_url

    async def _get_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            if not self._url:
                raise RuntimeError("POSTGRES_URL not configured")

            async def _init(conn):
                await register_vector(conn)

            self._pool = await asyncpg.create_pool(
                self._url,
                min_size=1,
                max_size=5,
                init=_init,
            )
            async with self._pool.acquire() as conn:
                await conn.execute(CREATE_TABLE)
            logger.info("PGVectorStore: pool ready, table ensured")
        return self._pool

    def upsert_vectors(self, nodes: list[dict[str, Any]]) -> bool:
        """Sync wrapper — schedules async upsert. Returns True on success."""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Inside async context — caller should use upsert_vectors_async
                import concurrent.futures
                future = asyncio.run_coroutine_threadsafe(
                    self._upsert_async(nodes), loop
                )
                future.result(timeout=30)
            else:
                loop.run_until_complete(self._upsert_async(nodes))
            return True
        except Exception as e:
            logger.error(f"PGVectorStore upsert failed: {e}", exc_info=True)
            return False

    async def upsert_vectors_async(self, nodes: list[dict[str, Any]]) -> bool:
        try:
            await self._upsert_async(nodes)
            return True
        except Exception as e:
            logger.error(f"PGVectorStore upsert failed: {e}", exc_info=True)
            return False

    async def _upsert_async(self, nodes: list[dict[str, Any]]):
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO synapse_vectors (id, label, name, domain, embedding)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (id) DO UPDATE
                    SET label = EXCLUDED.label,
                        name  = EXCLUDED.name,
                        embedding = EXCLUDED.embedding
                """,
                [
                    (
                        str(n["id"]),
                        n.get("label", ""),
                        n.get("name", ""),
                        n.get("domain", "ai"),
                        HalfVector(n["vector"]),
                    )
                    for n in nodes
                ],
            )

    def search_similar(
        self,
        query_vector: list[float],
        limit: int = 10,
        score_threshold: float = 0.7,
        label_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        """Sync wrapper for search. Returns list matching Qdrant payload shape."""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                future = asyncio.run_coroutine_threadsafe(
                    self._search_async(query_vector, limit, score_threshold, label_filter),
                    loop,
                )
                return future.result(timeout=10)
            else:
                return loop.run_until_complete(
                    self._search_async(query_vector, limit, score_threshold, label_filter)
                )
        except Exception as e:
            logger.warning(f"PGVectorStore search failed: {e}")
            return []

    async def search_similar_async(
        self,
        query_vector: list[float],
        limit: int = 10,
        score_threshold: float = 0.7,
        label_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        return await self._search_async(query_vector, limit, score_threshold, label_filter)

    async def _search_async(
        self,
        query_vector: list[float],
        limit: int,
        score_threshold: float,
        label_filter: str | None,
    ) -> list[dict[str, Any]]:
        pool = await self._get_pool()
        # cosine distance: 0 = identical, 2 = opposite. similarity = 1 - distance
        distance_threshold = 1.0 - score_threshold
        # Wrap as HalfVector so asyncpg picks the halfvec codec instead of
        # relying on Postgres-side parameter type inference.
        query_param = HalfVector(query_vector)
        async with pool.acquire() as conn:
            if label_filter:
                rows = await conn.fetch(
                    """
                    SELECT id, label, name, domain,
                           1 - (embedding <=> $1) AS score
                    FROM synapse_vectors
                    WHERE label = $2
                      AND (embedding <=> $1) <= $3
                    ORDER BY embedding <=> $1
                    LIMIT $4
                    """,
                    query_param,
                    label_filter,
                    distance_threshold,
                    limit,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT id, label, name, domain,
                           1 - (embedding <=> $1) AS score
                    FROM synapse_vectors
                    WHERE (embedding <=> $1) <= $2
                    ORDER BY embedding <=> $1
                    LIMIT $3
                    """,
                    query_param,
                    distance_threshold,
                    limit,
                )
        return [
            {
                "id": r["id"],
                "score": float(r["score"]),
                "payload": {
                    "uuid": r["id"],
                    "label": r["label"],
                    "name": r["name"],
                    "domain": r["domain"],
                },
            }
            for r in rows
        ]

    def get_collection_info(self) -> dict[str, Any]:
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                future = asyncio.run_coroutine_threadsafe(self._info_async(), loop)
                return future.result(timeout=10)
            return loop.run_until_complete(self._info_async())
        except Exception as e:
            logger.warning(f"PGVectorStore info failed: {e}")
            return {}

    async def _info_async(self) -> dict[str, Any]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT COUNT(*) AS cnt FROM synapse_vectors")
            return {"name": "synapse_vectors", "vectors_count": row["cnt"]}

    def delete_vectors(self, ids: list[str]) -> bool:
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                future = asyncio.run_coroutine_threadsafe(self._delete_async(ids), loop)
                future.result(timeout=10)
            else:
                loop.run_until_complete(self._delete_async(ids))
            return True
        except Exception as e:
            logger.error(f"PGVectorStore delete failed: {e}", exc_info=True)
            return False

    async def _delete_async(self, ids: list[str]):
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM synapse_vectors WHERE id = ANY($1::text[])", ids
            )

    async def close(self):
        if self._pool:
            await self._pool.close()
            self._pool = None


def get_qdrant_client() -> PGVectorStore:
    """Backward-compatible name — returns PGVectorStore singleton."""
    global _instance
    if _instance is None:
        _instance = PGVectorStore()
    return _instance


# Alias for clarity in new code
get_vector_store = get_qdrant_client
