from __future__ import annotations

from dataclasses import dataclass

from schema.models import FactTier, QueryAnswer


FORBIDDEN_TOKENS = {"DELETE", "DETACH", "MERGE", "CREATE", "SET", "REMOVE", "DROP"}


@dataclass(slots=True)
class QueryTemplate:
    name: str
    cypher: str


SAFE_TEMPLATES = [
    QueryTemplate(
        name="whats_new",
        cypher="MATCH (n) WHERE n.status = 'new' RETURN n LIMIT 50",
    ),
    QueryTemplate(
        name="top_tools",
        cypher="MATCH (t:Tool) RETURN t ORDER BY t.github_stars DESC LIMIT 20",
    ),
]


def validate_cypher(cypher: str) -> list[str]:
    upper = cypher.upper()
    warnings: list[str] = []
    for token in FORBIDDEN_TOKENS:
        if token in upper:
            warnings.append(f"Forbidden token detected: {token}")
    if "LIMIT" not in upper:
        warnings.append("Query must include an explicit LIMIT.")
    return warnings


def plan_query(question: str) -> QueryAnswer:
    normalized = question.lower().strip()
    if "what" in normalized and "new" in normalized:
        template = SAFE_TEMPLATES[0]
    else:
        template = SAFE_TEMPLATES[1]
    warnings = validate_cypher(template.cypher)
    return QueryAnswer(
        question=question,
        cypher=template.cypher,
        rows=[],
        fact_tier=FactTier.T1,
        warnings=warnings,
    )
