"""Base classes for source fetchers."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SourceManifest:
    """Metadata about a source."""
    name: str
    source_type: str = "rest_json"
    base_url: str = ""
    rate_limit: dict[str, Any] = field(default_factory=dict)
    entity_coverage: list[str] = field(default_factory=list)
    auth_required: bool = False


@dataclass
class SourceDocument:
    """A raw document fetched from a source before entity extraction."""
    source_name: str
    external_id: str
    entity_type: str
    payload: dict[str, Any]
    raw_text: str = ""
    evidence_url: str = ""


class SourceFetcher(ABC):
    """Abstract base class for all source fetchers."""

    manifest: SourceManifest

    @abstractmethod
    async def fetch(self) -> list[SourceDocument]:
        """Fetch documents from the source."""
        ...

    def validate(self, data: dict[str, Any]) -> bool:
        """Validate a single fetched item. Override per source."""
        return bool(data)
