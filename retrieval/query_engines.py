"""Named query engine functions — vector, BM25, graph, and hybrid retrieval."""
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


async def query_vector(question: str, limit: int = 10, score_threshold: float = 0.7) -> list[dict[str, Any]]:
    """Vector similarity search via Qdrant."""
    try:
        from ingestion.neo4j.client import get_neo4j_client

        client = await get_neo4j_client()
        documents: list[dict[str, Any]] = []
        async with client.session() as session:
            result = await session.run(
                """
                MATCH (n)
                WHERE n.description IS NOT NULL OR n.summary IS NOT NULL OR n.content_md IS NOT NULL OR n.abstract_summary IS NOT NULL OR n.name IS NOT NULL OR n.full_name IS NOT NULL
                WITH n, labels(n)[0] AS label
                RETURN
                    coalesce(n.github_repo, n.full_name, n.hf_model_id, n.arxiv_id,
                             n.canonical_name, n.name, n.title, n.id) AS id,
                    coalesce(n.full_name, n.github_repo, n.hf_model_id,
                             n.canonical_name, n.name, n.title, n.id) AS name,
                    label,
                    coalesce(n.description, n.summary, n.abstract_summary, n.content_md, "") AS body,
                    coalesce(n.html_url, n.link, n.source_url, "") AS url,
                    n.source AS source
                LIMIT 500
                """
            )
            async for row in result:
                name = str(row.get("name") or "")
                body = str(row.get("body") or "")
                content = f"{name}\n{body}".strip()
                if content:
                    documents.append(
                        {
                            "id": row.get("id") or name,
                            "name": name,
                            "label": row.get("label") or "",
                            "content": content,
                            "url": row.get("url") or "",
                            "source": row.get("source") or "neo4j",
                        }
                    )

        if not documents:
            return []

        def tokenize(text: str) -> list[str]:
            return re.findall(r"[a-z0-9][a-z0-9._/-]*", text.lower())

        bm25 = BM25Okapi([tokenize(doc["content"]) for doc in documents])
        scores = bm25.get_scores(tokenize(question))
        ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)[:limit]
        return [
            {
                **documents[index],
                "score": float(score),
                "source": documents[index]["source"] or "neo4j_bm25",
                "retrieval_source": "neo4j_bm25",
            }
            for index, score in ranked
            if score > 0
        ]
    except Exception as e:
        logger.warning(f"BM25 query unavailable: {e}")
        return []


async def query_graph(entity: str, max_depth: int = 2) -> list[dict[str, Any]]:
    """Knowledge graph traversal from an entity name."""
    try:
        from ingestion.neo4j.client import get_neo4j_client
        client = await get_neo4j_client()
        results = []
        async with client.session() as session:
            r = await session.run(
                """MATCH (n)
                WHERE toLower(n.name) CONTAINS toLower($entity)
                   OR toLower(n.full_name) CONTAINS toLower($entity)
                   OR toLower(n.title) CONTAINS toLower($entity)
                OPTIONAL MATCH (n)-[rel]-(related)
                RETURN n, type(rel) as rel_type, labels(related) as related_labels,
                       related.name as related_name, related.full_name as related_full_name
                LIMIT 20""",
                entity=entity
            )
            async for record in r:
                results.append({
                    "node": dict(record.get("n", {})),
                    "rel_type": record.get("rel_type"),
                    "related": record.get("related_name") or record.get("related_full_name") or ""
                })
        return results
    except Exception as e:
        logger.warning(f"Graph query unavailable: {e}")
        return []


async def query_hybrid(
    question: str,
    vector_weight: float = 0.6,
    bm25_weight: float = 0.4,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Hybrid retrieval — weighted fusion of vector and BM25 results."""
    vector_results = await query_vector(question, limit=limit * 2)
    bm25_results = await query_bm25(question, limit=limit * 2)

    # Simple weighted merge by score
    merged: dict[str, float] = {}
    for r in vector_results:
        key = r.get("name") or r.get("id", "")
        if key:
            merged[key] = merged.get(key, 0) + r.get("score", 0) * vector_weight

    for r in bm25_results:
        key = r.get("content") or r.get("name") or r.get("id", "")
        if key:
            merged[key] = merged.get(key, 0) + r.get("score", 0) * bm25_weight

    ranked = sorted(merged.items(), key=lambda x: x[1], reverse=True)[:limit]
    return [{"content": key, "score": score, "source": "hybrid"} for key, score in ranked]
