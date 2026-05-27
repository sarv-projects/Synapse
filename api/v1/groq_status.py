"""Groq API key management and rotation status endpoints."""
from fastapi import APIRouter, HTTPException, Header
from datetime import datetime, timezone
import logging

from api.groq_manager import get_groq_manager
from schema.config import get_settings

logger = logging.getLogger(__name__)

# No prefix here — this router is included under /api/v1 by the parent router
router = APIRouter(prefix="/groq", tags=["groq"])


def _verify_admin(authorization: str | None):
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required")
    settings = get_settings()
    if authorization != f"Bearer {settings.synapse_admin_key}":
        raise HTTPException(status_code=403, detail="Invalid admin key")


@router.get("/status")
async def get_groq_status():
    """Get current status of all Groq API keys and models."""
    try:
        manager = get_groq_manager()
        return manager.get_full_stats()
    except Exception as e:
        logger.error(f"Error getting Groq status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/models")
async def get_model_status():
    """Get status of available Groq models."""
    try:
        manager = get_groq_manager()
        return {
            "service": "Groq Model Manager",
            "version": "3.0.0",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **manager.get_model_stats(),
        }
    except Exception as e:
        logger.error(f"Error getting model status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/rotate")
async def force_rotation(authorization: str | None = Header(default=None)):
    """Force rotation to next available key (admin only)."""
    _verify_admin(authorization)
    manager = get_groq_manager()
    manager.current_key_index = (manager.current_key_index + 1) % max(len(manager.keys), 1)
    return {
        "message": "Rotated to next key",
        "current_key_index": manager.current_key_index,
        "total_keys": len(manager.keys),
    }


@router.post("/reset")
async def reset_key_limits(authorization: str | None = Header(default=None)):
    """Reset all key TPM limits (admin only)."""
    _verify_admin(authorization)
    manager = get_groq_manager()
    await manager.reset_hourly_limits()
    return {
        "message": "All key limits reset",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
