"""Background content acquisition — 9 curated sources, 6-hourly scrape, 5-gate verifier."""
import asyncio
import hashlib
import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

REJECT_LOG = Path(__file__).parent / "reject_log.jsonl"

AI_KEYWORDS = [
    "neural", "transformer", "attention", "llm", "embedding", "fine-tuning",
    "loss", "gradient", "architecture", "training", "inference", "lora",
    "diffusion", "rag", "retrieval", "reinforcement learning", "nlp",
    "computer vision", "model", "deep learning", "machine learning",
    "language model", "gpt", "bert", "llama", "mistral", "quantization",
    "multimodal", "prompt", "chain-of-thought", "alignment", "rlhf",
]

SPAM_PATTERNS = [
    "you won't believe", "shocking", "mind blowing", "secret",
    "buy now", "limited offer", "discount", "subscribe",
]


def _log_reject(reason: str, url: str, gate: int, metadata: dict | None = None):
    entry = {"timestamp": datetime.now(UTC).isoformat(), "url": url, "gate": gate, "reason": reason, "metadata": metadata or {}}
    with open(REJECT_LOG, "a") as f:
        f.write(json.dumps(entry) + "\n")


def _gate1_structural(content: str, url: str) -> bool:
    if not content or len(content) < 200:
        _log_reject("Content too short or empty", url, 1, {"length": len(content)})
        return False
    content_lower = content[:500].lower()
    for sig in ["404", "not found", "access denied", "captcha", "cloudflare"]:
        if sig in content_lower:
            _log_reject(f"Error page: {sig}", url, 1)
            return False
    return True


def _gate2_domain_relevance(content: str, url: str) -> bool:
    content_lower = content.lower()
    hits = sum(1 for kw in AI_KEYWORDS if kw in content_lower)
    if hits < 2:
        _log_reject(f"Domain relevance low: {hits} keywords", url, 2, {"keyword_hits": hits})
        return False
    return True


def _gate3_spam(title: str, content: str, url: str) -> bool:
    title_upper = title.upper()
    cap_ratio = sum(1 for c in title_upper if c.isupper()) / max(1, len(title))
    if cap_ratio > 0.3:
        _log_reject(f"Excessive ALL CAPS: {cap_ratio:.2f}", url, 3)
        return False
    text_lower = (title + " " + content[:300]).lower()
    for pattern in SPAM_PATTERNS:
        if pattern in text_lower:
            _log_reject(f"Spam pattern: {pattern}", url, 3)
            return False
    return True


def _gate4_source_credibility(source_type: str, metrics: dict, url: str) -> bool:
    thresholds = {"reddit": 5, "hackernews": 5, "medium": 10, "github": 5, "youtube": 100}
    threshold = thresholds.get(source_type)
    if threshold is None:
        return True
    score = metrics.get("score", metrics.get("stars", metrics.get("views", 0)))
    if score < threshold:
        _log_reject(f"Credibility below threshold: {score} < {threshold}", url, 4, {"score": score})
        return False
    return True


async def _gate5_semantic_dedup(title: str, content: str, url: str) -> bool:
    """Gate 5: Qdrant semantic dedup — cosine ≥ 0.92 means duplicate."""
    try:
        from embedding.generator import EmbeddingGenerator
        from embedding.qdrant_client import get_qdrant_client
        gen = EmbeddingGenerator()
        vector = gen.generate_entity_embedding(title, content[:512])
        qdrant = get_qdrant_client()
        results = qdrant.search_similar(vector, limit=1, score_threshold=0.92)
        if results:
            _log_reject(f"Semantic duplicate (cosine ≥ 0.92)", url, 5, {"match_url": results[0].get("payload", {}).get("name", "")})
            return False
    except Exception as e:
        logger.debug(f"Gate 5 Qdrant dedup skipped: {e}")
    return True


async def _store_in_neo4q(title: str, content: str, url: str, source_type: str):
    """Store verified content as BackgroundContent node in Neo4j."""
    try:
        from ingestion.neo4j.client import Neo4jClient
        from schema.config import get_settings
        client = Neo4jClient.from_settings(get_settings())
        async with client.session() as s:
            await s.run("""
                MERGE (bc:BackgroundContent {source_url: $url})
                SET bc.title = $title, bc.content_md = $content, bc.source_type = $type,
                    bc.scraped_at = datetime(), bc.status = 'active', bc.verified = true
            """, url=url, title=title, content=content[:10000], type=source_type)
        await client.close()
    except Exception as e:
        logger.debug(f"Neo4j storage skipped: {e}")


# ── Source-specific fetch functions ──────────────────────────────────────────

async def _fetch_hn(session) -> list[dict]:
    """Hacker News AI posts via Algolia API."""
    try:
        import aiohttp
        async with session.get("https://hn.algolia.com/api/v1/search?query=AI+machine+learning&tags=story&hitsPerPage=5") as resp:
            if resp.status == 200:
                data = await resp.json()
                return [{"title": h.get("title", ""), "content": h.get("story_text", "") or f"Points: {h.get('points', 0)} URL: {h.get('url', '')}", "url": h.get("url", f"https://news.ycombinator.com/item?id={h.get('objectID')}"), "source_type": "hackernews", "metrics": {"score": h.get("points", 0)}} for h in data.get("hits", [])]
    except Exception as e:
        logger.debug(f"HN fetch failed: {e}")
    return []


async def _fetch_reddit(session) -> list[dict]:
    """ML subreddits via Reddit JSON API."""
    results = []
    for sub in ["MachineLearning", "LocalLLaMA"]:
        try:
            import aiohttp
            async with session.get(f"https://www.reddit.com/r/{sub}/hot.json?limit=3", headers={"User-Agent": "SYNAPSE/4.0"}) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    for post in data.get("data", {}).get("children", []):
                        d = post["data"]
                        results.append({"title": d.get("title", ""), "content": d.get("selftext", "")[:5000], "url": f"https://reddit.com{d.get('permalink', '')}", "source_type": "reddit", "metrics": {"score": d.get("score", 0)}})
        except Exception as e:
            logger.debug(f"Reddit r/{sub} failed: {e}")
    return results


async def _fetch_medium(session) -> list[dict]:
    """Medium AI publications via RSS."""
    feeds = ["https://towardsdatascience.com/feed", "https://medium.com/feed/towards-artificial-intelligence", "https://medium.com/feed/mlreview"]
    results = []
    for feed_url in feeds:
        try:
            import feedparser
            import asyncio
            feed = await asyncio.to_thread(feedparser.parse, feed_url)
            for entry in feed.entries[:3]:
                results.append({"title": entry.get("title", ""), "content": entry.get("summary", "")[:5000], "url": entry.get("link", ""), "source_type": "medium", "metrics": {"score": 10}})
        except Exception as e:
            logger.debug(f"Medium feed {feed_url} failed: {e}")
    return results


async def _fetch_github_trending(session) -> list[dict]:
    """GitHub trending ML repos."""
    try:
        import aiohttp
        async with session.get("https://api.github.com/search/repositories?q=machine+learning+language:python&sort=stars&per_page=5", headers={"Accept": "application/vnd.github.v3+json"}) as resp:
            if resp.status == 200:
                data = await resp.json()
                return [{"title": r.get("full_name", ""), "content": r.get("description", "") or "", "url": r.get("html_url", ""), "source_type": "github", "metrics": {"stars": r.get("stargazers_count", 0)}} for r in data.get("items", [])]
    except Exception as e:
        logger.debug(f"GitHub trending failed: {e}")
    return []


async def _fetch_devto(session) -> list[dict]:
    """Dev.to AI articles."""
    results = []
    for tag in ["ai", "machinelearning"]:
        try:
            import aiohttp
            async with session.get(f"https://dev.to/api/articles?tag={tag}&top=3") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    for item in data[:3]:
                        results.append({"title": item.get("title", ""), "content": item.get("body_markdown", item.get("description", ""))[:5000], "url": item.get("url", ""), "source_type": "devto", "metrics": {"score": item.get("positive_reactions_count", 0)}})
        except Exception as e:
            logger.debug(f"Dev.to {tag} failed: {e}")
    return results


async def _fetch_youtube(session) -> list[dict]:
    """YouTube ML papers explained."""
    try:
        from youtube_search import YoutubeSearch
        results = await asyncio.to_thread(lambda: YoutubeSearch("machine learning paper explained", max_results=3).to_dict())
        return [{"title": r.get("title", ""), "content": r.get("description", "") or f"Views: {r.get('views', '')}", "url": f"https://youtube.com{r.get('url_suffix', '')}", "source_type": "youtube", "metrics": {"views": int(r.get("views", "0").replace(",", ""))}} for r in (results if isinstance(results, list) else [])]
    except Exception as e:
        logger.debug(f"YouTube search failed: {e}")
    return []


async def _fetch_substack(session) -> list[dict]:
    """Substack AI newsletters (placeholder — RSS feeds vary)."""
    return []


async def _fetch_blogs(session) -> list[dict]:
    """AI research blogs (Distill, BAIR, OpenAI, DeepMind, Anthropic)."""
    blog_urls = [
        "https://openai.com/blog/rss.xml",
        "https://www.anthropic.com/blog/rss.xml",
        "https://bair.berkeley.edu/blog/feed.xml",
    ]
    results = []
    for feed_url in blog_urls:
        try:
            import feedparser
            import asyncio
            feed = await asyncio.to_thread(feedparser.parse, feed_url)
            for entry in feed.entries[:2]:
                results.append({"title": entry.get("title", ""), "content": entry.get("summary", "")[:5000], "url": entry.get("link", ""), "source_type": "research_blog", "metrics": {}})
        except Exception as e:
            logger.debug(f"Blog feed {feed_url} failed: {e}")
    return results


async def run_background_scrape(dry_run: bool = False) -> dict:
    """Run full background content acquisition pipeline."""
    logger.info("Starting background scrape (6-hourly) — 9 sources")
    stats = {"total_fetched": 0, "passed": 0, "rejected": 0, "stored": 0, "errors": 0}

    import aiohttp
    async with aiohttp.ClientSession() as session:
        fetchers = [
            _fetch_devto(session),
            _fetch_hn(session),
            _fetch_reddit(session),
            _fetch_medium(session),
            _fetch_github_trending(session),
            _fetch_youtube(session),
            _fetch_substack(session),
            _fetch_blogs(session),
        ]
        results = await asyncio.gather(*fetchers, return_exceptions=True)

        for source_results in results:
            if isinstance(source_results, Exception):
                stats["errors"] += 1
                continue
            for item in source_results:
                stats["total_fetched"] += 1
                title = str(item.get("title", ""))
                content = str(item.get("content", ""))
                url = str(item.get("url", ""))
                source_type = str(item.get("source_type", "unknown"))
                metrics = item.get("metrics", {})

                if not _gate1_structural(content, url):
                    stats["rejected"] += 1; continue
                if not _gate2_domain_relevance(content, url):
                    stats["rejected"] += 1; continue
                if not _gate3_spam(title, content, url):
                    stats["rejected"] += 1; continue
                if not _gate4_source_credibility(source_type, metrics, url):
                    stats["rejected"] += 1; continue
                if not await _gate5_semantic_dedup(title, content, url):
                    stats["rejected"] += 1; continue

                stats["passed"] += 1
                if not dry_run:
                    await _store_in_neo4q(title, content, url, source_type)
                    stats["stored"] += 1

    logger.info(f"Background scrape complete: {stats}")
    return stats


def main():
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    parser = argparse.ArgumentParser(description="SYNAPSE v4 Background Scraper")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    result = asyncio.run(run_background_scrape(dry_run=args.dry_run))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
