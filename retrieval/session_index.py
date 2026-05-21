"""Session-scoped in-memory index for web research content."""
import logging
from typing import Any

logger = logging.getLogger(__name__)


class SessionIndex:
    """In-memory index scoped to a single reasoning session."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.documents: list[dict[str, Any]] = []
        self.embeddings: list[list[float]] = []

    def add_documents(self, docs: list[dict[str, Any]]):
        """Add documents from Crawl4AI results to the session index."""
        for doc in docs:
            self.documents.append({
                "url": doc.get("url", ""),
                "title": doc.get("title", ""),
                "content_md": doc.get("content_md", ""),
                "fetched_at": doc.get("fetched_at", ""),
            })
        logger.info(f"Session {self.session_id}: added {len(docs)} documents, total {len(self.documents)}")

    async def search(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """Simple keyword search over session documents."""
        query_lower = query.lower()
        results = []
        for doc in self.documents:
            content = doc.get("content_md", "")
            title = doc.get("title", "")
            if query_lower in content.lower() or query_lower in title.lower():
                results.append({
                    "url": doc.get("url"),
                    "title": title,
                    "snippet": content[:500],
                    "source": "session_index",
                })
        return results[:limit]

    def clear(self):
        self.documents = []
        self.embeddings = []
        logger.info(f"Session {self.session_id}: index cleared")

    @property
    def doc_count(self) -> int:
        return len(self.documents)


# Global session index registry
_sessions: dict[str, SessionIndex] = {}


def get_session_index(session_id: str) -> SessionIndex:
    if session_id not in _sessions:
        _sessions[session_id] = SessionIndex(session_id)
    return _sessions[session_id]


def destroy_session_index(session_id: str):
    if session_id in _sessions:
        _sessions[session_id].clear()
        del _sessions[session_id]
