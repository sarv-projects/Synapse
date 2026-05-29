"""One-time pgvector setup for Neon Postgres.

Creates the ``vector`` extension and the ``synapse_vectors`` table with HNSW
index over a halfvec(384) column. Safe to run multiple times — every statement
is ``CREATE ... IF NOT EXISTS``.

Usage::

    uv run python -m scripts.setup_pgvector
    # or
    uv run python scripts/setup_pgvector.py

Reads ``POSTGRES_URL`` directly from the environment (or a ``.env`` file via
python-dotenv) so it does not depend on the broader application settings —
i.e. you do **not** need ``CORS_ORIGINS`` or ``NEO4J_URI`` set just to bootstrap
pgvector. The Neon free tier ships pgvector pre-installed, so
``CREATE EXTENSION`` succeeds without superuser elevation.

This script is technically optional because :mod:`embedding.qdrant_client`
runs the same DDL on first connection. Running it explicitly during setup
avoids a cold-start hiccup on the first ingestion job and surfaces any
permission or connectivity issues up-front.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys

import asyncpg
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("setup_pgvector")

DDL = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS synapse_vectors (
    id        TEXT PRIMARY KEY,
    label     TEXT NOT NULL,
    name      TEXT NOT NULL,
    domain    TEXT NOT NULL DEFAULT 'ai',
    embedding halfvec(384) NOT NULL
);

CREATE INDEX IF NOT EXISTS synapse_vectors_hnsw
    ON synapse_vectors USING hnsw (embedding halfvec_cosine_ops);

CREATE INDEX IF NOT EXISTS synapse_vectors_label
    ON synapse_vectors (label);
"""


async def setup() -> int:
    load_dotenv()
    url = os.getenv("POSTGRES_URL", "").strip()
    if not url:
        logger.error("POSTGRES_URL is not set. Add it to .env (Neon connection string).")
        return 1

    logger.info("Connecting to Postgres ...")
    try:
        conn = await asyncpg.connect(url)
    except Exception as exc:  # noqa: BLE001 — surface any connection error
        logger.error("Connection failed: %s", exc)
        return 2

    try:
        logger.info("Applying pgvector DDL (idempotent) ...")
        await conn.execute(DDL)

        ext_row = await conn.fetchrow(
            "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
        )
        count_row = await conn.fetchrow(
            "SELECT COUNT(*) AS n FROM synapse_vectors"
        )
        logger.info(
            "pgvector ready: extension v%s, synapse_vectors rows=%d",
            ext_row["extversion"] if ext_row else "?",
            count_row["n"] if count_row else 0,
        )
        return 0
    finally:
        await conn.close()


def main() -> None:
    sys.exit(asyncio.run(setup()))


if __name__ == "__main__":
    main()
