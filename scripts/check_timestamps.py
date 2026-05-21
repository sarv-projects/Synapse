"""Check what created_at looks like on actual nodes."""
import asyncio
from ingestion.neo4j.client import Neo4jClient
from schema.config import get_settings

async def main():
    c = Neo4jClient.from_settings(get_settings())
    async with c.session() as s:
        r = await s.run("MATCH (n:Tool) RETURN n.created_at, n.last_seen, n.status LIMIT 3")
        async for row in r:
            print(dict(row))
    await c.close()

asyncio.run(main())
