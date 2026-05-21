"""LocalProvider — zero-API-cost fallback (spaCy, BM25, rule-based)."""
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
        content = prompt.to_string()
        result_text = f"[LOCAL FALLBACK] Unable to process: {content[:200]}..."
        return InferenceResult(
            content=result_text,
            input_tokens_used=0,
            output_tokens_used=0,
            model_id="local",
            latency_ms=1,
        )

    async def stream(self, prompt: AssembledPrompt, config: InferenceConfig) -> AsyncIterator[str]:
        yield "[LOCAL FALLBACK] Streaming not supported.\n"
