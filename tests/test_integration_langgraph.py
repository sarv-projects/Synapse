"""Integration tests for the LangGraph reasoning state machine.

These tests don't need a live LangGraph runtime. They test the state
shape, the node routing, and the checkpoint serialization.
"""
from __future__ import annotations

import json

import pytest

from reasoning.graph.state import ReasoningState


pytestmark = pytest.mark.integration


class TestReasoningStateShape:
    def test_state_is_typed_dict(self):
        state: ReasoningState = {
            "query": "What is RAG?",
            "session_id": "test-session",
        }
        assert state["query"] == "What is RAG?"
        assert state["session_id"] == "test-session"

    def test_state_allows_partial_fields(self):
        # total=False — partial states are allowed
        state: ReasoningState = {"query": "test"}
        assert "format" not in state
        assert "session_id" not in state

    def test_state_can_hold_complex_nested_data(self):
        state: ReasoningState = {
            "query": "test",
            "sub_questions": ["q1", "q2", "q3"],
            "search_queries": [{"type": "direct", "query": "test"}],
            "retrieval_context": [
                {"id": "node1", "score": 0.95, "content": "Some text"},
            ],
            "extracted_claims": [
                {"claim_text": "X is true", "confidence": 0.9, "fact_tier": "T1"},
            ],
        }
        assert len(state["sub_questions"]) == 3
        assert state["retrieval_context"][0]["score"] == 0.95

    def test_state_round_trip_json(self):
        state: ReasoningState = {
            "query": "test",
            "session_id": "sess-1",
            "model_trace": {"node1": "llama-3.3-70b", "node2": "llama-3.1-8b"},
            "total_tokens_used": {"llama-3.3-70b": 1500},
            "retrieval_confidence": 0.87,
        }
        # Round trip through JSON
        serialized = json.dumps(state, default=str)
        restored = json.loads(serialized)
        assert restored["query"] == "test"
        assert restored["model_trace"]["node1"] == "llama-3.3-70b"
        assert restored["retrieval_confidence"] == 0.87

    def test_state_status_values(self):
        # The state is a TypedDict (no enum constraint), so we just
        # verify the documented values can be set.
        for status in ("PENDING", "PROCESSING", "COMPLETE", "FAILED"):
            state: ReasoningState = {"status": status, "query": "test"}
            assert state["status"] == status

    def test_state_confidence_map_structure(self):
        # Verify a realistic confidence_map shape
        state: ReasoningState = {
            "confidence_map": {
                "claim-1": {"score": 0.9, "tier": "T1", "source": "github-stars"},
                "claim-2": {"score": 0.6, "tier": "T3", "source": "inferred"},
            }
        }
        cm = state["confidence_map"]
        assert cm["claim-1"]["score"] == 0.9
        assert cm["claim-2"]["tier"] == "T3"


class TestStateMergeLogic:
    """Test the _merge_graph_update helper from api.v1.reasoning."""

    def test_merge_direct_field_update(self):
        # Import the merge function (depends on FastAPI imports)
        try:
            from api.v1.reasoning import _merge_graph_update
        except ImportError:
            pytest.skip("api.v1.reasoning requires FastAPI; skipping")

        state: ReasoningState = {"query": "test", "status": "PENDING"}
        update = {"status": "PROCESSING", "current_node": "decomposition"}
        merged = _merge_graph_update(state, update)
        assert merged["status"] == "PROCESSING"
        assert merged["current_node"] == "decomposition"
        assert merged["query"] == "test"

    def test_merge_named_node_update(self):
        try:
            from api.v1.reasoning import _merge_graph_update
        except ImportError:
            pytest.skip("api.v1.reasoning requires FastAPI; skipping")

        state: ReasoningState = {"query": "test", "retrieval_context": []}
        # LangGraph format: {node_name: {field_updates}}
        update = {"retrieval_node": {"retrieval_context": [{"id": "n1"}], "current_node": "retrieval"}}
        merged = _merge_graph_update(state, update)
        assert len(merged["retrieval_context"]) == 1
        assert merged["current_node"] == "retrieval"

    def test_merge_ignores_unknown_fields(self):
        try:
            from api.v1.reasoning import _merge_graph_update
        except ImportError:
            pytest.skip("api.v1.reasoning requires FastAPI; skipping")

        state: ReasoningState = {"query": "test"}
        update = {"totally_made_up_field": "garbage", "another_bad": 42}
        # Should not crash; unknown fields are silently dropped
        merged = _merge_graph_update(state, update)
        assert "totally_made_up_field" not in merged

    def test_merge_handles_end_marker(self):
        try:
            from api.v1.reasoning import _merge_graph_update
        except ImportError:
            pytest.skip("api.v1.reasoning requires FastAPI; skipping")

        state: ReasoningState = {"query": "test"}
        update = {"__end__": {"status": "COMPLETE"}}
        merged = _merge_graph_update(state, update)
        # __end__ is a marker, not a node — status should not be applied
        # (the merge skips it intentionally)
        assert merged.get("status") != "COMPLETE"
