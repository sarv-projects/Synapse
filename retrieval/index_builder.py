"""Retrieval layer — LlamaIndex RouterQueryEngine with VectorStoreIndex + BM25 + KG."""
import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)

LLAMAINDEX_AVAILABLE = False
try:
    from llama_index.core import Settings as LlamaSettings
    from llama_index.core import VectorStoreIndex, SimpleKeywordTableIndex
    from llama_index.core.query_engine import RouterQueryEngine
    from llama_index.core.selectors import LLMSingleSelector
    from llama_index.core.tools import QueryEngineTool
    LLAMAINDEX_AVAILABLE = True
except ImportError:
    logger.warning("llama-index not installed; using hand-rolled retrieval fallback")


class HybridRetrievalEngine:
    """LlamaIndex RouterQueryEngine wrapping VectorStore + BM25 + KG indexes."""

    def __init__(self):
        self._vector_index = None
        self._bm25_index = None
        self._query_engines: dict[str, Callable[..., Any]] = {}
        self._initialized = False

    async def initialize(self):
        if self._initialized:
            return

        if LLAMAINDEX_AVAILABLE:
            await self._init_llamaindex()
        else:
            await self._init_fallback()

        self._initialized = True

    async def _init_llamaindex(self):
        """Build LlamaIndex VectorStoreIndex backed by Qdrant."""
        try:
            from llama_index.vector_stores.qdrant import QdrantVectorStore
            from llama_index.embeddings.huggingface import HuggingFaceEmbedding
            from llama_index.core import Settings
            from embedding.qdrant_client import get_qdrant_client
            import qdrant_client

            embed_model = HuggingFaceEmbedding(model_name="thenlper/gte-small")
            Settings.embed_model = embed_model

            qdrant = get_qdrant_client()
            vector_store = QdrantVectorStore(
                client=qdrant.client,
                collection_name="synapse_nodes",
            )
            self._vector_index = VectorStoreIndex.from_vector_store(vector_store)
            logger.info("LlamaIndex VectorStoreIndex connected to Qdrant synapse_nodes")
        except Exception as e:
            logger.warning(f"LlamaIndex VectorStoreIndex init failed: {e}")
            self._vector_index = None

    async def _init_fallback(self):
        """Fallback to hand-rolled retrieval when LlamaIndex unavailable."""
        from retrieval.query_engines import query_vector, query_bm25, query_graph, query_hybrid
        self._query_engines = {
            "vector": query_vector,
            "bm25": query_bm25,
            "kg": query_graph,
            "hybrid": query_hybrid,
        }
        logger.info("Fallback retrieval engines initialized (vector + BM25 + KG + Hybrid)")

    async def query(self, question: str, strategy: str = "hybrid", limit: int = 10) -> list[dict]:
        """Execute a retrieval query using the configured strategy."""
        await self.initialize()

        if LLAMAINDEX_AVAILABLE and self._vector_index:
            try:
                retriever = self._vector_index.as_retriever(similarity_top_k=limit)
                nodes = await retriever.aretrieve(question)
                return [
                    {"content": n.get_content()[:500], "score": n.get_score() or 0.0,
                     "source": "llamaindex_vector"}
                    for n in nodes
                ]
            except Exception as e:
                logger.warning(f"LlamaIndex query failed: {e}")

        # Fallback path
        if strategy == "hybrid":
            hybrid_func = self._query_engines.get("hybrid")
            if hybrid_func:
                return await hybrid_func(question, limit=limit)
        elif strategy == "vector":
            vec_func = self._query_engines.get("vector")
            if vec_func:
                return await vec_func(question, limit=limit)
        elif strategy == "bm25":
            bm25_func = self._query_engines.get("bm25")
            if bm25_func:
                return await bm25_func(question, limit=limit)
        elif strategy in ("graph", "kg"):
            kg_func = self._query_engines.get("kg")
            if kg_func:
                return await kg_func(question)
        
        logger.warning(f"Unrecognized or unsupported fallback retrieval strategy: {strategy}")
        return []


_engine: HybridRetrievalEngine | None = None


def get_retrieval_engine() -> HybridRetrievalEngine:
    global _engine
    if _engine is None:
        _engine = HybridRetrievalEngine()
    return _engine
