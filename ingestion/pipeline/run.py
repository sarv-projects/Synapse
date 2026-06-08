"""
SYNAPSE v3.0 — Real ingestion pipeline.

Stages:
  1. Fetch from all configured sources (parallel, circuit-breaker protected)
  2. Fast-path extraction → GraphNode objects
  3. Relationship extraction → GraphEdge objects
  4. MERGE nodes + edges into Neo4j (batched, idempotent)
  5. Generate embeddings → pgvector + Neo4j
  6. Semantic similarity pass → SEMANTICALLY_SIMILAR edges
  7. Webhook dispatch → notify subscribers
  8. Print run summary
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime

from ingestion.circuit_breaker_wrapper import CircuitBreakerWrapper
from ingestion.generic_source import GenericSourceFetcher
from ingestion.neo4j.client import get_neo4j_client, close_neo4j_client
from ingestion.neo4j.writer import merge_edges, merge_nodes
from ingestion.pipeline.extraction import fast_path_transform
from ingestion.pipeline.relationships import extract_relationships
from ingestion.pipeline.state import PipelineState
from ingestion.source_factory import SourceFactory
from schema.config import get_settings

logger = logging.getLogger(__name__)


def _nodes_to_dicts(nodes: list) -> list[dict]:
    """Convert GraphNode objects to plain dicts for embedding pipeline."""
    from ingestion.neo4j.writer import _dedup_key_for

    dicts = []
    for node in nodes:
        d = dict(node.properties) if hasattr(node, "properties") else {}
        # Use the natural dedup key (same as Neo4j MERGE key) as embedding ID
        label = node.label if hasattr(node, "label") else ""
        key_prop = _dedup_key_for(label)
        natural_id = (node.properties.get(key_prop) or node.properties.get("name") or node.key) if hasattr(node, "properties") else ""
        d["id"] = str(natural_id)
        d["entity_type"] = label
        d["source"] = node.source if hasattr(node, "source") else "unknown"
        dicts.append(d)
    return dicts


async def run_pipeline(domain: str = "ai", sources: list[str] | None = None) -> dict:
    """
    Run the full ingestion pipeline.

    Args:
        domain:  Domain pack name (default: "ai")
        sources: List of source names to run. None = all sources.

    Returns:
        Summary dict with counts and timing.
    """
    settings = get_settings()
    started_at = datetime.now(UTC)
    t0 = time.perf_counter()

    logger.info(f"=== SYNAPSE ingestion pipeline starting — domain={domain} ===")

    # ── Initialize checkpoint (optional) ────────────────────────────────────
    checkpoint = None
    try:
        if settings.postgres_url:
            from ingestion.checkpoint.postgres import FirestoreCheckpoint
            checkpoint = FirestoreCheckpoint()
            await checkpoint.connect()
            logger.info("Checkpoint store connected")
    except Exception as e:
        logger.warning(f"Checkpoint unavailable (pipeline will run without persistence): {e}")

    # ── Stage 1: Load source factory ────────────────────────────────────────
    factory = SourceFactory()
    all_source_names = factory.get_all_source_names()
    target_sources = sources if sources else all_source_names
    logger.info(f"Sources to run: {target_sources}")

    # ── Stage 2: Fetch all sources in parallel ───────────────────────────────
    async def fetch_one(name: str):
        try:
            fetcher: GenericSourceFetcher = factory.create_fetcher(name)
            wrapped = CircuitBreakerWrapper(fetcher)
            docs = await wrapped.fetch()
            logger.info(f"  {name}: fetched {len(docs)} documents")
            return docs
        except Exception as e:
            logger.error(f"  {name}: fetch failed — {e}")
            return []

    fetch_results = await asyncio.gather(*[fetch_one(n) for n in target_sources])

    all_docs = [doc for docs in fetch_results for doc in docs]
    logger.info(f"Stage 1 complete: {len(all_docs)} total documents from {len(target_sources)} sources")

    if not all_docs:
        logger.warning("No documents fetched — check source connectivity and circuit breaker states")
        return {
            "status": "empty",
            "documents": 0,
            "nodes_written": 0,
            "duration_seconds": round(time.perf_counter() - t0, 2),
        }

    # ── Stage 3: Fast-path extraction ────────────────────────────────────────
    state = PipelineState(documents=all_docs)
    state = fast_path_transform(state)
    logger.info(f"Stage 2 complete: {len(state.nodes)} nodes extracted")

    # ── Stage 3b: Relationship extraction ────────────────────────────────────
    state = extract_relationships(state)
    logger.info(
        f"Stage 2b complete: {state.metrics.get('relationships_extracted', 0)} edges, "
        f"{state.metrics.get('extra_nodes_from_relationships', 0)} extra nodes"
    )

    # ── Stage 4: Write nodes → Neo4j ─────────────────────────────────────────
    # Use the module-level singleton so all pipeline stages share one
    # connection pool (see get_neo4j_client / close_neo4j_client).
    neo4j = await get_neo4j_client()
    try:
        written = await merge_nodes(neo4j, state.nodes)
        logger.info(f"Stage 3a complete: {written} nodes merged into Neo4j")

        # ── Stage 5: Write edges to Neo4j ─────────────────────────────────────
        edges_written = await merge_edges(neo4j, state.edges)
        logger.info(f"Stage 3b complete: {edges_written} edges merged into Neo4j")
    except Exception:
        logger.exception("Neo4j write stage failed")
        # Don't close here — later stages may recover; final cleanup in Stage 9.

    # ── Stage 6: Generate embeddings ──────────────────────────────────────────
    embeddings_result = {"embeddings_generated": 0, "errors": []}
    try:
        from ingestion.embedding_pipeline import get_embedding_pipeline
        # Pass the shared Neo4j client so the embedding pipeline reuses
        # the same connection pool instead of creating a second driver.
        emb_pipeline = await get_embedding_pipeline(neo4j_client=neo4j)
        node_dicts = _nodes_to_dicts(state.nodes)
        if node_dicts:
            embeddings_result = await emb_pipeline.process_documents(node_dicts)
            logger.info(f"Stage 4: {embeddings_result.get('embeddings_generated', 0)} embeddings generated")
    except Exception as e:
        logger.warning(f"Embedding pipeline skipped: {e}")

    # ── Stage 7: Semantic similarity pass ─────────────────────────────────────
    similarity_result = {"similar_edges_created": 0, "errors": []}
    try:
        from ingestion.semantic_similarity import get_semantic_similarity_pass
        sim_pass = get_semantic_similarity_pass()
        # Inject the shared client so the similarity pass doesn't create a
        # third driver pool that would leak.
        sim_pass.neo4j_client = neo4j
        similarity_result = await sim_pass.run_similarity_pass()
        logger.info(f"Stage 5: {similarity_result.get('similar_edges_created', 0)} similarity edges created")
    except Exception as e:
        logger.warning(f"Semantic similarity pass skipped: {e}")

    # ── Stage 8: Webhook dispatch ─────────────────────────────────────────────
    webhook_result = {"events_dispatched": 0, "deliveries_successful": 0}
    try:
        from webhook.dispatcher import get_webhook_dispatcher
        dispatcher = get_webhook_dispatcher()
        entities_created = [
            {"id": getattr(n, "id", ""), "type": n.label if hasattr(n, "label") else "",
             "name": n.properties.get("name") if hasattr(n, "properties") else "",
             "source": n.source if hasattr(n, "source") else "unknown",
             "confidence": n.confidence if hasattr(n, "confidence") else 0.8}
            for n in state.nodes
        ]
        pipeline_events = {"entities_created": entities_created}
        webhook_result = await dispatcher.dispatch_pipeline_events(pipeline_events)
        await dispatcher.close()
    except Exception as e:
        logger.warning(f"Webhook dispatch skipped: {e}")

    # ── Stage 9: Close shared resources ─────────────────────────────────────────
    # Shut down the singleton Neo4j client now that all stages are done.
    await close_neo4j_client()

    duration = round(time.perf_counter() - t0, 2)

    summary = {
        "status":                "completed",
        "started_at":            started_at.isoformat(),
        "domain":                domain,
        "sources_run":           len(target_sources),
        "documents":             len(all_docs),
        "nodes_extracted":       len(state.nodes),
        "nodes_written":         written,
        "edges_extracted":       state.metrics.get("relationships_extracted", 0),
        "edges_written":         edges_written,
        "embeddings_generated":  embeddings_result.get("embeddings_generated", 0),
        "similarity_edges":      similarity_result.get("similar_edges_created", 0),
        "webhook_deliveries":    webhook_result.get("deliveries_successful", 0),
        "warnings":              state.warnings,
        "duration_seconds":      duration,
    }

    logger.info(f"=== Pipeline complete in {duration}s — {written} nodes written ===")
    return summary


def main() -> None:
    import argparse
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%H:%M:%S",
    )

    parser = argparse.ArgumentParser(description="Run SYNAPSE ingestion pipeline")
    parser.add_argument("--domain",  default="ai",  help="Domain pack (default: ai)")
    parser.add_argument("--sources", default=None,  help="Comma-separated source names (default: all)")
    args = parser.parse_args()

    sources = [s.strip() for s in args.sources.split(",")] if args.sources else None

    summary = asyncio.run(run_pipeline(domain=args.domain, sources=sources))

    print("\n" + "="*50)
    print("SYNAPSE Pipeline Summary")
    print("="*50)
    for k, v in summary.items():
        if k != "warnings":
            print(f"  {k:<20} {v}")
    if summary.get("warnings"):
        print("  warnings:")
        for w in summary["warnings"]:
            print(f"    - {w}")
    print("="*50)


if __name__ == "__main__":
    main()
