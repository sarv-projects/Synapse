"""Review queue store backed by PostgreSQL."""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from schema.config import get_settings
from schema.models import ReviewQueueItem

logger = logging.getLogger(__name__)


class ReviewQueueStore:
    def __init__(self, postgres_url: str | None = None) -> None:
        settings = get_settings()
        self.url = postgres_url or settings.postgres_url
        self._pool = None

    async def _ensure_pool(self):
        if self._pool is None:
            import asyncpg
            self._pool = await asyncpg.create_pool(self.url, min_size=1, max_size=2)
            async with self._pool.acquire() as conn:
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS review_queue (
                        item_id TEXT PRIMARY KEY,
                        entity_type TEXT NOT NULL,
                        entity_id TEXT NOT NULL,
                        reason TEXT NOT NULL,
                        confidence REAL NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        payload JSONB NOT NULL DEFAULT '{}',
                        resolved_at TIMESTAMPTZ,
                        resolution TEXT
                    )
                """)
                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_review_queue_entity
                    ON review_queue(entity_type, entity_id)
                """)

    async def add(self, item: ReviewQueueItem) -> None:
        await self._ensure_pool()
        async with self._pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO review_queue (item_id, entity_type, entity_id, reason, confidence, created_at, payload)
                VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)
                ON CONFLICT (item_id) DO NOTHING
            """, item.item_id, item.entity_type, item.entity_id, item.reason,
                item.confidence, item.created_at, json.dumps(item.payload))

    async def count(self) -> int:
        await self._ensure_pool()
        async with self._pool.acquire() as conn:
            row = await conn.fetchval("SELECT COUNT(*) FROM review_queue WHERE resolved_at IS NULL")
            return row or 0

    async def list_pending(self, limit: int = 50) -> list[dict[str, Any]]:
        await self._ensure_pool()
        async with self._pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT * FROM review_queue WHERE resolved_at IS NULL
                ORDER BY created_at DESC LIMIT $1
            """, limit)
            return [dict(row) for row in rows]

    async def resolve(self, item_id: str, resolution: str) -> bool:
        await self._ensure_pool()
        async with self._pool.acquire() as conn:
            result = await conn.execute("""
                UPDATE review_queue SET resolved_at = NOW(), resolution = $1
                WHERE item_id = $2 AND resolved_at IS NULL
            """, resolution, item_id)
            return result != "UPDATE 0"

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()
