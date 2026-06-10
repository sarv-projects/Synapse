"""Leaky Bucket Scheduler — per-model asyncio semaphores for concurrency control."""
import asyncio
import logging
import random
from datetime import datetime, UTC
from typing import Any

logger = logging.getLogger(__name__)


class LeakyBucketScheduler:
    """Prevents racing into per-minute rate limits via per-model semaphores."""

    MODEL_CONCURRENCY = {
        "llama-3.1-8b-instant": 2,
        "meta-llama/llama-4-scout-17b-16e-instruct": 4,
        "llama-3.3-70b-versatile": 2,
        "openai/gpt-oss-20b": 2,
        "openai/gpt-oss-120b": 1,
        "qwen-qwq-32b": 2,
    }

    def __init__(self):
        self._semaphores: dict[str, asyncio.Semaphore] = {}
        self.recent_routes: list[dict[str, Any]] = []

    def _get_semaphore(self, model_id: str) -> asyncio.Semaphore:
        if model_id not in self._semaphores:
            # Default concurrency limit per model (conservative to avoid rate limits)
            limit = self.MODEL_CONCURRENCY.get(model_id, 2)
            self._semaphores[model_id] = asyncio.Semaphore(limit)
        return self._semaphores[model_id]

    async def acquire(self, model_id: str, max_retries: int = 10) -> None:
        """Acquire semaphore with maximum retry limit to prevent infinite loops."""
        sem = self._get_semaphore(model_id)
        delay: float = 0.0
        max_delay = 30.0
        retries = 0
        
        while retries < max_retries:
            try:
                # Semaphore timeout (5s allows for network latency + processing)
                await asyncio.wait_for(sem.acquire(), timeout=5.0)
                self._log_route(model_id, "acquired")
                return
            except asyncio.TimeoutError:
                retries += 1
                if retries >= max_retries:
                    logger.error(f"LeakyBucket: {model_id} exceeded max retries ({max_retries})")
                    raise RuntimeError(f"Failed to acquire semaphore for {model_id} after {max_retries} attempts")
                
                delay = min(delay + 1 + random.uniform(0, 1), max_delay)
                logger.debug(f"LeakyBucket: {model_id} waiting {delay:.1f}s (attempt {retries}/{max_retries})")
                await asyncio.sleep(delay)

    def release(self, model_id: str) -> None:
        if model_id in self._semaphores:
            self._semaphores[model_id].release()

    def _log_route(self, model_id: str, action: str):
        self.recent_routes.append({
            "model": model_id,
            "action": action,
            "timestamp": datetime.now(UTC).isoformat(),
        })
        if len(self.recent_routes) > 200:
            self.recent_routes = self.recent_routes[-100:]
