"""Webhook event dispatcher for SYNAPSE v3.0 pipeline Stage 9."""
import httpx
import asyncio
import logging
from typing import Dict, Any, List
from datetime import datetime, UTC, timedelta
import hashlib
import hmac
import json

from webhook.registry import WebhookRegistry
from ingestion.checkpoint.postgres import PostgresCheckpoint

logger = logging.getLogger(__name__)

class WebhookDispatcher:
    """Enhanced webhook dispatcher with retry logic and delivery tracking."""
    
    def __init__(self, registry: WebhookRegistry):
        self.registry = registry
        self.client = httpx.AsyncClient(timeout=30.0)
        self.checkpoint = None
        self.retry_delays = [30, 300, 1800]  # 30s, 5m, 30m
        self.max_retries = 3
    
    async def initialize(self):
        """Initialize checkpoint client for delivery tracking."""
        if not self.checkpoint:
            self.checkpoint = PostgresCheckpoint()
            await self.checkpoint.connect()
    
    async def dispatch_pipeline_events(self, pipeline_results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Dispatch webhook events for pipeline completion.
        
        Args:
            pipeline_results: Results from the ingestion pipeline
            
        Returns:
            Dict with delivery statistics
        """
        await self.initialize()
        
        stats = {
            "events_dispatched": 0,
            "deliveries_successful": 0,
            "deliveries_failed": 0,
            "subscriptions_inactive": 0,
            "errors": []
        }
        
        # Extract events from pipeline results
        events = self._extract_events_from_pipeline(pipeline_results)
        
        if not events:
            logger.info("No events to dispatch from pipeline results")
            return stats
        
        # Dispatch each event
        for event in events:
            event_stats = await self._dispatch_single_event(event)
            
            # Aggregate statistics
            stats["events_dispatched"] += 1
            stats["deliveries_successful"] += event_stats["successful"]
            stats["deliveries_failed"] += event_stats["failed"]
            stats["subscriptions_inactive"] += event_stats["inactive"]
            stats["errors"].extend(event_stats["errors"])
        
        logger.info(f"Webhook dispatch completed: {stats}")
        return stats
    
    def _extract_events_from_pipeline(self, pipeline_results: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract webhook events from pipeline results."""
        events = []
        
        # Entity creation events
        if "entities_created" in pipeline_results:
            for entity in pipeline_results["entities_created"]:
                events.append({
                    "event": "entity.created",
                    "entity_id": entity.get("id"),
                    "label": entity.get("type"),
                    "name": entity.get("name") or entity.get("title"),
                    "source": entity.get("source"),
                    "confidence": entity.get("confidence", 1.0),
                    "evidence_url": entity.get("evidence_url"),
                    "created_at": datetime.now(UTC).isoformat()
                })
        
        # Edge dispute events
        if "disputed_edges" in pipeline_results:
            for edge in pipeline_results["disputed_edges"]:
                events.append({
                    "event": "edge.disputed",
                    "from_id": edge.get("from_id"),
                    "to_id": edge.get("to_id"),
                    "rel_type": edge.get("relationship_type"),
                    "old_confidence": edge.get("confidence"),
                    "reason": edge.get("dispute_reason"),
                    "disputed_at": datetime.now(UTC).isoformat()
                })
        
        # Review queue events
        if "review_queue_items" in pipeline_results:
            for item in pipeline_results["review_queue_items"]:
                events.append({
                    "event": "review.queued",
                    "item_id": item.get("id"),
                    "edge_type": item.get("edge_type"),
                    "confidence": item.get("confidence"),
                    "reason": item.get("reason"),
                    "queued_at": datetime.now(UTC).isoformat()
                })
        
        return events
    
    async def _dispatch_single_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatch a single event to all matching subscribers."""
        event_type = event["event"]
        subscriptions = self.registry.get_active_subscriptions(event_type)
        
        stats = {
            "successful": 0,
            "failed": 0,
            "inactive": 0,
            "errors": []
        }
        
        if not subscriptions:
            logger.debug(f"No active subscriptions for event type: {event_type}")
            return stats
        
        # Dispatch to all subscribers concurrently
        tasks = []
        for sub in subscriptions:
            task = self._dispatch_to_subscription(sub, event)
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                stats["failed"] += 1
                stats["errors"].append(f"Subscription {subscriptions[i].id}: {str(result)}")
            else:
                if result["success"]:
                    stats["successful"] += 1
                elif result.get("inactive"):
                    stats["inactive"] += 1
                else:
                    stats["failed"] += 1
                    stats["errors"].append(result.get("error", "Unknown error"))
        
        return stats
    
    async def _dispatch_to_subscription(self, subscription, event: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatch event to a specific subscription with retry logic."""
        payload = json.dumps(event, default=str)
        signature = self._generate_signature(payload, subscription.secret_token)
        
        headers = {
            "X-SYNAPSE-Signature": signature,
            "X-SYNAPSE-Event": event["event"],
            "Content-Type": "application/json",
            "User-Agent": "SYNAPSE-Webhook/3.0"
        }
        
        # Check delivery history
        delivery_id = f"{subscription.id}_{event['event']}_{event.get('entity_id', 'unknown')}"
        
        for attempt in range(self.max_retries + 1):
            try:
                # Log delivery attempt
                await self._log_delivery_attempt(delivery_id, subscription.id, event["event"], attempt)
                
                response = await self.client.post(
                    subscription.endpoint_url,
                    data=payload,
                    headers=headers,
                    timeout=30.0
                )
                
                if response.status_code in [200, 201, 202, 204]:
                    # Success
                    await self._log_delivery_success(delivery_id, response.status_code)
                    return {"success": True}
                
                # HTTP error - check if retryable
                if response.status_code in [429, 500, 502, 503, 504]:
                    if attempt < self.max_retries:
                        delay = self.retry_delays[min(attempt, len(self.retry_delays) - 1)]
                        logger.warning(f"Webhook delivery attempt {attempt + 1} failed with {response.status_code}, retrying in {delay}s")
                        await asyncio.sleep(delay)
                        continue
                
                # Non-retryable error
                error_msg = f"HTTP {response.status_code}: {response.text[:200]}"
                await self._log_delivery_failure(delivery_id, error_msg, attempt)
                return {"success": False, "error": error_msg}
                
            except httpx.TimeoutException:
                if attempt < self.max_retries:
                    delay = self.retry_delays[min(attempt, len(self.retry_delays) - 1)]
                    logger.warning(f"Webhook timeout on attempt {attempt + 1}, retrying in {delay}s")
                    await asyncio.sleep(delay)
                    continue
                
                error_msg = "Request timeout"
                await self._log_delivery_failure(delivery_id, error_msg, attempt)
                return {"success": False, "error": error_msg}
                
            except Exception as e:
                error_msg = str(e)
                await self._log_delivery_failure(delivery_id, error_msg, attempt)
                return {"success": False, "error": error_msg}
        
        # All retries failed
        error_msg = f"Failed after {self.max_retries + 1} attempts"
        await self._log_delivery_failure(delivery_id, error_msg, self.max_retries)
        return {"success": False, "error": error_msg}
    
    def _generate_signature(self, payload: str, secret: str) -> str:
        """Generate HMAC-SHA256 signature for webhook payload."""
        return hmac.new(
            secret.encode(),
            payload.encode(),
            hashlib.sha256
        ).hexdigest()
    
    async def _log_delivery_attempt(self, delivery_id: str, subscription_id: str, event_type: str, attempt: int):
        """Log webhook delivery attempt."""
        if self.checkpoint:
            try:
                await self.checkpoint.log_webhook_delivery(
                    delivery_id=delivery_id,
                    subscription_id=subscription_id,
                    event_type=event_type,
                    attempt=attempt,
                    status="attempted"
                )
            except Exception as e:
                logger.error(f"Failed to log delivery attempt: {e}")
    
    async def _log_delivery_success(self, delivery_id: str, status_code: int):
        """Log successful webhook delivery."""
        if self.checkpoint:
            try:
                await self.checkpoint.update_webhook_delivery(
                    delivery_id=delivery_id,
                    status="delivered",
                    response_code=status_code
                )
            except Exception as e:
                logger.error(f"Failed to log delivery success: {e}")
    
    async def _log_delivery_failure(self, delivery_id: str, error_msg: str, attempt: int):
        """Log failed webhook delivery."""
        if self.checkpoint:
            try:
                await self.checkpoint.update_webhook_delivery(
                    delivery_id=delivery_id,
                    status="failed",
                    error_message=error_msg,
                    attempt=attempt
                )
            except Exception as e:
                logger.error(f"Failed to log delivery failure: {e}")
    
    async def get_delivery_stats(self, hours: int = 24) -> Dict[str, Any]:
        """Get webhook delivery statistics for the last N hours."""
        await self.initialize()
        
        if not self.checkpoint:
            return {"error": "Checkpoint not available"}
        
        try:
            since = datetime.now(UTC) - timedelta(hours=hours)
            return await self.checkpoint.get_webhook_delivery_stats(since)
        except Exception as e:
            logger.error(f"Failed to get delivery stats: {e}")
            return {"error": str(e)}
    
    async def cleanup_old_deliveries(self, days: int = 30):
        """Clean up old delivery logs."""
        await self.initialize()
        
        if not self.checkpoint:
            return
        
        try:
            cutoff = datetime.now(UTC) - timedelta(days=days)
            deleted = await self.checkpoint.cleanup_webhook_deliveries(cutoff)
            logger.info(f"Cleaned up {deleted} old webhook delivery logs")
        except Exception as e:
            logger.error(f"Failed to cleanup old deliveries: {e}")
    
    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()

# Global dispatcher instance
_webhook_dispatcher = None

def get_webhook_dispatcher() -> WebhookDispatcher:
    """Get the global webhook dispatcher instance."""
    global _webhook_dispatcher
    if _webhook_dispatcher is None:
        from webhook.registry import get_webhook_registry
        _webhook_dispatcher = WebhookDispatcher(get_webhook_registry())
    return _webhook_dispatcher
