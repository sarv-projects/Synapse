"""Natural Language to Cypher query translation using Llama 4 Scout."""
from typing import Dict, Any, List, Optional
import asyncio
import logging
import re
from datetime import datetime

from ingestion.neo4j.client import Neo4jClient
from api.groq_manager import get_groq_manager
from schema.config import get_settings

logger = logging.getLogger(__name__)

class NLToCypherTranslator:
    """Translates natural language queries to Cypher using Llama 4 Scout."""
    
    def __init__(self):
        self.settings = get_settings()
        self.neo4j_client = None
        self.groq_manager = None
        self.schema_cache = None
        self.query_cache: dict[str, Any] = {}
        self._cache_max_size = 256
        
        # Safety patterns for Cypher injection prevention
        self.forbidden_keywords = {
            'DELETE', 'REMOVE', 'DETACH', 'DROP', 'CREATE', 'MERGE', 'SET',
            'FOREACH', 'LOAD CSV', 'CALL', 'UNWIND', 'WITH', 'RETURN', 'ORDER BY'
        }
        self.allowed_keywords = {
            'MATCH', 'WHERE', 'AND', 'OR', 'NOT', 'IN', 'CONTAINS', 'STARTS WITH',
            'ENDS WITH', 'EXISTS', 'IS NULL', 'IS NOT NULL', '=', '>', '<', '>=', '<=',
            'LIMIT', 'SKIP', 'DISTINCT', 'COUNT', 'SUM', 'AVG', 'MIN', 'MAX'
        }
    
    async def initialize(self):
        """Initialize the translator with schema information."""
        if not self.neo4j_client:
            self.neo4j_client = Neo4jClient.from_settings(self.settings)

        if not hasattr(self, "groq_manager") or self.groq_manager is None:
            self.groq_manager = get_groq_manager()

        if not self.schema_cache:
            try:
                await self._load_schema()
            except Exception as e:
                logger.warning(f"Could not load Neo4j schema: {e}. Using empty schema.")
    
    async def _load_schema(self):
        """Load Neo4j schema for context."""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                async with self.neo4j_client.session() as session:
                    # Get node labels and their properties
                    node_query = """
                    CALL db.labels() YIELD label
                    CALL db.schema.nodeTypeProperties() YIELD nodeLabels, propertyName, propertyTypes
                    RETURN label, propertyName, propertyTypes
                    """
                    
                    # Get relationship types
                    rel_query = """
                    CALL db.relationshipTypes() YIELD relationshipType
                    RETURN relationshipType
                    """
                    
                    result = await session.run(node_query)
                    node_schema = {}
                    async for record in result:
                        label = record["label"]
                        if label not in node_schema:
                            node_schema[label] = {"properties": {}}
                        node_schema[label]["properties"][record["propertyName"]] = record["propertyTypes"]
                    
                    result = await session.run(rel_query)
                    rel_types = []
                    async for record in result:
                        rel_types.append(record["relationshipType"])
                    
                    self.schema_cache = {
                        "nodes": node_schema,
                        "relationships": rel_types
                    }
                    logger.info(f"Successfully loaded Neo4j schema: {len(node_schema)} node types, {len(rel_types)} relationship types")
                    return
                    
            except Exception as e:
                logger.warning(f"Schema load attempt {attempt + 1}/{max_retries} failed: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                else:
                    logger.error("Failed to load Neo4j schema after all retries. NL-to-Cypher quality will be degraded.")
                    # Set minimal schema to allow operation
                    self.schema_cache = {
                        "nodes": {},
                        "relationships": []
                    }
    
    async def translate_query(
        self, 
        natural_query: str, 
        max_results: int = 50,
        use_cache: bool = True
    ) -> Dict[str, Any]:
        """
        Translate natural language query to Cypher and execute it.
        
        Args:
            natural_query: Natural language query string
            max_results: Maximum number of results to return
            use_cache: Whether to use query cache
            
        Returns:
            Dict with translation results and data
        """
        # Check cache first
        cache_key = f"{natural_query}:{max_results}"
        if use_cache and cache_key in self.query_cache:
            logger.info(f"Returning cached result for query: {natural_query[:50]}...")
            return self.query_cache[cache_key]
        
        await self.initialize()
        
        # Sanitize input
        sanitized_query = self._sanitize_input(natural_query)
        
        # Generate Cypher query
        cypher_query = await self._generate_cypher(sanitized_query, max_results)
        
        if not cypher_query:
            return {
                "success": False,
                "error": "Failed to generate valid Cypher query",
                "natural_query": natural_query,
                "cypher_query": None,
                "results": [],
                "fact_tier": "T3",
            }
        
        # Validate and execute query
        validation_result = self._validate_cypher(cypher_query)
        if not validation_result["valid"]:
            return {
                "success": False,
                "error": f"Generated Cypher query failed validation: {validation_result['error']}",
                "natural_query": natural_query,
                "cypher_query": cypher_query,
                "results": [],
                "fact_tier": "T3",
            }

        # Use the (possibly auto-corrected) query from validation
        cypher_query = validation_result.get("query", cypher_query)
        
        # Execute the query
        try:
            results = await self._execute_cypher(cypher_query)
            
            response = {
                "success": True,
                "natural_query": natural_query,
                "cypher_query": cypher_query,
                "results": results,
                "result_count": len(results),
                "execution_time": validation_result.get("execution_time", 0),
                "fact_tier": "T2",
            }
            
            # Cache the result
            if use_cache:
                if len(self.query_cache) >= self._cache_max_size:
                    # Evict oldest half
                    keys = list(self.query_cache.keys())
                    for k in keys[: len(keys) // 2]:
                        del self.query_cache[k]
                self.query_cache[cache_key] = response
            
            return response
            
        except Exception as e:
            logger.error(f"Failed to execute Cypher query: {e}")
            return {
                "success": False,
                "error": f"Query execution failed: {str(e)}",
                "natural_query": natural_query,
                "cypher_query": cypher_query,
                "results": [],
                "fact_tier": "T3",
            }
    
    def _sanitize_input(self, query: str) -> str:
        """Sanitize natural language input."""
        # Remove potential Cypher keywords
        sanitized = re.sub(r'\b(MATCH|WHERE|RETURN|CREATE|DELETE|MERGE|SET)\b', '', query, flags=re.IGNORECASE)
        
        # Remove special characters that could cause issues
        sanitized = re.sub(r'[<>"\'`]', '', sanitized)
        
        # Normalize whitespace
        sanitized = ' '.join(sanitized.split())
        
        return sanitized.strip()
    
    async def _generate_cypher(self, natural_query: str, max_results: int) -> Optional[str]:
        """Generate Cypher query using Llama 4 Scout."""
        schema_context = self._format_schema_for_prompt()
        
        prompt = f"""You are a Cypher query generator for a knowledge graph database. 

SCHEMA:
{schema_context}

IMPORTANT TIMESTAMP NOTE:
- The property `created_at` stores Unix timestamps in MILLISECONDS (e.g. 1778678177545)
- Neo4j's timestamp() function also returns milliseconds
- To query "last 24 hours": WHERE n.created_at >= timestamp() - 86400000
- To query "last 7 days":   WHERE n.created_at >= timestamp() - 604800000
- To query "last 30 days":  WHERE n.created_at >= timestamp() - 2592000000
- "today" and "latest" mean last 24 hours: timestamp() - 86400000

RULES:
1. Generate ONLY read-only queries (MATCH, WHERE, RETURN, ORDER BY, LIMIT)
2. NEVER use DELETE, CREATE, MERGE, SET, REMOVE
3. Always include LIMIT {max_results}
4. Use property names exactly as shown in schema
5. For "most popular" use ORDER BY n.stargazers_count DESC or n.likes DESC or n.downloads DESC
6. ALWAYS RETURN ENTIRE NODES (e.g. RETURN n) instead of individual properties. The frontend needs the full node object to render the UI cards correctly.

TASK: Convert this natural language question to a Cypher query:
"{natural_query}"

Respond with ONLY the Cypher query, no explanations, no markdown fences."""

        try:
            from providers.groq_provider import GroqProvider
            from providers.protocol import AssembledPrompt, InferenceConfig

            manager = get_groq_manager()
            model = manager.get_best_model_for_task("complex_reasoning")

            provider = GroqProvider(model_id=model)
            assembled = AssembledPrompt(
                system="You are an expert Cypher query generator for a knowledge graph about AI research.",
                context=[],
                tools=[],
                task=prompt,
            )
            config = InferenceConfig(max_tokens=500, temperature=0.1)
            result = await provider.generate(assembled, config)

            cypher_query = result.content.strip()

            # Clean up the response
            cypher_query = re.sub(r'```cypher\s*', '', cypher_query)
            cypher_query = re.sub(r'```\s*$', '', cypher_query)
            cypher_query = cypher_query.strip()

            logger.info(f"Generated Cypher: {cypher_query}")
            return cypher_query

        except Exception as e:
            logger.error(f"Failed to generate Cypher with Llama 4 Scout: {e}")
            return None
    
    def _format_schema_for_prompt(self) -> str:
        """Format schema for LLM prompt — only useful properties, not raw API noise."""
        if not self.schema_cache:
            return "Schema not available"

        # Curated useful properties per label — ignore raw API fields
        USEFUL_PROPS = {
            "Tool":         ["full_name", "description", "stargazers_count", "language", "created_at", "updated_at", "topics", "forks_count"],
            "Model":        ["id", "pipeline_tag", "likes", "downloads", "library_name", "created_at", "tags"],
            "Paper":        ["title", "arxiv_id", "summary", "published", "link", "created_at"],
            "Author":       ["name", "created_at"],
            "Organization": ["name", "created_at"],
            "Technique":    ["name", "description", "created_at"],
            "Dataset":      ["name", "description", "created_at"],
            "Benchmark":    ["name", "description", "created_at"],
        }

        schema_text = "NODE TYPES (with key properties):\n"
        for label in self.schema_cache["nodes"]:
            props = USEFUL_PROPS.get(label, ["name", "created_at"])
            schema_text += f"- {label}: {props}\n"

        schema_text += """
IMPORTANT FIELD NOTES:
- Tool.topics is a LIST of strings e.g. ['pytorch', 'deep-learning', 'python']
  To filter by topic: WHERE 'pytorch' IN n.topics
- Tool.full_name is 'owner/repo' e.g. 'pytorch/pytorch'
- Tool.stargazers_count is the GitHub star count (integer)
- Model.pipeline_tag is the task type e.g. 'text-generation', 'automatic-speech-recognition'
- Model.tags is a LIST of strings
  To filter by tag: WHERE 'pytorch' IN n.tags
- Model.downloads and Model.likes are integers
"""

        return schema_text
    
    def _validate_cypher(self, query: str) -> Dict[str, Any]:
        """Validate generated Cypher query for safety and correctness."""
        start_time = datetime.now()

        # Strip markdown code fences if model wrapped the query
        query = re.sub(r'```[\w]*\n?', '', query).strip()

        # Basic syntax checks
        query_upper = query.upper()

        # Check for write keywords as whole words (not substrings like "created_at")
        write_keywords = ['DELETE', 'DETACH', 'REMOVE', 'DROP', 'FOREACH', 'LOAD CSV']
        # CREATE and MERGE are only forbidden when standalone (not inside property names)
        standalone_write = ['CREATE', 'MERGE', 'SET']
        for kw in write_keywords + standalone_write:
            # Use word boundary check
            if re.search(rf'\b{kw}\b', query_upper):
                return {"valid": False, "error": f"Forbidden keyword detected: {kw}"}

        # Must start with MATCH or WITH
        if not re.match(r'^\s*(MATCH|WITH|CALL)\b', query, re.IGNORECASE):
            return {"valid": False, "error": "Query must start with MATCH, WITH, or CALL"}

        # Must contain RETURN
        if 'RETURN' not in query_upper:
            return {"valid": False, "error": "Query must contain RETURN"}

        # Must contain LIMIT
        if 'LIMIT' not in query_upper:
            # Auto-append LIMIT rather than rejecting
            query = query.rstrip(';').rstrip() + ' LIMIT 50'

        execution_time = (datetime.now() - start_time).total_seconds()
        return {"valid": True, "execution_time": execution_time, "query": query}
    
    async def _execute_cypher(self, query: str) -> List[Dict[str, Any]]:
        """Execute Cypher query and return results."""
        async with self.neo4j_client.session() as session:
            result = await session.run(query)
            records = []
            
            async for record in result:
                # Convert Record to dict
                record_dict = dict(record)
                # Convert Neo4j types to Python types
                for key, value in record_dict.items():
                    if hasattr(value, 'element_id'):  # Neo4j Node
                        record_dict[key] = {
                            "id": value.element_id,
                            "labels": list(value.labels),
                            "properties": dict(value)
                        }
                    elif hasattr(value, 'relation'):  # Neo4j Relationship
                        record_dict[key] = {
                            "id": value.element_id,
                            "type": value.type,
                            "properties": dict(value),
                            "start": value.start_node.element_id,
                            "end": value.end_node.element_id
                        }
                
                records.append(record_dict)
            
            return records
    
    async def get_query_suggestions(self, partial_query: str) -> List[str]:
        """Get query suggestions based on partial input."""
        await self.initialize()
        
        # Simple keyword-based suggestions
        suggestions = []
        
        if any(word in partial_query.lower() for word in ['paper', 'research', 'article']):
            suggestions.extend([
                "Find papers about machine learning",
                "Show me papers published in 2024",
                "Find papers with high citation counts"
            ])
        
        if any(word in partial_query.lower() for word in ['model', 'ai', 'llm']):
            suggestions.extend([
                "Find models for text generation",
                "Show me transformer models",
                "Find models with high performance"
            ])
        
        if any(word in partial_query.lower() for word in ['tool', 'library', 'framework']):
            suggestions.extend([
                "Find tools for data processing",
                "Show me popular machine learning libraries",
                "Find tools for model deployment"
            ])
        
        return suggestions[:5]  # Return top 5 suggestions
    
    def clear_cache(self):
        """Clear the query cache."""
        self.query_cache.clear()
        logger.info("Query cache cleared")

# Global translator instance
_nl_translator = None

def get_nl_translator() -> NLToCypherTranslator:
    """Get the global NL-to-Cypher translator instance."""
    global _nl_translator
    if _nl_translator is None:
        _nl_translator = NLToCypherTranslator()
    return _nl_translator
