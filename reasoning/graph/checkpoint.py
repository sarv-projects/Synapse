"""LangGraph PostgreSQL checkpoint persistence — 7-day TTL, 3 logical checkpoints."""
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)


class LangGraphCheckpoint:
    """Persists LangGraph session state to PostgreSQL at logical checkpoints."""

    def __init__(self):
        self._pool = None
        self._connected = False

    async def connect(self):
        try:
            import asyncpg
            from schema.config import get_settings
            settings = get_settings()
            postgres_url = settings.postgres_url
            if not postgres_url:
                logger.info("No POSTGRES_URL configured; checkpoints disabled")
                return
            self._pool = await asyncpg.create_pool(postgres_url, min_size=1, max_size=3)
            await self._create_tables()
            self._connected = True
            logger.info("LangGraph checkpoints connected to PostgreSQL")
        except ImportError:
            logger.info("asyncpg not installed; checkpoints disabled")
        except Exception as e:
            logger.warning(f"LangGraph checkpoints unavailable: {e}")

    async def _create_tables(self):
        async with self._pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS langgraph_checkpoints (
                    session_id TEXT NOT NULL,
                    checkpoint_name TEXT NOT NULL,
                    state JSONB NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    PRIMARY KEY (session_id, checkpoint_name)
                )
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_checkpoint_created
                ON langgraph_checkpoints (created_at)
            """)

    async def save(self, session_id: str, checkpoint_name: str, state: dict):
        if not self._connected:
            return
        try:
            import json
            async with self._pool.acquire() as conn:
                await conn.execute(
                    """INSERT INTO langgraph_checkpoints (session_id, checkpoint_name, state, created_at)
                       VALUES ($1, $2, $3::jsonb, NOW())
                       ON CONFLICT (session_id, checkpoint_name)
                       DO UPDATE SET state = $3::jsonb, created_at = NOW()""",
                    session_id, checkpoint_name, json.dumps(state, default=str),
                )
        except Exception as e:
            logger.debug(f"Checkpoint save failed: {e}")

    async def load(self, session_id: str, checkpoint_name: str) -> dict | None:
        if not self._connected:
            return None
        try:
            import json
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT state FROM langgraph_checkpoints WHERE session_id = $1 AND checkpoint_name = $2",
                    session_id, checkpoint_name,
                )
                if row:
                    return json.loads(row["state"])
        except Exception as e:
            logger.debug(f"Checkpoint load failed: {e}")
        return None

    async def cleanup_old(self):
        """Remove checkpoints older than 7 days."""
        if not self._connected:
            return
        try:
            cutoff = datetime.now(UTC) - timedelta(days=7)
            async with self._pool.acquire() as conn:
                result = await conn.execute(
                    "DELETE FROM langgraph_checkpoints WHERE created_at < $1", cutoff
                )
                if result and "DELETE" in result:
                    logger.info(f"Checkpoint cleanup: {result}")
        except Exception as e:
            logger.debug(f"Checkpoint cleanup failed: {e}")

    async def close(self):
        if self._pool:
            try:
                await self._pool.close()
            except Exception as e:
                logger.error(f"Failed to close checkpoint pool: {e}", exc_info=True)
            finally:
                self._pool = None
                self._connected = False


_checkpoint: LangGraphCheckpoint | None = None


def get_checkpoint_store() -> LangGraphCheckpoint:
    global _checkpoint
    if _checkpoint is None:
        _checkpoint = LangGraphCheckpoint()
    return _checkpoint
