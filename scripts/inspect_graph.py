"""Quick inspection of what's in the Neo4j graph."""
import asyncio
from ingestion.neo4j.client import Neo4jClient
from schema.config import get_settings

async def main():
    c = Neo4jClient.from_settings(get_settings())
    async with c.session() as s:
        # Node counts by label
        r = await s.run("MATCH (n) RETURN labels(n)[0] as label, count(n) as cnt ORDER BY cnt DESC")
        print("=== Node counts ===")
        async for row in r:
            print(f"  {row['label']}: {row['cnt']}")

        # Sample Model nodes
        print("\n=== Sample Models ===")
        r2 = await s.run("MATCH (n:Model) RETURN n.id, n.hf_model_id, n.likes, n.pipeline_tag LIMIT 5")
        async for row in r2:
            print(f"  {dict(row)}")

        # Sample Tool nodes
        print("\n=== Sample Tools ===")
        r3 = await s.run("MATCH (n:Tool) RETURN n.id, n.full_name, n.stargazers_count, n.description LIMIT 5")
        async for row in r3:
            print(f"  {dict(row)}")

        # Sample Paper nodes
        print("\n=== Sample Papers ===")
        r4 = await s.run("MATCH (n:Paper) RETURN n.id, n.title, n.link LIMIT 5")
        async for row in r4:
            print(f"  {dict(row)}")

    await c.close()

asyncio.run(main())
