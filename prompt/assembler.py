"""Prompt Assembly Layer — mandatory pre-inference step for all LLM calls."""
import logging
import tiktoken
from pathlib import Path
from typing import Optional

from providers.protocol import AssembledPrompt

logger = logging.getLogger(__name__)


class PromptAssembler:
    """Five-layer prompt builder with budget trimming."""

    ROLE_DIR = Path(__file__).parent / "roles"

    def __init__(self):
        self._encoding = None
        self._role_cache: dict[str, str] = {}

    @property
    def encoding(self):
        if self._encoding is None:
            try:
                self._encoding = tiktoken.get_encoding("cl100k_base")
            except Exception:
                self._encoding = tiktoken.get_encoding("gpt2")
        return self._encoding

    def _load_role(self, role_name: str) -> str:
        if role_name not in self._role_cache:
            path = self.ROLE_DIR / f"{role_name}.txt"
            if path.exists():
                self._role_cache[role_name] = path.read_text()
            else:
                self._role_cache[role_name] = ""
        return self._role_cache[role_name]

    def estimate_tokens(self, text: str) -> int:
        try:
            return len(self.encoding.encode(text))
        except Exception:
            return len(text) // 4

    def assemble(
        self,
        role: str,
        task_content: str,
        retrieval_context: list[str] | None = None,
        tools: list[str] | None = None,
        max_tokens: int = 6000,
    ) -> AssembledPrompt:
        """Build an AssembledPrompt with budget-aware trimming."""

        # Layer 1: System (cached, never trimmed)
        system = self._load_role(role)

        # Layer 2: Retrieval context (trimmed first when budget is tight)
        context = retrieval_context or []

        # Layer 3: Tool schemas (trimmed before retrieval context)
        tool_schemas = tools or []

        # Layer 4: Dynamic task content (never trimmed)
        task = task_content

        # Estimate and trim
        prompt = AssembledPrompt(system=system, context=list(context), tools=list(tool_schemas), task=task)
        estimated = self.estimate_tokens(system) + self.estimate_tokens(task)

        # If over budget, trim layer 3 then layer 2
        remaining = max_tokens - estimated

        # Trim tools first
        while tool_schemas and self.estimate_tokens("\n".join(tool_schemas)) > max(0, remaining // 4):
            tool_schemas.pop()

        remaining = max_tokens - estimated - self.estimate_tokens("\n".join(tool_schemas))

        # Trim context next (lowest-ranked chunks removed first)
        while context and self.estimate_tokens("\n\n".join(context)) > max(0, remaining):
            context.pop()

        prompt.context = list(context)
        prompt.tools = list(tool_schemas)
        prompt.estimated_tokens = self.estimate_tokens(prompt.to_string())

        logger.debug(f"Assembled prompt for {role}: ~{prompt.estimated_tokens} tokens")
        return prompt

    def assemble_json(self, role: str, task_content: str, **kwargs) -> AssembledPrompt:
        """Assemble with JSON output format instructions appended to system."""
        system = self._load_role(role)
        system += "\n\nOUTPUT: Return valid JSON only. No markdown fences, no explanatory text."

        ctx = kwargs.get("retrieval_context", [])
        tools = kwargs.get("tools", [])
        task = task_content
        max_tokens = kwargs.get("max_tokens", 6000)

        prompt = AssembledPrompt(system=system, context=list(ctx), tools=list(tools), task=task)
        prompt.estimated_tokens = self.estimate_tokens(prompt.to_string())
        return prompt
