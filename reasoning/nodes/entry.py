"""Node 1: Budget Oracle Entry — checks budgets, returns routing plan."""
import logging
import uuid

from reasoning.graph.state import ReasoningState

logger = logging.getLogger(__name__)


async def entry_node(state: ReasoningState) -> ReasoningState:
    state.current_node = "entry"
    state.status = "PROCESSING"

    if not state.session_id:
        state.session_id = str(uuid.uuid4())

    from budget.oracle import get_budget_oracle
    oracle = get_budget_oracle()
    snapshot = oracle.snapshot()
    state.budget_snapshot = snapshot

    # Quick complexity estimation
    query_len = len(state.query)
    if query_len < 100:
        estimated_complexity = "low"
    elif query_len < 500:
        estimated_complexity = "medium"
    else:
        estimated_complexity = "high"

    # Check if any capable model is available
    models_available = [
        mid for mid, m in snapshot.items()
        if m["rpd_remaining"] > 0 and m["rpm_remaining"] > 0 and m["tpm_remaining"] > 1000
    ]

    if not models_available:
        state.status = "FAILED"
        state.error = "All model budgets exhausted. Try again after rate limit reset."
        return state

    logger.info(
        f"Entry: session={state.session_id}, complexity={estimated_complexity}, "
        f"models_available={len(models_available)}, query='{state.query[:80]}...'"
    )

    return state
