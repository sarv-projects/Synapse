"""Seed SYNAPSE with synthetic historical data for testing."""
from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import UTC, datetime, timedelta

from ingestion.generic_source import GenericSourceFetcher, SourceConfig
from ingestion.sources.base import SourceDocument
from ingestion.pipeline.run import run_pipeline
from schema.config import get_settings


def build_seed_documents(days: int) -> list[SourceDocument]:
    documents: list[SourceDocument] = []
    now = datetime.now(UTC)

    topics = [
        "transformer", "attention", "diffusion", "rag", "lora",
        "fine-tuning", "rlhf", "quantization", "distillation", "embedding",
    ]

    for index in range(days):
        published_at = now - timedelta(days=index)
        topic = topics[index % len(topics)]

        documents.append(SourceDocument(
            source_name="seed",
            external_id=f"paper-{index}",
            entity_type="Paper",
            payload={
                "arxiv_id": f"seed-{index}",
                "title": f"Seed paper {index}: Advances in {topic.title()}",
                "summary": f"This paper explores recent advances in {topic} for deep learning applications.",
                "published": published_at.isoformat(),
                "topics": [topic],
            },
        ))

        documents.append(SourceDocument(
            source_name="seed",
            external_id=f"tool-{index}",
            entity_type="Tool",
            payload={
                "full_name": f"org/seed-tool-{index}",
                "description": f"A tool for {topic}",
                "stargazers_count": 1000 + index * 50,
                "language": "Python",
                "topics": [topic, "machine-learning"],
            },
        ))

        documents.append(SourceDocument(
            source_name="seed",
            external_id=f"model-{index}",
            entity_type="Model",
            payload={
                "hf_model_id": f"seed-org/model-{index}",
                "pipeline_tag": "text-generation",
                "likes": 100 + index * 10,
                "downloads": 5000 + index * 200,
                "library_name": "transformers",
            },
        ))

    return documents


async def main_async(days: int) -> None:
    settings = get_settings()

    print(f"\nSeeding {days} days of synthetic data...")
    docs = build_seed_documents(days)
    print(f"Built {len(docs)} seed documents ({days * 3} total nodes)")
    print()

    for doc in docs[:5]:
        print(f"  {doc.entity_type:12s} {doc.external_id}")

    print()

    summary = await run_pipeline(domain="ai")
    print(f"\nSeed complete — {summary.get('nodes_written', 0)} nodes written to Neo4j")


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%H:%M:%S",
    )

    parser = argparse.ArgumentParser(description="Seed SYNAPSE with synthetic historical data")
    parser.add_argument("--days", type=int, default=30, help="Number of days to seed (default: 30)")
    args = parser.parse_args()

    asyncio.run(main_async(args.days))


if __name__ == "__main__":
    main()
