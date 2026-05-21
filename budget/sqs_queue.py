"""SQS job queue — decouples Lambda API surface from EC2 reasoning engine."""
import asyncio
import json
import logging
import os
import uuid
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

SQS_AVAILABLE = False
try:
    import boto3
    SQS_AVAILABLE = True
except ImportError:
    pass


class SQSJobQueue:
    """AWS SQS-based job queue for async reasoning requests."""

    def __init__(self, queue_url: str | None = None):
        self.queue_url = queue_url or os.getenv("SQS_QUEUE_URL", "")
        self._client = None
        self._available = False

    async def connect(self):
        if not SQS_AVAILABLE or not self.queue_url:
            self._available = False
            return
        try:
            region = os.getenv("AWS_REGION", "ap-south-1")
            self._client = boto3.client("sqs", region_name=region)
            self._client.get_queue_url(QueueName=self.queue_url.split("/")[-1])
            self._available = True
            logger.info(f"SQS connected: {self.queue_url}")
        except Exception as e:
            logger.warning(f"SQS unavailable ({e}); using direct task spawning")
            self._available = False

    async def enqueue(self, job_id: str, query: str, session_id: str, fmt: str = "markdown") -> bool:
        if not self._available:
            return False
        try:
            message = json.dumps({
                "job_id": job_id, "query": query,
                "session_id": session_id, "format": fmt,
                "timestamp": datetime.now(UTC).isoformat(),
            })
            self._client.send_message(QueueUrl=self.queue_url, MessageBody=message)
            logger.info(f"SQS enqueued job {job_id}")
            return True
        except Exception as e:
            logger.warning(f"SQS enqueue failed: {e}")
            return False

    async def dequeue(self, wait_time: int = 5) -> list[dict[str, Any]]:
        if not self._available:
            return []
        try:
            response = self._client.receive_message(
                QueueUrl=self.queue_url,
                MaxNumberOfMessages=1,
                WaitTimeSeconds=wait_time,
            )
            messages = response.get("Messages", [])
            results = []
            for msg in messages:
                body = json.loads(msg.get("Body", "{}"))
                body["receipt_handle"] = msg.get("ReceiptHandle")
                results.append(body)
            return results
        except Exception as e:
            logger.debug(f"SQS dequeue failed: {e}")
            return []

    async def delete_message(self, receipt_handle: str):
        if not self._available or not receipt_handle:
            return
        try:
            self._client.delete_message(
                QueueUrl=self.queue_url, ReceiptHandle=receipt_handle
            )
        except Exception as e:
            logger.debug(f"SQS delete failed: {e}")


_queue: SQSJobQueue | None = None


def get_sqs_queue() -> SQSJobQueue:
    global _queue
    if _queue is None:
        _queue = SQSJobQueue()
    return _queue
