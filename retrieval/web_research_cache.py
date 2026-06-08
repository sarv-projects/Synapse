"""Cross-session web research cache — persist WebResearchResult nodes in Neo4j."""
import logging
from datetime import UTC, datetime, timedelta

logger = logging.getLogger(__name__)


class WebResearchCache:
    """Persists web research results to Neo4j for cross-session reuse (7-day TTL)."""

    def __init__(self):
        self._connected = False

    async def store(self, query_text: str, query_embedding: list[float], result_urls: list[str], content_md: str, session_id: str):
        """Store web research results as WebResearchResult nodes."""
        try:
            from ingestion.neo4j.client import Neo4jClient
            from schema.config import get_settings
            client = Neo4jClient.from_settings(get_settings())
            try:
                async with client.session() as s:
                    await s.run("""
                        MERGE (wr:WebResearchResult {query_text: $query})
                        SET wr.query_embedding = $embedding,
                            wr.result_urls = $urls,
                            wr.content_md = $content,
                            wr.session_id = $sid,
                            wr.cached_at = datetime(),
                            wr.ttl_days = 7,
                            wr.status = 'active'
                    """, query=query_text, embedding=query_embedding, urls=result_urls, content=content_md[:10000], sid=session_id)
            finally:
                await client.close()
            logger.info(f"WebResearchCache: stored result for '{query_text[:60]}...'")
        except (ConnectionError, TimeoutError, OSError) as e:
            logger.debug(f"WebResearchCache store network failure: {type(e).__name__}: {e}")
        except (TypeError, ValueError) as e:
            logger.warning(f"WebResearchCache store bad payload: {type(e).__name__}: {e}")

    async def lookup(self, query_embedding: list[float], similarity_threshold: float = 0.85) -> dict | None:
        """Look up cached results by query embedding similarity."""
        try:
            from embedding.qdrant_client import get_qdrant_client
            store = get_qdrant_client()
            results = await store.search_similar_async(query_embedding, limit=1, score_threshold=similarity_threshold)
            if results:
                logger.info(f"WebResearchCache: cache hit (score={results[0]['score']:.3f})")
                return results[0].get("payload", {})
        except (ConnectionError, TimeoutError, OSError) as e:
            logger.debug(f"WebResearchCache lookup network failure: {type(e).__name__}: {e}")
        except (TypeError, ValueError) as e:
            logger.debug(f"WebResearchCache lookup decode failure: {type(e).__name__}: {e}")
        return None

    async def cleanup_expired(self):
        """Archive cached results older than 7 days."""
        try:
            from ingestion.neo4j.client import Neo4jClient
            from schema.config import get_settings
            client = Neo4jClient.from_settings(get_settings())
            try:
                cutoff = datetime.now(UTC) - timedelta(days=7)
                async with client.session() as s:
                    await s.run(
                        "MATCH (wr:WebResearchResult) WHERE wr.cached_at < $cutoff SET wr.status = 'archived'",
                        cutoff=cutoff.isoformat(),
                    )
            finally:
                await client.close()
            logger.info("WebResearchCache: expired entries archived")
        except (ConnectionError, TimeoutError, OSError) as e:
            logger.debug(f"WebResearchCache cleanup network failure: {type(e).__name__}: {e}")


_cache: WebResearchCache | None = None


def get_web_research_cache() -> WebResearchCache:
    global _cache
    if _cache is None:
        _cache = WebResearchCache()
    return _cache
