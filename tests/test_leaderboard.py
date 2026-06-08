import os
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from api.main import app
from api.v1.router import _get_lmsys_arena_leaderboard

@pytest.mark.asyncio
async def test_get_lmsys_arena_leaderboard_fallback():
    """Verify that the leaderboard helper returns the high quality fallbacks when parquet fails."""
    _CACHE_PATH = "lmsys_arena_leaderboard.json"
    cache_exists = os.path.exists(_CACHE_PATH)
    cache_backup = None
    if cache_exists:
        with open(_CACHE_PATH, "r", encoding="utf-8") as f:
            cache_backup = f.read()
        os.remove(_CACHE_PATH)

    try:
        # Mock httpx Client to raise error to force fallback
        with patch("httpx.AsyncClient.get", side_effect=Exception("Network Offline")):
            data = await _get_lmsys_arena_leaderboard("overall")
            assert isinstance(data, list)
            assert len(data) > 0
            
            first = data[0]
            assert "id" in first
            assert "name" in first
            assert "score" in first
            assert "description" in first
            assert "library" in first
            assert "claude" in first["id"].lower()
    finally:
        # Restore cache file
        if cache_exists and cache_backup:
            with open(_CACHE_PATH, "w", encoding="utf-8") as f:
                f.write(cache_backup)


@pytest.mark.asyncio
async def test_leaderboard_api_endpoint():
    """Verify that the FastAPI /leaderboard endpoint accepts category and works for models."""
    client = TestClient(app)
    
    resp = client.get("/api/v1/leaderboard", params={"type": "models", "category": "coding", "limit": 5})
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "models"
    assert "items" in data
    assert len(data["items"]) > 0
    assert data["count"] > 0
    
    item = data["items"][0]
    assert "id" in item
    assert "score" in item
    assert "description" in item


@pytest.mark.asyncio
async def test_leaderboard_invalid_category_defaulting():
    """Verify that passing an invalid category to the leaderboard endpoint defaults to overall."""
    client = TestClient(app)
    resp = client.get("/api/v1/leaderboard", params={"type": "models", "category": "invalid-cat-name"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "models"
    assert len(data["items"]) > 0
