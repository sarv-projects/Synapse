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
