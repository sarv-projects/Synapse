from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ingestion.sources.base import SourceDocument
from schema.models import GraphEdge, GraphNode, ReviewQueueItem


@dataclass(slots=True)
class PipelineState:
    documents: list[SourceDocument] = field(default_factory=list)
    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)
    review_items: list[ReviewQueueItem] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
