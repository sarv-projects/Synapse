"""Groq API key management and rotation status endpoints."""
from fastapi import APIRouter, HTTPException
from datetime import datetime, timezone
import logging

from api.groq_manager import get_groq_manager

logger = logging.getLogger(__name__)

# No prefix here — this router is included under /api/v1 by the parent router
router = APIRouter(prefix="/groq", tags=["groq"])


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
async def force_rotation():
    """Force rotation to next available key."""
    manager = get_groq_manager()
    manager.current_key_index = (manager.current_key_index + 1) % max(len(manager.keys), 1)
    return {
        "message": "Rotated to next key",
        "current_key_index": manager.current_key_index,
        "total_keys": len(manager.keys),
    }


@router.post("/reset")
async def reset_key_limits():
    """Reset all key TPM limits."""
    manager = get_groq_manager()
    await manager.reset_hourly_limits()
    return {
        "message": "All key limits reset",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
