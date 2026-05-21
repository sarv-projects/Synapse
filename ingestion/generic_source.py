"""Generic configurable source system."""
from typing import Dict, Any, List, Optional
import httpx
import asyncio
import logging
from dataclasses import dataclass, field
import xml.etree.ElementTree as ET
import feedparser

from ingestion.sources.base import SourceDocument

logger = logging.getLogger(__name__)


@dataclass
class SourceConfig:
    """Configuration for a generic source (mirrors sources.yaml entry)."""
    name: str
    base_url: str
    entity_coverage: List[str] = field(default_factory=list)
    type: str = "rest_json"
    auth_required: bool = False
    auth_env_var: Optional[str] = None
    rate_limit: Dict[str, Any] = field(default_factory=dict)
    headers: Dict[str, str] = field(default_factory=dict)
    fetch_params: Dict[str, Any] = field(default_factory=dict)
    pagination: Dict[str, Any] = field(default_factory=dict)
    extraction_rules: Dict[str, Any] = field(default_factory=dict)

    # Allow dict-style access for backward compat
    def get(self, key: str, default=None):
        return getattr(self, key, default)


class GenericSourceFetcher:
    """Universal fetcher that works with any configured source."""

    def __init__(self, config):
        # Accept both SourceConfig dataclass and raw dict (from YAML)
        if isinstance(config, dict):
            self.config = SourceConfig(
                name=config.get("name", "unknown"),
                base_url=config.get("base_url", ""),
                entity_coverage=config.get("entity_coverage", []),
                type=config.get("type", "rest_json"),
                auth_required=config.get("auth_required", False),
                auth_env_var=config.get("auth_env_var"),
                rate_limit=config.get("rate_limit", {}),
                headers=config.get("headers", {}),
                fetch_params=config.get("fetch_params", {}),
                pagination=config.get("pagination", {}),
                extraction_rules=config.get("extraction_rules", {}),
            )
        else:
            self.config = config

        self.source_name = self.config.name
        import os
        headers = dict(self.config.headers or {})
        if self.config.auth_env_var:
            token = os.environ.get(self.config.auth_env_var, "")
            if token:
                headers["Authorization"] = f"token {token}"

        self.client = httpx.AsyncClient(
            headers=headers,
            timeout=30.0,
            follow_redirects=True,
        )

    async def fetch(self) -> List[SourceDocument]:
        """Fetch with basic error handling (circuit breaker applied by wrapper)."""
        return await self._fetch_with_backoff()

    async def _fetch_with_backoff(self) -> List[SourceDocument]:
        """Dispatch to the correct fetch method based on source type."""
        source_type = self.config.type

        if source_type == "rest_json":
            return await self._fetch_rest_json()
        elif source_type == "rest_xml":
            return await self._fetch_rest_xml()
        elif source_type in ("rss", "rss_xml", "github_rss"):
            return await self._fetch_rss()
        else:
            logger.warning(f"Unsupported source type: {source_type}")
            return []

    async def _fetch_rest_json(self) -> List[SourceDocument]:
        try:
            response = await self.client.get(self.config.base_url, params=self.config.fetch_params)
            response.raise_for_status()
            data = response.json()
            return [d for d in (self._create_document_from_json(item) for item in self._extract_items_from_json(data)) if d]
        except Exception as e:
            logger.error(f"REST JSON fetch failed for {self.config.name}: {e}")
            raise

    async def _fetch_rest_xml(self) -> List[SourceDocument]:
        try:
            response = await self.client.get(self.config.base_url, params=self.config.fetch_params)
            response.raise_for_status()
            root = ET.fromstring(response.text)
            return [d for d in (self._create_document_from_xml(item) for item in self._extract_items_from_xml(root)) if d]
        except Exception as e:
            logger.error(f"REST XML fetch failed for {self.config.name}: {e}")
            raise

    async def _fetch_rss(self) -> List[SourceDocument]:
        try:
            feed = feedparser.parse(self.config.base_url)
            return [d for d in (self._create_document_from_rss(entry) for entry in feed.entries) if d]
        except Exception as e:
            logger.error(f"RSS fetch failed for {self.config.name}: {e}")
            raise

    # ── helpers ──────────────────────────────────────────────────────────────

    def _extract_items_from_json(self, data) -> List[Dict[str, Any]]:
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ("items", "results", "data", "papers", "models"):
                if key in data and isinstance(data[key], list):
                    return data[key]
        return []

    def _extract_items_from_xml(self, root: ET.Element) -> List[ET.Element]:
        for tag in ("item", "entry", "paper", "model"):
            items = root.findall(f".//{tag}")
            if items:
                return items
        return []

    def _create_document_from_json(self, item: Dict[str, Any]) -> Optional[SourceDocument]:
        try:
            external_id = self._extract_id(item)
            entity_type = self._determine_entity_type(item)
            if not external_id or not entity_type:
                return None
            return SourceDocument(
                source_name=self.config.name,
                external_id=external_id,
                entity_type=entity_type,
                payload=item,
            )
        except Exception as e:
            logger.warning(f"Failed to create document from JSON item: {e}")
            return None

    def _create_document_from_xml(self, item: ET.Element) -> Optional[SourceDocument]:
        try:
            return self._create_document_from_json(self._xml_to_dict(item))
        except Exception as e:
            logger.warning(f"Failed to create document from XML item: {e}")
            return None

    def _create_document_from_rss(self, entry) -> Optional[SourceDocument]:
        try:
            item_dict = {
                "title": getattr(entry, "title", ""),
                "link": getattr(entry, "link", ""),
                "summary": getattr(entry, "summary", ""),
                "published": getattr(entry, "published", ""),
                "id": getattr(entry, "id", getattr(entry, "link", "")),
            }
            return self._create_document_from_json(item_dict)
        except Exception as e:
            logger.warning(f"Failed to create document from RSS entry: {e}")
            return None

    def _extract_id(self, item: Dict[str, Any]) -> Optional[str]:
        for key in ("id", "arxiv_id", "hf_model_id", "github_repo", "paperId"):
            if item.get(key):
                return str(item[key])
        return str(item.get("link") or item.get("title") or "")

    def _determine_entity_type(self, item: Dict[str, Any]) -> Optional[str]:
        if "arxiv_id" in item or "paperId" in item:
            return "Paper"
        if "hf_model_id" in item or "modelId" in item:
            return "Model"
        if "github_repo" in item or "repository" in item:
            return "Tool"
        if "canonical_name" in item or "method" in item:
            return "Technique"
        coverage = self.config.entity_coverage
        return coverage[0] if coverage else "Paper"

    def _xml_to_dict(self, element: ET.Element) -> Dict[str, Any]:
        result: Dict[str, Any] = dict(element.attrib)
        if element.text and element.text.strip():
            if len(element) == 0:
                return element.text.strip()  # type: ignore[return-value]
            result["text"] = element.text.strip()
        for child in element:
            child_data = self._xml_to_dict(child)
            if child.tag in result:
                if not isinstance(result[child.tag], list):
                    result[child.tag] = [result[child.tag]]
                result[child.tag].append(child_data)
            else:
                result[child.tag] = child_data
        return result



