"""Circuit breaker pattern for source fetchers."""
import asyncio
from enum import Enum
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Circuit breaker for individual sources."""
    
    def __init__(self, failure_threshold: int = 3, timeout_seconds: int = 1800, on_state_change=None):
        self.failure_threshold = failure_threshold
        self.timeout = timedelta(seconds=timeout_seconds)
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.on_state_change = on_state_change
    
    def _trigger_change(self):
        if self.on_state_change:
            self.on_state_change()

    def record_success(self):
        """Record successful call."""
        self.failure_count = 0
        self.state = CircuitState.CLOSED
        self._trigger_change()
    
    def record_failure(self):
        """Record failed call."""
        self.failure_count += 1
        self.last_failure_time = datetime.now()
        
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
        self._trigger_change()
    
    def can_attempt(self) -> bool:
        """Check if call can be attempted."""
        if self.state == CircuitState.CLOSED:
            return True
        
        if self.state == CircuitState.OPEN:
            if self.last_failure_time and datetime.now() - self.last_failure_time > self.timeout:
                self.state = CircuitState.HALF_OPEN
                self._trigger_change()
                return True
            return False
        
        # HALF_OPEN - allow one trial
        return True


class CircuitBreakerRegistry:
    """Registry of circuit breakers per source backed by JSON file persistence.

    Uses atomic temp-file + fcntl.flock so concurrent processes writing to
    the same state_path cannot corrupt the JSON. NOT a process-wide singleton
    — the owning module in circuit_breaker_wrapper.py holds the shared ref.
    """

    def __init__(self, state_path: str | None = None):
        self.breakers: Dict[str, CircuitBreaker] = {}
        if state_path is None:
            state_path = str(Path(__file__).parent / "circuit_breaker_state.json")
        self.state_path = state_path
        self._load_state()
    
    def _load_state(self):
        import os
        import json
        import fcntl
        import logging
        logger = logging.getLogger(__name__)
        if not os.path.exists(self.state_path):
            return
        lock_path = f"{self.state_path}.lock"
        lock_file = None
        f = None
        try:
            # Acquire a shared (read) lock so we never read a partially
            # replaced state file that a concurrent _save_state writes.
            lock_file = open(lock_path, "a+")
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_SH)

            f = open(self.state_path, "r")
            data = json.load(f)
            for name, item in data.items():
                breaker = CircuitBreaker(
                    failure_threshold=item.get("failure_threshold", 3),
                    timeout_seconds=item.get("timeout_seconds", 1800),
                    on_state_change=self._save_state
                )
                breaker.state = CircuitState(item.get("state", "closed"))
                breaker.failure_count = item.get("failure_count", 0)
                lft = item.get("last_failure_time")
                if lft:
                    breaker.last_failure_time = datetime.fromisoformat(lft)
                self.breakers[name] = breaker
        except Exception as e:
            logger.error(f"Failed to load circuit breaker state from {self.state_path}: {e}", exc_info=True)
        finally:
            if f:
                f.close()
            if lock_file is not None:
                try:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                except Exception:
                    pass
                try:
                    lock_file.close()
                except Exception:
                    pass

    def _save_state(self):
        """Persist all breaker states atomically.

        1. Lock file opened *before* entering try so we never half-hold a
           lock without knowing it.
        2. Temp file is written, fsynced, then atomically renamed via
           ``os.replace``.
        3. On any failure the lock is always released and any leftover
           ``*.tmp`` file is swept up so later runs start clean.
        """
        import json
        import os
        import fcntl
        import logging
        logger = logging.getLogger(__name__)

        lock_path = f"{self.state_path}.lock"
        temp_path = f"{self.state_path}.tmp"
        lock_file = None
        try:
            lock_file = open(lock_path, "a+")
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)

            data = {
                name: {
                    "state": breaker.state.value,
                    "failure_count": breaker.failure_count,
                    "last_failure_time": (
                        breaker.last_failure_time.isoformat()
                        if breaker.last_failure_time else None
                    ),
                    "failure_threshold": breaker.failure_threshold,
                    "timeout_seconds": int(breaker.timeout.total_seconds()),
                }
                for name, breaker in self.breakers.items()
            }

            with open(temp_path, "w") as temp_f:
                json.dump(data, temp_f, indent=2)
                temp_f.flush()
                os.fsync(temp_f.fileno())

            os.replace(temp_path, self.state_path)
        except Exception as e:
            logger.error(
                f"Failed to save circuit breaker state to {self.state_path}: {e}",
                exc_info=True,
            )
        finally:
            try:
                if lock_file is not None:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            except Exception:
                pass
            try:
                if lock_file is not None:
                    lock_file.close()
            except Exception:
                pass
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except Exception:
                pass
    
    def get_breaker(self, source_name: str) -> CircuitBreaker:
        """Get or create circuit breaker for source."""
        if source_name not in self.breakers:
            self.breakers[source_name] = CircuitBreaker(on_state_change=self._save_state)
            self._save_state()
        return self.breakers[source_name]
