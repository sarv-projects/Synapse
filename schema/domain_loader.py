from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(slots=True)
class DomainPack:
    name: str
    root: Path
    schema: dict[str, Any]
    sources: dict[str, Any]
    aliases: list[dict[str, Any]]


def load_domain_pack(name: str, root: Path | None = None) -> DomainPack:
    base_root = root or Path(__file__).resolve().parent.parent / "domains" / name
    schema = yaml.safe_load((base_root / "schema.yaml").read_text())
    sources = yaml.safe_load((base_root / "sources.yaml").read_text())
    aliases = [
        json.loads(line)
        for line in (base_root / "aliases.jsonl").read_text().splitlines()
        if line.strip()
    ]
    return DomainPack(name=name, root=base_root, schema=schema, sources=sources, aliases=aliases)
