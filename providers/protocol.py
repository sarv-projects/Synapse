"""InferenceProvider Protocol — the only interface for model calls in v4.0."""
import collections.abc
from dataclasses import dataclass, field
from typing import Literal, Protocol


@dataclass
class AssembledPrompt:
    """Output of Prompt Assembly Layer. Only accepted input to InferenceProvider."""
    system: str = ""
    context: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    task: str = ""
    estimated_tokens: int = 0

    def to_messages(self) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        if self.system:
            messages.append({"role": "system", "content": self.system})
        ctx = "\n\n".join(self.context) if self.context else ""
        tool_ctx = "\n".join(self.tools) if self.tools else ""
        parts = [p for p in [ctx, tool_ctx, self.task] if p]
        content = "\n\n".join(parts)
        messages.append({"role": "user", "content": content})
        return messages

    def to_string(self) -> str:
        parts = [self.system] if self.system else []
        if self.context:
            parts.append("\n\n".join(self.context))
        if self.tools:
            parts.append("\n".join(self.tools))
        parts.append(self.task)
        return "\n\n".join(parts)


@dataclass
class InferenceConfig:
    max_tokens: int = 1024
    temperature: float = 0.1
    reasoning_effort: Literal["low", "medium", "high"] | None = None
    response_format: Literal["text", "json"] = "text"


@dataclass
class InferenceResult:
    content: str
    input_tokens_used: int = 0
    output_tokens_used: int = 0
    cached_tokens: int = 0
    model_id: str = ""
    latency_ms: int = 0


class InferenceProvider(Protocol):
    model_id: str

    async def generate(self, prompt: AssembledPrompt, config: InferenceConfig) -> InferenceResult:
        ...

    async def stream(self, prompt: AssembledPrompt, config: InferenceConfig) -> collections.abc.AsyncIterator[str]:
        ...

