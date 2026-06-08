"""Integration tests for pgvector vector search.

These tests require a live Postgres with the pgvector extension.
They are skipped unless POSTGRES_URL is set.
"""
from __future__ import annotations

import os

import pytest

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.getenv("POSTGRES_URL"),
        reason="POSTGRES_URL not set; pgvector tests require a live Postgres DB",
    ),
]


class TestPgVectorOps:
    async def test_connection(self, require_postgres):
        from schema.config import get_settings
        # Just verify the postgres connection can be made
        import asyncpg
        settings = get_settings()
        conn = await asyncpg.connect(settings.postgres_url)
        try:
            version = await conn.fetchval("SELECT version()")
            assert version is not None
        finally:
            await conn.close()

    async def test_vector_extension_loaded(self, require_postgres):
        import asyncpg
        from schema.config import get_settings
        settings = get_settings()
        conn = await asyncpg.connect(settings.postgres_url)
        try:
            result = await conn.fetchval(
                "SELECT extname FROM pg_extension WHERE extname = 'vector'"
            )
            assert result == "vector"
        finally:
            await conn.close()
