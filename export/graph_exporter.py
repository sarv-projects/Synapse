"""Graph export functionality for SYNAPSE v3.0 - JSON-LD, CSV, GraphML."""
from typing import Dict, Any, List, Optional, Union
import asyncio
import logging
import csv
import io
import zipfile
from datetime import datetime, UTC
import json

from ingestion.neo4j.client import Neo4jClient
from schema.config import get_settings

logger = logging.getLogger(__name__)

class GraphExporter:
    """Export knowledge graph data in multiple formats."""
    
    def __init__(self):
        self.settings = get_settings()
        self.neo4j_client = None
        
        # Export limits
        self.max_nodes_per_export = 500
        self.max_edges_per_export = 2500
    
    async def initialize(self):
        """Initialize Neo4j client."""
        if not self.neo4j_client:
            from ingestion.neo4j.client import Neo4jClient
            self.neo4j_client = Neo4jClient.from_settings(self.settings)
    
    async def export_subgraph(
        self, 
        query: str,
        format_type: str = "json-ld",
        include_embeddings: bool = False
    ) -> Dict[str, Any]:
        """
        Export a subgraph based on a Cypher query.
        
        Args:
            query: Cypher query to define the subgraph
            format_type: Export format (json-ld, csv, graphml)
            include_embeddings: Whether to include embedding vectors
            
        Returns:
            Dict with export data and metadata
        """
        await self.initialize()
        
        try:
            # Execute query to get nodes and edges
            nodes, edges = await self._extract_subgraph(query)
            
            # Apply export limits
            if len(nodes) > self.max_nodes_per_export:
                logger.warning(f"Truncating nodes from {len(nodes)} to {self.max_nodes_per_export}")
                nodes = nodes[:self.max_nodes_per_export]
            
            if len(edges) > self.max_edges_per_export:
                logger.warning(f"Truncating edges from {len(edges)} to {self.max_edges_per_export}")
                edges = edges[:self.max_edges_per_export]
            
            # Export in requested format
            if format_type.lower() == "json-ld":
                export_data = await self._export_json_ld(nodes, edges, include_embeddings)
            elif format_type.lower() == "csv":
                export_data = await self._export_csv(nodes, edges, include_embeddings)
            elif format_type.lower() == "graphml":
                export_data = await self._export_graphml(nodes, edges, include_embeddings)
            else:
                raise ValueError(f"Unsupported export format: {format_type}")
            
            # Add metadata
            metadata = {
                "exported_at": datetime.now(UTC).isoformat(),
                "format": format_type,
                "nodes_count": len(nodes),
                "edges_count": len(edges),
                "query": query,
                "include_embeddings": include_embeddings,
                "truncated": len(nodes) == self.max_nodes_per_export or len(edges) == self.max_edges_per_export
            }
            
            return {
                "success": True,
                "metadata": metadata,
                "data": export_data
            }
            
        except Exception as e:
            logger.error(f"Graph export failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "metadata": None,
                "data": None
            }
    
    async def _extract_subgraph(self, query: str) -> tuple[List[Dict], List[Dict]]:
        """Extract nodes and edges from a Cypher query."""
        async with self.neo4j_client.session() as session:
            # Modify query to return both nodes and relationships
            modified_query = f"""
            {query}
            RETURN collect(DISTINCT n) as nodes, collect(DISTINCT r) as relationships
            """
            
            result = await session.run(modified_query)
            record = await result.single()
            
            if not record:
                return [], []
            
            # Process nodes
            nodes = []
            for node in record["nodes"]:
                node_data = {
                    "id": node.element_id,
                    "labels": list(node.labels),
                    "properties": dict(node)
                }
                nodes.append(node_data)
            
            # Process relationships
            edges = []
            for rel in record["relationships"]:
                edge_data = {
                    "id": rel.element_id,
                    "type": rel.type,
                    "start_node": rel.start_node.element_id,
                    "end_node": rel.end_node.element_id,
                    "properties": dict(rel)
                }
                edges.append(edge_data)
            
            return nodes, edges
    
    async def _export_json_ld(self, nodes: List[Dict], edges: List[Dict], include_embeddings: bool) -> str:
        """Export graph as JSON-LD format."""
        # Create JSON-LD context
        context = {
            "@vocab": "https://synapse.ai/schema/",
            "synapse": "https://synapse.ai/schema/",
            "id": "@id",
            "type": "@type",
            "neo4j_id": "synapse:neo4jId",
            "labels": "synapse:labels",
            "properties": "synapse:properties",
            "relationship": "synapse:relationship",
            "start_node": "synapse:startNode",
            "end_node": "synapse:endNode"
        }
        
        # Create JSON-LD graph
        graph = []
        
        # Add nodes
        for node in nodes:
            node_obj = {
                "@id": f"node:{node['id']}",
                "@type": node["labels"],
                "neo4j_id": node["id"],
                "labels": node["labels"]
            }
            
            # Add properties
            properties = node["properties"].copy()
            if not include_embeddings and "embedding" in properties:
                del properties["embedding"]
            
            node_obj.update(properties)
            graph.append(node_obj)
        
        # Add relationships
        for edge in edges:
            edge_obj = {
                "@id": f"rel:{edge['id']}",
                "@type": "Relationship",
                "neo4j_id": edge["id"],
                "relationship": edge["type"],
                "start_node": f"node:{edge['start_node']}",
                "end_node": f"node:{edge['end_node']}"
            }
            
            # Add edge properties
            edge_obj.update(edge["properties"])
            graph.append(edge_obj)
        
        # Create JSON-LD document
        json_ld = {
            "@context": context,
            "@graph": graph
        }
        
        return json.dumps(json_ld, indent=2, default=str)
    
    async def _export_csv(self, nodes: List[Dict], edges: List[Dict], include_embeddings: bool) -> bytes:
        """Export graph as CSV format (ZIP with nodes.csv and edges.csv)."""
        # Create in-memory ZIP file
        zip_buffer = io.BytesIO()
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            # Export nodes
            if nodes:
                nodes_csv = io.StringIO()
                all_properties = set()
                
                # Collect all property keys
                for node in nodes:
                    all_properties.update(node["properties"].keys())
                
                # Prepare CSV headers
                headers = ["id", "labels"] + sorted(list(all_properties))
                writer = csv.DictWriter(nodes_csv, fieldnames=headers)
                writer.writeheader()
                
                # Write nodes
                for node in nodes:
                    row = {
                        "id": node["id"],
                        "labels": "|".join(node["labels"])
                    }
                    
                    # Add properties
                    for prop in all_properties:
                        value = node["properties"].get(prop, "")
                        if prop == "embedding" and not include_embeddings:
                            value = ""
                        elif isinstance(value, (list, dict)):
                            value = json.dumps(value)
                        row[prop] = value
                    
                    writer.writerow(row)
                
                # Add to ZIP
                zip_file.writestr("nodes.csv", nodes_csv.getvalue())
            
            # Export edges
            if edges:
                edges_csv = io.StringIO()
                all_properties = set()
                
                # Collect all property keys
                for edge in edges:
                    all_properties.update(edge["properties"].keys())
                
                # Prepare CSV headers
                headers = ["id", "type", "start_node", "end_node"] + sorted(list(all_properties))
                writer = csv.DictWriter(edges_csv, fieldnames=headers)
                writer.writeheader()
                
                # Write edges
                for edge in edges:
                    row = {
                        "id": edge["id"],
                        "type": edge["type"],
                        "start_node": edge["start_node"],
                        "end_node": edge["end_node"]
                    }
                    
                    # Add properties
                    for prop in all_properties:
                        value = edge["properties"].get(prop, "")
                        if isinstance(value, (list, dict)):
                            value = json.dumps(value)
                        row[prop] = value
                    
                    writer.writerow(row)
                
                # Add to ZIP
                zip_file.writestr("edges.csv", edges_csv.getvalue())
            
            # Add metadata
            metadata = {
                "exported_at": datetime.now(UTC).isoformat(),
                "format": "csv",
                "nodes_count": len(nodes),
                "edges_count": len(edges),
                "include_embeddings": include_embeddings
            }
            zip_file.writestr("metadata.json", json.dumps(metadata, indent=2))
        
        zip_buffer.seek(0)
        return zip_buffer.getvalue()
    
    async def _export_graphml(self, nodes: List[Dict], edges: List[Dict], include_embeddings: bool) -> str:
        """Export graph as GraphML format."""
        # GraphML header
        graphml_header = '''<?xml version="1.0" encoding="UTF-8"?>
<graphml xmlns="http://graphml.graphdrawing.org/xmlns"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://graphml.graphdrawing.org/xmlns
         http://graphml.graphdrawing.org/xmlns/1.0/graphml.xsd">
'''
        
        # Define key attributes
        key_definitions = []
        all_node_keys = set()
        all_edge_keys = set()
        
        # Collect all property keys
        for node in nodes:
            all_node_keys.update(node["properties"].keys())
        
        for edge in edges:
            all_edge_keys.update(edge["properties"].keys())
        
        # Generate key definitions for nodes
        for key in sorted(all_node_keys):
            if key == "embedding" and not include_embeddings:
                continue
            key_definitions.append(f'  <key id="node_{key}" for="node" attr.name="{key}" attr.type="string"/>')
        
        # Generate key definitions for edges
        for key in sorted(all_edge_keys):
            key_definitions.append(f'  <key id="edge_{key}" for="edge" attr.name="{key}" attr.type="string"/>')
        
        # Start graph
        graph_start = '''
  <graph id="synapse_graph" edgedefault="directed">
'''
        
        # Generate nodes
        node_elements = []
        for node in nodes:
            label = node["labels"][0] if node["labels"] else "Node"
            node_xml = f'    <node id="{node["id"]}">\n'
            node_xml += f'      <data key="label">{label}</data>\n'
            
            # Add properties
            for key, value in node["properties"].items():
                if key == "embedding" and not include_embeddings:
                    continue
                
                # Convert value to string
                if isinstance(value, (list, dict)):
                    value = json.dumps(value)
                else:
                    value = str(value)
                
                # Escape XML special characters
                value = value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                node_xml += f'      <data key="node_{key}">{value}</data>\n'
            
            node_xml += '    </node>\n'
            node_elements.append(node_xml)
        
        # Generate edges
        edge_elements = []
        for edge in edges:
            edge_xml = f'    <edge id="{edge["id"]}" source="{edge["start_node"]}" target="{edge["end_node"]}">\n'
            edge_xml += f'      <data key="label">{edge["type"]}</data>\n'
            
            # Add properties
            for key, value in edge["properties"].items():
                # Convert value to string
                if isinstance(value, (list, dict)):
                    value = json.dumps(value)
                else:
                    value = str(value)
                
                # Escape XML special characters
                value = value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                edge_xml += f'      <data key="edge_{key}">{value}</data>\n'
            
            edge_xml += '    </edge>\n'
            edge_elements.append(edge_xml)
        
        # End graph
        graph_end = '''
  </graph>
</graphml>'''
        
        # Combine all parts
        graphml = (
            graphml_header +
            "\n".join(key_definitions) + "\n" +
            graph_start +
            "".join(node_elements) +
            "".join(edge_elements) +
            graph_end
        )
        
        return graphml
    
    async def get_export_stats(self) -> Dict[str, Any]:
        """Get statistics about the graph for export planning."""
        await self.initialize()
        
        stats = {}
        
        async with self.neo4j_client.session() as session:
            # Count nodes by type
            node_query = """
            MATCH (n)
            RETURN labels(n) as labels, count(n) as count
            ORDER BY count DESC
            """
            
            result = await session.run(node_query)
            stats["nodes_by_type"] = {}
            total_nodes = 0
            
            async for record in result:
                labels = record["labels"]
                label = labels[0] if labels else "Unknown"
                stats["nodes_by_type"][label] = record["count"]
                total_nodes += record["count"]
            
            stats["total_nodes"] = total_nodes
            
            # Count edges by type
            edge_query = """
            MATCH ()-[r]->()
            RETURN type(r) as type, count(r) as count
            ORDER BY count DESC
            """
            
            result = await session.run(edge_query)
            stats["edges_by_type"] = {}
            total_edges = 0
            
            async for record in result:
                stats["edges_by_type"][record["type"]] = record["count"]
                total_edges += record["count"]
            
            stats["total_edges"] = total_edges
            
            # Check for embeddings
            embedding_query = """
            MATCH (n)
            WHERE n.embedding IS NOT NULL
            RETURN count(n) as count
            """
            
            result = await session.run(embedding_query)
            record = await result.single()
            stats["nodes_with_embeddings"] = record["count"] if record else 0
        
        return stats
    
    async def validate_export_query(self, query: str) -> Dict[str, Any]:
        """Validate an export query for safety and performance."""
        await self.initialize()
        
        validation = {
            "valid": True,
            "warnings": [],
            "estimated_nodes": 0,
            "estimated_edges": 0
        }
        
        # Check for dangerous operations
        dangerous_keywords = ["DELETE", "REMOVE", "DETACH", "DROP", "CREATE", "MERGE", "SET"]
        query_upper = query.upper()
        
        for keyword in dangerous_keywords:
            if keyword in query_upper:
                validation["valid"] = False
                validation["warnings"].append(f"Query contains dangerous keyword: {keyword}")
        
        # Check for RETURN clause
        if "RETURN" not in query_upper:
            validation["valid"] = False
            validation["warnings"].append("Query must contain RETURN clause")
        
        # Estimate result size (simple heuristic)
        if validation["valid"]:
            try:
                # Create a count version of the query
                count_query = query.replace("RETURN", "RETURN count(*) as count")
                
                async with self.neo4j_client.session() as session:
                    result = await session.run(count_query)
                    record = await result.single()
                    
                    if record:
                        validation["estimated_nodes"] = record["count"]
                        
                        # Warn about large exports
                        if record["count"] > self.max_nodes_per_export:
                            validation["warnings"].append(
                                f"Query may return {record['count']} nodes, which exceeds the limit of {self.max_nodes_per_export}"
                            )
                
            except Exception as e:
                validation["warnings"].append(f"Could not estimate query size: {e}")
        
        return validation

# Global exporter instance
_graph_exporter = None

def get_graph_exporter() -> GraphExporter:
    """Get the global graph exporter instance."""
    global _graph_exporter
    if _graph_exporter is None:
        _graph_exporter = GraphExporter()
    return _graph_exporter
