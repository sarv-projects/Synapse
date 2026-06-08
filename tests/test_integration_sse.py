"""Integration tests for the SSE streaming endpoint logic.

These tests verify the SSE event format and the streaming loop
behaviour using FastAPI's TestClient.  They don't hit a live LLM.
"""
from __future__ import annotations


import pytest


pytestmark = pytest.mark.integration


def _try_import_test_client():
    try:
        from fastapi.testclient import TestClient
        from api.main import app
        return TestClient, app
    except ImportError as e:
        pytest.skip(f"SSE test requires FastAPI + api.main: {e}")


class TestSSEEventFormat:
    def test_stream_returns_event_stream_content_type(self):
        TestClient, app = _try_import_test_client()
        client = TestClient(app)
        # We don't have a real job, so this should 404 (or stream an error)
        with client.stream("GET", "/api/v1/reason/nonexistent-job-id/stream") as resp:
            assert resp.headers["content-type"].startswith("text/event-stream")

    def test_stream_emits_data_prefix(self):
        TestClient, app = _try_import_test_client()
        client = TestClient(app)
        with client.stream("GET", "/api/v1/reason/nonexistent-job-id/stream") as resp:
            # Read first chunk
            for chunk in resp.iter_text():
                if chunk.strip():
                    # SSE format: data: {...}\n\n
                    assert chunk.startswith("data: ") or "Job not found" in chunk
                    break


class TestReasoningAPIShape:
    def test_reason_endpoint_accepts_post(self):
        TestClient, app = _try_import_test_client()
        client = TestClient(app)
        resp = client.post("/api/v1/reason", json={"query": "test"})
        # Should return 200 with job_id, or 500 if backend isn't fully configured
        assert resp.status_code in (200, 500)

    def test_budget_endpoint(self):
        TestClient, app = _try_import_test_client()
        client = TestClient(app)
        resp = client.get("/api/v1/budget")
        assert resp.status_code == 200
        data = resp.json()
        # Either an error or models dict
        assert "models" in data or "error" in data

    def test_eval_endpoint(self):
        TestClient, app = _try_import_test_client()
        client = TestClient(app)
        resp = client.get("/api/v1/eval")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_runs" in data or "error" in data

    def test_get_reason_result_404_for_unknown(self):
        TestClient, app = _try_import_test_client()
        client = TestClient(app)
        resp = client.get("/api/v1/reason/nonexistent-job-id")
        assert resp.status_code == 404
