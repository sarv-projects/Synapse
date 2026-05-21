from __future__ import annotations

import asyncio
from typing import Iterable

from ingestion.neo4j.client import Neo4jClient
from schema.config import get_settings
from schema.domain_loader import load_domain_pack


def _node_constraints(domain_schema: dict) -> Iterable[str]:
    for label, spec in domain_schema.get("node_types", {}).items():
        dedup_key = spec["dedup_key"]
        yield (
            f"CREATE CONSTRAINT {label.lower()}_dedup IF NOT EXISTS "
            f"FOR (n:{label}) REQUIRE n.{dedup_key} IS UNIQUE"
        )
        for prop, prop_spec in spec.get("properties", {}).items():
            if prop_spec.get("indexed"):
                yield f"CREATE INDEX {label.lower()}_{prop}_idx IF NOT EXISTS FOR (n:{label}) ON (n.{prop})"


async def create_schema() -> None:
    settings = get_settings()
    domain_pack = load_domain_pack(settings.default_domain)
    client = Neo4jClient.from_settings(settings)
    async with client.session() as session:
        for statement in _node_constraints(domain_pack.schema):
            await session.run(statement)


def main() -> None:
    asyncio.run(create_schema())


if __name__ == "__main__":
    main()
