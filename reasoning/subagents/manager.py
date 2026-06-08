"""Subagent Manager — spawns budget-sliced subgraphs."""
import asyncio
import logging

from reasoning.graph.state import ReasoningState

logger = logging.getLogger(__name__)


class SubagentManager:
    """Spawns isolated LangGraph sub-graphs with budget allocation."""

    def __init__(self):
        self.max_depth = 3
        self.max_children = 5

    async def spawn(
        self,
        parent_state: ReasoningState,
        task_type: str,
        max_tokens: int = 2000,
        max_duration: int = 60,
    ) -> tuple[dict, int, bool]:
        """Spawn a subgraph execution with budget constraints.

        Returns (result_dict, tokens_used, success).
        """
        from budget.oracle import get_budget_oracle
        from providers.groq_provider import GroqProvider
        from providers.protocol import AssembledPrompt, InferenceConfig

        oracle = get_budget_oracle()
        model_id = oracle.resolve_model(task_type, "llama-3.3-70b-versatile", max_tokens)

        if model_id == "local":
            logger.warning(f"Subagent {task_type}: no budget, falling back to local")
            return {"result": f"[Budget exhausted for {task_type}]"}, 0, False

        provider = GroqProvider(model_id=model_id)
        prompt = AssembledPrompt(
            system=f"You are a focused sub-agent for task: {task_type}",
            context=[],
            tools=[],
            task=parent_state.get("query"),
        )
        config = InferenceConfig(max_tokens=max_tokens, temperature=0.3)

        try:
            result = await asyncio.wait_for(
                provider.generate(prompt, config),
                timeout=max_duration,
            )
            tokens_used = result.input_tokens_used + result.output_tokens_used
            oracle.record_usage(model_id, tokens_used)
            return {"result": result.content, "model": model_id}, tokens_used, True
        except asyncio.TimeoutError:
            logger.warning(f"Subagent {task_type} timed out after {max_duration}s")
            return {"result": f"[Timeout after {max_duration}s]"}, 0, False
        except Exception as e:
            logger.error(f"Subagent {task_type} failed: {e}")
            return {"result": f"[Error: {e}]"}, 0, False


_manager: SubagentManager | None = None


def get_subagent_manager() -> SubagentManager:
    global _manager
    if _manager is None:
        _manager = SubagentManager()
    return _manager
