from __future__ import annotations

from contextlib import asynccontextmanager

from neo4j import AsyncGraphDatabase

from schema.config import Settings


class Neo4jClient:
    def __init__(self, uri: str, username: str, password: str, database: str) -> None:
        self._driver = AsyncGraphDatabase.driver(uri, auth=(username, password))
        self.database = database

    @classmethod
    def from_settings(cls, settings: Settings) -> "Neo4jClient":
        return cls(
            uri=settings.neo4j_uri,
            username=settings.neo4j_username,
            password=settings.neo4j_password,
            database=settings.neo4j_database,
        )

    @asynccontextmanager
    async def session(self):
        async with self._driver.session(database=self.database) as session:
            yield session

    async def close(self) -> None:
        await self._driver.close()


_neo4j_client: Neo4jClient | None = None


def get_neo4j_client() -> Neo4jClient:
    global _neo4j_client
    if _neo4j_client is None:
        from schema.config import get_settings
        _neo4j_client = Neo4jClient.from_settings(get_settings())
    return _neo4j_client


async def close_neo4j_client() -> None:
    global _neo4j_client
    if _neo4j_client is not None:
        await _neo4j_client.close()
        _neo4j_client = None
