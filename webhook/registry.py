"""Webhook subscription registry."""
from typing import List, Optional
from pydantic import BaseModel, Field
import hmac
import hashlib
from uuid import uuid4


class WebhookSubscription(BaseModel):
    """Webhook subscription model."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    endpoint_url: str
    event_types: List[str]
    secret_token: str
    active: bool = True
    owner_id: str


class WebhookRegistry:
    """Manages webhook subscriptions."""
    
    def __init__(self):
        self.subscriptions: List[WebhookSubscription] = []
    
    def register(self, subscription: WebhookSubscription) -> str:
        """Register a new webhook subscription."""
        self.subscriptions.append(subscription)
        return subscription.endpoint_url
    
    def get_active_subscriptions(self, event_type: str) -> List[WebhookSubscription]:
        """Get all active subscriptions for an event type."""
        return [
            sub for sub in self.subscriptions
            if sub.active and event_type in sub.event_types
        ]
    
    @staticmethod
    def sign_payload(payload: str, secret: str) -> str:
        """Generate HMAC-SHA256 signature for payload."""
        return hmac.new(
            secret.encode(),
            payload.encode(),
            hashlib.sha256
        ).hexdigest()


# Global webhook registry instance
_webhook_registry = None


def get_webhook_registry() -> WebhookRegistry:
    """Get the global webhook registry instance."""
    global _webhook_registry
    if _webhook_registry is None:
        _webhook_registry = WebhookRegistry()
    return _webhook_registry
