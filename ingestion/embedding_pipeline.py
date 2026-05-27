"""Embedding generation pipeline for SYNAPSE v3.0."""
from typing import List, Dict, Any, Optional
import asyncio
import logging
from datetime import datetime, UTC
import uuid

from embedding.generator import EmbeddingGenerator, get_embedding_generator
from embedding.qdrant_client import get_qdrant_client
from ingestion.neo4j.client import Neo4jClient
from schema.config import get_settings

logger = logging.getLogger(__name__)

class EmbeddingPipeline:
    """Pipeline for generating and storing embeddings for nodes."""
    
    def __init__(self):
        self.embedding_generator: EmbeddingGenerator | None = None
        self.qdrant_client = get_qdrant_client()
        self.settings = get_settings()
        self.neo4j_client = None  # Will be initialized when needed

    async def ensure_initialized(self) -> EmbeddingGenerator:
        if self.embedding_generator is None:
            self.embedding_generator = await get_embedding_generator()
        return self.embedding_generator
    
    async def process_documents(self, documents: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Process a batch of documents and generate embeddings.

        Args:
            documents: List of documents with extracted entities

        Returns:
            Dict with processing results
        """
        _ = await self.ensure_initialized()
        results = {
            "processed": 0,
            "embeddings_generated": 0,
            "qdrant_upserted": 0,
            "neo4j_updated": 0,
            "errors": []
        }
        
        # Extract entities that need embeddings
        entities_to_embed = self._extract_entities_for_embedding(documents)
        
        if not entities_to_embed:
            logger.info("No entities found that need embeddings")
            return results
        
        # Generate embeddings in batches
        batch_size = 64
        for i in range(0, len(entities_to_embed), batch_size):
            batch = entities_to_embed[i:i + batch_size]
            batch_results = await self._process_batch(batch)
            
            # Aggregate results
            for key in results:
                if key != "errors":
                    results[key] += batch_results[key]
            results["errors"].extend(batch_results["errors"])
        
        logger.info(f"Embedding pipeline completed: {results}")
        return results
    
    def _extract_entities_for_embedding(self, documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Extract entities that need embeddings from processed documents."""
        entities = []
        
        for doc in documents:
            # Extract different entity types
            if doc.get("entity_type") == "Paper":
                entities.append({
                    "type": "Paper",
                    "id": doc.get("id") or str(uuid.uuid4()),
                    "title": doc.get("title", ""),
                    "abstract": doc.get("abstract_summary", ""),
                    "arxiv_id": doc.get("arxiv_id"),
                    "source": doc.get("source", "unknown")
                })
            elif doc.get("entity_type") == "Model":
                entities.append({
                    "type": "Model",
                    "id": doc.get("id") or str(uuid.uuid4()),
                    "name": doc.get("name", ""),
                    "description": doc.get("description", ""),
                    "hf_model_id": doc.get("hf_model_id"),
                    "source": doc.get("source", "unknown")
                })
            elif doc.get("entity_type") == "Tool":
                entities.append({
                    "type": "Tool",
                    "id": doc.get("id") or str(uuid.uuid4()),
                    "name": doc.get("name", ""),
                    "description": doc.get("description", ""),
                    "github_repo": doc.get("github_repo"),
                    "source": doc.get("source", "unknown")
                })
            elif doc.get("entity_type") == "Technique":
                entities.append({
                    "type": "Technique",
                    "id": doc.get("id") or str(uuid.uuid4()),
                    "name": doc.get("canonical_name", ""),
                    "description": doc.get("description", ""),
                    "source": doc.get("source", "unknown")
                })
        
        return entities
    
    async def _process_batch(self, entities: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Process a batch of entities for embedding."""
        results = {
            "processed": 0,
            "embeddings_generated": 0,
            "qdrant_upserted": 0,
            "neo4j_updated": 0,
            "errors": []
        }
        
        # Generate embeddings
        embedding_vectors = []
        for entity in entities:
            try:
                vector = await asyncio.to_thread(self._generate_embedding_for_entity, entity)
                if vector:
                    embedding_vectors.append({
                        "entity": entity,
                        "vector": vector
                    })
                    results["embeddings_generated"] += 1
            except Exception as e:
                error_msg = f"Failed to generate embedding for {entity.get('type')} {entity.get('id')}: {e}"
                logger.error(error_msg, exc_info=True)
                results["errors"].append(error_msg)
        
        if not embedding_vectors:
            return results
        
        # Prepare vectors for Qdrant upsert
        qdrant_nodes = []
        for item in embedding_vectors:
            entity = item["entity"]
            qdrant_nodes.append({
                "id": entity["id"],
                "vector": item["vector"],
                "label": entity["type"],
                "name": entity.get("name") or entity.get("title", ""),
                "domain": "ai"  # Default domain
            })
        
        # Upsert to Qdrant
        if self.qdrant_client.upsert_vectors(qdrant_nodes):
            results["qdrant_upserted"] = len(qdrant_nodes)
        else:
            error_msg = "Failed to upsert vectors to Qdrant"
            logger.error(error_msg)
            results["errors"].append(error_msg)
            return results
        
        # Update Neo4j with embedding references
        neo4j_updated = await self._update_neo4j_embeddings(embedding_vectors)
        results["neo4j_updated"] = neo4j_updated
        
        results["processed"] = len(entities)
        return results
    
    def _generate_embedding_for_entity(self, entity: Dict[str, Any]) -> Optional[List[float]]:
        """Generate embedding for a specific entity."""
        entity_type = entity.get("type")
        gen = self.embedding_generator
        assert gen is not None

        if entity_type == "Paper":
            return gen.generate_paper_embedding(
                entity.get("title", ""),
                entity.get("abstract", "")
            )
        elif entity_type in ["Model", "Tool", "Technique"]:
            return gen.generate_entity_embedding(
                entity.get("name", ""),
                entity.get("description", "")
            )
        else:
            logger.warning(f"Unsupported entity type for embedding: {entity_type}")
            return None
    
    async def _update_neo4j_embeddings(self, embedding_vectors: List[Dict[str, Any]]) -> int:
        """Update Neo4j nodes with embedding references."""
        if not self.neo4j_client:
            from ingestion.neo4j.client import Neo4jClient
            self.neo4j_client = Neo4jClient.from_settings(self.settings)
        
        updated_count = 0
        
        async with self.neo4j_client.session() as session:
            for item in embedding_vectors:
                entity = item["entity"]
                entity_id = entity["id"]
                entity_type = entity["type"]
                
                try:
                    # Update the node with embedding metadata
                    query = f"""
                    MATCH (n:{entity_type} {{id: $id}})
                    SET n.embedding = $vector,
                        n.embedding_model = 'all-MiniLM-L6-v2',
                        n.embedding_dim = 384,
                        n.embedding_generated_at = datetime(),
                        n.last_seen = datetime()
                    RETURN count(n) as updated
                    """
                    
                    result = await session.run(
                        query,
                        id=entity_id,
                        vector=item["vector"]
                    )
                    
                    record = await result.single()
                    if record and record["updated"] > 0:
                        updated_count += 1
                    
                    # Create EmbeddingIndex node
                    await self._create_embedding_index_node(session, entity, item["vector"])
                    
                except Exception as e:
                    logger.error(f"Failed to update Neo4j embedding for {entity_type} {entity_id}: {e}", exc_info=True)
        
        return updated_count
    
    async def _create_embedding_index_node(self, session, entity: Dict[str, Any], vector: List[float]):
        """Create EmbeddingIndex node to track vector metadata."""
        qdrant_id = str(entity["id"])  # Use same ID as entity
        
        query = """
        MERGE (ei:EmbeddingIndex {qdrant_id: $qdrant_id})
        SET ei.node_uuid = $node_uuid,
            ei.model_version = 'all-MiniLM-L6-v2',
            ei.dim = $dim,
            ei.indexed_at = datetime(),
            ei.last_seen = datetime()
        """
        
        await session.run(
            query,
            qdrant_id=qdrant_id,
            node_uuid=entity["id"],
            dim=len(vector)
        )
    
    async def search_similar_entities(
        self,
        query_text: str,
        entity_type: Optional[str] = None,
        limit: int = 10,
        score_threshold: float = 0.85
    ) -> List[Dict[str, Any]]:
        """Search for similar entities using vector similarity."""
        gen = await self.ensure_initialized()
        # Generate query embedding
        query_vector = gen.generate_query_embedding(query_text)
        
        # Search Qdrant
        similar_items = self.qdrant_client.search_similar(
            query_vector=query_vector,
            limit=limit,
            score_threshold=score_threshold,
            label_filter=entity_type
        )
        
        # Get full entity details from Neo4j
        if not self.neo4j_client:
            from ingestion.neo4j.client import Neo4jClient
            self.neo4j_client = Neo4jClient.from_settings(self.settings)
        
        results = []
        async with self.neo4j_client.session() as session:
            for item in similar_items:
                entity_uuid = item["payload"]["uuid"]
                entity_label = item["payload"]["label"]
                
                try:
                    query = f"""
                    MATCH (n:{entity_label} {{id: $uuid}})
                    RETURN n
                    """
                    
                    result = await session.run(query, uuid=entity_uuid)
                    record = await result.single()
                    
                    if record:
                        node = record["n"]
                        results.append({
                            "entity": dict(node),
                            "similarity_score": item["score"],
                            "entity_type": entity_label
                        })
                        
                except Exception as e:
                    logger.error(f"Failed to fetch entity {entity_uuid}: {e}", exc_info=True)
        
        return results
    
    async def get_embedding_stats(self) -> Dict[str, Any]:
        """Get statistics about the embedding pipeline."""
        _ = await self.ensure_initialized()
        # Get Qdrant collection info
        qdrant_stats = self.qdrant_client.get_collection_info()
        
        # Get Neo4j embedding index stats
        if not self.neo4j_client:
            from ingestion.neo4j.client import Neo4jClient
            self.neo4j_client = Neo4jClient.from_settings(self.settings)
        
        neo4j_stats = {}
        async with self.neo4j_client.session() as session:
            # Count nodes with embeddings by type
            for entity_type in ["Paper", "Model", "Tool", "Technique"]:
                query = f"""
                MATCH (n:{entity_type})
                WHERE n.embedding IS NOT NULL
                RETURN count(n) as count
                """
                
                result = await session.run(query)
                record = await result.single()
                neo4j_stats[entity_type] = record["count"] if record else 0
        
        return {
            "qdrant": qdrant_stats,
            "neo4j": neo4j_stats,
            "model": "all-MiniLM-L6-v2",
            "dimensions": 384
        }

# Global pipeline instance
_embedding_pipeline = None

async def get_embedding_pipeline() -> EmbeddingPipeline:
    """Get the global embedding pipeline instance."""
    global _embedding_pipeline
    if _embedding_pipeline is None:
        _embedding_pipeline = EmbeddingPipeline()
        await _embedding_pipeline.ensure_initialized()
    return _embedding_pipeline
