"""PostgreSQL checkpoint manager (replaces SQLite on ephemeral disk)."""
import asyncpg
from typing import Optional
from schema.config import get_settings


class PostgresCheckpoint:
    """Persistent checkpoint storage using Neon.dev PostgreSQL."""
    
    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None
    
    async def connect(self) -> None:
        """Initialize connection pool."""
        settings = get_settings()
        self.pool = await asyncpg.create_pool(settings.postgres_url)
        await self._create_tables()
    
    async def _create_tables(self) -> None:
        """Create checkpoint tables if not exist."""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS run_log (
                    run_id TEXT PRIMARY KEY,
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    status TEXT,
                    trace_json JSONB
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS entity_checkpoint (
                    entity_id TEXT PRIMARY KEY,
                    source TEXT,
                    stage TEXT,
                    status TEXT,
                    error TEXT,
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS webhook_deliveries (
                    delivery_id TEXT PRIMARY KEY,
                    subscription_id TEXT,
                    event_type TEXT,
                    payload_hash TEXT,
                    status TEXT,
                    attempt INTEGER DEFAULT 0,
                    response_code INTEGER,
                    error_message TEXT,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_created 
                ON webhook_deliveries(created_at)
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_status 
                ON webhook_deliveries(status)
            """)
    
    async def save_entity_stage(self, entity_id: str, source: str, stage: str, status: str) -> None:
        """Save entity processing stage."""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO entity_checkpoint (entity_id, source, stage, status)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (entity_id) DO UPDATE
                SET stage = $3, status = $4, updated_at = NOW()
            """, entity_id, source, stage, status)
    
    async def get_entity_stage(self, entity_id: str) -> Optional[dict]:
        """Get entity processing stage."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM entity_checkpoint WHERE entity_id = $1",
                entity_id
            )
            return dict(row) if row else None
    
    async def log_webhook_delivery(
        self, 
        delivery_id: str, 
        subscription_id: str, 
        event_type: str, 
        attempt: int,
        status: str = "attempted"
    ) -> None:
        """Log webhook delivery attempt."""
        import hashlib
        payload_hash = hashlib.sha256(f"{delivery_id}_{event_type}".encode()).hexdigest()[:16]
        
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO webhook_deliveries 
                (delivery_id, subscription_id, event_type, payload_hash, status, attempt)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (delivery_id) DO UPDATE
                SET attempt = $6, status = $5, updated_at = NOW()
            """, delivery_id, subscription_id, event_type, payload_hash, status, attempt)
    
    async def update_webhook_delivery(
        self,
        delivery_id: str,
        status: str,
        response_code: Optional[int] = None,
        error_message: Optional[str] = None,
        attempt: Optional[int] = None
    ) -> None:
        """Update webhook delivery status."""
        async with self.pool.acquire() as conn:
            if response_code is not None:
                await conn.execute("""
                    UPDATE webhook_deliveries
                    SET status = $2, response_code = $3, updated_at = NOW()
                    WHERE delivery_id = $1
                """, delivery_id, status, response_code)
            elif error_message is not None:
                await conn.execute("""
                    UPDATE webhook_deliveries
                    SET status = $2, error_message = $3, attempt = $4, updated_at = NOW()
                    WHERE delivery_id = $1
                """, delivery_id, status, error_message, attempt or 0)
            else:
                await conn.execute("""
                    UPDATE webhook_deliveries
                    SET status = $2, updated_at = NOW()
                    WHERE delivery_id = $1
                """, delivery_id, status)
    
    async def get_webhook_delivery_stats(self, since) -> dict:
        """Get webhook delivery statistics."""
        from datetime import datetime
        async with self.pool.acquire() as conn:
            result = await conn.fetchrow("""
                SELECT 
                    COUNT(*) as total_deliveries,
                    COUNT(*) FILTER (WHERE status = 'delivered') as successful,
                    COUNT(*) FILTER (WHERE status = 'failed') as failed,
                    COUNT(*) FILTER (WHERE status = 'attempted') as pending,
                    AVG(attempt) as avg_attempts
                FROM webhook_deliveries
                WHERE created_at >= $1
            """, since)
            
            return {
                "total_deliveries": result["total_deliveries"],
                "successful": result["successful"],
                "failed": result["failed"],
                "pending": result["pending"],
                "avg_attempts": float(result["avg_attempts"]) if result["avg_attempts"] else 0,
                "since": since.isoformat()
            }
    
    async def cleanup_webhook_deliveries(self, cutoff) -> int:
        """Clean up old webhook delivery logs."""
        async with self.pool.acquire() as conn:
            result = await conn.execute("""
                DELETE FROM webhook_deliveries
                WHERE created_at < $1
            """, cutoff)
            
            # Extract number of deleted rows from result
            return int(result.split()[-1]) if result else 0
