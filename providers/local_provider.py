"""LocalProvider — zero-API-cost fallback (spaCy NER, BM25, extractive)."""
import logging
from typing import AsyncIterator

from providers.protocol import AssembledPrompt, InferenceConfig, InferenceResult, InferenceProvider

logger = logging.getLogger(__name__)


class LocalProvider(InferenceProvider):
    """Falls back to local processing when all API budget is exhausted."""

    provider_name = "local"

    def __init__(self, model_id: str = "local"):
        self.model_id = model_id

    async def generate(self, prompt: AssembledPrompt, config: InferenceConfig) -> InferenceResult:
        """Use BM25 retrieval context to produce an extractive summary."""
        task = prompt.task or prompt.to_string()
        context_texts = [c.get("content", "") if isinstance(c, dict) else str(c) for c in (prompt.context or [])]

        if context_texts:
            # Extractive: return the most relevant context passages
            from rank_bm25 import BM25Okapi
            import re

            def tokenize(t: str) -> list[str]:
                return re.findall(r"[a-z0-9]+", t.lower())

            corpus = [tokenize(t) for t in context_texts]
            bm25 = BM25Okapi(corpus)
            scores = bm25.get_scores(tokenize(task))
            ranked = sorted(zip(scores, context_texts), key=lambda x: x[0], reverse=True)
            top_passages = [text for _, text in ranked[:3] if text.strip()]
            result_text = "\n\n".join(top_passages) if top_passages else "[LOCAL] No relevant context found."
        else:
            result_text = "[LOCAL FALLBACK] No API budget available and no context provided."

        return InferenceResult(
            content=result_text,
            input_tokens_used=0,
            output_tokens_used=0,
            model_id="local",
            latency_ms=1,
        )

    async def stream(self, prompt: AssembledPrompt, config: InferenceConfig) -> AsyncIterator[str]:
        result = await self.generate(prompt, config)
        yield result.content
