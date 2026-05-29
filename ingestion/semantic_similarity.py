"""Semantic similarity pass for creating SEMANTICALLY_SIMILAR edges."""
from typing import List, Dict, Any, Tuple
import asyncio
import logging
from datetime import datetime, UTC

from embedding.qdrant_client import get_qdrant_client
from ingestion.neo4j.client import Neo4jClient
from schema.config import get_settings

logger = logging.getLogger(__name__)

class SemanticSimilarityPass:
    """Creates SEMANTICALLY_SIMILAR edges based on vector similarity."""
    
    def __init__(self):
        self.qdrant_client = get_qdrant_client()
        self.settings = get_settings()
        self.neo4j_client = None
        
        # Configuration
        self.similarity_threshold = 0.85  # Minimum cosine similarity
        self.max_similar_per_entity = 5   # Max similar entities to connect
        self.batch_size = 50              # Process entities in batches
    
    async def run_similarity_pass(self, entity_types: List[str] = None) -> Dict[str, Any]:
        """
        Run the semantic similarity pass for specified entity types.
        
        Args:
            entity_types: List of entity types to process. If None, processes all.
            
        Returns:
            Dict with processing results
        """
        if entity_types is None:
            entity_types = ["Paper", "Technique"]  # Default to v3.0 spec
        
        results = {
            "processed_entities": 0,
            "similar_edges_created": 0,
            "duplicate_edges_skipped": 0,
            "errors": []
        }
        
        for entity_type in entity_types:
            logger.info(f"Running semantic similarity pass for {entity_type}")
            
            # Get all entities of this type with embeddings
            entities = await self._get_entities_with_embeddings(entity_type)
            
            if not entities:
                logger.info(f"No {entity_type} entities with embeddings found")
                continue
            
            # Process in batches
            for i in range(0, len(entities), self.batch_size):
                batch = entities[i:i + self.batch_size]
                batch_results = await self._process_entity_batch(batch, entity_type)
                
                # Aggregate results
                results["processed_entities"] += batch_results["processed_entities"]
                results["similar_edges_created"] += batch_results["similar_edges_created"]
                results["duplicate_edges_skipped"] += batch_results["duplicate_edges_skipped"]
                results["errors"].extend(batch_results["errors"])
        
        logger.info(f"Semantic similarity pass completed: {results}")
        return results
    
    async def _get_entities_with_embeddings(self, entity_type: str) -> List[Dict[str, Any]]:
        """Get all entities of a type that have embeddings."""
        if not self.neo4j_client:
            from ingestion.neo4j.client import Neo4jClient
            self.neo4j_client = Neo4jClient.from_settings(self.settings)
        
        async with self.neo4j_client.session() as session:
            query = f"""
            MATCH (n:{entity_type})
            WHERE n.embedding IS NOT NULL
            RETURN n.id as id, n.embedding as embedding, n.name as name
            ORDER BY n.last_seen DESC
            """
            
            result = await session.run(query)
            entities = []
            
            async for record in result:
                entities.append({
                    "id": record["id"],
                    "embedding": record["embedding"],
                    "name": record["name"]
                })
            
            return entities
    
    async def _process_entity_batch(self, entities: List[Dict[str, Any]], entity_type: str) -> Dict[str, Any]:
        """Process a batch of entities to find similar ones."""
        results = {
            "processed_entities": 0,
            "similar_edges_created": 0,
            "duplicate_edges_skipped": 0,
            "errors": []
        }
        
        for entity in entities:
            try:
                # Find similar entities using pgvector
                similar_entities = await self.qdrant_client.search_similar_async(
                    query_vector=entity["embedding"],
                    limit=self.max_similar_per_entity + 1,
                    score_threshold=self.similarity_threshold,
                    label_filter=entity_type
                )
                
                # Filter out self-matches and create edges
                edges_to_create = []
                for similar in similar_entities:
                    similar_id = similar["payload"]["uuid"]
                    
                    # Skip self-match
                    if similar_id == entity["id"]:
                        continue
                    
                    edges_to_create.append({
                        "from_id": entity["id"],
                        "to_id": similar_id,
                        "similarity_score": similar["score"],
                        "entity_type": entity_type
                    })
                
                # Create edges in Neo4j
                edges_created, duplicates_skipped = await self._create_similarity_edges(
                    edges_to_create, entity_type
                )
                
                results["similar_edges_created"] += edges_created
                results["duplicate_edges_skipped"] += duplicates_skipped
                results["processed_entities"] += 1
                
            except Exception as e:
                error_msg = f"Failed to process entity {entity['id']}: {e}"
                logger.error(error_msg)
                results["errors"].append(error_msg)
        
        return results
    
    async def _create_similarity_edges(
        self, 
        edges: List[Dict[str, Any]], 
        entity_type: str
    ) -> Tuple[int, int]:
        """Create SEMANTICALLY_SIMILAR edges in Neo4j."""
        if not self.neo4j_client:
            from ingestion.neo4j.client import Neo4jClient
            self.neo4j_client = Neo4jClient.from_settings(self.settings)
        
        edges_created = 0
        duplicates_skipped = 0
        
        async with self.neo4j_client.session() as session:
            for edge in edges:
                try:
                    # Check if edge already exists (avoid duplicates)
                    check_query = f"""
                    MATCH (a:{entity_type} {{id: $from_id}})-[r:SEMANTICALLY_SIMILAR]-(b:{entity_type} {{id: $to_id}})
                    RETURN r
                    """
                    
                    result = await session.run(
                        check_query,
                        from_id=edge["from_id"],
                        to_id=edge["to_id"]
                    )
                    
                    existing = await result.single()
                    if existing:
                        duplicates_skipped += 1
                        continue
                    
                    # Create the edge with provenance
                    create_query = f"""
                    MATCH (a:{entity_type} {{id: $from_id}}), (b:{entity_type} {{id: $to_id}})
                    MERGE (a)-[r:SEMANTICALLY_SIMILAR]->(b)
                    SET r.confidence = $similarity_score,
                        r.evidence_source = 'vector_similarity',
                        r.evidence_url = null,
                        r.evidence_snippet = $snippet,
                        r.extraction_method = 'pgvector_cosine_similarity',
                        r.first_seen = datetime(),
                        r.last_verified = datetime(),
                        r.verification_status = 'verified',
                        r.trust_level = 'T3'
                    RETURN r
                    """
                    
                    await session.run(
                        create_query,
                        from_id=edge["from_id"],
                        to_id=edge["to_id"],
                        similarity_score=edge["similarity_score"],
                        snippet=f"Cosine similarity: {edge['similarity_score']:.3f}"
                    )
                    
                    edges_created += 1
                    
                except Exception as e:
                    logger.error(f"Failed to create similarity edge {edge['from_id']} -> {edge['to_id']}: {e}")
        
        return edges_created, duplicates_skipped
    
    async def find_similar_entities_for_query(
        self, 
        query_embedding: List[float],
        entity_type: str,
        limit: int = 10,
        threshold: float = 0.85
    ) -> List[Dict[str, Any]]:
        """Find entities similar to a query embedding."""
        similar_items = await self.qdrant_client.search_similar_async(
            query_vector=query_embedding,
            limit=limit,
            score_threshold=threshold,
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
                    logger.error(f"Failed to fetch entity {entity_uuid}: {e}")
        
        return results
    
    async def get_similarity_stats(self) -> Dict[str, Any]:
        """Get statistics about semantic similarity edges."""
        if not self.neo4j_client:
            from ingestion.neo4j.client import Neo4jClient
            self.neo4j_client = Neo4jClient.from_settings(self.settings)
        
        stats = {}
        
        async with self.neo4j_client.session() as session:
            # Count SEMANTICALLY_SIMILAR edges by entity type
            for entity_type in ["Paper", "Technique"]:
                query = f"""
                MATCH (a:{entity_type})-[r:SEMANTICALLY_SIMILAR]-(b:{entity_type})
                RETURN count(r) as edge_count,
                       avg(r.confidence) as avg_similarity,
                       min(r.confidence) as min_similarity,
                       max(r.confidence) as max_similarity
                """
                
                result = await session.run(query)
                record = await result.single()
                
                if record:
                    stats[entity_type] = {
                        "edge_count": record["edge_count"],
                        "avg_similarity": float(record["avg_similarity"]) if record["avg_similarity"] else 0,
                        "min_similarity": float(record["min_similarity"]) if record["min_similarity"] else 0,
                        "max_similarity": float(record["max_similarity"]) if record["max_similarity"] else 0
                    }
                else:
                    stats[entity_type] = {
                        "edge_count": 0,
                        "avg_similarity": 0,
                        "min_similarity": 0,
                        "max_similarity": 0
                    }
        
        return stats

# Global similarity pass instance
_semantic_similarity_pass = None

def get_semantic_similarity_pass() -> SemanticSimilarityPass:
    """Get the global semantic similarity pass instance."""
    global _semantic_similarity_pass
    if _semantic_similarity_pass is None:
        _semantic_similarity_pass = SemanticSimilarityPass()
    return _semantic_similarity_pass
