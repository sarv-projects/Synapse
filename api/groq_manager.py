"""Groq API key and model rotation manager for SYNAPSE v3.0."""
import asyncio
import logging
import random
import time
from datetime import datetime, UTC, timedelta
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum

from groq import Groq
from schema.config import get_settings

logger = logging.getLogger(__name__)

class KeyStatus(Enum):
    ACTIVE = "active"
    DEPLETED = "depleted"
    ERROR = "error"
    COOLDOWN = "cooldown"

@dataclass
class ModelConfig:
    """Configuration for a Groq model with its capabilities."""
    model_id: str
    name: str
    context_window: int
    tpm_limit: int
    rpm_limit: int
    rpd_limit: int
    reasoning_quality: str  # high, medium, low
    best_for: List[str]  # entity_extraction, complex_reasoning, fast_inference

@dataclass
class GroqKey:
    """Represents a single Groq API key with its status."""
    key_id: str
    api_key: str
    tpm_limit: int
    current_tpm: int
    reset_time: datetime
    status: KeyStatus
    last_used: datetime
    error_count: int = 0
    cooldown_until: Optional[datetime] = None

# High-performance models configuration
HIGH_PERFORMANCE_MODELS = {
    "meta-llama/llama-4-scout-17b-16e-instruct": ModelConfig(
        model_id="meta-llama/llama-4-scout-17b-16e-instruct",
        name="Llama 4 Scout",
        context_window=128000,
        tpm_limit=30000,
        rpm_limit=30,
        rpd_limit=1000,
        reasoning_quality="high",
        best_for=["entity_extraction", "complex_reasoning", "long_context"]
    ),
    "llama-3.3-70b-versatile": ModelConfig(
        model_id="llama-3.3-70b-versatile",
        name="Llama 3.3 70B",
        context_window=8192,
        tpm_limit=6000,
        rpm_limit=30,
        rpd_limit=1000,
        reasoning_quality="high",
        best_for=["complex_reasoning", "multilingual", "coding"]
    ),
    "openai/gpt-oss-120b": ModelConfig(
        model_id="openai/gpt-oss-120b",
        name="GPT-OSS 120B",
        context_window=8192,
        tpm_limit=6000,
        rpm_limit=30,
        rpd_limit=1000,
        reasoning_quality="high",
        best_for=["complex_reasoning", "coding", "analysis"]
    ),
    "llama-3.1-8b-instant": ModelConfig(
        model_id="llama-3.1-8b-instant",
        name="Llama 3.1 8B",
        context_window=8192,
        tpm_limit=6000,
        rpm_limit=30,
        rpd_limit=1000,
        reasoning_quality="medium",
        best_for=["fast_inference", "basic_tasks", "fallback"]
    )
}

class GroqKeyManager:
    """Manages multiple Groq API keys and models with rotation and load balancing."""
    
    def __init__(self):
        self.settings = get_settings()
        self.keys: List[GroqKey] = []
        self.current_key_index = 0
        self.current_model_index = 0
        self.usage_cache = {}
        self.available_models = list(HIGH_PERFORMANCE_MODELS.keys())
        self._load_keys_from_env()
        
    def get_best_model_for_task(self, task_type: str = "entity_extraction") -> str:
        """Get the best model for a specific task type."""
        # Prioritize models based on task type and availability
        suitable_models = [
            model_id for model_id, config in HIGH_PERFORMANCE_MODELS.items()
            if task_type in config.best_for
        ]
        
        if not suitable_models:
            # Fallback to Llama 4 Scout (most versatile)
            return "llama-4-scout-17b-16e-instruct"
        
        # Return the first suitable model (will be rotated)
        return suitable_models[0]
    
    def get_next_model(self, task_type: str = "entity_extraction") -> str:
        """Get next model in rotation for load balancing."""
        suitable_models = [
            model_id for model_id, config in HIGH_PERFORMANCE_MODELS.items()
            if task_type in config.best_for
        ]
        
        if not suitable_models:
            suitable_models = ["llama-4-scout-17b-16e-instruct"]
        
        # Round-robin through suitable models
        model = suitable_models[self.current_model_index % len(suitable_models)]
        self.current_model_index += 1
        
        return model
    
    def _load_keys_from_env(self):
        """Load Groq keys from environment variables."""
        import os
        self.keys = []

        # Try GROQ_API_KEYS (comma-separated) first
        comma_keys = os.environ.get("GROQ_API_KEYS", "").strip()
        if not comma_keys:
            # Also check settings (in case loaded via dotenv before startup)
            comma_keys = getattr(self.settings, "groq_api_keys", "") or ""

        if comma_keys:
            key_list = [k.strip() for k in comma_keys.split(",") if k.strip()]
            for i, key_value in enumerate(key_list):
                self.keys.append(GroqKey(
                    key_id=f"key_{i}",
                    api_key=key_value,
                    tpm_limit=30000,
                    current_tpm=0,
                    reset_time=datetime.now(UTC) + timedelta(hours=1),
                    status=KeyStatus.ACTIVE,
                    last_used=datetime.now(UTC),
                ))
            logger.info(f"Loaded {len(self.keys)} Groq keys from GROQ_API_KEYS")
            return

        # Fallback: GROQ_API_KEY (single key)
        single_key = os.environ.get("GROQ_API_KEY", "").strip() or \
                     getattr(self.settings, "groq_api_key", "") or ""
        if single_key:
            self.keys.append(GroqKey(
                key_id="primary",
                api_key=single_key,
                tpm_limit=30000,
                current_tpm=0,
                reset_time=datetime.now(UTC) + timedelta(hours=1),
                status=KeyStatus.ACTIVE,
                last_used=datetime.now(UTC),
            ))
            logger.info("Loaded 1 Groq key from GROQ_API_KEY")
            return

        logger.warning("No Groq API keys found. Set GROQ_API_KEYS=key1,key2 in .env")
    
    async def get_next_key(self) -> Optional[GroqKey]:
        """Get the next available API key using round-robin with health checks."""
        if not self.keys:
            logger.error("No Groq API keys configured")
            return None
        
        # Try to find an active key, starting from current index
        attempts = 0
        while attempts < len(self.keys):
            key = self.keys[self.current_key_index]
            
            # Check if key is healthy
            if await self._is_key_healthy(key):
                self.current_key_index = (self.current_key_index + 1) % len(self.keys)
                return key
            else:
                # Mark key as unhealthy and try next
                logger.warning(f"Key {key.key_id} is unhealthy, trying next key")
                self.current_key_index = (self.current_key_index + 1) % len(self.keys)
                attempts += 1
        
        # All keys are unhealthy, return the first one anyway
        logger.error("All Groq keys are unhealthy, using first key")
        return self.keys[0]
    
    async def get_client_for_task(self, task_type: str = "entity_extraction") -> tuple[Groq, str]:
        """Get a Groq client with the best model for a specific task."""
        key = await self.get_next_key()
        if not key:
            raise RuntimeError("No healthy Groq API keys available")
        
        model = self.get_next_model(task_type)
        client = Groq(api_key=key.api_key)
        
        logger.info(f"Using key {key.key_id} with model {model} for task {task_type}")
        return client, model
    
    async def get_best_client_for_task(self, task_type: str = "entity_extraction") -> tuple[Groq, str]:
        """Get the best client and model for a specific task type."""
        key = await self.get_next_key()
        if not key:
            raise RuntimeError("No healthy Groq API keys available")
        
        model = self.get_best_model_for_task(task_type)
        client = Groq(api_key=key.api_key)
        
        logger.info(f"Using best model {model} with key {key.key_id} for task {task_type}")
        return client, model
    
    async def _is_key_healthy(self, key: GroqKey) -> bool:
        """Check if a key is healthy and available."""
        now = datetime.now(UTC)
        
        # Check cooldown status
        if key.cooldown_until and now < key.cooldown_until:
            return False
        
        # Check if key is in error state
        if key.status == KeyStatus.ERROR:
            return False
        
        # Check if key is depleted
        if key.status == KeyStatus.DEPLETED:
            return False
        
        # Check TPM limit
        if key.current_tpm >= key.tpm_limit:
            # Check if reset time has passed
            if now < key.reset_time:
                return False
        
        return True
    
    async def get_client(self) -> Groq:
        """Get a Groq client with automatic key rotation."""
        key = await self.get_next_key()
        if not key:
            raise Exception("No healthy Groq API keys available")
        
        return Groq(api_key=key.api_key)
    
    async def execute_with_rotation(self, func, *args, **kwargs):
        """Execute a function with automatic key rotation on failures."""
        max_retries = len(self.keys) * 2  # Allow 2 full cycles
        
        for attempt in range(max_retries):
            key = await self.get_next_key()
            if not key:
                await asyncio.sleep(1 * (attempt + 1))
                continue

            try:
                client = Groq(api_key=key.api_key)
                result = await func(client, *args, **kwargs)
                
                # Mark successful usage
                await self._record_usage(key.api_key, success=True)
                return result
                
            except Exception as e:
                logger.warning(f"Groq API call failed (attempt {attempt + 1}): {e}")
                
                # Mark failed usage
                await self._record_usage(key.api_key, success=False)
                
                # Update key status based on error
                await self._update_key_status_from_error(key.api_key, str(e))
                
                # Wait before retry
                if attempt < max_retries - 1:
                    await asyncio.sleep(1 * (attempt + 1))  # Exponential backoff
        
        raise Exception(f"All Groq API keys failed after {max_retries} attempts")
    
    async def _record_usage(self, api_key: str, success: bool):
        """Record usage for a specific key."""
        key = self._find_key_by_api_key(api_key)
        if not key:
            return
        
        key.last_used = datetime.now(UTC)
        
        if success:
            key.current_tpm += 1
            key.error_count = 0
            key.status = KeyStatus.ACTIVE
        else:
            key.error_count += 1
            if key.error_count >= 5:  # Mark as error after 5 failures
                key.status = KeyStatus.ERROR
                key.cooldown_until = datetime.now(UTC) + timedelta(minutes=10)
        
        # Check TPM limit
        if key.current_tpm >= key.tpm_limit:
            key.status = KeyStatus.DEPLETED
            logger.warning(f"Key {key.key_id} reached TPM limit")
    
    def _find_key_by_api_key(self, api_key: str) -> Optional[GroqKey]:
        """Find a key by its API key value."""
        for key in self.keys:
            if key.api_key == api_key:
                return key
        return None
    
    async def _update_key_status_from_error(self, api_key: str, error_msg: str):
        """Update key status based on error message."""
        key = self._find_key_by_api_key(api_key)
        if not key:
            return
        
        error_lower = error_msg.lower()
        
        if "rate limit" in error_lower or "quota" in error_lower:
            key.status = KeyStatus.DEPLETED
            key.cooldown_until = key.reset_time
        elif "invalid" in error_lower or "unauthorized" in error_lower:
            key.status = KeyStatus.ERROR
            key.cooldown_until = datetime.now(UTC) + timedelta(hours=1)
        elif "timeout" in error_lower or "connection" in error_lower:
            key.status = KeyStatus.ERROR
            key.cooldown_until = datetime.now(UTC) + timedelta(minutes=5)
    
    def get_key_stats(self) -> Dict[str, Any]:
        """Get statistics for all keys."""
        now = datetime.now(UTC)
        stats = {
            "total_keys": len(self.keys),
            "active_keys": len([k for k in self.keys if k.status == KeyStatus.ACTIVE]),
            "depleted_keys": len([k for k in self.keys if k.status == KeyStatus.DEPLETED]),
            "error_keys": len([k for k in self.keys if k.status == KeyStatus.ERROR]),
            "cooldown_keys": len([k for k in self.keys if k.cooldown_until and k.cooldown_until > now]),
            "total_tpm_available": sum(k.tpm_limit - k.current_tpm for k in self.keys),
        }
        
        # Per-key details
        stats["keys"] = []
        for key in self.keys:
            key_stats = {
                "key_id": key.key_id,
                "status": key.status.value,
                "current_tpm": key.current_tpm,
                "tpm_limit": key.tpm_limit,
                "tpm_remaining": max(0, key.tpm_limit - key.current_tpm),
                "last_used": key.last_used.isoformat(),
                "error_count": key.error_count,
                "cooldown_until": key.cooldown_until.isoformat() if key.cooldown_until else None
            }
            stats["keys"].append(key_stats)
        
        return stats
    
    def get_model_stats(self) -> Dict[str, Any]:
        """Get statistics for available models."""
        stats = {
            "total_models": len(HIGH_PERFORMANCE_MODELS),
            "current_model_index": self.current_model_index,
            "available_models": []
        }
        
        for model_id, config in HIGH_PERFORMANCE_MODELS.items():
            model_stats = {
                "model_id": model_id,
                "name": config.name,
                "context_window": config.context_window,
                "tpm_limit": config.tpm_limit,
                "rpm_limit": config.rpm_limit,
                "rpd_limit": config.rpd_limit,
                "reasoning_quality": config.reasoning_quality,
                "best_for": config.best_for
            }
            stats["available_models"].append(model_stats)
        
        return stats
    
    def get_full_stats(self) -> Dict[str, Any]:
        """Get comprehensive statistics including keys and models."""
        return {
            "service": "Groq Multi-Model Key Manager",
            "version": "3.0.0",
            "timestamp": datetime.now(UTC).isoformat(),
            "keys": self.get_key_stats(),
            "models": self.get_model_stats(),
            "rotation": {
                "current_key_index": self.current_key_index,
                "current_model_index": self.current_model_index,
                "rotation_strategy": "round_robin_with_task_optimization"
            }
        }
    
    async def reset_hourly_limits(self):
        """Reset TPM limits when hourly reset occurs."""
        now = datetime.now(UTC)
        
        for key in self.keys:
            if now >= key.reset_time:
                key.current_tpm = 0
                key.reset_time = now + timedelta(hours=1)
                
                # Reactivate depleted keys
                if key.status == KeyStatus.DEPLETED:
                    key.status = KeyStatus.ACTIVE
                    key.cooldown_until = None
        
        logger.info("Reset hourly TPM limits for all keys")

# Global key manager instance
_groq_manager = None

def get_groq_manager() -> GroqKeyManager:
    """Get the global Groq key manager instance."""
    global _groq_manager
    if _groq_manager is None:
        _groq_manager = GroqKeyManager()
    return _groq_manager

# Background task for hourly reset
async def hourly_reset_task():
    """Background task to reset TPM limits."""
    manager = get_groq_manager()
    await manager.reset_hourly_limits()

# Decorator for automatic key rotation
def with_groq_rotation(func):
    """Decorator to automatically handle Groq key rotation."""
    async def wrapper(*args, **kwargs):
        manager = get_groq_manager()
        return await manager.execute_with_rotation(func, *args, **kwargs)
    
    return wrapper
