"""Ingestion checkpoint backed by Firestore — replaces PostgreSQL checkpoint."""
import logging
import os
from datetime import UTC, datetime
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


class PostgresCheckpoint:
    """Firestore-backed ingestion checkpoint. Interface unchanged from Postgres version."""

    def __init__(self):
        self._db = None

    async def connect(self):
        self._db = _get_db()
        logger.info("FirestoreCheckpoint (ingestion): connected")

    async def save_entity_stage(self, entity_id: str, stage: str, metadata: dict | None = None):
        if not self._db:
            return
        try:
            doc = self._db.collection("ingestion_checkpoints").document(entity_id)
            await doc.set({
                "entity_id": entity_id,
                "stage": stage,
                "metadata": metadata or {},
                "updated_at": datetime.now(UTC).isoformat(),
            }, merge=True)
        except Exception as e:
            logger.debug(f"Checkpoint save failed: {e}")

    async def get_entity_stage(self, entity_id: str) -> str | None:
        if not self._db:
            return None
        try:
            snap = await self._db.collection("ingestion_checkpoints").document(entity_id).get()
            return snap.to_dict().get("stage") if snap.exists else None
        except Exception as e:
            logger.debug(f"Checkpoint get failed: {e}")
            return None

    async def log_webhook_delivery(
        self, subscription_id: str, event_type: str, endpoint_url: str,
        status: str, status_code: int | None = None, error: str | None = None,
    ):
        if not self._db:
            return
        try:
            doc_id = f"{subscription_id}_{datetime.now(UTC).timestamp()}"
            await self._db.collection("webhook_deliveries").document(doc_id).set({
                "subscription_id": subscription_id,
                "event_type": event_type,
                "endpoint_url": endpoint_url,
                "status": status,
                "status_code": status_code,
                "error": error,
                "delivered_at": datetime.now(UTC).isoformat(),
            })
        except Exception as e:
            logger.debug(f"Webhook log failed: {e}")

    async def update_webhook_delivery(self, delivery_id: str, status: str, status_code: int | None = None):
        if not self._db:
            return
        try:
            await self._db.collection("webhook_deliveries").document(delivery_id).set(
                {"status": status, "status_code": status_code}, merge=True
            )
        except Exception as e:
            logger.debug(f"Webhook update failed: {e}")

    async def get_webhook_delivery_stats(self) -> dict[str, Any]:
        if not self._db:
            return {}
        try:
            docs = self._db.collection("webhook_deliveries").stream()
            total = success = failed = 0
            async for _ in docs:
                total += 1
            return {"total": total}
        except Exception as e:
            logger.debug(f"Webhook stats failed: {e}")
            return {}

    async def cleanup_webhook_deliveries(self, days: int = 30):
        """Archive old webhook delivery records."""
        if not self._db:
            return
        try:
            from datetime import timedelta
            cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()
            docs = self._db.collection("webhook_deliveries").where(
                "delivered_at", "<", cutoff
            ).stream()
            async for doc in docs:
                await doc.reference.delete()
        except Exception as e:
            logger.debug(f"Webhook cleanup failed: {e}")
