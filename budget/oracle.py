"""Budget Oracle — async singleton consulted before every LLM call in v4.0."""
import asyncio
import logging
import yaml
from pathlib import Path
from typing import Optional

from budget.register import BudgetRegister, ModelBudget
from budget.scheduler import LeakyBucketScheduler
from budget.prompt_caching import supports_prompt_caching, get_effective_tpm_cost

logger = logging.getLogger(__name__)


class BudgetOracle:
    """Shared singleton. Accessible from every LangGraph node before any LLM call."""

    def __init__(self):
        self.register = BudgetRegister()
        self.scheduler = LeakyBucketScheduler()
        self.fallback_chains: dict = {}
        self._load_fallback_chains()
        self._restored = False

    async def _restore_if_needed(self):
        if self._restored:
            return
        try:
            from budget.dynamodb import get_dynamodb_store
            db = get_dynamodb_store()
            await db.connect()
            data = await db.load_budget()
            if data:
                for mid, mdata in data.items():
                    budget = self.register.get(mid)
                    budget.rpm_remaining = mdata.get("rpm_remaining", budget.rpm_remaining)
                    budget.rpd_remaining = mdata.get("rpd_remaining", budget.rpd_remaining)
                    budget.tpm_remaining = mdata.get("tpm_remaining", budget.tpm_remaining)
                logger.info(f"Budget Oracle restored {len(data)} models from DynamoDB")
        except Exception as e:
            logger.exception("Failed to restore budget state from DynamoDB")
            logger.warning("Falling back to default in-memory budgets.")
        self._restored = True

    def _load_fallback_chains(self):
        path = Path(__file__).parent / "fallback_chains.yaml"
        try:
            with open(path) as f:
                self.fallback_chains = yaml.safe_load(f) or {}
            logger.info(f"Loaded fallback chains for: {list(self.fallback_chains)}")
        except Exception as e:
            logger.warning(f"Could not load fallback_chains.yaml: {e}")

    def can_afford(self, model_id: str, estimated_tokens: int) -> bool:
        budget = self.register.get(model_id)
        effective = self._effective_tokens(model_id, estimated_tokens)
        return budget.can_afford(effective)

    async def gate(self, model_id: str, estimated_tokens: int) -> tuple[bool, str]:
        await self._restore_if_needed()
        budget = self.register.get(model_id)
        effective = self._effective_tokens(model_id, estimated_tokens)
        if budget.can_afford(effective):
            budget.reserve(effective)
            try:
                await self.scheduler.acquire(model_id)
            except Exception:
                # Cancel reservation to prevent token leak
                budget.tokens_in_flight = max(0, budget.tokens_in_flight - effective)
                raise
            return True, model_id
        return False, "local"

    def resolve_model(self, task_type: str, model_id: str, estimated_tokens: int) -> str:
        """Walk fallback chain to find first model that can afford the call."""
        budget = self.register.get(model_id)
        effective = self._effective_tokens(model_id, estimated_tokens)
        if budget.can_afford(effective):
            budget.reserve(effective)
            return model_id

        chain = self.fallback_chains.get(task_type, {}).get("fallbacks", [])
        for fallback_id in chain:
            if fallback_id == "local":
                return "local"
            fb = self.register.get(fallback_id)
            fb_effective = self._effective_tokens(fallback_id, estimated_tokens)
            if fb.can_afford(fb_effective):
                fb.reserve(fb_effective)
                logger.info(f"Budget gate: {task_type} fell back from {model_id} to {fallback_id}")
                return fallback_id
        return "local"

    def _effective_tokens(self, model_id: str, estimated_tokens: int) -> int:
        """Deduct cached tokens if model supports prompt caching."""
        if supports_prompt_caching(model_id):
            return max(1, estimated_tokens // 4)
        return estimated_tokens

    def record_usage(self, model_id: str, actual_tokens: int, headers: dict | None = None):
        budget = self.register.get(model_id)
        budget.release(actual_tokens)
        if headers:
            budget.update_from_headers(headers)

    def snapshot(self) -> dict:
        return self.register.snapshot()

    async def persist(self):
        try:
            from budget.dynamodb import get_dynamodb_store
            db = get_dynamodb_store()
            await db.connect()
            await db.save_budget(self.snapshot())
        except Exception as e:
            logger.debug(f"Budget persist skipped: {e}")

    def routing_log(self) -> list[dict]:
        return self.scheduler.recent_routes


_oracle: Optional[BudgetOracle] = None


def get_budget_oracle() -> BudgetOracle:
    global _oracle
    if _oracle is None:
        _oracle = BudgetOracle()
    return _oracle
