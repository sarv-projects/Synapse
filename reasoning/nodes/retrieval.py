"""Node 3: Retrieval — 4-tier hybrid retrieval via LlamaIndex + existing Neo4j/Qdrant."""
import logging

from reasoning.graph.state import ReasoningState
from retrieval.query_engines import query_hybrid, query_graph, query_vector
from retrieval.session_index import get_session_index

logger = logging.getLogger(__name__)


async def retrieval_node(state: ReasoningState) -> ReasoningState:
    state.current_node = "retrieval"

    all_results: list[dict] = []
    total_score = 0.0

    for sq in state.sub_questions:
        # Tier 1: Knowledge Graph traversal (zero tokens, zero API)
        kg_results = await query_graph(sq, max_depth=2)
        for r in kg_results:
            r["source"] = "neo4j_kg"
        all_results.extend(kg_results)

        # Tier 2: Cross-session web research cache (from prior sessions)
        try:
            from embedding.generator import EmbeddingGenerator
            gen = EmbeddingGenerator()
            qv = gen.generate_query_embedding(sq)
            from embedding.qdrant_client import get_qdrant_client
            qdrant = get_qdrant_client()
            cache_results = qdrant.search_similar(qv, limit=5, score_threshold=0.85)
            for r in cache_results:
                all_results.append({
                    "content": r["payload"].get("name", ""),
                    "score": r["score"],
                    "source": "cross_session_cache",
                })
                total_score += r["score"]
        except Exception as e:
            logger.debug(f"Cross-session cache query skipped: {e}")

        # Tier 3: Vector + BM25 hybrid
        hybrid_results = await query_hybrid(sq, limit=10)
        for r in hybrid_results:
            total_score += r.get("score", 0)
        all_results.extend(hybrid_results)

        # Tier 4: Session-scoped index (current session's Crawl4AI content)
        if state.session_id:
            sess_idx = get_session_index(state.session_id)
            session_results = await sess_idx.search(sq, limit=5)
            all_results.extend(session_results)

    # Deduplicate and rank
    seen = set()
    ranked = []
    for r in sorted(all_results, key=lambda x: x.get("score", 0), reverse=True):
        key = r.get("content") or r.get("title") or r.get("url") or str(r.get("node", ""))
        if key and key not in seen:
            seen.add(key)
            ranked.append(r)

    state.retrieval_context = ranked[:30]

    # Compute confidence
    result_count = len(ranked)
    kg_count = sum(1 for r in ranked if r.get("source") == "neo4j_kg")
    if result_count == 0:
        state.retrieval_confidence = 0.0
    elif kg_count > 0:
        state.retrieval_confidence = min(0.95, 0.5 + (kg_count / result_count) * 0.45)
    else:
        state.retrieval_confidence = min(0.65, (result_count / 10) * 0.5)

    logger.info(
        f"Retrieval: {result_count} unique results, "
        f"kg={kg_count}, confidence={state.retrieval_confidence:.2f}"
    )

    return state
