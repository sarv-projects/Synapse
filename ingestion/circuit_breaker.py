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
    
    def __init__(self, failure_threshold: int = 3, timeout_seconds: int = 1800):
        self.failure_threshold = failure_threshold
        self.timeout = timedelta(seconds=timeout_seconds)
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time: Optional[datetime] = None
    
    def record_success(self):
        """Record successful call."""
        self.failure_count = 0
        self.state = CircuitState.CLOSED
    
    def record_failure(self):
        """Record failed call."""
        self.failure_count += 1
        self.last_failure_time = datetime.now()
        
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
    
    def can_attempt(self) -> bool:
        """Check if call can be attempted."""
        if self.state == CircuitState.CLOSED:
            return True
        
        if self.state == CircuitState.OPEN:
            if datetime.now() - self.last_failure_time > self.timeout:
                self.state = CircuitState.HALF_OPEN
                return True
            return False
        
        # HALF_OPEN - allow one trial
        return True


class CircuitBreakerRegistry:
    """Registry of circuit breakers per source."""
    
    def __init__(self):
        self.breakers: Dict[str, CircuitBreaker] = {}
    
    def get_breaker(self, source_name: str) -> CircuitBreaker:
        """Get or create circuit breaker for source."""
        if source_name not in self.breakers:
            self.breakers[source_name] = CircuitBreaker()
        return self.breakers[source_name]
