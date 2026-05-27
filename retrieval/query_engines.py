"""Named query engine functions — vector, BM25, graph, and hybrid retrieval."""
import logging
import re
from typing import Any

from rank_bm25 import BM25Okapi

logger = logging.getLogger(__name__)


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9][a-z0-9._/-]*", text.lower())


async def query_vector(question: str, limit: int = 10, score_threshold: float = 0.7) -> list[dict[str, Any]]:
    """Vector similarity search via Qdrant using sentence-transformers embeddings."""
    try:
        from embedding.generator import get_embedding_generator
        from embedding.qdrant_client import get_qdrant_client

        gen = await get_embedding_generator()
        qdrant = get_qdrant_client()

        query_embedding = gen.generate_query_embedding(question)
        results = qdrant.search_similar(
            query_vector=query_embedding,
            limit=limit,
            score_threshold=score_threshold,
        )
        return [
            {
                "id": r.get("payload", {}).get("uuid", ""),
                "name": r.get("payload", {}).get("name", ""),
                "label": r.get("payload", {}).get("label", ""),
                "content": r.get("payload", {}).get("name", ""),
                "score": r.get("score", 0.0),
                "source": "qdrant_vector",
                "retrieval_source": "qdrant_vector",
            }
            for r in results
        ]
    except Exception as e:
        logger.warning(f"Vector query unavailable: {e}")
        return []


async def query_bm25(question: str, limit: int = 10) -> list[dict[str, Any]]:
    """BM25 keyword search over Neo4j documents."""
    try:
        from ingestion.neo4j.client import get_neo4j_client

        client = await get_neo4j_client()
        documents: list[dict[str, Any]] = []
        async with client.session() as session:
            result = await session.run(
                """
                MATCH (n)
                WHERE n.description IS NOT NULL OR n.summary IS NOT NULL
                   OR n.content_md IS NOT NULL OR n.name IS NOT NULL
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

        corpus = [_tokenize(doc["content"]) for doc in documents]
        bm25 = BM25Okapi(corpus)
        scores = bm25.get_scores(_tokenize(question))
        ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)[:limit]
        return [
            {
                **documents[index],
                "score": float(score),
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
                entity=entity,
            )
            async for record in r:
                results.append(
                    {
                        "node": dict(record.get("n", {})),
                        "rel_type": record.get("rel_type"),
                        "related": record.get("related_name") or record.get("related_full_name") or "",
                    }
                )
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

    merged: dict[str, dict[str, Any]] = {}
    for r in vector_results:
        key = r.get("name") or r.get("id", "")
        if key:
            merged[key] = {"score": r.get("score", 0) * vector_weight, "content": key, "source": "hybrid"}

    for r in bm25_results:
        key = r.get("name") or r.get("id", "")
        if key:
            if key in merged:
                merged[key]["score"] += r.get("score", 0) * bm25_weight
            else:
                merged[key] = {"score": r.get("score", 0) * bm25_weight, "content": key, "source": "hybrid"}

    ranked = sorted(merged.values(), key=lambda x: x["score"], reverse=True)[:limit]
    return ranked
