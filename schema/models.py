from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class FactTier(str, Enum):
    T1 = "T1"
    T2 = "T2"
    T3 = "T3"
    T4 = "T4"
    SYSTEM = "SYSTEM"


class VerificationStatus(str, Enum):
    UNVERIFIED = "unverified"
    WEAK = "weak"
    VERIFIED = "verified"
    DISPUTED = "disputed"


class NodeStatus(str, Enum):
    NEW = "new"
    ACTIVE = "active"
    ARCHIVED = "archived"


class ProvenanceRecord(BaseModel):
    evidence_source: str
    evidence_url: str | None = None
    evidence_snippet: str | None = None
    extraction_method: str
    confidence: float = Field(ge=0.0, le=1.0)
    first_seen: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_verified: datetime | None = None
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED


class GraphNode(BaseModel):
    label: str
    key: str
    properties: dict[str, Any]
    id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_seen: datetime = Field(default_factory=lambda: datetime.now(UTC))
    status: NodeStatus = NodeStatus.NEW
    source: str
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class GraphEdge(BaseModel):
    relationship: str
    from_label: str
    from_key: str
    to_label: str
    to_key: str
    fact_tier: FactTier
    provenance: ProvenanceRecord | None = None
    properties: dict[str, Any] = Field(default_factory=dict)


class IngestionCheckpoint(BaseModel):
    entity_id: str
    source_name: str
    stage: str
    completed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ReviewQueueItem(BaseModel):
    item_id: str = Field(default_factory=lambda: str(uuid4()))
    entity_type: str
    entity_id: str
    reason: str
    confidence: float = Field(ge=0.0, le=1.0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    payload: dict[str, Any] = Field(default_factory=dict)


class QueryAnswer(BaseModel):
    question: str
    cypher: str
    rows: list[dict[str, Any]]
    fact_tier: FactTier
    warnings: list[str] = Field(default_factory=list)
