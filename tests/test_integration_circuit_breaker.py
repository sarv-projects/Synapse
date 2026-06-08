"""Integration tests for the circuit breaker state machine.

These tests do NOT require a live Neo4j / Postgres. They exercise the
state transitions, file persistence, and concurrency guarantees of
:class:`ingestion.circuit_breaker.CircuitBreaker`.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from ingestion.circuit_breaker import CircuitBreaker, CircuitBreakerRegistry, CircuitState


pytestmark = pytest.mark.integration


class TestCircuitBreakerStateMachine:
    """Test the three-state circuit breaker logic."""

    def test_initial_state_is_closed(self):
        cb = CircuitBreaker(failure_threshold=3)
        assert cb.state == CircuitState.CLOSED
        assert cb.can_attempt() is True
        assert cb.failure_count == 0

    def test_closes_after_threshold_failures(self):
        cb = CircuitBreaker(failure_threshold=3, timeout_seconds=10)
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert cb.can_attempt() is False

    def test_success_resets_failure_count(self):
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        assert cb.failure_count == 2
        cb.record_success()
        assert cb.failure_count == 0
        assert cb.state == CircuitState.CLOSED

    def test_open_transitions_to_half_open_after_timeout(self):
        cb = CircuitBreaker(failure_threshold=2, timeout_seconds=1)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        # Manually backdate the last failure so the timeout has elapsed
        cb.last_failure_time = datetime.now() - timedelta(seconds=10)
        assert cb.can_attempt() is True
        assert cb.state == CircuitState.HALF_OPEN

    def test_half_open_to_closed_on_success(self):
        cb = CircuitBreaker(failure_threshold=1, timeout_seconds=0)
        cb.record_failure()
        cb.last_failure_time = datetime.now() - timedelta(seconds=1)
        cb.can_attempt()  # Transitions to HALF_OPEN
        assert cb.state == CircuitState.HALF_OPEN
        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_half_open_to_open_on_failure(self):
        cb = CircuitBreaker(failure_threshold=1, timeout_seconds=0)
        cb.record_failure()
        cb.last_failure_time = datetime.now() - timedelta(seconds=1)
        cb.can_attempt()  # Transitions to HALF_OPEN
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_on_state_change_callback_fires(self):
        events = []
        cb = CircuitBreaker(failure_threshold=1, on_state_change=lambda: events.append(cb.state))
        cb.record_failure()
        assert len(events) == 1
        assert events[0] == CircuitState.OPEN


class TestCircuitBreakerRegistry:
    """Test the registry and JSON file persistence."""

    def test_get_breaker_creates_new(self, tmp_path):
        state_path = str(tmp_path / "cb.json")
        reg = CircuitBreakerRegistry(state_path=state_path)
        cb = reg.get_breaker("test-source")
        assert cb.state == CircuitState.CLOSED
        assert os.path.exists(state_path)

    def test_persistence_round_trip(self, tmp_path):
        state_path = str(tmp_path / "cb.json")
        reg1 = CircuitBreakerRegistry(state_path=state_path)
        cb1 = reg1.get_breaker("source-a")
        cb1.failure_threshold = 5
        cb1.record_failure()
        cb1.record_failure()
        # State should be persisted to disk
        with open(state_path) as f:
            data = json.load(f)
        assert "source-a" in data
        assert data["source-a"]["state"] == "closed"
        # Reload into a fresh registry
        reg2 = CircuitBreakerRegistry(state_path=state_path)
        cb2 = reg2.get_breaker("source-a")
        assert cb2.failure_count == 2
        assert cb2.failure_threshold == 5

    def test_multiple_breakers_isolated(self, tmp_path):
        state_path = str(tmp_path / "cb.json")
        reg = CircuitBreakerRegistry(state_path=state_path)
        cb_a = reg.get_breaker("source-a")
        cb_b = reg.get_breaker("source-b")
        for _ in range(3):
            cb_a.record_failure()
        assert cb_a.state == CircuitState.OPEN
        assert cb_b.state == CircuitState.CLOSED

    def test_invalid_state_file_does_not_crash(self, tmp_path):
        state_path = str(tmp_path / "cb.json")
        Path(state_path).write_text("not-valid-json{")
        # Should not raise
        reg = CircuitBreakerRegistry(state_path=state_path)
        assert reg.get_breaker("new").state == CircuitState.CLOSED
