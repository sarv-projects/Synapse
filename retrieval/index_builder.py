"""Retrieval layer — hybrid vector + BM25 + knowledge-graph router.

Earlier revisions tried to use LlamaIndex's ``RouterQueryEngine`` over its
``PGVectorStore``. That path was removed because LlamaIndex's PGVectorStore
silently creates and reads from a ``data_synapse_vectors`` table with its own
schema (``data_<table_name>`` is hardcoded in the library), which is
incompatible with SYNAPSE's hand-managed ``synapse_vectors`` halfvec(384)
table populated by :mod:`embedding.qdrant_client`. Routing through
LlamaIndex therefore returned zero results regardless of how much data was
ingested.

The functions in :mod:`retrieval.query_engines` already implement vector,
BM25, graph, and weighted hybrid retrieval directly against SYNAPSE's data
stores, so this module is now a thin strategy dispatcher over them.
"""
from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)


class HybridRetrievalEngine:
    """Dispatches retrieval queries to the appropriate hand-rolled engine."""

    def __init__(self) -> None:
        self._engines: dict[str, Callable[..., Awaitable[list[dict[str, Any]]]]] = {}
        self._initialized = False

    async def initialize(self) -> None:
        if self._initialized:
            return

        from retrieval.query_engines import (
            query_bm25,
            query_graph,
            query_hybrid,
            query_vector,
        )

        self._engines = {
            "vector": query_vector,
            "bm25": query_bm25,
            "kg": query_graph,
            "graph": query_graph,
            "hybrid": query_hybrid,
        }
        self._initialized = True
        logger.info("HybridRetrievalEngine ready (vector + BM25 + KG + Hybrid)")

    async def query(
        self,
        question: str,
        strategy: str = "hybrid",
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Run ``question`` through the chosen retrieval ``strategy``.

        Strategies: ``hybrid`` (default), ``vector``, ``bm25``, ``kg``/``graph``.
        Unknown strategies fall back to ``hybrid``.
        """
        await self.initialize()

        engine = self._engines.get(strategy)
        if engine is None:
            logger.warning(
                "Unknown retrieval strategy %r; falling back to hybrid", strategy
            )
            engine = self._engines["hybrid"]

        # query_graph takes (entity, max_depth=...) — others take (question, limit=...).
        if strategy in ("kg", "graph"):
            return await engine(question)  # type: ignore[arg-type]
        return await engine(question, limit=limit)  # type: ignore[arg-type]


_engine: HybridRetrievalEngine | None = None


def get_retrieval_engine() -> HybridRetrievalEngine:
    global _engine
    if _engine is None:
        _engine = HybridRetrievalEngine()
    return _engine
