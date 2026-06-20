"""API v1 router with versioned endpoints - Open Access."""
from fastapi import APIRouter, Query, HTTPException, Path
from typing import Optional, Any
from api.v1 import groq_status
from pydantic import BaseModel
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1")

router.include_router(groq_status.router)


@router.get("/health")
async def health():
    """Health check endpoint — includes live Neo4j node/edge counts."""
    from ingestion.neo4j.client import get_neo4j_client
    from schema.config import get_settings

    result = {
        "status": "healthy",
        "version": "4.0.0",
        "service": "SYNAPSE",
        "total_nodes": 0,
        "total_edges": 0,
        "today_entities": 0,
        "nodes_with_embeddings": 0,
    }

    client = None
    try:
        client = await get_neo4j_client()
        async with client.session() as session:
            r = await session.run(
                "MATCH (n) RETURN count(n) AS nodes, "
                "sum(CASE WHEN n.created_at > timestamp() - 86400000 THEN 1 ELSE 0 END) AS today"
            )
            row = await r.single()
            if row:
                result["total_nodes"]    = row["nodes"]
                result["today_entities"] = row["today"]

            r2 = await session.run("MATCH ()-[r]->() RETURN count(r) AS edges")
            row2 = await r2.single()
            if row2:
                result["total_edges"] = row2["edges"]

            r3 = await session.run("MATCH (n) WHERE n.embedding IS NOT NULL RETURN count(n) AS c")
            row3 = await r3.single()
            if row3:
                result["nodes_with_embeddings"] = row3["c"]
    except HTTPException:
        # Preserve FastAPI's intended 4xx response — don't let it get
        # rewritten as a 200 by the catch-all below.
        raise
    except Exception as e:
        logger.error(f"Health check failed: {e}", exc_info=True)
        result["status"] = "degraded"
        result["db_error"] = str(e)
    finally:
        # Ensure client is properly closed even if exception occurs
        if client:
            try:
                await client.close()
            except Exception as close_err:
                logger.warning(f"Failed to close Neo4j client in health check: {close_err}")

    return result


@router.get("/whats-new")
async def whats_new(days: int = Query(default=1, ge=1, le=30)):
    """Get new entities from last N days."""
    from ingestion.neo4j.client import get_neo4j_client
    from schema.config import get_settings

    client = None
    try:
        client = await get_neo4j_client()
        cutoff = days * 86400000
        async with client.session() as session:
            r = await session.run("""
                MATCH (n) WHERE n.created_at > timestamp() - $cutoff
                RETURN labels(n)[0] AS label, count(n) AS count
                ORDER BY count DESC
            """, cutoff=cutoff)
            entities = []
            async for record in r:
                entities.append({"label": record["label"], "count": record["count"]})

            r2 = await session.run("""
                MATCH (n) WHERE n.created_at > timestamp() - $cutoff
                RETURN n ORDER BY n.created_at DESC LIMIT 20
            """, cutoff=cutoff)
            recent = []
            async for record in r2:
                node = dict(record["n"])
                recent.append({
                    "id": node.get("full_name") or node.get("name") or node.get("title") or "",
                    "label": list(record["n"].labels)[0] if record["n"].labels else "Node",
                    "name": node.get("full_name") or node.get("name") or node.get("title") or node.get("canonical_name") or "",
                })

        return {"days": days, "entities": entities, "recent": recent}
    except HTTPException:
        # Preserve FastAPI's intended 4xx response — don't let it get
        # rewritten as a 200 by the catch-all below.
        raise
    except Exception as e:
        logger.error(f"Whats-new query failed: {e}", exc_info=True)
        return {"days": days, "entities": [], "recent": [], "error": str(e)}
    finally:
        if client:
            try:
                await client.close()
            except Exception as close_err:
                logger.warning(f"Failed to close Neo4j client in whats-new: {close_err}")


@router.get("/search")
async def search(
    q: str = Query(..., min_length=1),
    type: Optional[str] = None,
    cursor: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=100),
):
    """Full-text search across Neo4j nodes."""
    from ingestion.neo4j.client import get_neo4j_client
    from schema.config import get_settings

    client = None
    ALLOWED_LABELS = {"Paper", "Model", "Tool", "Author", "Organization", "Technique", "Dataset", "Benchmark", "Space"}
    try:
        client = await get_neo4j_client()
        if type and type != "all" and type not in ALLOWED_LABELS:
            raise HTTPException(status_code=400, detail=f"Invalid type filter. Allowed: {', '.join(sorted(ALLOWED_LABELS))}")
        label_filter = f":{type}" if type and type != "all" else ""

        cypher = f"""
        MATCH (n{label_filter})
        WHERE toLower(n.full_name) CONTAINS toLower($q)
           OR toLower(n.name) CONTAINS toLower($q)
           OR toLower(n.title) CONTAINS toLower($q)
           OR toLower(n.description) CONTAINS toLower($q)
           OR toLower(n.canonical_name) CONTAINS toLower($q)
           OR toLower(n.pipeline_tag) CONTAINS toLower($q)
           OR $q IN n.topics
           OR $q IN n.tags
        RETURN n, labels(n)[0] as label
        ORDER BY
          CASE WHEN n.stargazers_count IS NOT NULL THEN n.stargazers_count ELSE 0 END DESC,
          CASE WHEN n.downloads IS NOT NULL THEN n.downloads ELSE 0 END DESC,
          CASE WHEN n.likes IS NOT NULL THEN n.likes ELSE 0 END DESC
        LIMIT $limit
        """

        results = []
        async with client.session() as session:
            result = await session.run(cypher, q=q.lower(), limit=limit)
            async for record in result:
                node = record["n"]
                label = record["label"]
                props = dict(node)
                for k in ["commits_url", "pulls_url", "hooks_url", "trees_url", "git_url",
                          "ssh_url", "clone_url", "svn_url", "archive_url", "downloads_url",
                          "issues_url", "events_url", "labels_url", "releases_url",
                          "deployments_url", "git_refs_url", "git_commits_url", "compare_url",
                          "merges_url", "blobs_url", "tags_url", "teams_url", "keys_url",
                          "assignees_url", "branches_url", "collaborators_url", "comments_url",
                          "issue_comment_url", "contents_url", "subscribers_url",
                          "subscription_url", "notifications_url", "milestones_url",
                          "statuses_url", "stargazers_url", "forks_url", "node_id",
                          "permissions", "owner", "license", "pull_request_creation_policy"]:
                    props.pop(k, None)

                results.append({
                    "id": props.get("full_name") or props.get("name") or props.get("id") or "",
                    "label": label,
                    "name": props.get("full_name") or props.get("name") or props.get("title") or props.get("canonical_name") or "",
                    "properties": props,
                    "confidence": float(props.get("confidence", 1.0)),
                    "source": props.get("source", ""),
                    "evidence_url": props.get("html_url") or props.get("link") or "",
                })

        return {"results": results, "next_cursor": None, "total_hint": len(results)}
    except HTTPException:
        # Preserve FastAPI's intended 4xx response — don't let it get
        # rewritten as a 200 by the catch-all below.
        raise
    except Exception as e:
        logger.error(f"Search query failed: {e}", exc_info=True)
        return {"results": [], "next_cursor": None, "total_hint": 0, "error": str(e)}
    finally:
        if client:
            try:
                await client.close()
            except Exception as close_err:
                logger.warning(f"Failed to close Neo4j client in search: {close_err}")


@router.get("/similar")
async def similar(id: str = Query(...), k: int = Query(default=5, ge=1, le=20)):
    """Top-k semantically similar nodes via pgvector."""
    from embedding.qdrant_client import get_qdrant_client
    from ingestion.neo4j.client import get_neo4j_client
    from schema.config import get_settings

    client = None
    store = get_qdrant_client()

    try:
        client = await get_neo4j_client()
        async with client.session() as session:
            r = await session.run("""
                MATCH (n) WHERE n.full_name = $id OR n.name = $id OR n.id = $id
                RETURN n, labels(n)[0] AS label LIMIT 1
            """, id=id)
            row = await r.single()
            if not row:
                return {"similar": [], "error": "Entity not found"}

            node = dict(row["n"])
            label = row["label"]
            embedding = node.get("embedding")
            if not embedding:
                return {"similar": [], "error": "Entity has no embedding"}

            similar_items = await store.search_similar_async(
                query_vector=embedding,
                limit=k + 1,
                score_threshold=0.7,
                label_filter=label
            )

            results = []
            for item in similar_items:
                similar_uuid = item["payload"]["uuid"]
                if similar_uuid == node.get("id", node.get("full_name", "")):
                    continue
                r2 = await session.run("""
                    MATCH (n) WHERE n.id = $uuid OR n.full_name = $uuid OR n.name = $uuid
                    RETURN n, labels(n)[0] AS label LIMIT 1
                """, uuid=similar_uuid)
                row2 = await r2.single()
                if row2:
                    n2 = dict(row2["n"])
                    results.append({
                        "id": n2.get("full_name") or n2.get("name") or "",
                        "label": row2["label"],
                        "name": n2.get("full_name") or n2.get("name") or n2.get("title") or n2.get("canonical_name") or "",
                        "similarity_score": item["score"],
                    })

        return {"similar": results, "query_id": id}
    except HTTPException:
        # Preserve FastAPI's intended 4xx response — don't let it get
        # rewritten as a 200 by the catch-all below.
        raise
    except Exception as e:
        logger.error(f"Similar query failed: {e}", exc_info=True)
        return {"similar": [], "error": str(e)}
    finally:
        if client:
            try:
                await client.close()
            except Exception as close_err:
                logger.warning(f"Failed to close Neo4j client in similar: {close_err}")


@router.get("/export")
async def export(
    query: str = Query(...),
    format: str = Query(default="json-ld"),
    include_embeddings: bool = Query(default=False),
):
    """Export subgraph as JSON-LD, CSV, or GraphML."""
    from ingestion.neo4j.client import get_neo4j_client
    from schema.config import get_settings

    client = None
    try:
        client = await get_neo4j_client()
        from export.graph_exporter import get_graph_exporter

        exporter = get_graph_exporter()
        result = await exporter.export_subgraph(
            query=query,
            format_type=format,
            include_embeddings=include_embeddings,
        )
        return result
    finally:
        if client:
            try:
                await client.close()
            except Exception as close_err:
                logger.warning(f"Failed to close Neo4j client in export: {close_err}")


@router.get("/diff")
async def diff(
    from_date: Optional[str] = Query(default=None, alias="from"),
    to_date: Optional[str] = Query(default=None, alias="to"),
):
    """Temporal diff between two dates."""
    from ingestion.neo4j.client import get_neo4j_client
    from schema.config import get_settings

    client = None
    try:
        client = await get_neo4j_client()
        async with client.session() as session:
            if from_date and to_date:
                from_ts = int(datetime.fromisoformat(from_date).timestamp() * 1000)
                to_ts = int(datetime.fromisoformat(to_date).timestamp() * 1000)

                added_r = await session.run("""
                    MATCH (n) WHERE n.created_at >= $since_ts AND n.created_at < $to_ts
                    RETURN n, labels(n)[0] AS label ORDER BY n.created_at DESC LIMIT 100
                """, since_ts=from_ts, to_ts=to_ts)
                added = []
                async for record in added_r:
                    node = dict(record["n"])
                    added.append({
                        "id": node.get("full_name") or node.get("name") or node.get("title") or "",
                        "label": record["label"],
                        "name": node.get("full_name") or node.get("name") or node.get("title") or "",
                        "created_at": node.get("created_at"),
                    })

                recent_r = await session.run("""
                    MATCH (n)
                    WHERE n.last_seen IS NOT NULL AND n.last_seen < $since_ts
                    RETURN n, labels(n)[0] AS label
                    ORDER BY n.last_seen DESC LIMIT 50
                """, since_ts=from_ts)
                removed = []
                async for record in recent_r:
                    node = dict(record["n"])
                    removed.append({
                        "id": node.get("full_name") or node.get("name") or node.get("title") or "",
                        "label": record["label"],
                        "name": node.get("full_name") or node.get("name") or node.get("title") or "",
                    })
            else:
                last_7d = int(datetime.now(timezone.utc).timestamp() * 1000) - 604800000
                added_r = await session.run("""
                    MATCH (n) WHERE n.created_at >= $since
                    RETURN n, labels(n)[0] AS label ORDER BY n.created_at DESC LIMIT 100
                """, since=last_7d)
                added = []
                async for record in added_r:
                    node = dict(record["n"])
                    added.append({
                        "id": node.get("full_name") or node.get("name") or node.get("title") or "",
                        "label": record["label"],
                        "name": node.get("full_name") or node.get("name") or node.get("title") or "",
                        "created_at": node.get("created_at"),
                    })
                removed = []

        return {"added": added, "removed": removed, "from": from_date, "to": to_date}
    except HTTPException:
        # Preserve FastAPI's intended 4xx response — don't let it get
        # rewritten as a 200 by the catch-all below.
        raise
    except Exception as e:
        logger.error(f"Diff query failed: {e}", exc_info=True)
        return {"added": [], "removed": [], "from": from_date, "to": to_date, "error": str(e)}
    finally:
        if client:
            try:
                await client.close()
            except Exception as close_err:
                logger.warning(f"Failed to close Neo4j client in diff: {close_err}")


async def _get_lmsys_arena_leaderboard(category: str = "overall") -> list[dict]:
    """Fetch LMSYS Chatbot Arena leaderboard from Hugging Face parquet or fallback to cached state."""
    import os
    import json
    import time
    import httpx
    import tempfile
    import pyarrow.parquet as pq

    _CACHE_PATH = "lmsys_arena_leaderboard.json"
    category_norm = category.lower().strip()
    if category_norm not in ("overall", "coding", "math", "instruction_following", "creative_writing", "hard_prompts"):
        category_norm = "overall"

    # Up-to-date high quality fallback list in case everything fails
    fallback_models = {
        "overall": [
            {"id": "claude-opus-4-6-thinking", "name": "Claude Opus 4.6 (Thinking)", "score": 1499, "description": "Arena Elo: 1499 | Rank: 1 | License: Proprietary | Org: Anthropic | Date: 2026-05-27", "library": "Proprietary"},
            {"id": "claude-opus-4-6", "name": "Claude Opus 4.6", "score": 1497, "description": "Arena Elo: 1497 | Rank: 2 | License: Proprietary | Org: Anthropic | Date: 2026-05-27", "library": "Proprietary"},
            {"id": "gemini-3.5-flash", "name": "Gemini 3.5 Flash", "score": 1482, "description": "Arena Elo: 1482 | Rank: 4 | License: Proprietary | Org: Google | Date: 2026-05-27", "library": "Proprietary"},
            {"id": "gemini-3.1-pro-preview", "name": "Gemini 3.1 Pro (Preview)", "score": 1481, "description": "Arena Elo: 1481 | Rank: 5 | License: Proprietary | Org: Google | Date: 2026-05-27", "library": "Proprietary"},
            {"id": "qwen3.7-max-preview", "name": "Qwen 3.7 Max (Preview)", "score": 1474, "description": "Arena Elo: 1474 | Rank: 8 | License: Proprietary | Org: Alibaba | Date: 2026-05-27", "library": "Proprietary"},
            {"id": "muse-spark", "name": "Muse Spark", "score": 1474, "description": "Arena Elo: 1474 | Rank: 9 | License: Open Weights | Org: Meta | Date: 2026-05-27", "library": "Open Weights"},
            {"id": "gpt-5.4-high", "name": "GPT 5.4 High", "score": 1472, "description": "Arena Elo: 1472 | Rank: 10 | License: Proprietary | Org: OpenAI | Date: 2026-05-27", "library": "Proprietary"},
            {"id": "llama-3.3-70b-instruct", "name": "Llama 3.3 70B", "score": 1421, "description": "Arena Elo: 1421 | Rank: 25 | License: Open Weights | Org: Meta | Date: 2026-05-27", "library": "Open Weights"},
            {"id": "deepseek-v3", "name": "DeepSeek V3", "score": 1410, "description": "Arena Elo: 1410 | Rank: 29 | License: Open Weights | Org: DeepSeek | Date: 2026-05-27", "library": "Open Weights"},
        ],
        "coding": [
            {"id": "claude-opus-4-6-thinking", "name": "Claude Opus 4.6 (Thinking)", "score": 1520, "description": "Arena Elo: 1520 | Rank: 1 | License: Proprietary | Org: Anthropic | Date: 2026-05-27", "library": "Proprietary"},
            {"id": "gemini-3.5-flash", "name": "Gemini 3.5 Flash", "score": 1501, "description": "Arena Elo: 1501 | Rank: 2 | License: Proprietary | Org: Google | Date: 2026-05-27", "library": "Proprietary"},
            {"id": "qwen3.7-max-preview", "name": "Qwen 3.7 Max (Preview)", "score": 1490, "description": "Arena Elo: 1490 | Rank: 4 | License: Proprietary | Org: Alibaba | Date: 2026-05-27", "library": "Proprietary"},
            {"id": "deepseek-v3", "name": "DeepSeek V3", "score": 1455, "description": "Arena Elo: 1455 | Rank: 12 | License: Open Weights | Org: DeepSeek | Date: 2026-05-27", "library": "Open Weights"},
        ]
    }
    # Add other categories with fallback to overall if missing
    for cat in ("math", "instruction_following", "creative_writing", "hard_prompts"):
        if cat not in fallback_models:
            fallback_models[cat] = fallback_models["overall"]

    # 1. Try reading from local cache file
    if os.path.exists(_CACHE_PATH):
        try:
            mtime = os.path.getmtime(_CACHE_PATH)
            if time.time() - mtime < 14400:  # 4 hours
                with open(_CACHE_PATH, "r", encoding="utf-8") as f:
                    cache_data = json.load(f)
                    if isinstance(cache_data, dict) and category_norm in cache_data:
                        return cache_data[category_norm]
        except Exception as e:
            logger.warning(f"Failed to read from leaderboard cache file: {e}")

    # 2. Try fetching from Hugging Face
    try:
        url = "https://huggingface.co/datasets/lmarena-ai/leaderboard-dataset/resolve/main/text/latest-00000-of-00001.parquet"
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(url)
            if response.status_code == 200:
                with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp:
                    tmp.write(response.content)
                    tmp_path = tmp.name

                try:
                    table = pq.read_table(tmp_path)
                    df = table.to_pandas()

                    new_cache = {}
                    categories_to_cache = ["overall", "coding", "math", "instruction_following", "creative_writing", "hard_prompts"]
                    for cat in categories_to_cache:
                        cat_df = df[df["category"] == cat].copy()
                        if cat_df.empty:
                            continue
                        
                        cat_df = cat_df.sort_values("rating", ascending=False)
                        
                        records = []
                        for rank_idx, (_, row) in enumerate(cat_df.iterrows(), 1):
                            model_name = str(row.get("model_name", ""))
                            org = str(row.get("organization", "unknown"))
                            license_type = str(row.get("license", "unknown"))
                            rating = row.get("rating", 1200)
                            rating_val = int(rating) if not hasattr(rating, "isna") or not rating.isna() else 1200
                            pub_date = str(row.get("leaderboard_publish_date", ""))

                            license_display = "Open Weights" if any(x in license_type.lower() for x in ("open", "apache", "mit", "llama", "gemma", "qwen")) else "Proprietary"

                            records.append({
                                "id": model_name,
                                "name": f"{model_name} ({org.upper()})",
                                "score": rating_val,
                                "description": f"Arena Elo: {rating_val} | Rank: {rank_idx} | License: {license_display} | Org: {org.title()} | Date: {pub_date}",
                                "library": license_display
                            })
                        
                        new_cache[cat] = records

                    if new_cache:
                        with open(_CACHE_PATH, "w", encoding="utf-8") as f:
                            json.dump(new_cache, f, ensure_ascii=False, indent=2)
                        
                        if category_norm in new_cache:
                            return new_cache[category_norm]
                finally:
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)
    except Exception as e:
        logger.error(f"Failed to fetch live LMSYS leaderboard from HF: {e}", exc_info=True)

    # 3. Fallback to expired cache if available
    if os.path.exists(_CACHE_PATH):
        try:
            with open(_CACHE_PATH, "r", encoding="utf-8") as f:
                cache_data = json.load(f)
                if isinstance(cache_data, dict) and category_norm in cache_data:
                    logger.info("Using expired leaderboard cache as fallback.")
                    return cache_data[category_norm]
        except Exception:
            pass

    logger.warning("Using hardcoded fallback list for Chatbot Arena leaderboard.")
    return fallback_models.get(category_norm, fallback_models["overall"])


@router.get("/leaderboard")
async def leaderboard(
    type: str = Query(default="tools"),
    category: str = Query(default="overall"),
    limit: int = Query(default=20, ge=1, le=100),
):
    """Top tools, papers, or techniques leaderboard."""
    from ingestion.neo4j.client import get_neo4j_client
    from schema.config import get_settings

    client = None
    try:
        client = await get_neo4j_client()
        items = []
        if type == "models":
            # Direct LMSYS Chatbot Arena leaderboard merge
            items = await _get_lmsys_arena_leaderboard(category=category)
        else:
            async with client.session() as session:
                if type == "tools":
                    r = await session.run("""
                        MATCH (n:Tool) WHERE n.stargazers_count IS NOT NULL
                        RETURN n.full_name AS id, n.full_name AS name,
                               n.stargazers_count AS score, n.description AS description,
                               n.language AS language, n.topics AS topics,
                               n.html_url AS url
                        ORDER BY n.stargazers_count DESC LIMIT $limit
                    """, limit=limit)
                elif type == "papers":
                    r = await session.run("""
                        MATCH (n:Paper) RETURN n.title AS id, n.title AS name,
                               n.arxiv_id AS arxiv_id, n.published AS published,
                               n.link AS url
                        ORDER BY n.published DESC LIMIT $limit
                    """, limit=limit)
                elif type == "techniques":
                    r = await session.run("""
                        MATCH (n:Technique) RETURN n.canonical_name AS id,
                               n.canonical_name AS name, n.description AS description
                        ORDER BY n.name LIMIT $limit
                    """, limit=limit)
                else:
                    r = await session.run("""
                        MATCH (n:Tool) WHERE n.stargazers_count IS NOT NULL
                        RETURN n.full_name AS id, n.full_name AS name,
                               n.stargazers_count AS score
                        ORDER BY n.stargazers_count DESC LIMIT $limit
                    """, limit=limit)

                async for record in r:
                    items.append(dict(record))

        return {"type": type, "items": items[:limit], "count": len(items[:limit])}
    except HTTPException:
        # Preserve FastAPI's intended 4xx response — don't let it get
        # rewritten as a 200 by the catch-all below.
        raise
    except Exception as e:
        logger.error(f"Leaderboard query failed: {e}", exc_info=True)
        return {"type": type, "items": [], "error": str(e)}
    finally:
        if client:
            try:
                await client.close()
            except Exception as close_err:
                logger.warning(f"Failed to close Neo4j client in leaderboard: {close_err}")


@router.get("/changelog")
async def changelog():
    """Schema and pipeline changelog."""
    from ingestion.neo4j.client import get_neo4j_client
    from schema.config import get_settings

    client = None
    try:
        client = await get_neo4j_client()
        async with client.session() as session:
            r = await session.run("""
                MATCH (n:ChangelogEntry)
                RETURN n ORDER BY n.date DESC LIMIT 50
            """)
            entries = []
            async for record in r:
                node = dict(record["n"])
                entries.append({
                    "version": node.get("version", ""),
                    "date": node.get("date", ""),
                    "summary": node.get("summary", ""),
                    "breaking_change": node.get("breaking_change", False),
                })

        return {"entries": entries}
    except HTTPException:
        # Preserve FastAPI's intended 4xx response — don't let it get
        # rewritten as a 200 by the catch-all below.
        raise
    except Exception as e:
        logger.error(f"Changelog query failed: {e}", exc_info=True)
        return {"entries": [], "error": str(e)}
    finally:
        if client:
            try:
                await client.close()
            except Exception as close_err:
                logger.warning(f"Failed to close Neo4j client in changelog: {close_err}")


# ── Graph Traversal Endpoints ──────────────────────────────────────────────────


@router.get("/technique/{name}/ecosystem")
async def technique_ecosystem(name: str = Path(...)):
    """2-hop ecosystem graph for a technique — papers, tools, models."""
    from ingestion.neo4j.client import get_neo4j_client
    from schema.config import get_settings

    client = None
    try:
        client = await get_neo4j_client()
        async with client.session() as session:
            r = await session.run("""
                MATCH (t:Technique {canonical_name: $name})
                OPTIONAL MATCH (p:Paper)-[:INTRODUCES]->(t)
                OPTIONAL MATCH (tool:Tool)-[:IMPLEMENTS]->(t)
                OPTIONAL MATCH (m:Model)-[:IMPLEMENTS]->(t)
                WITH t, collect(DISTINCT {id: p.arxiv_id, label: 'Paper', title: p.title}) AS papers,
                     collect(DISTINCT {id: tool.full_name, label: 'Tool', name: tool.full_name, stars: tool.stargazers_count}) AS tools,
                     collect(DISTINCT {id: m.hf_model_id, label: 'Model', name: m.hf_model_id, downloads: m.downloads}) AS models
                RETURN t.canonical_name AS name, t.description AS description,
                       papers, tools, models
            """, name=name)
            row = await r.single()
            if not row:
                return {"name": name, "nodes": [], "edges": []}

            technique = {
                "id": f"technique:{name}",
                "label": "Technique",
                "name": name,
                "description": row["description"],
                "size": 20,
            }

            nodes = [technique]
            edges = []

            for paper in row["papers"]:
                if not paper.get("id"):
                    continue
                nodes.append({
                    "id": f"paper:{paper['id']}",
                    "label": "Paper",
                    "name": paper.get("title", paper["id"]),
                    "size": 8,
                })
                edges.append({
                    "id": f"introduces:{paper['id']}",
                    "source": f"paper:{paper['id']}",
                    "target": f"technique:{name}",
                    "type": "INTRODUCES",
                })

            for tool in row["tools"]:
                if not tool.get("id"):
                    continue
                nodes.append({
                    "id": f"tool:{tool['id']}",
                    "label": "Tool",
                    "name": tool.get("name", tool["id"]),
                    "size": min(20, (tool.get("stars") or 0) / 1000 + 5),
                })
                edges.append({
                    "id": f"implements:{tool['id']}",
                    "source": f"tool:{tool['id']}",
                    "target": f"technique:{name}",
                    "type": "IMPLEMENTS",
                })

            for model in row["models"]:
                if not model.get("id"):
                    continue
                nodes.append({
                    "id": f"model:{model['id']}",
                    "label": "Model",
                    "name": model.get("name", model["id"]),
                    "size": min(15, (model.get("downloads") or 0) / 100000 + 5),
                })
                edges.append({
                    "id": f"implements:{model['id']}",
                    "source": f"model:{model['id']}",
                    "target": f"technique:{name}",
                    "type": "IMPLEMENTS",
                })

        return {"name": name, "nodes": nodes, "edges": edges}
    except HTTPException:
        # Preserve FastAPI's intended 4xx response — don't let it get
        # rewritten as a 200 by the catch-all below.
        raise
    except Exception as e:
        logger.error(f"Technique ecosystem query failed: {e}", exc_info=True)
        return {"name": name, "nodes": [], "edges": [], "error": str(e)}
    finally:
        if client:
            try:
                await client.close()
            except Exception as close_err:
                logger.warning(f"Failed to close Neo4j client in technique_ecosystem: {close_err}")


@router.get("/org/{name}/releases")
async def org_releases(name: str = Path(...), since: Optional[str] = Query(default=None)):
    """All papers, models, tools from an org."""
    from ingestion.neo4j.client import get_neo4j_client
    from schema.config import get_settings

    client = None
    try:
        client = await get_neo4j_client()
        async with client.session() as session:
            filter_clause = ""
            params: dict[str, Any] = {"name": name}
            if since:
                since_ts = int(datetime.fromisoformat(since).timestamp() * 1000)
                filter_clause = "AND n.created_at >= $since"
                params["since"] = since_ts

            r = await session.run(f"""
                MATCH (n) WHERE
                    toLower(n.full_name) CONTAINS toLower($name)
                    OR toLower(n.name) CONTAINS toLower($name)
                    {filter_clause}
                RETURN n, labels(n)[0] AS label
                ORDER BY n.created_at DESC LIMIT 50
            """, **params)

            items = []
            async for record in r:
                node = dict(record["n"])
                items.append({
                    "id": node.get("full_name") or node.get("name") or node.get("title") or "",
                    "label": record["label"],
                    "name": node.get("full_name") or node.get("name") or node.get("title") or "",
                    "created_at": node.get("created_at"),
                })

        return {"org": name, "items": items, "count": len(items)}
    except HTTPException:
        # Preserve FastAPI's intended 4xx response — don't let it get
        # rewritten as a 200 by the catch-all below.
        raise
    except Exception as e:
        logger.error(f"Org releases query failed: {e}", exc_info=True)
        return {"org": name, "items": [], "error": str(e)}
    finally:
        if client:
            try:
                await client.close()
            except Exception as close_err:
                logger.warning(f"Failed to close Neo4j client in org_releases: {close_err}")


@router.get("/model/{hf_id}/lineage")
async def model_lineage(hf_id: str = Path(...)):
    """Base model, fine-tunes, tools, benchmarks."""
    from ingestion.neo4j.client import get_neo4j_client
    from schema.config import get_settings

    client = None
    try:
        client = await get_neo4j_client()
        async with client.session() as session:
            r = await session.run("""
                MATCH (m:Model {hf_model_id: $hf_id})
                OPTIONAL MATCH (m)-[:FINE_TUNED_FROM]->(base:Model)
                OPTIONAL MATCH (ft:Model)-[:FINE_TUNED_FROM]->(m)
                OPTIONAL MATCH (tool:Tool)-[:SUPPORTS_MODEL]->(m)
                OPTIONAL MATCH (br:BenchmarkResult)-[:BENCHMARKS_ON]->(m)
                WITH m, base, collect(DISTINCT ft.hf_model_id) AS fine_tunes,
                     collect(DISTINCT tool.full_name) AS supporting_tools,
                     collect(DISTINCT {benchmark: br.name, score: br.score}) AS benchmarks
                RETURN m.hf_model_id AS id, m.pipeline_tag AS pipeline_tag,
                       m.likes AS likes, m.downloads AS downloads,
                       base.hf_model_id AS base_model,
                       fine_tunes, supporting_tools, benchmarks
            """, hf_id=hf_id)
            row = await r.single()
            if not row:
                return {"id": hf_id, "error": "Model not found"}

        return dict(row)
    except HTTPException:
        # Preserve FastAPI's intended 4xx response — don't let it get
        # rewritten as a 200 by the catch-all below.
        raise
    except Exception as e:
        logger.error(f"Model lineage query failed: {e}", exc_info=True)
        return {"id": hf_id, "error": str(e)}
    finally:
        if client:
            try:
                await client.close()
            except Exception as close_err:
                logger.warning(f"Failed to close Neo4j client in model_lineage: {close_err}")


# ── Query endpoints ──────────────────────────────────────────────────────────


class NLQueryRequest(BaseModel):
    natural_query: str
    max_results: int = 50
    use_cache: bool = True


@router.post("/query")
async def nl_query(body: NLQueryRequest):
    """Natural language query — NL-to-Cypher translation."""
    try:
        from query.nl_to_cypher import get_nl_translator
        translator = get_nl_translator()
        result = await translator.translate_query(
            natural_query=body.natural_query,
            max_results=body.max_results,
            use_cache=body.use_cache,
        )
        return result
    except HTTPException:
        # Preserve FastAPI's intended 4xx response — don't let it get
        # rewritten as a 200 by the catch-all below.
        raise
    except Exception as e:
        logger.error(f"NL query failed: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "natural_query": body.natural_query,
            "cypher_query": None,
            "results": [],
            "result_count": 0,
            "execution_time": 0,
            "fact_tier": "T3",
        }


@router.get("/query/suggestions")
async def query_suggestions(q: Optional[str] = Query(default="")):
    """Get query suggestions."""
    try:
        from query.nl_to_cypher import get_nl_translator
        translator = get_nl_translator()
        suggestions = await translator.get_query_suggestions(q or "")
        return suggestions
    except HTTPException:
        # Preserve FastAPI's intended 4xx response — don't let it get
        # rewritten as a 200 by the catch-all below.
        raise
    except Exception as e:
        logger.error(f"Query suggestions failed: {e}", exc_info=True)
        return [
            "Find the latest papers about transformers",
            "Show me top models for text generation",
            "Which tools implement RAG?",
            "Find papers published in 2025",
            "Show techniques used in LLM fine-tuning",
        ]
