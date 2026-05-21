from __future__ import annotations

from math import log10


def compute_rank(*, relevance: float, verification: float, freshness: float, popularity: float) -> float:
    return (
        0.45 * relevance
        + 0.25 * verification
        + 0.15 * freshness
        + 0.15 * log10(max(popularity, 1))
    )
