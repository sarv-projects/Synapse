"""Embedding generation using sentence-transformers."""
import asyncio
from typing import List
from sentence_transformers import SentenceTransformer


class EmbeddingGenerator:
    """Generate 384-dim embeddings using all-MiniLM-L6-v2."""

    def __init__(self):
        self.model = SentenceTransformer('all-MiniLM-L6-v2')
        self.dimensions = 384

    def generate_paper_embedding(self, title: str, abstract: str) -> List[float]:
        """Generate embedding for a paper from title + abstract."""
        text = f"{title} [SEP] {abstract[:512]}"
        return self.model.encode(text).tolist()

    def generate_entity_embedding(self, name: str, description: str) -> List[float]:
        """Generate embedding for technique/model/tool."""
        text = f"{name} [SEP] {description[:256]}"
        return self.model.encode(text).tolist()

    def generate_query_embedding(self, query: str) -> List[float]:
        """Generate embedding for search query."""
        return self.model.encode(query).tolist()


_generator = None
_lock = asyncio.Lock()


async def get_embedding_generator() -> EmbeddingGenerator:
    global _generator
    if _generator is None:
        async with _lock:
            if _generator is None:
                _generator = EmbeddingGenerator()
    return _generator


async def close_embedding_generator() -> None:
    global _generator
    async with _lock:
        if _generator is not None:
            _generator = None

