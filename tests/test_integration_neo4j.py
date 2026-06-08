"""Integration tests for Neo4j graph database operations.

These tests require a live Neo4j instance. They are skipped unless
NEO4J_URI is set in the environment.
"""
from __future__ import annotations

import os
import uuid

import pytest

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.getenv("NEO4J_URI"),
        reason="NEO4J_URI not set; Neo4j integration tests require a live DB",
    ),
]


class TestNeo4jCRUD:
    async def test_connect(self, require_neo4j):
        try:
            from schema.config import get_settings
            from ingestion.neo4j.client import Neo4jClient
            settings = get_settings()
            client = Neo4jClient.from_settings(settings)
            try:
                assert client is not None
            finally:
                await client.close()
        except (OSError, ValueError) as e:
            # DNS / network failure — skip the test gracefully
            pytest.skip(f"Cannot reach Neo4j: {e}")

    async def test_create_and_delete_node(self, require_neo4j):
        try:
            from schema.config import get_settings
            from ingestion.neo4j.client import Neo4jClient
            settings = get_settings()
            client = Neo4jClient.from_settings(settings)
        except (OSError, ValueError) as e:
            pytest.skip(f"Cannot connect to Neo4j: {e}")
        test_id = f"test-{uuid.uuid4()}"
        try:
            async with client.session() as s:
                # Create
                await s.run(
                    "MERGE (n:TestNode {test_id: $id}) SET n.created_at = datetime()",
                    id=test_id,
                )
                # Read
                result = await s.run(
                    "MATCH (n:TestNode {test_id: $id}) RETURN n", id=test_id
                )
                record = await result.single()
                assert record is not None
                # Delete
                await s.run(
                    "MATCH (n:TestNode {test_id: $id}) DELETE n", id=test_id
                )
                # Verify deleted
                result = await s.run(
                    "MATCH (n:TestNode {test_id: $id}) RETURN n", id=test_id
                )
                record = await result.single()
                assert record is None
        except (OSError, ValueError) as e:
            pytest.skip(f"Network error during test: {e}")
        finally:
            await client.close()

    async def test_create_relationship(self, require_neo4j):
        try:
            from schema.config import get_settings
            from ingestion.neo4j.client import Neo4jClient
            settings = get_settings()
            client = Neo4jClient.from_settings(settings)
        except (OSError, ValueError) as e:
            pytest.skip(f"Cannot connect to Neo4j: {e}")
        n1_id = f"a-{uuid.uuid4()}"
        n2_id = f"b-{uuid.uuid4()}"
        try:
            async with client.session() as s:
                await s.run("MERGE (a:TestNode {test_id: $id})", id=n1_id)
                await s.run("MERGE (b:TestNode {test_id: $id})", id=n2_id)
                await s.run(
                    """
                    MATCH (a:TestNode {test_id: $a}), (b:TestNode {test_id: $b})
                    MERGE (a)-[r:TEST_REL]->(b)
                    """,
                    a=n1_id, b=n2_id,
                )
                # Verify relationship
                result = await s.run(
                    """
                    MATCH (a:TestNode {test_id: $a})-[r:TEST_REL]->(b:TestNode {test_id: $b})
                    RETURN r
                    """,
                    a=n1_id, b=n2_id,
                )
                record = await result.single()
                assert record is not None
                # Cleanup
                await s.run(
                    "MATCH (n:TestNode) WHERE n.test_id IN [$a, $b] DETACH DELETE n",
                    a=n1_id, b=n2_id,
                )
        except (OSError, ValueError) as e:
            pytest.skip(f"Network error during test: {e}")
        finally:
            await client.close()
