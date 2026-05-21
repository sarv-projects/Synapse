"""Prompt caching awareness — GPT-OSS models get free static prefix tokens."""
import logging

logger = logging.getLogger(__name__)

# Models that support prompt caching (May 2026):
# Only GPT-OSS models on Groq support prompt caching.
# Llama 4 Scout, Llama 3.3 70B, Llama 3.1 8B, Qwen3-32B do NOT.
PROMPT_CACHING_MODELS = {
    "openai/gpt-oss-20b": True,
    "openai/gpt-oss-120b": True,
}


def supports_prompt_caching(model_id: str) -> bool:
    """Check if a model supports prompt caching (static prefix costs zero TPM)."""
    return model_id in PROMPT_CACHING_MODELS


def estimate_cached_tokens(system_prompt: str, model_id: str) -> int:
    """Return 0 if model caches prompts (free), else estimate token cost."""
    if supports_prompt_caching(model_id):
        return 0
    # Rough estimate: 1 token ≈ 4 chars
    return len(system_prompt) // 4


def get_effective_tpm_cost(total_tokens: int, cached_tokens: int, model_id: str) -> int:
    """Compute effective TPM cost after prompt caching deduction."""
    if supports_prompt_caching(model_id):
        return max(0, total_tokens - cached_tokens)
    return total_tokens
