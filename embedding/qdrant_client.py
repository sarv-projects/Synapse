"""Qdrant vector database client (singleton)."""
from typing import List, Dict, Any, Optional
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue
from schema.config import get_settings
import uuid
import logging

logger = logging.getLogger(__name__)

_instance = None


class QdrantVectorStore:
    """Enhanced Qdrant client with collection management and vector operations."""
    
    def __init__(self):
        self.settings = get_settings()
        self.client = QdrantClient(
            url=self.settings.qdrant_url,
            api_key=self.settings.qdrant_api_key,
        )
        self.collection_name = "synapse_nodes"
        self._ensure_collection()
    
    def _ensure_collection(self):
        """Ensure the synapse_nodes collection exists with proper configuration."""
        try:
            self.client.get_collection(self.collection_name)
            logger.info(f"Collection {self.collection_name} already exists")
        except Exception:
            logger.info(f"Creating collection {self.collection_name}")
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=384, distance=Distance.COSINE),
                # Create payload indexes for efficient filtering
                optimizers_config={
                    "default_segment_number": 2,
                    "max_segment_size": 200000,
                    "memmap_threshold": 50000,
                },
                quantization_config=None,  # No quantization for free tier
            )
    
    def upsert_vectors(self, nodes: List[Dict[str, Any]]) -> bool:
        """
        Upsert multiple vectors to Qdrant.
        
        Args:
            nodes: List of dicts with keys: id, vector, label, name, domain
            
        Returns:
            bool: Success status
        """
        try:
            points = []
            for node in nodes:
                point = PointStruct(
                    id=str(node["id"]),
                    vector=node["vector"],
                    payload={
                        "label": node["label"],
                        "name": node["name"],
                        "domain": node.get("domain", "ai"),
                        "uuid": str(node["id"])
                    }
                )
                points.append(point)
            
            # Batch upsert for efficiency
            self.client.upsert(
                collection_name=self.collection_name,
                points=points
            )
            logger.info(f"Successfully upserted {len(points)} vectors to Qdrant")
            return True
            
        except Exception as e:
            logger.error(f"Failed to upsert vectors to Qdrant: {e}")
            return False
    
    def search_similar(
        self, 
        query_vector: List[float], 
        limit: int = 10,
        score_threshold: float = 0.85,
        label_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for similar vectors.
        
        Args:
            query_vector: Query embedding
            limit: Maximum number of results
            score_threshold: Minimum similarity score
            label_filter: Optional entity type filter
            
        Returns:
            List of similar nodes with scores
        """
        try:
            search_filter = None
            if label_filter:
                search_filter = Filter(
                    must=[FieldCondition(key="label", match=MatchValue(value=label_filter))]
                )
            
            results = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_vector,
                query_filter=search_filter,
                limit=limit,
                score_threshold=score_threshold,
                with_payload=True,
                with_vectors=False
            )
            
            return [
                {
                    "id": str(point.id),
                    "score": point.score,
                    "payload": point.payload
                }
                for point in results
            ]
            
        except Exception as e:
            logger.error(f"Failed to search Qdrant: {e}")
            return []
    
    def get_collection_info(self) -> Dict[str, Any]:
        """Get collection statistics."""
        try:
            info = self.client.get_collection(self.collection_name)
            return {
                "name": self.collection_name,
                "vectors_count": info.vectors_count,
                "segments_count": info.segments_count,
                "disk_data_size": info.disk_data_size,
                "ram_data_size": info.ram_data_size
            }
        except Exception as e:
            logger.error(f"Failed to get collection info: {e}")
            return {}
    
    def delete_vectors(self, ids: List[str]) -> bool:
        """Delete vectors by IDs."""
        try:
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=ids
            )
            logger.info(f"Successfully deleted {len(ids)} vectors from Qdrant")
            return True
        except Exception as e:
            logger.error(f"Failed to delete vectors from Qdrant: {e}")
            return False


def get_qdrant_client() -> QdrantVectorStore:
    """Get singleton Qdrant vector store."""
    global _instance
    if _instance is None:
        _instance = QdrantVectorStore()
    return _instance
