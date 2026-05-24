"""Circuit breaker pattern for source fetchers."""
from enum import Enum
from datetime import datetime, timedelta
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
    """Registry of circuit breakers per source backed by JSON file persistence."""
    
    def __init__(self, state_path: str | None = None):
        import os
        from pathlib import Path
        
        self.breakers: Dict[str, CircuitBreaker] = {}
        if state_path is None:
            state_path = str(Path(__file__).parent / "circuit_breaker_state.json")
        self.state_path = state_path
        self._load_state()
    
    def _load_state(self):
        import os
        import json
        import logging
        logger = logging.getLogger(__name__)
        if not os.path.exists(self.state_path):
            return
        f = None
        try:
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

    def _save_state(self):
        import json
        import os
        import fcntl
        import logging
        logger = logging.getLogger(__name__)
        lock_file = None
        temp_f = None
        try:
            data = {}
            for name, breaker in self.breakers.items():
                data[name] = {
                    "state": breaker.state.value,
                    "failure_count": breaker.failure_count,
                    "last_failure_time": breaker.last_failure_time.isoformat() if breaker.last_failure_time else None,
                    "failure_threshold": breaker.failure_threshold,
                    "timeout_seconds": int(breaker.timeout.total_seconds())
                }

            temp_path = f"{self.state_path}.tmp"
            lock_file = open(self.state_path, "a+")
            fcntl.flock(lock_file, fcntl.LOCK_EX)
            try:
                temp_f = open(temp_path, "w")
                json.dump(data, temp_f, indent=2)
                temp_f.close()
                temp_f = None
                os.replace(temp_path, self.state_path)
            finally:
                fcntl.flock(lock_file, fcntl.LOCK_UN)
        except Exception as e:
            logger.error(f"Failed to save circuit breaker state to {self.state_path}: {e}", exc_info=True)
        finally:
            if lock_file:
                lock_file.close()
            if temp_f:
                temp_f.close()
    
    def get_breaker(self, source_name: str) -> CircuitBreaker:
        """Get or create circuit breaker for source."""
        if source_name not in self.breakers:
            self.breakers[source_name] = CircuitBreaker(on_state_change=self._save_state)
            self._save_state()
        return self.breakers[source_name]
