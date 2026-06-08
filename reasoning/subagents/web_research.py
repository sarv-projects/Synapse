"""Web Research Subagent — Crawl4AI + DuckDuckGo + Tavily + ZenRows fallback."""
import asyncio
import logging
import os

from reasoning.graph.state import ReasoningState
from retrieval.session_index import get_session_index

logger = logging.getLogger(__name__)

CRAWL4AI_AVAILABLE = False
try:
    from crawl4ai import AsyncWebCrawler
    CRAWL4AI_AVAILABLE = True
except ImportError:
    logger.warning("crawl4ai not installed; web content fetching will use aiohttp fallback")

TAVILY_AVAILABLE = False
try:
    from tavily import TavilyClient
    TAVILY_AVAILABLE = True
except ImportError:
    logger.warning("tavily-python not installed; Tavily search disabled")

ZENROWS_AVAILABLE = False
try:
    ZENROWS_API_KEY = os.getenv("ZENROWS_API_KEY", "")
    if ZENROWS_API_KEY:
        ZENROWS_AVAILABLE = True
except Exception as e:
    logger.warning(f"Non-critical failure checking ZenRows (continuing): {e}")


async def _search_duckduckgo(queries: list[dict]) -> list[dict]:
    """Search DuckDuckGo for free web results."""
    results = []
    try:
        from duckduckgo_search import AsyncDDGS
        async with AsyncDDGS() as ddgs:
            for sq in queries[:5]:
                query_text = sq.get("query", sq) if isinstance(sq, dict) else str(sq)
                try:
                    ddg_results = await asyncio.wait_for(
                        asyncio.to_thread(
                            lambda q: list(ddgs.text(q, max_results=3)),
                            query_text,
                        ),
                        timeout=10.0,
                    )
                    for r in ddg_results if isinstance(ddg_results, list) else []:
                        results.append({
                            "url": r.get("href", ""),
                            "title": r.get("title", ""),
                            "snippet": r.get("body", ""),
                            "source": "duckduckgo",
                        })
                except Exception as e:
                    logger.error(f"DuckDuckGo query failed: {e}", exc_info=True)
    except ImportError:
        logger.warning("duckduckgo-search not installed")
    except Exception as e:
        logger.error(f"DuckDuckGo search failed: {e}", exc_info=True)
    return results


async def _search_tavily(queries: list[dict]) -> list[dict]:
    """Search Tavily for AI-ranked results (top 2-3 priority queries)."""
    api_key = os.getenv("TAVILY_API_KEY", "")
    if not api_key or not TAVILY_AVAILABLE:
        return []
    results = []
    try:
        client = TavilyClient(api_key=api_key)
        priority_queries = sorted(
            [q for q in queries[:5] if isinstance(q, dict)],
            key=lambda q: q.get("priority", 3),
        )[:3]
        for sq in priority_queries:
            query_text = sq.get("query", str(sq))
            try:
                response = await asyncio.wait_for(
                    asyncio.to_thread(
                        client.search,
                        query_text,
                        search_depth="advanced",
                        max_results=3,
                    ),
                    timeout=15.0,
                )
                for r in (response.get("results", []) if isinstance(response, dict) else []):
                    results.append({
                        "url": r.get("url", ""),
                        "title": r.get("title", ""),
                        "snippet": r.get("content", ""),
                        "source": "tavily",
                        "score": r.get("score", 0),
                    })
            except Exception as e:
                logger.error(f"Tavily query failed: {e}", exc_info=True)
    except Exception as e:
        logger.error(f"Tavily search failed: {e}", exc_info=True)
    return results


async def _fetch_with_crawl4ai(urls: list[str]) -> list[dict]:
    """Fetch and clean web content using Crawl4AI (Playwright-backed)."""
    if not CRAWL4AI_AVAILABLE:
        return await _fetch_with_aiohttp(urls)

    results = []
    try:
        async with AsyncWebCrawler(verbose=False) as crawler:
            for url in urls[:5]:
                try:
                    result = await asyncio.wait_for(
                        crawler.arun(url=url),
                        timeout=int(os.getenv("CRAWL4AI_TIMEOUT", "30")),
                    )
                    if result and result.markdown:
                        results.append({
                            "url": url,
                            "content_md": result.markdown[:10000],
                            "title": getattr(result, "title", "") or url,
                            "fetched_at": "",
                            "source": "crawl4ai",
                        })
                except asyncio.TimeoutError:
                    logger.warning(f"Crawl4AI timeout for {url}, trying ZenRows fallback")
                    zenrows_result = await _fetch_with_zenrows(url)
                    if zenrows_result:
                        results.append(zenrows_result)
                except Exception as e:
                    logger.error(f"Crawl4AI fetch failed for {url}: {e}", exc_info=True)
                    zenrows_result = await _fetch_with_zenrows(url)
                    if zenrows_result:
                        results.append(zenrows_result)
    except Exception as e:
        logger.error(f"Crawl4AI crawler failed, falling back to aiohttp: {e}", exc_info=True)
        results = await _fetch_with_aiohttp(urls)
    return results


async def _fetch_with_zenrows(url: str) -> dict | None:
    """ZenRows anti-bot fallback when Crawl4AI fails."""
    api_key = os.getenv("ZENROWS_API_KEY", "")
    if not api_key:
        return None
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            params = {"url": url, "apikey": api_key, "premium_proxy": "true"}
            async with session.get(
                "https://api.zenrows.com/v1/",
                params=params,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as resp:
                if resp.status == 200:
                    text = await resp.text()
                    return {
                        "url": url, "content_md": text[:10000], "title": url,
                        "fetched_at": "", "source": "zenrows",
                    }
    except Exception as e:
        logger.error(f"ZenRows fallback failed for {url}: {e}", exc_info=True)
    return None


async def _fetch_with_aiohttp(urls: list[str]) -> list[dict]:
    """Simple aiohttp fallback when Crawl4AI is not available."""
    import aiohttp
    results = []
    async with aiohttp.ClientSession() as session:
        for url in urls[:5]:
            try:
                async with session.get(
                    url,
                    headers={"User-Agent": "SYNAPSE/4.0"},
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status == 200:
                        text = await resp.text()
                        results.append({
                            "url": url, "content_md": text[:10000], "title": url,
                            "fetched_at": "", "source": "aiohttp",
                        })
            except Exception as e:
                logger.error(f"aiohttp fetch failed for {url}: {e}", exc_info=True)
    return results


async def web_research_subagent(state: ReasoningState) -> ReasoningState:
    """Node 4: DuckDuckGo + Tavily + Crawl4AI + ZenRows fallback."""
    state["current_node"] = "web_research"
    state["web_research_used"] = True

    queries = state.get("search_queries")
    if not queries:
        queries = [{"query": state.get("query", ""), "priority": 1}]

    logger.info(f"Web research: {len(queries)} queries, Crawl4AI={CRAWL4AI_AVAILABLE}, Tavily={TAVILY_AVAILABLE}")

    # Parallel search across DuckDuckGo and Tavily
    ddg_results, tavily_results = await asyncio.gather(
        _search_duckduckgo(queries),
        _search_tavily(queries),
    )

    # Merge, deduplicate by URL, Tavily results first (higher quality)
    all_search = tavily_results + ddg_results
    seen_urls = set()
    ranked = []
    for r in all_search:
        url = r.get("url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            ranked.append(r)

    # Fetch content via Crawl4AI (with ZenRows fallback)
    urls_to_fetch = [r["url"] for r in ranked[:5]]
    fetched = await _fetch_with_crawl4ai(urls_to_fetch)

    # Store in session index
    session_id = state.get("session_id")
    if session_id and fetched:
        sess_idx = get_session_index(session_id)
        sess_idx.add_documents(fetched)
        logger.info(f"Web research: fetched {len(fetched)} pages, stored in session index")

    return {
        "web_results": fetched,
        "web_research_used": True
    }


class WebResearchAgent:
    """Web research agent that orchestrates search and content fetching.

    Wraps the :func:`web_research_subagent` function for use as a
    drop-in LangGraph node or standalone research tool.
    """

    def __init__(self) -> None:
        self._last_results: list[dict] | None = None

    async def run(self, state: ReasoningState) -> ReasoningState:
        """Execute web research and update *state* with results."""
        result = await web_research_subagent(state)
        self._last_results = result.get("web_results")
        return result

    @property
    def last_results(self) -> list[dict] | None:
        """Results from the most recent :meth:`run` call."""
        return self._last_results
