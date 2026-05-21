"""Check graph structure — relationships, pytorch tools, topics field."""
import asyncio
from ingestion.neo4j.client import Neo4jClient
from schema.config import get_settings

async def main():
    c = Neo4jClient.from_settings(get_settings())
    async with c.session() as s:

        # 1. Total counts
        r = await s.run("MATCH (n) RETURN count(n) as nodes")
        row = await r.single()
        print(f"Total nodes: {row['nodes']}")

        r = await s.run("MATCH ()-[r]->() RETURN count(r) as total")
        row = await r.single()
        print(f"Total relationships: {row['total']}")

        # 2. Relationship types
        r = await s.run("MATCH ()-[r]->() RETURN type(r) as rel, count(r) as cnt ORDER BY cnt DESC")
        print("\nRelationship counts:")
        async for row in r:
            print(f"  {row['rel']}: {row['cnt']}")

        # 3. Node counts by label
        r = await s.run("MATCH (n) RETURN labels(n)[0] as label, count(n) as cnt ORDER BY cnt DESC")
        print("\nNode counts:")
        async for row in r:
            print(f"  {row['label']}: {row['cnt']}")

        # 4. PyTorch tools via graph traversal
        r = await s.run("""
            MATCH (t:Tool)-[:IMPLEMENTS]->(tech:Technique)
            WHERE tech.canonical_name IN ['Transformer', 'Large Language Model', 'Natural Language Processing']
            RETURN t.full_name, t.stargazers_count, collect(tech.canonical_name) as techniques
            ORDER BY t.stargazers_count DESC LIMIT 5
        """)
        print("\nTop tools implementing Transformer/LLM/NLP (via graph):")
        async for row in r:
            print(f"  {row['t.full_name']}: {row['t.stargazers_count']} stars → {row['techniques']}")

        # 5. Orgs with most models
        r = await s.run("""
            MATCH (m:Model)-[:PUBLISHED_BY]->(o:Organization)
            RETURN o.name, count(m) as model_count
            ORDER BY model_count DESC LIMIT 10
        """)
        print("\nOrgs with most models:")
        async for row in r:
            print(f"  {row['o.name']}: {row['model_count']} models")

    await c.close()

asyncio.run(main())
