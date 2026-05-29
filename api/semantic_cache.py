import json
import logging
import uuid
from typing import Any

import asyncpg
from pgvector import HalfVector
from pgvector.asyncpg import register_vector

from schema.config import get_settings
from embedding.generator import get_embedding_generator

logger = logging.getLogger(__name__)

CREATE_CACHE_TABLE = """
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS synapse_query_cache (
    id TEXT PRIMARY KEY,
    query_text TEXT NOT NULL,
    embedding halfvec(384) NOT NULL,
    result_payload JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

class SemanticCache:
    """pgvector-backed semantic cache for bypassing the reasoning pipeline."""

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
                await conn.execute(CREATE_CACHE_TABLE)
            logger.info("SemanticCache: pool ready, table ensured")
        return self._pool

    async def check_cache(self, query: str, threshold: float = 0.95) -> dict[str, Any] | None:
        """Returns the cached result payload if a highly similar query exists."""
        try:
            gen = await get_embedding_generator()
            query_vector = gen.generate_query_embedding(query)
            distance_threshold = 1.0 - threshold
            
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                # Wrap as HalfVector so asyncpg picks the halfvec codec
                query_param = HalfVector(query_vector)
                row = await conn.fetchrow(
                    """
                    SELECT result_payload, 1 - (embedding <=> $1) as score
                    FROM synapse_query_cache
                    WHERE (embedding <=> $1) <= $2
                    ORDER BY embedding <=> $1
                    LIMIT 1
                    """,
                    query_param,
                    distance_threshold
                )
                if row:
                    score = float(row['score'])
                    logger.info(f"Semantic Cache HIT: score={score:.3f}")
                    return json.loads(row["result_payload"])
            return None
        except Exception as e:
            logger.error(f"Semantic Cache check failed: {e}", exc_info=True)
            return None

    async def save_to_cache(self, query: str, result_payload: dict[str, Any]) -> None:
        """Saves a query and its successful result to the cache."""
        try:
            gen = await get_embedding_generator()
            query_vector = gen.generate_query_embedding(query)
            
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO synapse_query_cache (id, query_text, embedding, result_payload)
                    VALUES ($1, $2, $3, $4)
                    """,
                    str(uuid.uuid4()),
                    query,
                    HalfVector(query_vector),
                    json.dumps(result_payload)
                )
            logger.info("Semantic Cache: Saved new query result")
        except Exception as e:
            logger.error(f"Semantic Cache save failed: {e}", exc_info=True)

    async def close(self):
        if self._pool:
            await self._pool.close()
            self._pool = None

_instance = None

def get_semantic_cache() -> SemanticCache:
    """Returns the SemanticCache singleton."""
    global _instance
    if _instance is None:
        _instance = SemanticCache()
    return _instance
