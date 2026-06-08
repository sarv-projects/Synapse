"""Circuit breaker wrapper for source fetchers."""
import asyncio
import logging
from typing import List, Any

from ingestion.circuit_breaker import CircuitBreakerRegistry, CircuitState
from ingestion.sources.base import SourceDocument, SourceFetcher

logger = logging.getLogger(__name__)

# Module-level registry instance — lazily initialised so each OS process
# (e.g. Gunicorn worker) opens its own file descriptors and the
# fcntl.flock-based persistence protocol serialises them correctly.
_circuit_registry: CircuitBreakerRegistry | None = None


def _get_registry() -> CircuitBreakerRegistry:
    """Return the global registry, constructing it on first access."""
    global _circuit_registry
    if _circuit_registry is None:
        _circuit_registry = CircuitBreakerRegistry()
    return _circuit_registry


def reset_registry() -> None:
    """Replace the global registry with a fresh one.

    Intended for tests that supply an isolated ``state_path`` via
    ``CircuitBreakerRegistry(state_path=tmp)`` so each test gets its
    own independent breaker state without cross-test pollution.
    """
    global _circuit_registry
    _circuit_registry = None


class CircuitBreakerWrapper:
    """Wrapper that adds circuit breaker functionality to any fetcher."""

    def __init__(self, fetcher, _use_raw_fetch: bool = False):
        self.fetcher = fetcher
        self._use_raw_fetch = _use_raw_fetch
        source_name = "unknown"
        try:
            manifest = getattr(fetcher, "manifest", None)
            if manifest is not None and hasattr(manifest, "name"):
                source_name = manifest.name
            elif hasattr(fetcher, "config"):
                config = fetcher.config
                source_name = getattr(config, "name", "unknown") if hasattr(config, "name") else "unknown"
            else:
                source_name = getattr(fetcher, "source_name", "unknown")
        except Exception:
            source_name = "unknown"
        self.circuit_breaker = _get_registry().get_breaker(source_name)
        self.source_name = source_name
    
    async def fetch(self) -> List[SourceDocument]:
        """Fetch with circuit breaker protection."""
        if not self.circuit_breaker.can_attempt():
            logger.warning(f"Circuit breaker OPEN for {self.source_name}, skipping fetch")
            return []

        try:
            result = await self._fetch_with_backoff()
            self.circuit_breaker.record_success()
            # Defensive coercion: a fetcher that forgets to `return` would
            # otherwise leak `None` into downstream pipeline stages that
            # expect an iterable.
            return result if result is not None else []
        except Exception as e:
            logger.error(f"Fetch failed for {self.source_name}: {e}")
            self.circuit_breaker.record_failure()
            return []
    
    async def _fetch_with_backoff(self, max_retries: int = 3) -> List[SourceDocument]:
        """Fetch with exponential backoff for transient errors."""
        base_delay = 1.0
        
        for attempt in range(max_retries + 1):
            try:
                # If wrapping a ProtectedFetcher, call the raw parent fetch
                if self._use_raw_fetch and hasattr(self.fetcher, '_raw_fetch'):
                    return await self.fetcher._raw_fetch()
                return await self.fetcher.fetch()
            except Exception as e:
                if attempt == max_retries:
                    raise
                if not self._is_retryable_error(e):
                    raise
                delay = base_delay * (2 ** attempt)
                logger.warning(f"Attempt {attempt + 1} failed for {self.source_name}, retrying in {delay}s: {e}")
                await asyncio.sleep(delay)
    
    def _is_retryable_error(self, error: Exception) -> bool:
        """Check if error is retryable (transient)."""
        error_str = str(error).lower()
        
        # Retryable HTTP errors
        retryable_codes = ["429", "500", "502", "503", "504"]
        if any(code in error_str for code in retryable_codes):
            return True
        
        # Retryable network errors
        retryable_patterns = [
            "timeout", "connection", "network", "temporary", "rate limit"
        ]
        return any(pattern in error_str for pattern in retryable_patterns)
    
    def get_circuit_state(self) -> CircuitState:
        """Get current circuit breaker state."""
        return self.circuit_breaker.state
    
    def get_failure_count(self) -> int:
        """Get current failure count."""
        return self.circuit_breaker.failure_count


def circuit_breaker_protected(fetcher_class: type) -> type:
    """
    Class decorator to add circuit breaker protection to a SourceFetcher.
    
    Usage:
        @circuit_breaker_protected
        class MySourceFetcher(SourceFetcher):
            ...
    """
    class ProtectedFetcher(fetcher_class):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._circuit_wrapper = CircuitBreakerWrapper(self, _use_raw_fetch=True)
        
        async def _raw_fetch(self) -> List[SourceDocument]:
            """Call the original parent fetch (bypasses circuit breaker)."""
            return await super().fetch()
        
        async def fetch(self) -> List[SourceDocument]:
            return await self._circuit_wrapper.fetch()
        
        def get_circuit_state(self) -> CircuitState:
            return self._circuit_wrapper.get_circuit_state()
        
        def get_failure_count(self) -> int:
            return self._circuit_wrapper.get_failure_count()
    
    # Preserve original class name and module
    ProtectedFetcher.__name__ = fetcher_class.__name__
    ProtectedFetcher.__qualname__ = fetcher_class.__qualname__
    
    return ProtectedFetcher


def wrap_source_with_circuit_breaker(fetcher: SourceFetcher) -> SourceFetcher:
    """Wrap an existing SourceFetcher instance with circuit breaker."""
    return CircuitBreakerWrapper(fetcher)


def get_all_circuit_states() -> dict[str, dict[str, Any]]:
    """Get circuit breaker states for all sources."""
    registry = _get_registry()
    return {
        name: {
            "state": breaker.state.value,
            "failure_count": breaker.failure_count,
            "can_attempt": breaker.can_attempt()
        }
        for name, breaker in registry.breakers.items()
    }


def reset_circuit_breaker(source_name: str) -> bool:
    """Reset circuit breaker for a specific source (admin function)."""
    registry = _get_registry()
    if source_name in registry.breakers:
        breaker = registry.breakers[source_name]
        breaker.failure_count = 0
        breaker.state = CircuitState.CLOSED
        breaker.last_failure_time = None
        registry._save_state()
        logger.info(f"Reset circuit breaker for {source_name}")
        return True
    return False
