"""Shared pytest fixtures and configuration for SYNAPSE integration tests."""
from __future__ import annotations

import hashlib
import os
import random
from typing import List

import pytest


def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers."""
    config.addinivalue_line(
        "markers",
        "integration: marks tests as integration tests (may require external services)",
    )


@pytest.fixture
def deterministic_embedding() -> List[float]:
    """Return a deterministic 384-dim embedding derived from a seed string."""
    def _make(text: str) -> List[float]:
        seed = int(hashlib.sha256(text.encode()).hexdigest()[:8], 16)
        rng = random.Random(seed)
        return [rng.random() for _ in range(384)]
    return _make


@pytest.fixture
def require_neo4j() -> None:
    if not os.getenv("NEO4J_URI"):
        pytest.skip("NEO4J_URI not set; Neo4j integration tests require a live DB")


@pytest.fixture
def require_postgres() -> None:
    if not os.getenv("POSTGRES_URL"):
        pytest.skip("POSTGRES_URL not set; Postgres/pgvector integration tests skipped")


@pytest.fixture
def require_firestore() -> None:
    if not os.getenv("GOOGLE_CLOUD_PROJECT") and not os.getenv("GCP_PROJECT"):
        pytest.skip("GOOGLE_CLOUD_PROJECT not set; Firestore integration tests skipped")


@pytest.fixture
def require_groq_keys() -> None:
    if not os.getenv("GROQ_API_KEYS") and not os.getenv("GROQ_API_KEY"):
        pytest.skip("GROQ_API_KEYS not set; Groq integration tests skipped")
