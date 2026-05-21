"""Subagent Manager — spawns budget-sliced subgraphs."""
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
        """Spawn a subgraph execution with budget constraints."""
        logger.info(f"Spawning subagent for {task_type} (max {max_tokens} tokens, {max_duration}s)")
        return {"result": "placeholder"}, 0, True


_manager: SubagentManager | None = None


def get_subagent_manager() -> SubagentManager:
    global _manager
    if _manager is None:
        _manager = SubagentManager()
    return _manager
