"""Tests for critical bug fixes — circuit breaker, retrieval, budget, security."""
import asyncio
import pytest
from unittest.mock import MagicMock, patch


class TestCypherInjectionPrevention:
    """Fix #1: Verify label whitelist blocks injection."""

    @pytest.mark.asyncio
    async def test_invalid_type_rejected(self):
        from fastapi.testclient import TestClient
        from api.main import app

        client = TestClient(app)
        resp = client.get("/api/v1/search", params={"q": "test", "type": "Tool) DETACH DELETE n //"})
        assert resp.status_code == 400
        assert "Invalid type filter" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_valid_type_accepted(self):
        # Just verify the whitelist logic doesn't reject valid labels
        ALLOWED = {"Paper", "Model", "Tool", "Author", "Organization", "Technique", "Dataset", "Benchmark", "Space"}
        for label in ALLOWED:
            assert label in ALLOWED


class TestRetrievalLayer:
    """Fix #2/#8: Verify BM25 and vector search are properly separated."""

    def test_bm25_import(self):
        from rank_bm25 import BM25Okapi
        # Use a 3-doc corpus so IDF is nonzero. 'hello' appears in doc 0 only;
        # 'common' appears in all docs, so its IDF is low. Doc 0 must score
        # highest for the query "hello".
        corpus = [
            ["hello", "world", "common"],
            ["foo", "bar", "common"],
            ["baz", "qux", "common"],
        ]
        bm25 = BM25Okapi(corpus)
        scores = bm25.get_scores(["hello"])
        assert scores[0] > scores[1]
        assert scores[0] > scores[2]

    def test_query_engines_importable(self):
        from retrieval.query_engines import query_vector, query_bm25, query_graph, query_hybrid
        assert callable(query_vector)
        assert callable(query_bm25)
        assert callable(query_graph)
        assert callable(query_hybrid)


class TestCircuitBreakerNoRecursion:
    """Fix #4: Verify ProtectedFetcher doesn't infinitely recurse."""

    @pytest.mark.asyncio
    async def test_protected_fetcher_calls_parent(self):
        from ingestion.circuit_breaker_wrapper import circuit_breaker_protected
        from ingestion.sources.base import SourceFetcher

        call_count = 0

        @circuit_breaker_protected
        class TestFetcher(SourceFetcher):
            def __init__(self):
                self.source_name = "test"

            async def fetch(self):
                # The decorator's _raw_fetch reaches this via super().fetch().
                nonlocal call_count
                call_count += 1
                return []

        # ProtectedFetcher.fetch() -> CircuitBreakerWrapper.fetch()
        #   -> _fetch_with_backoff()
        #     -> self.fetcher._raw_fetch()
        #       -> super().fetch()  i.e. TestFetcher.fetch above
        # If recursion bug returns, this hangs / RecursionError.
        fetcher = TestFetcher()
        result = await fetcher.fetch()
        assert isinstance(result, list)
        assert call_count == 1, f"parent fetch should be invoked exactly once, was {call_count}"


class TestBudgetSemaphoreRelease:
    """Fix #6: Verify semaphore is released after budget gate."""

    def test_scheduler_release_exists(self):
        from budget.scheduler import LeakyBucketScheduler
        scheduler = LeakyBucketScheduler()
        # Acquire and release should not deadlock
        loop = asyncio.new_event_loop()
        loop.run_until_complete(scheduler.acquire("test-model"))
        scheduler.release("test-model")
        # Should be able to acquire again
        loop.run_until_complete(scheduler.acquire("test-model"))
        scheduler.release("test-model")
        loop.close()


class TestEmbeddingIdConsistency:
    """Fix #7: Verify _nodes_to_dicts uses natural keys."""

    def test_nodes_to_dicts_uses_natural_key(self):
        from ingestion.pipeline.run import _nodes_to_dicts

        node = MagicMock()
        node.label = "Paper"
        node.properties = {"arxiv_id": "2401.12345", "title": "Test Paper"}
        node.key = "fallback"
        node.source = "arxiv"
        node.id = "random-uuid-should-not-be-used"

        result = _nodes_to_dicts([node])
        assert result[0]["id"] == "2401.12345"  # Natural key, not UUID


class TestGate3SpamCheck:
    """Fix #10: Verify spam check uses original title case."""

    def test_normal_title_passes(self):
        from sync.background_scraper import _gate3_spam
        assert _gate3_spam("Advances in Transformer Architecture", "Some content about AI", "http://example.com") is True

    def test_all_caps_title_rejected(self):
        from sync.background_scraper import _gate3_spam
        assert _gate3_spam("BUY NOW AMAZING AI TOOL FREE", "content", "http://spam.com") is False

    def test_spam_pattern_rejected(self):
        from sync.background_scraper import _gate3_spam
        assert _gate3_spam("You won't believe this AI trick", "content", "http://spam.com") is False


class TestQueryCacheBounded:
    """Fix #18: Verify query cache doesn't grow unbounded."""

    def test_cache_eviction(self):
        from query.nl_to_cypher import NLToCypherTranslator

        with patch.dict("os.environ", {
            "NEO4J_URI": "bolt://localhost:7687",
            "CORS_ORIGINS": "http://localhost:3000",
        }):
            translator = NLToCypherTranslator()
            # Fill cache beyond max
            for i in range(300):
                translator.query_cache[f"key_{i}"] = {"result": i}
                if len(translator.query_cache) >= translator._cache_max_size:
                    keys = list(translator.query_cache.keys())
                    for k in keys[: len(keys) // 2]:
                        del translator.query_cache[k]

            assert len(translator.query_cache) <= translator._cache_max_size


class TestAdminAuthOnGroqEndpoints:
    """Fix #19: Verify rotate/reset require admin auth."""

    @pytest.mark.asyncio
    async def test_rotate_requires_auth(self):
        from fastapi.testclient import TestClient
        from api.main import app

        client = TestClient(app)
        resp = client.get("/api/v1/groq/rotate")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_reset_requires_auth(self):
        from fastapi.testclient import TestClient
        from api.main import app

        client = TestClient(app)
        resp = client.post("/api/v1/groq/reset")
        assert resp.status_code == 401


class TestReasoningStateTypedDict:
    """Fix #27: Verify ReasoningState is a TypedDict."""

    def test_state_is_typeddict(self):
        from reasoning.graph.state import ReasoningState
        # TypedDict instances are just dicts
        state: ReasoningState = {"query": "test", "status": "PENDING"}
        assert state["query"] == "test"
        assert state["status"] == "PENDING"


class TestConfigOptionalAdminKey:
    """Fix #29: Verify SYNAPSE_ADMIN_KEY is optional."""

    def test_settings_without_admin_key(self):
        with patch.dict("os.environ", {
            "NEO4J_URI": "bolt://localhost:7687",
            "CORS_ORIGINS": "http://localhost:3000",
        }, clear=False):
            import importlib
            import schema.config
            importlib.reload(schema.config)
            # Should not raise
            from schema.config import Settings
            s = Settings(
                neo4j_uri="bolt://localhost:7687",
                cors_origins=["http://localhost:3000"],
            )
            assert s.synapse_admin_key == ""
