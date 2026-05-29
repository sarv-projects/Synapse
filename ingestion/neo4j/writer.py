"""Bulk MERGE writer for Neo4j — idempotent, batched."""
from __future__ import annotations

import logging
from typing import Any

from ingestion.neo4j.client import Neo4jClient
from schema.models import GraphEdge, GraphNode

logger = logging.getLogger(__name__)

# Cypher template: MERGE on dedup key, SET all other properties
_MERGE_TMPL = """
UNWIND $rows AS row
MERGE (n:{label} {{{key}: row.key_value}})
ON CREATE SET n += row.props, n.created_at = timestamp(), n.status = 'new'
ON MATCH  SET n += row.props, n.last_seen  = timestamp(), n.status = 'active'
"""

# Map entity label → dedup key property name
_DEDUP_KEY: dict[str, str] = {
    "Paper":        "arxiv_id",
    "Model":        "hf_model_id",
    "Tool":         "github_repo",
    "Technique":    "canonical_name",
    "Organization": "name",
    "Author":       "name",
    "Dataset":      "name",
    "Benchmark":    "name",
    "Space":        "name",
}


def _dedup_key_for(label: str) -> str:
    return _DEDUP_KEY.get(label, "name")


def _node_to_row(node: GraphNode) -> dict[str, Any]:
    """Flatten a GraphNode into a Cypher parameter row."""
    props: dict[str, Any] = {}
    for k, v in node.properties.items():
        # Neo4j only accepts primitives / lists of primitives
        if isinstance(v, (str, int, float, bool)):
            props[k] = v
        elif isinstance(v, list):
            props[k] = [str(i) for i in v]
        elif v is not None:
            props[k] = str(v)

    props["source"]     = node.source
    props["confidence"] = node.confidence

    key_prop = _dedup_key_for(node.label)
    key_val  = node.properties.get(key_prop) or node.properties.get("id") or node.properties.get("title") or node.properties.get("name") or node.key

    return {"key_value": str(key_val), "props": props}


async def merge_nodes(
    client: Neo4jClient,
    nodes: list[GraphNode],
    batch_size: int = 200,
) -> int:
    """MERGE nodes into Neo4j in batches. Returns count written."""
    if not nodes:
        return 0

    # Group by label so each batch uses the right MERGE template
    by_label: dict[str, list[dict]] = {}
    for node in nodes:
        by_label.setdefault(node.label, []).append(_node_to_row(node))

    total = 0
    async with client.session() as session:
        for label, rows in by_label.items():
            key = _dedup_key_for(label)
            cypher = _MERGE_TMPL.format(label=label, key=key)

            for i in range(0, len(rows), batch_size):
                batch = rows[i : i + batch_size]
                await session.run(cypher, rows=batch)
                total += len(batch)
                logger.info(f"Merged {len(batch)} {label} nodes (batch {i//batch_size + 1})")

    return total


# ── Edge writer ───────────────────────────────────────────────────────────────

# Dedup key per label (must match node writer)
_EDGE_DEDUP_KEY: dict[str, str] = {
    "Paper":        "arxiv_id",
    "Model":        "hf_model_id",
    "Tool":         "github_repo",
    "Technique":    "canonical_name",
    "Organization": "name",
    "Author":       "name",
    "Dataset":      "name",
    "Benchmark":    "name",
}

_EDGE_TMPL = """
UNWIND $rows AS row
MATCH (a:{from_label}) WHERE a.{from_key} = row.from_val
MATCH (b:{to_label}) WHERE b.{to_key} = row.to_val
MERGE (a)-[r:{rel_type}]->(b)
ON CREATE SET r += row.props, r.created_at = timestamp()
ON MATCH  SET r.last_seen = timestamp()
"""


def _edge_to_row(edge: GraphEdge) -> dict[str, Any]:
    props: dict[str, Any] = dict(edge.properties)
    props["fact_tier"] = edge.fact_tier.value if hasattr(edge.fact_tier, "value") else str(edge.fact_tier)
    if edge.provenance:
        props["confidence"]        = edge.provenance.confidence
        props["extraction_method"] = edge.provenance.extraction_method
        props["evidence_source"]   = edge.provenance.evidence_source
    return {
        "from_val": str(edge.from_key),
        "to_val":   str(edge.to_key),
        "props":    props,
    }


async def merge_edges(
    client: Neo4jClient,
    edges: list[GraphEdge],
    batch_size: int = 200,
) -> int:
    """MERGE edges into Neo4j in batches. Returns count written."""
    if not edges:
        return 0

    # Group by (from_label, to_label, relationship)
    groups: dict[tuple[str, str, str], list[dict]] = {}
    for edge in edges:
        key = (edge.from_label, edge.to_label, edge.relationship)
        groups.setdefault(key, []).append(_edge_to_row(edge))

    total = 0
    async with client.session() as session:
        for (from_label, to_label, rel_type), rows in groups.items():
            from_key = _EDGE_DEDUP_KEY.get(from_label, "name")
            to_key   = _EDGE_DEDUP_KEY.get(to_label,   "name")
            cypher   = _EDGE_TMPL.format(
                from_label=from_label,
                to_label=to_label,
                rel_type=rel_type,
                from_key=from_key,
                to_key=to_key,
            )
            for i in range(0, len(rows), batch_size):
                batch = rows[i : i + batch_size]
                try:
                    await session.run(cypher, rows=batch)
                    total += len(batch)
                except Exception as e:
                    logger.warning(f"Edge batch failed ({from_label})-[{rel_type}]->({to_label}): {e}")

            logger.info(f"Merged {len(rows)} ({from_label})-[{rel_type}]->({to_label}) edges")

    return total
