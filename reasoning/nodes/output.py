"""Node 7: Output Node — template assembly, source list, RAGAS evaluation, final Markdown."""
import logging

from reasoning.graph.state import ReasoningState

logger = logging.getLogger(__name__)


async def output_node(state: ReasoningState) -> ReasoningState:
    state.current_node = "output"
    state.status = "COMPLETE"

    markdown = state.synthesis_markdown
    if not markdown:
        markdown = f"## Summary\nNo synthesis was produced for query: {state.query}\n"
        markdown += f"\n## Knowledge Gaps\nUnable to process this query. {state.error}"

    # Build source list
    sources = []
    seen_urls = set()
    for r in state.retrieval_context[:10]:
        url = r.get("url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            sources.append({
                "url": url,
                "title": r.get("title", ""),
                "source": r.get("source", "unknown"),
                "snippet": (r.get("snippet") or r.get("content", ""))[:200],
            })

    state.sources = sources
    state.knowledge_gaps = state.critic_result.get("missing_sub_questions", [])
    state.final_markdown = markdown
    state.produced_by = "markdown"

    # ── RAGAS evaluation ────────────────────────────────────────────────
    total_tokens = sum(state.total_tokens_used.values()) if state.total_tokens_used else 0
    contexts = [
        r.get("content") or r.get("snippet") or str(r)
        for r in state.retrieval_context[:20]
    ]
    try:
        from eval.ragas_monitor import get_ragas_monitor
        monitor = get_ragas_monitor()
        await monitor.evaluate(
            query=state.query,
            answer=markdown,
            contexts=contexts,
            retrieval_confidence=state.retrieval_confidence,
            total_tokens=total_tokens,
            model_trace=state.model_trace,
        )
    except Exception as e:
        logger.debug(f"RAGAS eval skipped: {e}")

    logger.info(
        f"Output: produced_by={state.produced_by}, "
        f"markdown={len(state.final_markdown)} chars, sources={len(sources)}"
    )

    return state
