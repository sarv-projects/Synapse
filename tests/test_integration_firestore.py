"""Integration tests for Firestore checkpoint persistence.

These tests require a live Firestore instance. They are skipped
unless GOOGLE_CLOUD_PROJECT (or GCP_PROJECT) is set.
"""
from __future__ import annotations

import os
import uuid

import pytest

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.getenv("GOOGLE_CLOUD_PROJECT") and not os.getenv("GCP_PROJECT"),
        reason="GOOGLE_CLOUD_PROJECT not set; Firestore tests require a live project",
    ),
]


class TestReasoningCheckpoint:
    async def test_save_and_load(self, require_firestore):
        from reasoning.graph.checkpoint import get_checkpoint_store
        store = get_checkpoint_store()
        await store.connect()
        session_id = f"test-{uuid.uuid4()}"
        state = {"query": "test", "status": "PENDING", "node": "entry"}
        try:
            await store.save(session_id, "entry", state)
            loaded = await store.load(session_id, "entry")
            assert loaded is not None
            assert loaded.get("query") == "test"
        finally:
            # Cleanup is best-effort
            try:
                # No public delete; use raw collection
                from google.cloud.firestore_v1 import AsyncClient
                project = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT")
                db = AsyncClient(project=project)
                await db.collection("reasoning_checkpoints").document(f"{session_id}_entry").delete()
            except Exception:
                pass


class TestIngestionCheckpoint:
    async def test_save_and_get_stage(self, require_firestore):
        from ingestion.checkpoint.postgres import PostgresCheckpoint
        store = PostgresCheckpoint()
        await store.connect()
        entity_id = f"test-{uuid.uuid4()}"
        try:
            await store.save_entity_stage(entity_id, "extracted", {"source": "test"})
            stage = await store.get_entity_stage(entity_id)
            assert stage == "extracted"
        finally:
            try:
                from google.cloud.firestore_v1 import AsyncClient
                project = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT")
                db = AsyncClient(project=project)
                await db.collection("ingestion_checkpoints").document(entity_id).delete()
            except Exception:
                pass
