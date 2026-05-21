"""GroqProvider — wraps GroqKeyManager behind the InferenceProvider protocol."""
import logging
import time
from typing import AsyncIterator

from providers.protocol import AssembledPrompt, InferenceConfig, InferenceResult, InferenceProvider

logger = logging.getLogger(__name__)


class GroqProvider(InferenceProvider):
    """One instance per Groq model. Delegates to GroqKeyManager for key rotation."""

    provider_name = "groq"

    def __init__(self, model_id: str):
        self.model_id = model_id

    async def generate(self, prompt: AssembledPrompt, config: InferenceConfig) -> InferenceResult:
        from api.groq_manager import get_groq_manager
        from groq import Groq

        manager = get_groq_manager()
        key = await manager.get_next_key()
        if not key:
            raise RuntimeError(f"No healthy Groq keys for model {self.model_id}")

        client = Groq(api_key=key.api_key)
        messages = prompt.to_messages()

        kwargs: dict = dict(
            model=self.model_id,
            messages=messages,
            max_tokens=config.max_tokens,
            temperature=config.temperature,
        )
        if config.response_format == "json":
            kwargs["response_format"] = {"type": "json_object"}

        t0 = time.perf_counter()
        try:
            response = client.chat.completions.create(**kwargs)
            choice = response.choices[0]
            usage = response.usage

            await manager._record_usage(key.api_key, success=True)

            return InferenceResult(
                content=choice.message.content or "",
                input_tokens_used=usage.prompt_tokens if usage else 0,
                output_tokens_used=usage.completion_tokens if usage else 0,
                cached_tokens=(usage.prompt_tokens_details.cached_tokens if usage and usage.prompt_tokens_details else 0),
                model_id=self.model_id,
                latency_ms=int((time.perf_counter() - t0) * 1000),
            )
        except Exception as e:
            await manager._record_usage(key.api_key, success=False)
            await manager._update_key_status_from_error(key.api_key, str(e))
            raise

    async def stream(self, prompt: AssembledPrompt, config: InferenceConfig) -> AsyncIterator[str]:
        from api.groq_manager import get_groq_manager
        from groq import Groq

        manager = get_groq_manager()
        key = await manager.get_next_key()
        if not key:
            raise RuntimeError(f"No healthy Groq keys for model {self.model_id}")

        client = Groq(api_key=key.api_key)
        messages = prompt.to_messages()

        stream = client.chat.completions.create(
            model=self.model_id,
            messages=messages,
            max_tokens=config.max_tokens,
            temperature=config.temperature,
            stream=True,
        )
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
