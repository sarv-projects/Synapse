from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4


@dataclass(slots=True)
class RunTrace:
    run_id: str = field(default_factory=lambda: str(uuid4()))
    run_date: str = field(default_factory=lambda: datetime.now(UTC).date().isoformat())
    source_fetch_results: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


class TraceWriter:
    def __init__(self, directory: str = "observability_traces") -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def write(self, trace: RunTrace) -> Path:
        path = self.directory / f"{trace.run_date}.jsonl"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(trace.__dict__) + "\n")
        return path
