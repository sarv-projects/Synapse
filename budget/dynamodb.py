"""DynamoDB persistence layer — budget register + job results."""
import json
import logging
import os
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

DYNAMODB_AVAILABLE = False
try:
    import boto3
    DYNAMODB_AVAILABLE = True
except ImportError:
    logger.info("boto3 not installed; DynamoDB persistence disabled")


class DynamoDBStore:
    """Persists budget state and job results to DynamoDB."""

    def __init__(self, table_name: str | None = None):
        self.table_name = table_name or os.getenv("DYNAMODB_TABLE", "synapse_jobs")
        self._table = None
        self._available = False

    async def connect(self):
        if not DYNAMODB_AVAILABLE:
            return
        try:
            region = os.getenv("AWS_REGION", "ap-south-1")
            dynamodb = boto3.resource("dynamodb", region_name=region)
            self._table = dynamodb.Table(self.table_name)
            self._table.load()
            self._available = True
            logger.info(f"DynamoDB connected: {self.table_name}")
        except Exception as e:
            logger.warning(f"DynamoDB unavailable ({e}); using in-memory store")
            self._available = False

    async def save_budget(self, snapshot: dict):
        if not self._available:
            return
        try:
            self._table.put_item(Item={
                "pk": "budget_snapshot",
                "sk": datetime.now(UTC).isoformat(),
                "data": json.dumps(snapshot, default=str),
                "ttl": int(datetime.now(UTC).timestamp()) + 86400,
            })
        except Exception as e:
            logger.debug(f"DynamoDB budget save failed: {e}")

    async def save_job(self, job_id: str, job_data: dict):
        if not self._available:
            return
        try:
            self._table.put_item(Item={
                "pk": f"job#{job_id}",
                "sk": "result",
                "query": job_data.get("query", ""),
                "status": job_data.get("status", ""),
                "result": json.dumps(job_data.get("result", {}), default=str),
                "created_at": job_data.get("created_at", ""),
                "ttl": int(datetime.now(UTC).timestamp()) + 604800,
            })
        except Exception as e:
            logger.debug(f"DynamoDB job save failed: {e}")

    async def get_job(self, job_id: str) -> dict | None:
        if not self._available:
            return None
        try:
            response = self._table.get_item(Key={"pk": f"job#{job_id}", "sk": "result"})
            item = response.get("Item")
            if item:
                return {
                    "job_id": job_id,
                    "status": item.get("status"),
                    "query": item.get("query"),
                    "result": json.loads(item.get("result", "{}")),
                    "created_at": item.get("created_at"),
                }
        except Exception as e:
            logger.debug(f"DynamoDB job fetch failed: {e}")
        return None

    async def load_budget(self) -> dict | None:
        if not self._available:
            return None
        try:
            response = self._table.query(
                KeyConditionExpression="pk = :pk",
                ExpressionAttributeValues={":pk": "budget_snapshot"},
                ScanIndexForward=False,
                Limit=1,
            )
            items = response.get("Items", [])
            if items:
                return json.loads(items[0].get("data", "{}"))
        except Exception as e:
            logger.debug(f"DynamoDB budget load failed: {e}")
        return None


_store: DynamoDBStore | None = None


def get_dynamodb_store() -> DynamoDBStore:
    global _store
    if _store is None:
        _store = DynamoDBStore()
    return _store
