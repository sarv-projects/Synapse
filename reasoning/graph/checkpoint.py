"""LangGraph reasoning checkpoint backed by Firestore — replaces PostgreSQL version."""
import json
import logging
import os
from datetime import UTC, datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)

_db = None


def _get_db():
    global _db
    if _db is None:
        from google.cloud.firestore_v1 import AsyncClient
        project = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT")
        _db = AsyncClient(project=project) if project else AsyncClient()
    return _db


class LangGraphCheckpoint:
    """Firestore-backed checkpoint for LangGraph reasoning sessions."""

    def __init__(self):
        self._db = None

    async def connect(self):
        self._db = _get_db()
        logger.info("FirestoreCheckpoint (reasoning): connected")

    async def save(self, session_id: str, node_name: str, state: dict[str, Any]):
        if not self._db:
            return
        try:
            doc_id = f"{session_id}_{node_name}"
            await self._db.collection("reasoning_checkpoints").document(doc_id).set({
                "session_id": session_id,
                "node_name": node_name,
                "state": json.dumps(state, default=str),
                "saved_at": datetime.now(UTC).isoformat(),
            })
        except Exception as e:
            logger.debug(f"Reasoning checkpoint save failed: {e}")

    async def load(self, session_id: str, node_name: str) -> dict[str, Any] | None:
        if not self._db:
            return None
        try:
            doc_id = f"{session_id}_{node_name}"
            snap = await self._db.collection("reasoning_checkpoints").document(doc_id).get()
            if snap.exists:
                data = snap.to_dict()
                return json.loads(data.get("state", "{}"))
        except Exception as e:
            logger.debug(f"Reasoning checkpoint load failed: {e}")
        return None

    async def cleanup_old(self, days: int = 7):
        if not self._db:
            return
        try:
            cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()
            docs = self._db.collection("reasoning_checkpoints").where(
                "saved_at", "<", cutoff
            ).stream()
            async for doc in docs:
                await doc.reference.delete()
            logger.info(f"Cleaned up reasoning checkpoints older than {days} days")
        except Exception as e:
            logger.debug(f"Reasoning checkpoint cleanup failed: {e}")

    async def close(self):
        pass


_store: LangGraphCheckpoint | None = None


def get_checkpoint_store() -> LangGraphCheckpoint:
    global _store
    if _store is None:
        _store = LangGraphCheckpoint()
    return _store
